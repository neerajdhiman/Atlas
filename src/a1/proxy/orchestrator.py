"""Multi-agent sequential chaining orchestrator (Phase 4.4).

Flow:
  1. atlas-plan decomposes the task into 2-4 subtasks, each assigned a specialist model.
  2. Parallel specialist model calls execute concurrently.
  3. atlas-plan synthesizes a final answer from all specialist outputs.
"""

import asyncio
import json
import re

from a1.common.logging import get_logger
from a1.proxy.request_models import ChatCompletionRequest, MessageInput

log = get_logger("proxy.orchestrator")

_DECOMPOSE_PROMPT = (
    "You are a task decomposition agent. Break the following request into 2-4 independent "
    "subtasks that can be handled by specialist AI models. Output ONLY a valid JSON array. "
    "Each element must have:\n"
    '  "subtask": string describing the subtask\n'
    '  "model": one of atlas-plan, atlas-code, atlas-secure, atlas-infra, '
    "atlas-data, atlas-books, atlas-audit\n\n"
    "Request: {input}\n\nJSON array:"
)

_SYNTHESIZE_PROMPT = (
    "You are a synthesis agent. Combine the following specialist outputs into a single "
    "coherent, well-structured final answer.\n\n"
    "Original request: {input}\n\n"
    "Specialist outputs:\n{outputs}\n\n"
    "Final synthesized answer:"
)


async def run_multi_agent(
    input_text: str,
    context_messages: list,
    max_tokens: int,
    provider_registry,
) -> str:
    """Orchestrate a multi-agent request. Returns the synthesized final text.

    Falls back to empty string if decomposition fails — caller should then
    fall through to the normal single-provider path.
    """
    from a1.routing.atlas_models import ATLAS_TASK_MAP
    from a1.routing.strategy import select_model

    # ------------------------------------------------------------------ #
    # Step 1: Decompose with atlas-plan (chat task → llama / best local)  #
    # ------------------------------------------------------------------ #
    plan_model, plan_provider_name = await select_model("chat", "best_quality")
    plan_provider = provider_registry.get_provider(plan_provider_name)

    subtasks: list[dict] = []
    if plan_provider:
        decompose_req = ChatCompletionRequest(
            model=plan_model,
            messages=[
                MessageInput(
                    role="user",
                    content=_DECOMPOSE_PROMPT.format(input=input_text[:1000]),
                )
            ],
            max_tokens=400,
            temperature=0,
        )
        try:
            result = await plan_provider.complete(decompose_req)
            raw = result.choices[0].message.content if result.choices else ""
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                subtasks = json.loads(match.group())
        except Exception as e:
            log.warning(f"[orchestrator] decompose failed: {e}")

    if not subtasks:
        log.warning("[orchestrator] no subtasks — caller should fall back to single-task")
        return ""

    log.info(f"[orchestrator] decomposed into {len(subtasks)} subtasks")

    # ------------------------------------------------------------------ #
    # Step 2: Parallel specialist calls                                    #
    # ------------------------------------------------------------------ #
    async def run_subtask(subtask_info: dict) -> tuple[str, str]:
        subtask_text = subtask_info.get("subtask", "")
        atlas_model = subtask_info.get("model", "atlas-plan")
        task_type = ATLAS_TASK_MAP.get(atlas_model, "chat")

        specialist_model, specialist_provider_name = await select_model(task_type, "best_quality")
        specialist_provider = provider_registry.get_provider(specialist_provider_name)

        if not specialist_provider:
            return atlas_model, f"[{atlas_model}] No provider available"

        per_task_tokens = max(max_tokens // max(len(subtasks), 1), 200)
        req = ChatCompletionRequest(
            model=specialist_model,
            messages=list(context_messages) + [MessageInput(role="user", content=subtask_text)],
            max_tokens=per_task_tokens,
        )
        try:
            result = await specialist_provider.complete(req)
            text = result.choices[0].message.content if result.choices else ""
            return atlas_model, text
        except Exception as e:
            return atlas_model, f"[{atlas_model}] Error: {e}"

    specialist_results: list[tuple[str, str]] = await asyncio.gather(
        *[run_subtask(s) for s in subtasks]
    )

    # ------------------------------------------------------------------ #
    # Step 3: Synthesize with atlas-plan                                  #
    # ------------------------------------------------------------------ #
    outputs_text = "\n\n".join(f"[{model}]: {text}" for model, text in specialist_results)
    synth_req = ChatCompletionRequest(
        model=plan_model,
        messages=[
            MessageInput(
                role="user",
                content=_SYNTHESIZE_PROMPT.format(
                    input=input_text[:600],
                    outputs=outputs_text,
                ),
            )
        ],
        max_tokens=max_tokens,
    )

    if plan_provider:
        try:
            result = await plan_provider.complete(synth_req)
            return result.choices[0].message.content if result.choices else ""
        except Exception as e:
            log.warning(f"[orchestrator] synthesize failed: {e}")

    # Last resort: concatenate
    return "\n\n".join(f"**{model}**: {text}" for model, text in specialist_results)
