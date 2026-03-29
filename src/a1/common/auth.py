import hashlib
import time

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from a1.db.engine import async_session
from a1.db.models import ApiKey
from config.settings import settings

security = HTTPBearer(auto_error=False)

_DEFAULT_RATE_LIMIT_RPM = 60
_WINDOW_SECONDS = 60


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def _get_rate_limit_for_hash(key_hash: str) -> int:
    """Look up per-key rate limit from DB, or return default."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(ApiKey.rate_limit).where(ApiKey.key_hash == key_hash)
            )
            row = result.first()
            if row:
                return row[0]
    except Exception:
        pass
    return _DEFAULT_RATE_LIMIT_RPM


async def _enforce_rate_limit(key_hash: str) -> None:
    """Sliding-window rate limiter via Redis. Raises 429 if limit exceeded."""
    try:
        from a1.dependencies import get_redis
        r = await get_redis()
        rate_limit = await _get_rate_limit_for_hash(key_hash)

        redis_key = f"rate_limit:{key_hash}"
        now = time.time()
        window_start = now - _WINDOW_SECONDS

        # Use nanoseconds as unique member to avoid collisions in the same second
        member = str(time.time_ns())

        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, _WINDOW_SECONDS + 1)
        results = await pipe.execute()

        current_count = results[2]
        if current_count > rate_limit:
            # Retry-After = time until the oldest request in the window falls off
            oldest = await r.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(_WINDOW_SECONDS - (now - oldest[0][1])) + 1)
            else:
                retry_after = _WINDOW_SECONDS
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({rate_limit} req/min). Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Redis unavailable — fail open, don't block legitimate requests


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> str:
    """Verify API key from Bearer token and enforce per-key rate limits. Returns the key if valid."""
    # If no API keys configured, allow all (dev mode)
    if not settings.api_keys:
        return "dev"

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing API key")

    key = credentials.credentials
    if key not in settings.api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Enforce sliding-window rate limit keyed by api_key_hash
    await _enforce_rate_limit(hash_key(key))

    return key
