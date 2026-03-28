"""OpenAI-compatible endpoints: /v1/chat/completions and /v1/models."""

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.auth import verify_api_key, hash_key
from a1.common.logging import get_logger
from a1.common.metrics import metrics
from a1.common.telemetry import record_otel_request, tracer
from a1.common.tokens import count_tokens_for_model, count_messages_tokens_for_model
from a1.db.repositories import ConversationRepo, MessageRepo, RoutingRepo
from a1.dependencies import get_db
from a1.providers.registry import provider_registry
from a1.proxy.cache import cache_lookup, cache_store, is_cacheable
from a1.proxy.pipeline import (
    LEGACY_ALIASES, _load_session, _mask_pii, _persist_usage,
)
from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import ChatCompletionResponse, Usage
from a1.proxy.stream import sse_stream
from a1.routing.atlas_models import ATLAS_TASK_MAP
from a1.routing.classifier import classify_task
from a1.routing.strategy import select_model
from config.settings import settings

log = get_logger("proxy.openai")
router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    api_key: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    start_time = time.time()
    api_key_hash = hash_key(api_key) if api_key != "dev" else None

    # --- Session Memory ---
    session, request.messages = await _load_session(
        request.session_id, request.previous_response_id, request.user, request.messages
    )

    # --- PII Masking ---
    mask_map: dict = {}
    request.messages, mask_map = _mask_pii(request.messages)
    messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]

    # Optional OTLP tracing
    span = None
    if tracer:
        span = tracer.start_span("chat_completions")
        span.set_attribute("a1.model.requested", request.model)

    # Determine strategy
    strategy = request.strategy or "best_quality"

    request.model = LEGACY_ALIASES.get(request.model, request.model)

    # Atlas model family — route through Claude distillation or local fallback
    task_type: str | None = None
    confidence: float = 0.0
    if request.model in ATLAS_TASK_MAP:
        forced_task = ATLAS_TASK_MAP[request.model]
        task_type, confidence = forced_task, 1.0  # skip classify_task(); task is certain
        if settings.distillation_enabled:
            from a1.training.auto_trainer import handle_dual_execution
            dual_result = await handle_dual_execution(
                request, response, forced_task, 0.9,
            )
            if dual_result is not None:
                return dual_result
            # Claude failed — retry once before falling back
            m = request.model
            log.warning(f"Atlas {m} distillation failed, retrying")
            dual_result = await handle_dual_execution(
                request, response, forced_task, 0.9,
            )
            if dual_result is not None:
                return dual_result
            log.error(f"Atlas {m} failed twice, falling back")

        # Fallback: route to best local model for this task type
        request.model = "auto"
        strategy = "best_quality"

    # Route to model
    is_auto = request.model.startswith("auto") or request.model == "local"
    if is_auto:
        if task_type is None:
            task_type, confidence = classify_task(request)
        if request.model == "auto:fast":
            strategy = "lowest_latency"
        elif request.model == "auto:cheap":
            strategy = "lowest_cost"
        model_name, provider_name = await select_model(task_type, strategy)
        provider = provider_registry.get_provider(provider_name)
        if not provider:
            for p in provider_registry.healthy_providers.values():
                provider = p
                models = p.list_models()
                if models:
                    model_name = models[0].name
                    provider_name = p.name
                break
        request.model = model_name
    else:
        if task_type is None:
            task_type, confidence = classify_task(request)
        provider = provider_registry.get_provider_for_model(request.model)
        provider_name = provider.name if provider else "unknown"
        model_name = request.model

    if not provider:
        if span:
            span.end()
        raise HTTPException(status_code=404, detail=f"No provider found for model: {request.model}")

    # Determine if local
    is_local = provider_name == "ollama"

    if span:
        span.set_attribute("a1.task_type", task_type or "unknown")
        span.set_attribute("a1.model.selected", model_name)
        span.set_attribute("a1.provider", provider_name)
        span.set_attribute("a1.is_local", is_local)

    log.info(f"Routing to {provider_name}/{model_name} (task={task_type}, local={is_local})")

    # --- GPTCache lookup ---
    if is_cacheable(request.stream, request.tools):
        cached = cache_lookup(messages_dicts, model_name)
        if cached:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics.record_request(
                f"{provider_name}:cached", model_name, task_type, latency_ms, 0.0, 0, 0, is_local=is_local,
            )
            if span:
                span.set_attribute("a1.cache_hit", True)
                span.end()
            resp = ChatCompletionResponse(**cached)
            resp.provider = f"{provider_name}:cached"
            response.headers["X-A1-Cache"] = "hit"
            return resp

    # --- Streaming ---
    if request.stream:
        chunks = provider.stream(request)

        async def stream_and_log():
            full_content = ""
            stream_usage = None

            async for chunk in chunks:
                if chunk.choices and chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content
                # Capture provider-reported usage from final chunk
                if chunk.usage:
                    stream_usage = chunk.usage
                yield chunk

            # Accurate token counting
            if stream_usage:
                prompt_tokens = stream_usage.prompt_tokens
                completion_tokens = stream_usage.completion_tokens
            else:
                prompt_tokens = count_messages_tokens_for_model(messages_dicts, model_name)
                completion_tokens = count_tokens_for_model(full_content, model_name)

            latency_ms = int((time.time() - start_time) * 1000)
            cost = provider.estimate_cost(prompt_tokens, completion_tokens, model_name) if not is_local else 0.0

            # Emit usage SSE event
            from a1.proxy.response_models import ChatCompletionChunk
            yield ChatCompletionChunk(
                id="chatcmpl-usage",
                model=model_name,
                choices=[],
                usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                            total_tokens=prompt_tokens + completion_tokens),
            )

            metrics.record_request(
                provider_name, model_name, task_type, latency_ms, cost,
                prompt_tokens, completion_tokens, is_local=is_local,
            )
            record_otel_request(
                provider_name, model_name, task_type, latency_ms, cost,
                prompt_tokens, completion_tokens,
            )
            asyncio.create_task(_persist_usage(
                provider_name, model_name, is_local,
                prompt_tokens, completion_tokens, cost, latency_ms,
                api_key_hash,
            ))
            if span:
                span.set_attribute("a1.latency_ms", latency_ms)
                span.set_attribute("a1.cost_usd", cost)
                span.set_attribute("a1.tokens_in", prompt_tokens)
                span.set_attribute("a1.tokens_out", completion_tokens)
                span.end()

        response.headers["X-A1-Provider"] = provider_name
        response.headers["X-A1-Is-Local"] = str(is_local).lower()
        return await sse_stream(stream_and_log())

    # --- Non-streaming ---
    result = await provider.complete(request)
    latency_ms = int((time.time() - start_time) * 1000)
    cost = provider.estimate_cost(
        result.usage.prompt_tokens, result.usage.completion_tokens, model_name
    ) if not is_local else 0.0
    result.provider = provider_name
    result.task_type = task_type
    result.routing_strategy = strategy

    # Set response headers
    response.headers["X-A1-Cost"] = str(round(cost, 6))
    response.headers["X-A1-Provider"] = provider_name
    response.headers["X-A1-Tokens-In"] = str(result.usage.prompt_tokens)
    response.headers["X-A1-Tokens-Out"] = str(result.usage.completion_tokens)
    response.headers["X-A1-Is-Local"] = str(is_local).lower()
    response.headers["X-A1-Cache"] = "miss"

    # Record metrics
    metrics.record_request(
        provider_name, model_name, task_type, latency_ms, cost,
        result.usage.prompt_tokens, result.usage.completion_tokens, is_local=is_local,
    )
    record_otel_request(
        provider_name, model_name, task_type, latency_ms, cost,
        result.usage.prompt_tokens, result.usage.completion_tokens,
    )

    if span:
        span.set_attribute("a1.latency_ms", latency_ms)
        span.set_attribute("a1.cost_usd", cost)
        span.set_attribute("a1.tokens_in", result.usage.prompt_tokens)
        span.set_attribute("a1.tokens_out", result.usage.completion_tokens)
        span.end()

    # Cache store
    if is_cacheable(request.stream, request.tools):
        cache_store(messages_dicts, model_name, result.model_dump())

    # Persist usage in background
    asyncio.create_task(_persist_usage(
        provider_name, model_name, is_local,
        result.usage.prompt_tokens, result.usage.completion_tokens, cost, latency_ms,
        api_key_hash,
    ))

    # PII unmask and session save
    assistant_content = result.choices[0].message.content if result.choices else ""
    if mask_map:
        from a1.security.pii_masker import pii_masker
        assistant_content = pii_masker.unmask(assistant_content, mask_map)
        if result.choices:
            result.choices[0].message.content = assistant_content
    if session:
        user_input = next(
            (m.content for m in reversed(request.messages) if m.role == "user"), ""
        )
        session.add_message("user", user_input or "")
        session.add_message("assistant", assistant_content or "")
        resp_id = result.id if result.id else f"chatcmpl-{uuid.uuid4().hex[:12]}"
        from a1.session.manager import session_manager
        session_manager.link_response(resp_id, session.id)

    # Persist conversation to DB
    try:
        conv_repo = ConversationRepo(db)
        msg_repo = MessageRepo(db)
        routing_repo = RoutingRepo(db)

        conv_id = uuid.UUID(request.conversation_id) if request.conversation_id else None
        if not conv_id:
            conv = await conv_repo.create(source="proxy", user_id=request.user)
            conv_id = conv.id

        seq = 0
        for m in request.messages:
            await msg_repo.add(conv_id, m.role, m.content or "", seq)
            seq += 1

        assistant_msg = await msg_repo.add(conv_id, "assistant", assistant_content or "", seq)

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

    return result


@router.get("/v1/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    models = provider_registry.list_all_models()
    return {
        "object": "list",
        "data": [
            {
                "id": m.name,
                "object": "model",
                "owned_by": m.provider,
                "context_window": m.context_window,
            }
            for m in models
        ]
        + [
            {"id": "atlas-plan", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Planning, discussion, brainstorming"},
            {"id": "atlas-code", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Code generation, debugging, review"},
            {"id": "atlas-secure", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Security analysis, reasoning, auditing"},
            {"id": "atlas-infra", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Infrastructure, DevOps, deployment"},
            {"id": "atlas-data", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Data analysis, statistics, ETL"},
            {"id": "atlas-books", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Documentation, writing, research"},
            {"id": "atlas-audit", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Compliance auditing, log analysis, structured extraction"},
            {"id": "auto", "object": "model", "owned_by": "alpheric.ai", "context_window": 200000},
            {"id": "auto:fast", "object": "model", "owned_by": "alpheric.ai", "context_window": 200000},
            {"id": "auto:cheap", "object": "model", "owned_by": "alpheric.ai", "context_window": 200000},
            {"id": "alpheric-1", "object": "model", "owned_by": "alpheric.ai", "context_window": 128000, "description": "Legacy alias for atlas-plan"},
            {"id": "local", "object": "model", "owned_by": "alpheric.ai", "context_window": 4096},
        ],
    }
