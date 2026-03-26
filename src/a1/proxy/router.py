import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.auth import verify_api_key
from a1.common.logging import get_logger
from a1.common.metrics import metrics
from a1.common.telemetry import record_otel_request, tracer
from a1.common.tokens import count_messages_tokens
from a1.db.repositories import ConversationRepo, MessageRepo, RoutingRepo
from a1.dependencies import get_db
from a1.providers.registry import provider_registry
from a1.proxy.cache import cache_lookup, cache_store, is_cacheable
from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import ChatCompletionResponse
from a1.proxy.stream import sse_stream
from a1.routing.classifier import classify_task
from a1.routing.strategy import select_model

log = get_logger("proxy")
router = APIRouter(tags=["proxy"])


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    start_time = time.time()
    messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]

    # Optional OTLP tracing span
    span = None
    if tracer:
        span = tracer.start_span("chat_completions")
        span.set_attribute("a1.model.requested", request.model)

    # Determine strategy
    strategy = request.strategy or "best_quality"

    # Route to model
    is_auto = request.model.startswith("auto") or request.model == "local"
    if is_auto:
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
        task_type, confidence = classify_task(request)
        provider = provider_registry.get_provider_for_model(request.model)
        provider_name = provider.name if provider else "unknown"
        model_name = request.model

    if not provider:
        from fastapi import HTTPException
        if span:
            span.end()
        raise HTTPException(status_code=404, detail=f"No provider found for model: {request.model}")

    # Set span attributes after routing
    if span:
        span.set_attribute("a1.task_type", task_type or "unknown")
        span.set_attribute("a1.confidence", confidence or 0.0)
        span.set_attribute("a1.model.selected", model_name)
        span.set_attribute("a1.provider", provider_name)
        span.set_attribute("a1.strategy", strategy)

    log.info(f"Routing to {provider_name}/{model_name} (task={task_type}, strategy={strategy})")

    # --- GPTCache lookup (non-streaming, non-tool requests only) ---
    if is_cacheable(request.stream, request.tools):
        cached = cache_lookup(messages_dicts, model_name)
        if cached:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics.record_request(
                f"{provider_name}:cached", model_name, task_type, latency_ms, 0.0, 0, 0,
            )
            record_otel_request(
                f"{provider_name}:cached", model_name, task_type, latency_ms, 0.0, 0, 0,
            )
            if span:
                span.set_attribute("a1.cache_hit", True)
                span.end()
            response = ChatCompletionResponse(**cached)
            response.provider = f"{provider_name}:cached"
            return response

    # --- Streaming ---
    if request.stream:
        chunks = provider.stream(request)

        async def stream_and_log():
            full_content = ""
            async for chunk in chunks:
                if chunk.choices and chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content
                yield chunk

            latency_ms = int((time.time() - start_time) * 1000)
            prompt_tokens = count_messages_tokens(messages_dicts)
            completion_tokens = len(full_content.split()) * 2
            cost = provider.estimate_cost(prompt_tokens, completion_tokens, model_name)
            metrics.record_request(
                provider_name, model_name, task_type, latency_ms, cost,
                prompt_tokens, completion_tokens,
            )
            record_otel_request(
                provider_name, model_name, task_type, latency_ms, cost,
                prompt_tokens, completion_tokens,
            )
            if span:
                span.set_attribute("a1.latency_ms", latency_ms)
                span.set_attribute("a1.cost_usd", cost)
                span.end()

        return await sse_stream(stream_and_log())

    # --- Non-streaming ---
    response = await provider.complete(request)
    latency_ms = int((time.time() - start_time) * 1000)
    cost = provider.estimate_cost(
        response.usage.prompt_tokens, response.usage.completion_tokens, model_name
    )
    response.provider = provider_name
    response.task_type = task_type
    response.routing_strategy = strategy

    # Record metrics (in-memory + OTLP)
    metrics.record_request(
        provider_name, model_name, task_type, latency_ms, cost,
        response.usage.prompt_tokens, response.usage.completion_tokens,
    )
    record_otel_request(
        provider_name, model_name, task_type, latency_ms, cost,
        response.usage.prompt_tokens, response.usage.completion_tokens,
    )

    if span:
        span.set_attribute("a1.latency_ms", latency_ms)
        span.set_attribute("a1.cost_usd", cost)
        span.set_attribute("a1.cache_hit", False)
        span.end()

    # --- GPTCache store (on miss) ---
    if is_cacheable(request.stream, request.tools):
        cache_store(messages_dicts, model_name, response.model_dump())

    # Persist to DB (best-effort)
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

        assistant_content = response.choices[0].message.content if response.choices else ""
        assistant_msg = await msg_repo.add(conv_id, "assistant", assistant_content or "", seq)

        await routing_repo.record(
            message_id=assistant_msg.id,
            provider=provider_name, model=model_name, strategy=strategy,
            task_type=task_type, confidence=confidence, latency_ms=latency_ms,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=cost,
        )
    except Exception as e:
        log.error(f"Failed to persist conversation: {e}")

    return response


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
            {"id": "auto", "object": "model", "owned_by": "a1-trainer", "context_window": 200000},
            {"id": "auto:fast", "object": "model", "owned_by": "a1-trainer", "context_window": 200000},
            {"id": "auto:cheap", "object": "model", "owned_by": "a1-trainer", "context_window": 200000},
            {"id": "local", "object": "model", "owned_by": "a1-trainer", "context_window": 4096},
        ],
    }
