"""Alpheric.AI Atlas endpoint: /atlas and /atlas/models."""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from a1.common.auth import verify_api_key
from a1.common.logging import get_logger
from a1.common.metrics import metrics
from a1.providers.registry import provider_registry
from a1.proxy.pipeline import (
    LEGACY_ALIASES, _return_response_or_stream, execute_tool_loop, strip_think_tokens,
)
from a1.proxy.request_models import ChatCompletionRequest, MessageInput
from a1.routing.atlas_models import ATLAS_TASK_ROUTING, resolve_atlas_model
from a1.routing.classifier import classify_task, classify_task_with_fallback
from a1.routing.strategy import select_model

# deepseek-r1 model names — responses from these need <think> tokens stripped
_DEEPSEEK_R1_MODELS = frozenset({"deepseek-r1:8b", "deepseek-r1:14b", "deepseek-r1:32b", "deepseek-r1:70b"})
from config.settings import settings

log = get_logger("proxy.atlas")
router = APIRouter()


@router.post("/atlas")
async def atlas_endpoint(
    request: dict,
    response: Response,
    api_key: str = Depends(verify_api_key),
):
    """Alpheric.AI Atlas endpoint — auto-selects the right model.

    Accepts:
      - model: (optional) specific atlas model, or omit for auto-selection
      - input: string or message array
      - instructions: system prompt
      - max_output_tokens / temperature

    If model is omitted or "atlas", the system classifies the input
    and picks the best Atlas model automatically.
    """
    start_time = time.time()

    model = request.get("model", "atlas")
    input_data = request.get("input", "")
    instructions = request.get("instructions", "")
    tools = request.get("tools", [])
    temperature = request.get("temperature")
    max_tokens = request.get("max_output_tokens") or request.get("max_tokens", 1000)
    stream = request.get("stream", False)
    multi_agent = bool(request.get("multi_agent", False))

    # --- Session Memory ---
    session_id = request.get("session_id")
    previous_response_id = request.get("previous_response_id")

    session = None
    session_history = []
    if settings.session_enabled:
        from a1.session.manager import session_manager
        session = await session_manager.get_or_create(
            session_id=session_id,
            previous_response_id=previous_response_id,
            user_id=request.get("user"),
        )
        session_history = session.get_history(limit=settings.session_max_messages)

    # Build messages
    messages = []

    # Combine instructions + tools into system prompt
    system_parts = []
    if instructions:
        system_parts.append(instructions)
    if tools:
        tool_descriptions = []
        for tool in tools:
            name = tool.get("name", tool.get("function", {}).get("name", "unknown"))
            desc = tool.get("description", tool.get("function", {}).get("description", ""))
            tool_descriptions.append(f"- {name}: {desc}")
        if tool_descriptions:
            system_parts.append("\n\nAvailable tools:\n" + "\n".join(tool_descriptions))

    if system_parts:
        messages.append(MessageInput(role="system", content="\n".join(system_parts)))

    # Inject session history before current message
    for hist_msg in session_history:
        messages.append(MessageInput(role=hist_msg["role"], content=hist_msg["content"]))

    # Current input
    if isinstance(input_data, str):
        messages.append(MessageInput(role="user", content=input_data))
    elif isinstance(input_data, list):
        for msg in input_data:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
                messages.append(MessageInput(role=role, content=content))
            elif isinstance(msg, str):
                messages.append(MessageInput(role="user", content=msg))

    if not messages:
        messages.append(MessageInput(role="user", content="Hello"))

    # --- PII Masking (for external providers only) ---
    mask_map = {}
    if settings.pii_masking_enabled:
        from a1.security.pii_masker import pii_masker
        messages_dicts = [{"role": m.role, "content": m.content or ""} for m in messages]
        masked_dicts, mask_map = pii_masker.mask_messages(messages_dicts)
        messages = [MessageInput(role=d["role"], content=d["content"]) for d in masked_dicts]

    model = LEGACY_ALIASES.get(model, model)

    # Resolve Atlas model
    if model == "atlas" or model not in ATLAS_TASK_ROUTING:
        temp_req = ChatCompletionRequest(model="auto", messages=messages, max_tokens=max_tokens)
        task_type, confidence = classify_task(temp_req)
        atlas_model = resolve_atlas_model(task_type)
    else:
        atlas_model = model
        task_type = ATLAS_TASK_ROUTING[model]["tasks"][0]

    log.info(f"[atlas] {atlas_model} (task={task_type})")

    # Route through distillation (Claude) or local
    if settings.distillation_enabled:
        resp_id = f"resp_{uuid.uuid4().hex[:12]}"
        temp_req = ChatCompletionRequest(
            model="auto", messages=messages, max_tokens=max_tokens, temperature=temperature
        )

        # TRUE STREAMING: if stream=True, pipe Claude CLI tokens directly to client
        if stream:
            from a1.training.auto_trainer import handle_dual_execution_stream
            chunk_iter = await handle_dual_execution_stream(temp_req, task_type, 0.9)
            if chunk_iter is None:
                log.warning("[atlas] Stream distillation failed, retrying")
                chunk_iter = await handle_dual_execution_stream(temp_req, task_type, 0.9)
            if chunk_iter is not None:
                meta = {"provider": "claude-cli", "is_local": False, "task_type": task_type,
                        "atlas_model": atlas_model, "distillation": True,
                        "session_id": session.id if session else None}
                return await _return_response_or_stream(
                    True, resp_id, atlas_model, None, {}, meta, chunk_iterator=chunk_iter,
                )

        # NON-STREAMING: wait for full response (retry once on failure)
        from a1.training.auto_trainer import handle_dual_execution
        dual_result = await handle_dual_execution(temp_req, response, task_type, 0.9)
        if dual_result is None:
            log.warning(f"[atlas] Distillation failed for {atlas_model}, retrying Claude CLI once")
            dual_result = await handle_dual_execution(temp_req, response, task_type, 0.9)
        if dual_result is not None:
            assistant_text = dual_result.choices[0].message.content if dual_result.choices else ""

            if mask_map:
                from a1.security.pii_masker import pii_masker
                assistant_text = pii_masker.unmask(assistant_text, mask_map)

            if session:
                user_input = input_data if isinstance(input_data, str) else str(input_data)
                session.add_message("user", user_input)
                session.add_message("assistant", assistant_text)

            latency_ms = int((time.time() - start_time) * 1000)

            if session:
                from a1.session.manager import session_manager
                await session_manager.link_response(resp_id, session.id)

            usage = {"input_tokens": dual_result.usage.prompt_tokens,
                     "output_tokens": dual_result.usage.completion_tokens,
                     "total_tokens": dual_result.usage.total_tokens}
            meta = {"provider": "claude-cli", "is_local": False, "task_type": task_type,
                    "atlas_model": atlas_model, "distillation": True, "latency_ms": latency_ms,
                    "session_id": session.id if session else None,
                    "pii_masked": len(mask_map) > 0}
            return await _return_response_or_stream(False, resp_id, atlas_model, assistant_text, usage, meta)

    # Fallback: route to local model (Claude unavailable)
    log.warning(f"[atlas] Claude unavailable for {atlas_model}, falling back to local Ollama")
    temp_req = ChatCompletionRequest(
        model="auto", messages=messages, max_tokens=max_tokens, temperature=temperature
    )
    task_type_f, _ = classify_task(temp_req)
    model_name, provider_name = await select_model(task_type_f, "best_quality")
    provider = provider_registry.get_provider(provider_name)

    if not provider:
        raise HTTPException(404, "No provider available")

    temp_req.model = model_name
    try:
        result = await provider.complete(temp_req)
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return {
            "id": f"resp_{uuid.uuid4().hex[:12]}",
            "object": "response", "created_at": int(time.time()),
            "model": atlas_model, "status": "completed",
            "output": [{"type": "message", "id": f"msg_{uuid.uuid4().hex[:8]}",
                        "role": "assistant", "content": [{"type": "output_text", "text": f"Error: {e}"}],
                        "status": "completed"}],
            "error": {"type": "provider_error", "message": str(e)},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }

    latency_ms = int((time.time() - start_time) * 1000)
    assistant_text = result.choices[0].message.content if result.choices else ""
    is_local = provider_name == "ollama"
    cost = provider.estimate_cost(
        result.usage.prompt_tokens, result.usage.completion_tokens, model_name
    ) if not is_local else 0.0

    metrics.record_request(
        provider_name, model_name, task_type, latency_ms, cost,
        result.usage.prompt_tokens, result.usage.completion_tokens, is_local=is_local,
    )

    response.headers["X-Atlas-Model"] = atlas_model
    response.headers["X-Atlas-Provider"] = provider_name

    resp_id = f"resp_{uuid.uuid4().hex[:12]}"
    usage = {"input_tokens": result.usage.prompt_tokens,
             "output_tokens": result.usage.completion_tokens,
             "total_tokens": result.usage.total_tokens}
    meta = {
        "provider": provider_name,
        "actual_model": model_name,
        "is_local": is_local,
        "task_type": task_type,
        "atlas_model": atlas_model,
        "cost_usd": cost,
        "latency_ms": latency_ms,
        "fallback_to_local": True,
        "warning": "Claude CLI unavailable, used local model",
    }
    return await _return_response_or_stream(stream, resp_id, atlas_model, assistant_text, usage, meta)


@router.get("/atlas/models")
async def atlas_models():
    """List all Atlas models with their capabilities."""
    return {
        "object": "list",
        "family": "Atlas",
        "product": "Alpheric.AI",
        "models": [
            {**v, "id": k, "context_window": 128000}
            for k, v in ATLAS_TASK_ROUTING.items()
        ],
    }
