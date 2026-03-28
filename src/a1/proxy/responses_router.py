"""OpenAI Responses API endpoint: /v1/responses."""

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.auth import verify_api_key, hash_key
from a1.common.logging import get_logger
from a1.common.metrics import metrics
from a1.db.repositories import ConversationRepo, MessageRepo, RoutingRepo
from a1.dependencies import get_db
from a1.providers.registry import provider_registry
from a1.proxy.pipeline import (
    LEGACY_ALIASES, _load_session, _mask_pii, _persist_usage, _return_response_or_stream,
)
from a1.proxy.request_models import ChatCompletionRequest, MessageInput
from a1.routing.atlas_models import ATLAS_TASK_MAP
from a1.routing.classifier import classify_task
from a1.routing.strategy import select_model
from config.settings import settings

log = get_logger("proxy.responses")
router = APIRouter()


@router.post("/v1/responses")
async def responses_api(
    request: dict,
    response: Response,
    api_key: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """OpenAI Responses API format — used by OpenClaw and other clients.

    Accepts: { model, input (str or messages), instructions, temperature, max_output_tokens, stream }
    Returns: { id, object: "response", output: [{type: "message", content: [{type: "output_text", text}]}] }
    """
    start_time = time.time()
    api_key_hash = hash_key(api_key) if api_key != "dev" else None

    # Parse the Responses API format
    model = request.get("model", "atlas-plan")
    input_data = request.get("input", "")
    instructions = request.get("instructions", "")
    tools = request.get("tools", [])
    temperature = request.get("temperature")
    max_tokens = request.get("max_output_tokens") or request.get("max_tokens", 1000)
    stream = request.get("stream", False)

    # Build messages from input
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

    if isinstance(input_data, str):
        messages.append(MessageInput(role="user", content=input_data))
    elif isinstance(input_data, list):
        for msg in input_data:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                    content = " ".join(text_parts)
                messages.append(MessageInput(role=role, content=content))
            elif isinstance(msg, str):
                messages.append(MessageInput(role="user", content=msg))

    if not messages:
        messages.append(MessageInput(role="user", content="Hello"))

    # --- Session Memory ---
    session_id = request.get("session_id")
    previous_response_id = request.get("previous_response_id")
    user_id = request.get("user")
    # Capture user turn text before history injection
    user_turn_text = input_data if isinstance(input_data, str) else (
        next((m.get("content", "") for m in reversed(input_data)
              if isinstance(m, dict) and m.get("role") == "user"), "")
        if isinstance(input_data, list) else ""
    )
    session, messages = await _load_session(session_id, previous_response_id, user_id, messages)

    # --- PII Masking ---
    mask_map: dict = {}
    messages, mask_map = _mask_pii(messages)

    model = LEGACY_ALIASES.get(model, model)

    # Atlas model family routing
    task_type: str | None = None
    confidence: float = 0.0
    if model in ATLAS_TASK_MAP:
        atlas_task = ATLAS_TASK_MAP[model]
        task_type, confidence = atlas_task, 1.0
        atlas_model_name = model
        if settings.distillation_enabled:
            from a1.training.auto_trainer import handle_dual_execution
            temp_msgs = [MessageInput(role=m.role, content=m.content) for m in messages]
            temp_req = ChatCompletionRequest(model="auto", messages=temp_msgs, max_tokens=max_tokens)
            dual_result = await handle_dual_execution(temp_req, response, atlas_task, 0.9)
            if dual_result is not None:
                assistant_text = dual_result.choices[0].message.content if dual_result.choices else ""
                resp_id = f"resp_{uuid.uuid4().hex[:12]}"
                if mask_map:
                    from a1.security.pii_masker import pii_masker
                    assistant_text = pii_masker.unmask(assistant_text, mask_map)
                if session:
                    session.add_message("user", user_turn_text or "")
                    session.add_message("assistant", assistant_text or "")
                    from a1.session.manager import session_manager as _sm
                    _sm.link_response(resp_id, session.id)
                usage = {"input_tokens": dual_result.usage.prompt_tokens,
                         "output_tokens": dual_result.usage.completion_tokens,
                         "total_tokens": dual_result.usage.total_tokens}
                meta = {"provider": "claude-cli", "is_local": False,
                        "task_type": atlas_task, "distillation": True,
                        "atlas_model": atlas_model_name, "session_id": session.id if session else None}
                return await _return_response_or_stream(stream, resp_id, atlas_model_name, assistant_text, usage, meta)
            log.warning(f"[responses] Atlas distillation failed for {atlas_model_name}, retrying")
            dual_result = await handle_dual_execution(temp_req, response, atlas_task, 0.9)
            if dual_result is not None:
                assistant_text = dual_result.choices[0].message.content if dual_result.choices else ""
                resp_id = f"resp_{uuid.uuid4().hex[:12]}"
                if mask_map:
                    from a1.security.pii_masker import pii_masker
                    assistant_text = pii_masker.unmask(assistant_text, mask_map)
                if session:
                    session.add_message("user", user_turn_text or "")
                    session.add_message("assistant", assistant_text or "")
                    from a1.session.manager import session_manager as _sm
                    _sm.link_response(resp_id, session.id)
                usage = {"input_tokens": dual_result.usage.prompt_tokens,
                         "output_tokens": dual_result.usage.completion_tokens,
                         "total_tokens": dual_result.usage.total_tokens}
                meta = {"provider": "claude-cli", "is_local": False,
                        "task_type": atlas_task, "distillation": True,
                        "atlas_model": atlas_model_name, "session_id": session.id if session else None}
                return await _return_response_or_stream(stream, resp_id, atlas_model_name, assistant_text, usage, meta)
            log.error(f"[responses] Atlas {atlas_model_name} failed twice, falling back")
        model = "auto"

    # Build ChatCompletionRequest
    chat_req = ChatCompletionRequest(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Resolve model
    strategy = "best_quality"
    is_auto = chat_req.model.startswith("auto") or chat_req.model == "local"
    if is_auto:
        if task_type is None:
            task_type, confidence = classify_task(chat_req)
        if chat_req.model == "auto:fast":
            strategy = "lowest_latency"
        elif chat_req.model == "auto:cheap":
            strategy = "lowest_cost"
        model_name, provider_name = await select_model(task_type, strategy)
        provider = provider_registry.get_provider(provider_name)
        if not provider:
            for p in provider_registry.healthy_providers.values():
                provider = p
                ms = p.list_models()
                if ms:
                    model_name = ms[0].name
                    provider_name = p.name
                break
        chat_req.model = model_name
    else:
        if task_type is None:
            task_type, confidence = classify_task(chat_req)
        provider = provider_registry.get_provider_for_model(chat_req.model)
        provider_name = provider.name if provider else "unknown"
        model_name = chat_req.model

    if not provider:
        raise HTTPException(status_code=404, detail=f"No provider for model: {chat_req.model}")

    is_local = provider_name in ("ollama", "claude-cli")

    log.info(f"[responses] Routing to {provider_name}/{model_name} (task={task_type})")

    # Execute with error handling
    try:
        result = await provider.complete(chat_req)
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log.error(f"[responses] Provider error: {e}")
        metrics.record_request(
            provider_name, model_name, task_type, latency_ms, 0.0, 0, 0,
            is_local=is_local, error=True,
        )
        resp_id = f"resp_{uuid.uuid4().hex[:12]}"
        return {
            "id": resp_id,
            "object": "response",
            "created_at": int(time.time()),
            "model": model_name,
            "output": [
                {
                    "type": "message",
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": f"Error: Model {model_name} is loading. Please retry in a few seconds.",
                        }
                    ],
                    "status": "completed",
                }
            ],
            "status": "completed",
            "error": {"type": "timeout", "message": str(e)},
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }

    latency_ms = int((time.time() - start_time) * 1000)
    assistant_text = result.choices[0].message.content if result.choices else ""

    # PII unmask and session save
    if mask_map:
        from a1.security.pii_masker import pii_masker
        assistant_text = pii_masker.unmask(assistant_text, mask_map)
    resp_id = f"resp_{uuid.uuid4().hex[:12]}"
    if session:
        session.add_message("user", user_turn_text or "")
        session.add_message("assistant", assistant_text or "")
        from a1.session.manager import session_manager as _sm
        _sm.link_response(resp_id, session.id)

    # Record metrics
    cost = provider.estimate_cost(
        result.usage.prompt_tokens, result.usage.completion_tokens, model_name
    ) if not is_local else 0.0
    metrics.record_request(
        provider_name, model_name, task_type, latency_ms, cost,
        result.usage.prompt_tokens, result.usage.completion_tokens, is_local=is_local,
    )

    # Response headers
    response.headers["X-A1-Provider"] = provider_name
    response.headers["X-A1-Model"] = model_name
    response.headers["X-A1-Is-Local"] = str(is_local).lower()

    # Persist usage in background
    asyncio.create_task(_persist_usage(
        provider_name, model_name, is_local,
        result.usage.prompt_tokens, result.usage.completion_tokens, cost, latency_ms,
        api_key_hash,
    ))

    # Persist conversation to DB
    try:
        conv_repo = ConversationRepo(db)
        msg_repo = MessageRepo(db)
        routing_repo = RoutingRepo(db)

        conv = await conv_repo.create(source="proxy", user_id=request.get("user"))
        conv_id = conv.id

        seq = 0
        for m in messages:
            await msg_repo.add(conv_id, m.role, m.content or "", seq)
            seq += 1

        assistant_msg = await msg_repo.add(conv_id, "assistant", assistant_text or "", seq)

        await routing_repo.record(
            message_id=assistant_msg.id,
            provider=provider_name, model=model_name, strategy=strategy,
            task_type=task_type, confidence=confidence, latency_ms=latency_ms,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            cost_usd=cost, is_local=is_local, api_key_hash=api_key_hash,
        )
    except Exception as e:
        log.error(f"Failed to persist conversation: {e}")

    # Return Responses API format (JSON or SSE stream)
    usage = {"input_tokens": result.usage.prompt_tokens,
             "output_tokens": result.usage.completion_tokens,
             "total_tokens": result.usage.total_tokens}
    meta = {"provider": provider_name, "is_local": is_local,
            "task_type": task_type, "latency_ms": latency_ms, "cost_usd": cost,
            "session_id": session.id if session else None}
    return await _return_response_or_stream(stream, resp_id, model_name, assistant_text, usage, meta)
