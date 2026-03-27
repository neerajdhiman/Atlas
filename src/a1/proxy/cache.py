"""GPTCache semantic caching layer.

Caches responses for semantically similar queries using ONNX embeddings + FAISS.
Only applies to non-streaming, non-tool-use requests.
No-op when settings.cache_enabled is False.
"""

import json
import os
from pathlib import Path

from a1.common.logging import get_logger

log = get_logger("proxy.cache")

_cache = None
_initialized = False


def init_cache(settings) -> None:
    """Initialize GPTCache with semantic similarity matching."""
    global _cache, _initialized

    if not settings.cache_enabled or _initialized:
        return

    try:
        from gptcache import Cache
        from gptcache.adapter.api import init_similar_cache

        cache_dir = os.path.dirname(settings.cache_db_path)
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)

        _cache = Cache()
        init_similar_cache(cache_obj=_cache)

        _initialized = True
        log.info(f"GPTCache initialized (semantic mode, db={settings.cache_db_path})")

    except ImportError as e:
        log.warning(f"GPTCache not available: {e}")
    except Exception as e:
        log.error(f"Failed to initialize GPTCache: {e}")


def _extract_query(messages: list[dict]) -> str:
    """Extract the user's query text for cache key."""
    # Use the last user message as the cache key
    for msg in reversed(messages):
        if msg.get("role") == "user" and msg.get("content"):
            return msg["content"]
    return json.dumps(messages, sort_keys=True)


def cache_lookup(messages: list[dict], model: str) -> dict | None:
    """Look up a cached response by semantic similarity."""
    if _cache is None:
        return None

    try:
        query = _extract_query(messages)
        result = _cache.get(query)
        if result is not None and result != "":
            log.info(f"Cache HIT for model={model}")
            if isinstance(result, str):
                return json.loads(result)
            return result
    except Exception as e:
        log.debug(f"Cache lookup error: {e}")

    return None


def cache_store(messages: list[dict], model: str, response_dict: dict) -> None:
    """Store a response in the cache keyed by the user's query."""
    if _cache is None:
        return

    try:
        query = _extract_query(messages)
        value = json.dumps(response_dict, default=str)
        _cache.set(query, value)
        log.debug(f"Cache STORE for model={model}")
    except Exception as e:
        log.debug(f"Cache store error: {e}")


def is_cacheable(stream: bool, tools: list | None) -> bool:
    """Check if a request is eligible for caching."""
    return not stream and not tools
