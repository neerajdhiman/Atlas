"""Auto-trainer: Claude-to-Local distillation pipeline.

Routes Atlas model requests through Claude Opus (teacher), returns response to user,
then asynchronously compares with local model (student). Accumulates training data
and triggers fine-tuning when enough quality samples exist per task type.
Gradually shifts traffic to local models as they improve.
"""

import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timezone

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from a1.common.logging import get_logger
from a1.common.metrics import metrics
from a1.common.tokens import count_tokens_for_model, count_messages_tokens_for_model
from a1.providers.registry import provider_registry
from a1.proxy.request_models import ChatCompletionRequest
from a1.proxy.response_models import (
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    Usage,
)
from config.settings import settings

log = get_logger("auto_trainer")

# In-memory cache of handoff percentages (refreshed from DB periodically)
_handoff_cache: dict[str, float] = {}
_handoff_cache_ts: float = 0.0
_CACHE_TTL = 60.0  # refresh every 60s


async def _refresh_handoff_cache():
    """Load handoff percentages from DB into memory."""
    global _handoff_cache, _handoff_cache_ts
    try:
        from a1.db.engine import async_session
        from a1.db.repositories import TaskTypeReadinessRepo
        async with async_session() as session:
            repo = TaskTypeReadinessRepo(session)
            records = await repo.list_all()
            _handoff_cache = {r.task_type: r.local_handoff_pct for r in records}
            _handoff_cache_ts = time.time()
    except Exception as e:
        log.warning(f"Failed to refresh handoff cache: {e}")


async def should_use_local(task_type: str) -> bool:
    """Decide whether to route to local model based on graduated handoff percentage.

    Uses probabilistic routing: at 30% handoff, 30% of requests go local.
    Returns True if this request should use local model.
    """
    global _handoff_cache_ts
    if time.time() - _handoff_cache_ts > _CACHE_TTL:
        await _refresh_handoff_cache()

    handoff_pct = _handoff_cache.get(task_type, 0.0)
    if handoff_pct <= 0:
        return False
    return random.random() < handoff_pct


async def handle_dual_execution(
    request: ChatCompletionRequest,
    response: Response,
    task_type: str,
    confidence: float,
) -> ChatCompletionResponse:
    """Send request to Claude Opus, return response, fire background local comparison.

    This is the main entry point called from the proxy router when
    an Atlas model is requested and distillation is enabled.
    """
    start_time = time.time()

    # Get Claude CLI provider
    claude_provider = provider_registry.get_provider("claude-cli")
    if not claude_provider:
        # Fallback to any healthy provider if Claude CLI not available
        log.warning("Claude CLI not available, falling back to auto-routing")
        return None  # Signal to router to use normal auto-routing

    # Set model to Claude Opus
    claude_model = settings.distillation_claude_model
    original_model = request.model
    request.model = claude_model

    # Execute Claude request
    try:
        result = await claude_provider.complete(request)
    except Exception as e:
        log.error(f"Claude execution failed: {e}, falling back to local")
        request.model = original_model
        return None  # Signal to router to use normal auto-routing

    latency_ms = int((time.time() - start_time) * 1000)
    claude_text = result.choices[0].message.content if result.choices else ""

    # Set response metadata
    result.provider = "claude-cli"
    result.task_type = task_type
    result.routing_strategy = "distillation"

    # Set response headers
    response.headers["X-A1-Provider"] = "claude-cli"
    response.headers["X-A1-Model"] = claude_model
    response.headers["X-A1-Is-Local"] = "false"
    response.headers["X-A1-Distillation"] = "teacher"
    response.headers["X-A1-Tokens-In"] = str(result.usage.prompt_tokens)
    response.headers["X-A1-Tokens-Out"] = str(result.usage.completion_tokens)

    # Record metrics
    cost = claude_provider.estimate_cost(
        result.usage.prompt_tokens, result.usage.completion_tokens, claude_model
    )
    metrics.record_request(
        "claude-cli", claude_model, task_type, latency_ms, cost,
        result.usage.prompt_tokens, result.usage.completion_tokens, is_local=False,
    )

    # Persist usage record
    try:
        from a1.db.engine import async_session as _usage_session
        from a1.db.models import UsageRecord
        async with _usage_session() as session:
            async with session.begin():
                record = UsageRecord(
                    provider="claude-cli", model=claude_model, is_local=False,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    cost_usd=cost, equivalent_external_cost_usd=0,
                    latency_ms=latency_ms, error=False, cache_hit=False,
                )
                session.add(record)
    except Exception as e:
        log.warning(f"Failed to persist usage: {e}")

    # Persist conversation to DB (so it shows on dashboard)
    try:
        from a1.db.engine import async_session as _async_session
        from a1.db.repositories import ConversationRepo, MessageRepo, RoutingRepo
        async with _async_session() as db_session:
            async with db_session.begin():
                conv_repo = ConversationRepo(db_session)
                msg_repo = MessageRepo(db_session)
                routing_repo = RoutingRepo(db_session)

                conv = await conv_repo.create(source="distillation", user_id=None)
                seq = 0
                for m in request.messages:
                    if m.role != "system":  # don't store huge system prompts
                        await msg_repo.add(conv.id, m.role, (m.content or "")[:500], seq)
                        seq += 1
                assistant_msg = await msg_repo.add(conv.id, "assistant", claude_text[:2000], seq)
                await routing_repo.record(
                    message_id=assistant_msg.id,
                    provider="claude-cli", model=claude_model, strategy="distillation",
                    task_type=task_type, confidence=confidence,
                    latency_ms=latency_ms,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    cost_usd=cost, is_local=False,
                )
    except Exception as e:
        log.warning(f"Failed to persist distillation conversation: {e}")

    # Fire background: local model comparison + training data collection
    messages_dicts = [m.model_dump(exclude_none=True) for m in request.messages]
    asyncio.create_task(_background_local_comparison(
        messages_dicts=messages_dicts,
        claude_response_text=claude_text,
        claude_model=claude_model,
        task_type=task_type,
        claude_latency_ms=latency_ms,
        claude_prompt_tokens=result.usage.prompt_tokens,
        claude_completion_tokens=result.usage.completion_tokens,
    ))

    # Restore original model name for display
    request.model = original_model
    return result


async def handle_dual_execution_stream(
    request: ChatCompletionRequest,
    task_type: str,
    confidence: float,
):
    """Stream response from Claude CLI, fire background comparison.

    Returns an async chunk iterator for true token-by-token streaming.
    Returns None if Claude is unavailable.
    """
    claude_provider = provider_registry.get_provider("claude-cli")
    if not claude_provider:
        return None

    claude_model = settings.distillation_claude_model
    request.model = claude_model

    try:
        return claude_provider.stream(request)
    except Exception as e:
        log.error(f"Claude stream failed: {e}")
        return None


async def _background_local_comparison(
    messages_dicts: list[dict],
    claude_response_text: str,
    claude_model: str,
    task_type: str,
    claude_latency_ms: int,
    claude_prompt_tokens: int,
    claude_completion_tokens: int,
):
    """Background task: run local model on same request, compare, store, maybe train."""
    try:
        from a1.proxy.request_models import ChatCompletionRequest, MessageInput
        from a1.routing.strategy import select_model

        # Select best local model for this task type
        local_model_name, local_provider_name = await select_model(task_type, "best_quality")
        local_provider = provider_registry.get_provider(local_provider_name)

        local_text = None
        local_latency = 0
        local_prompt_tokens = 0
        local_completion_tokens = 0

        if local_provider and local_provider_name == "ollama":
            # Build request for local model
            local_messages = [MessageInput(role=m["role"], content=m.get("content", "")) for m in messages_dicts]
            local_req = ChatCompletionRequest(
                model=local_model_name,
                messages=local_messages,
                max_tokens=1000,
            )

            start = time.time()
            try:
                local_result = await local_provider.complete(local_req)
                local_latency = int((time.time() - start) * 1000)
                local_text = local_result.choices[0].message.content if local_result.choices else ""
                local_prompt_tokens = local_result.usage.prompt_tokens
                local_completion_tokens = local_result.usage.completion_tokens
            except Exception as e:
                log.warning(f"Local comparison failed for {local_model_name}: {e}")
                local_latency = int((time.time() - start) * 1000)

        # Compute similarity
        similarity = 0.0
        if local_text and claude_response_text:
            similarity = _compute_similarity(claude_response_text, local_text)

        # Store dual execution record
        try:
            from a1.db.engine import async_session
            from a1.db.repositories import DualExecutionRepo, TaskTypeReadinessRepo

            async with async_session() as session:
                async with session.begin():
                    repo = DualExecutionRepo(session)
                    await repo.create(
                        task_type=task_type,
                        request_messages=messages_dicts,
                        claude_model=claude_model,
                        claude_response=claude_response_text,
                        claude_latency_ms=claude_latency_ms,
                        claude_prompt_tokens=claude_prompt_tokens,
                        claude_completion_tokens=claude_completion_tokens,
                        local_model=local_model_name if local_text else None,
                        local_response=local_text,
                        local_latency_ms=local_latency if local_text else None,
                        local_prompt_tokens=local_prompt_tokens if local_text else None,
                        local_completion_tokens=local_completion_tokens if local_text else None,
                        similarity_score=similarity if local_text else None,
                        quality_score=1.0,  # Claude response is always high quality
                    )

                    # Increment sample count
                    readiness_repo = TaskTypeReadinessRepo(session)
                    count = await readiness_repo.increment_sample_count(task_type)

                    log.info(
                        f"Distillation: task={task_type} similarity={similarity:.2f} "
                        f"claude={claude_latency_ms}ms local={local_latency}ms "
                        f"samples={count}"
                    )

                    # Check if training should be triggered
                    await _check_and_trigger_training(session, task_type, count)

        except Exception as e:
            log.error(f"Failed to store dual execution record: {e}")

    except Exception as e:
        log.error(f"Background local comparison error: {e}")


def _compute_similarity(text_a: str, text_b: str) -> float:
    """Compute semantic similarity between two texts.

    Uses simple word overlap (Jaccard) as a fast approximation.
    Can be upgraded to sentence-transformers embeddings later.
    """
    if not text_a or not text_b:
        return 0.0

    # Normalize
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())

    if not words_a or not words_b:
        return 0.0

    # Jaccard similarity
    intersection = words_a & words_b
    union = words_a | words_b
    jaccard = len(intersection) / len(union) if union else 0.0

    # Also check length ratio (penalize very different lengths)
    len_ratio = min(len(text_a), len(text_b)) / max(len(text_a), len(text_b))

    # Combined score
    return round(jaccard * 0.6 + len_ratio * 0.4, 3)


async def _check_and_trigger_training(session: AsyncSession, task_type: str, sample_count: int):
    """Check if enough distillation samples exist and trigger training."""
    if sample_count < settings.distillation_min_samples:
        return

    # Check if training is already running
    from a1.db.repositories import TrainingRepo
    repo = TrainingRepo(session)
    runs = await repo.list_runs(limit=5)
    for run in runs:
        if run.status in ("pending", "running") and run.config and run.config.get("task_type") == task_type:
            return  # Already training for this task type

    # Check if we've trained recently (within 1 hour)
    from a1.db.repositories import TaskTypeReadinessRepo
    readiness_repo = TaskTypeReadinessRepo(session)
    readiness = await readiness_repo.get_or_create(task_type)
    if readiness.last_evaluated_at:
        from datetime import timedelta
        if datetime.now(timezone.utc) - readiness.last_evaluated_at < timedelta(hours=1):
            return  # Trained recently

    # Trigger training!
    log.info(f"Auto-triggering training for task_type={task_type} ({sample_count} samples)")
    config = {
        "base_model": settings.training_base_model,
        "lora_rank": settings.training_lora_rank,
        "epochs": 3,
        "task_type": task_type,
        "distillation": True,
    }
    run = await repo.create_run(
        base_model=config["base_model"],
        dataset_size=sample_count,
        config=config,
    )
    readiness.last_evaluated_at = datetime.now(timezone.utc)
    readiness.last_training_run_id = str(run.id)

    log.info(f"Training run created: {run.id} for {task_type}")
    from a1.dependencies import get_arq_pool
    arq_pool = await get_arq_pool()
    await arq_pool.enqueue_job("run_training_pipeline", str(run.id))
    log.info(f"Training job dispatched to ARQ: run_id={run.id}")


async def update_handoff_after_training(task_type: str, eval_results: dict):
    """After a training run completes, update the handoff percentage."""
    try:
        from a1.db.engine import async_session
        from a1.db.repositories import TaskTypeReadinessRepo

        improved = eval_results.get("improved", False)
        improvement = eval_results.get("improvement", 0.0)

        async with async_session() as session:
            async with session.begin():
                repo = TaskTypeReadinessRepo(session)
                readiness = await repo.get_or_create(task_type)

                if improved and improvement > 0.02:  # >2% improvement
                    # Use per-task cap from DB; fall back to global setting if not set
                    cap = getattr(readiness, "max_local_pct", None) or settings.distillation_max_handoff_pct
                    new_pct = min(
                        readiness.local_handoff_pct + settings.distillation_handoff_increment,
                        cap,
                    )
                    readiness.local_handoff_pct = new_pct
                    readiness.local_avg_quality = eval_results.get("avg_finetuned_loss", 0.0)
                    log.info(
                        f"Handoff increased for {task_type}: "
                        f"{readiness.local_handoff_pct:.0%} → {new_pct:.0%} "
                        f"(improvement: {improvement:.1%})"
                    )
                else:
                    log.info(
                        f"No handoff change for {task_type} "
                        f"(improved={improved}, improvement={improvement:.1%})"
                    )

                # Refresh in-memory cache
                _handoff_cache[task_type] = readiness.local_handoff_pct

    except Exception as e:
        log.error(f"Failed to update handoff: {e}")
