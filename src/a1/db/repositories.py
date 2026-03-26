import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from a1.db.models import (
    Conversation,
    Message,
    ModelPerformance,
    QualitySignal,
    RoutingDecision,
    TrainingRun,
)


class ConversationRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, source: str, user_id: str | None = None, external_id: str | None = None, metadata: dict | None = None) -> Conversation:
        conv = Conversation(source=source, user_id=user_id, external_id=external_id, metadata_=metadata or {})
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def get(self, conv_id: uuid.UUID) -> Conversation | None:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.routing_decision))
            .options(selectinload(Conversation.messages).selectinload(Message.quality_signals))
            .where(Conversation.id == conv_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Conversation.id)))
        return result.scalar_one()


class MessageRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, conversation_id: uuid.UUID, role: str, content: str, sequence: int, tool_calls: dict | None = None, token_count: int | None = None) -> Message:
        msg = Message(
            conversation_id=conversation_id, role=role, content=content,
            sequence=sequence, tool_calls=tool_calls, token_count=token_count,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg


class RoutingRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, message_id: uuid.UUID, provider: str, model: str, strategy: str, task_type: str | None, confidence: float | None, latency_ms: int, prompt_tokens: int, completion_tokens: int, cost_usd: float, error: str | None = None, fallback_from: uuid.UUID | None = None) -> RoutingDecision:
        decision = RoutingDecision(
            message_id=message_id, provider=provider, model=model, strategy=strategy,
            task_type=task_type, confidence=confidence, latency_ms=latency_ms,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            cost_usd=cost_usd, error=error, fallback_from=fallback_from,
        )
        self.session.add(decision)
        await self.session.flush()
        return decision

    async def list_recent(self, limit: int = 100) -> list[RoutingDecision]:
        stmt = select(RoutingDecision).order_by(RoutingDecision.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_performance(self, task_type: str | None = None) -> list[ModelPerformance]:
        stmt = select(ModelPerformance)
        if task_type:
            stmt = stmt.where(ModelPerformance.task_type == task_type)
        stmt = stmt.order_by(ModelPerformance.avg_quality.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class QualityRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_signal(self, message_id: uuid.UUID, signal_type: str, value: float, evaluator: str | None = None) -> QualitySignal:
        signal = QualitySignal(message_id=message_id, signal_type=signal_type, value=value, evaluator=evaluator)
        self.session.add(signal)
        await self.session.flush()
        return signal


class TrainingRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, base_model: str, dataset_size: int, config: dict) -> TrainingRun:
        run = TrainingRun(base_model=base_model, dataset_size=dataset_size, config=config)
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_run(self, run_id: uuid.UUID) -> TrainingRun | None:
        result = await self.session.execute(select(TrainingRun).where(TrainingRun.id == run_id))
        return result.scalar_one_or_none()

    async def list_runs(self, limit: int = 50) -> list[TrainingRun]:
        stmt = select(TrainingRun).order_by(TrainingRun.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, run_id: uuid.UUID, status: str, **kwargs) -> None:
        run = await self.get_run(run_id)
        if run:
            run.status = status
            for k, v in kwargs.items():
                setattr(run, k, v)
            await self.session.flush()
