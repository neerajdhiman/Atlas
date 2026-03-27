"""OpenAI-compatible proxy endpoint with accurate token counting,
local/external usage tracking, multi-account key pool, and response headers."""

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, Response
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
from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import ChatCompletionResponse, Usage
from a1.proxy.stream import sse_stream
from a1.routing.classifier import classify_task
from a1.routing.strategy import select_model

log = get_logger("proxy")
router = APIRouter(tags=["proxy"])

# Reference cost for savings calculation (gpt-4o-mini rates)
REFERENCE_COST_PER_1K_INPUT = 0.00015
REFERENCE_COST_PER_1K_OUTPUT = 0.0006


def _calc_equivalent_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """What this request would have cost using the reference external model."""
    return (prompt_tokens / 1000 * REFERENCE_COST_PER_1K_INPUT +
            completion_tokens / 1000 * REFERENCE_COST_PER_1K_OUTPUT)


async def _persist_usage(
    provider_name: str, model_name: str, is_local: bool,
    prompt_tokens: int, completion_tokens: int, cost: float,
    latency_ms: int, api_key_hash: str | None, account_id=None,
    cache_hit: bool = False, error: bool = False,
):
    """Persist usage record to DB (fire-and-forget background task)."""
    try:
        from a1.db.engine import async_session
        from a1.db.models import UsageRecord
        async with async_session() as session:
            async with session.begin():
                record = UsageRecord(
                    api_key_hash=api_key_hash,
                    account_id=account_id,
                    provider=provider_name,
                    model=model_name,
                    is_local=is_local,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    equivalent_external_cost_usd=_calc_equivalent_cost(prompt_tokens, completion_tokens) if is_local else 0,
                    latency_ms=latency_ms,
                    error=error,
                    cache_hit=cache_hit,
                )
                session.add(record)
    except Exception as e:
        log.error(f"Failed to persist usage: {e}")


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    api_key: str = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    start_time = time.time()
    messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]
    api_key_hash = hash_key(api_key) if api_key != "dev" else None

    # Optional OTLP tracing
    span = None
    if tracer:
        span = tracer.start_span("chat_completions")
        span.set_attribute("a1.model.requested", request.model)

    # Determine strategy
    strategy = request.strategy or "best_quality"

    # Route alpheric-1 to best local model via auto-routing
    if request.model == "alpheric-1":
        request.model = "auto"
        strategy = "best_quality"

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
            from a1.proxy.response_models import ChatCompletionChunk, StreamChoice, DeltaMessage
            yield ChatCompletionChunk(
                id=f"chatcmpl-usage",
                model=model_name,
                choices=[],
                usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=prompt_tokens + completion_tokens),
            )

            metrics.record_request(
                provider_name, model_name, task_type, latency_ms, cost,
                prompt_tokens, completion_tokens, is_local=is_local,
            )
            record_otel_request(
                provider_name, model_name, task_type, latency_ms, cost,
                prompt_tokens, completion_tokens,
            )
            # Persist usage in background
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

        assistant_content = result.choices[0].message.content if result.choices else ""
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

    # Parse the Responses API format
    model = request.get("model", "alpheric-1")
    input_data = request.get("input", "")
    instructions = request.get("instructions", "")
    temperature = request.get("temperature")
    max_tokens = request.get("max_output_tokens") or request.get("max_tokens", 1000)
    stream = request.get("stream", False)

    # Build messages from input
    from a1.proxy.request_models import MessageInput
    messages = []
    if instructions:
        messages.append(MessageInput(role="system", content=instructions))

    if isinstance(input_data, str):
        messages.append(MessageInput(role="user", content=input_data))
    elif isinstance(input_data, list):
        # Array of messages in OpenAI format
        for msg in input_data:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Content array format: [{"type": "input_text", "text": "..."}]
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                    content = " ".join(text_parts)
                messages.append(MessageInput(role=role, content=content))
            elif isinstance(msg, str):
                messages.append(MessageInput(role="user", content=msg))

    if not messages:
        messages.append(MessageInput(role="user", content="Hello"))

    # Route alpheric-1 to auto
    if model == "alpheric-1":
        model = "auto"

    # Build ChatCompletionRequest
    chat_req = ChatCompletionRequest(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Resolve model
    is_auto = chat_req.model.startswith("auto") or chat_req.model == "local"
    if is_auto:
        task_type, confidence = classify_task(chat_req)
        strategy = "best_quality"
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
        task_type, confidence = classify_task(chat_req)
        provider = provider_registry.get_provider_for_model(chat_req.model)
        provider_name = provider.name if provider else "unknown"
        model_name = chat_req.model

    if not provider:
        from fastapi import HTTPException
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

    # Return Responses API format
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
                        "text": assistant_text,
                    }
                ],
                "status": "completed",
            }
        ],
        "status": "completed",
        "usage": {
            "input_tokens": result.usage.prompt_tokens,
            "output_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.total_tokens,
        },
        "metadata": {
            "provider": provider_name,
            "is_local": is_local,
            "task_type": task_type,
            "latency_ms": latency_ms,
            "cost_usd": cost,
        },
    }


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
            {"id": "alpheric-1", "object": "model", "owned_by": "alpheric", "context_window": 128000},
            {"id": "auto", "object": "model", "owned_by": "a1-trainer", "context_window": 200000},
            {"id": "auto:fast", "object": "model", "owned_by": "a1-trainer", "context_window": 200000},
            {"id": "auto:cheap", "object": "model", "owned_by": "a1-trainer", "context_window": 200000},
            {"id": "local", "object": "model", "owned_by": "a1-trainer", "context_window": 4096},
        ],
    }
