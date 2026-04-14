"""Agent Executor — runs an agent for a single task turn.

Merges the agent's system prompt + tools into a ChatCompletionRequest,
routes through the CorePipeline (atlas_router), records an AgentExecution
audit row, and returns the assistant text.
"""

import time

from a1.agents.registry import AgentDefinition
from a1.common.logging import get_logger
from a1.proxy.request_models import ChatCompletionRequest, MessageInput

log = get_logger("agents.executor")


async def run_agent(
    agent: AgentDefinition,
    task: str,
    extra_messages: list[dict] | None = None,
    max_tokens: int = 2000,
    stream: bool = False,
) -> str | None:
    """Execute an agent for a single task.

    Builds a ChatCompletionRequest with the agent's persona injected as the
    system prompt, then routes through the Atlas distillation pipeline.
    Records the execution in agent_executions for audit.

    Returns assistant text, or None on failure.
    """
    start = time.time()
    result_text = None
    error_text = None

    try:
        from fastapi.responses import Response

        from a1.training.auto_trainer import handle_dual_execution

        # Build system prompt: agent persona first
        system_parts = []
        if agent.system_prompt:
            system_parts.append(agent.system_prompt)
        if agent.tools:
            tool_lines = "\n".join(f"- {t}" for t in agent.tools)
            system_parts.append(f"\nAvailable tools:\n{tool_lines}")

        messages: list[MessageInput] = []
        if system_parts:
            messages.append(MessageInput(role="system", content="\n\n".join(system_parts)))

        # Inject extra context messages (e.g. prior agent results)
        for m in extra_messages or []:
            messages.append(MessageInput(role=m.get("role", "user"), content=m.get("content", "")))

        messages.append(MessageInput(role="user", content=task))

        req = ChatCompletionRequest(
            model=agent.atlas_model,
            messages=messages,
            max_tokens=max_tokens,
        )

        # Route through distillation pipeline
        response_obj = Response()
        from a1.routing.classifier import classify_task

        task_type, _ = classify_task(req)

        result = await handle_dual_execution(
            req, response_obj, task_type, 0.9, atlas_model=agent.atlas_model
        )

        if result and result.choices:
            result_text = result.choices[0].message.content

    except Exception as e:
        log.error(f"[agent:{agent.name}] Execution error: {e}")
        error_text = str(e)

    latency_ms = int((time.time() - start) * 1000)

    # Fire-and-forget audit record
    import asyncio

    asyncio.create_task(
        _record_execution(
            agent_id=agent.id,
            task=task,
            result=result_text,
            latency_ms=latency_ms,
            error=error_text,
        )
    )

    return result_text


async def run_agent_by_id(
    agent_id: str,
    task: str,
    extra_messages: list[dict] | None = None,
    max_tokens: int = 2000,
) -> str | None:
    """Convenience wrapper — looks up agent by ID then runs it."""
    from a1.agents.registry import agent_registry

    agent = agent_registry.get_by_id(agent_id)
    if not agent:
        log.warning(f"[executor] Agent {agent_id} not found in registry")
        return None
    if agent.status != "active":
        log.warning(f"[executor] Agent {agent_id} is {agent.status}, skipping")
        return None
    return await run_agent(agent, task, extra_messages=extra_messages, max_tokens=max_tokens)


async def _record_execution(
    agent_id: str,
    task: str,
    result: str | None,
    latency_ms: int,
    error: str | None,
):
    """Persist AgentExecution audit row (runs as background task)."""
    try:
        import uuid as _uuid

        from a1.db.engine import async_session
        from a1.db.models import AgentExecution

        async with async_session() as session:
            async with session.begin():
                row = AgentExecution(
                    id=_uuid.uuid4(),
                    agent_id=_uuid.UUID(agent_id),
                    task=task[:4096],
                    result=result[:8192] if result else None,
                    latency_ms=latency_ms,
                    error=error,
                )
                session.add(row)
    except Exception as e:
        log.debug(f"Failed to record agent execution: {e}")
