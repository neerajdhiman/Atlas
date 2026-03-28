from typing import AsyncGenerator

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from a1.db.engine import async_session
from config.settings import settings

_redis: redis.Redis | None = None
_arq_pool = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        async with session.begin():
            yield session


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def init_arq_pool():
    """Create the ARQ Redis pool singleton. Called once at startup."""
    global _arq_pool
    from arq import create_pool
    from arq.connections import RedisSettings
    _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


async def get_arq_pool():
    """Return the ARQ pool, initializing lazily if needed."""
    global _arq_pool
    if _arq_pool is None:
        return await init_arq_pool()
    return _arq_pool
