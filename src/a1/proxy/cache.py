"""GPTCache semantic caching layer.

Caches responses for semantically similar queries to reduce API costs.
Only applies to non-streaming, non-tool-use requests.
Completely no-op when settings.cache_enabled is False.
"""

import hashlib
import json
import os
from pathlib import Path

from a1.common.logging import get_logger

log = get_logger("proxy.cache")

_cache = None
_initialized = False


def init_cache(settings) -> None:
    """Initialize GPTCache. No-op if cache_enabled is False."""
    global _cache, _initialized

    if not settings.cache_enabled or _initialized:
        return

    try:
        from gptcache import Cache
        from gptcache.adapter.api import init_similar_cache
        from gptcache.manager import get_data_manager, CacheBase, VectorBase
        from gptcache.similarity_evaluation import SearchDistanceEvaluation

        # Ensure cache directory exists
        cache_dir = os.path.dirname(settings.cache_db_path)
        if cache_dir:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)

        _cache = Cache()

        # Select embedding model
        if settings.cache_embedding == "local":
            from gptcache.embedding import Onnx
            embedding = Onnx()
        else:
            from gptcache.embedding import OpenAI as OpenAIEmbedding
            embedding = OpenAIEmbedding()

        data_manager = get_data_manager(
            CacheBase("sqlite", sql_url=f"sqlite:///{settings.cache_db_path}"),
            VectorBase("faiss", dimension=embedding.dimension),
        )

        init_similar_cache(
            cache_obj=_cache,
            data_manager=data_manager,
            embedding=embedding,
            evaluation=SearchDistanceEvaluation(),
        )

        _initialized = True
        log.info(f"GPTCache initialized (embedding={settings.cache_embedding}, db={settings.cache_db_path})")

    except ImportError as e:
        log.warning(f"GPTCache not available: {e}")
    except Exception as e:
        log.error(f"Failed to initialize GPTCache: {e}")


def _make_cache_key(messages: list[dict], model: str) -> str:
    """Create a deterministic cache key from messages + model."""
    data = json.dumps(messages, sort_keys=True) + "|" + model
    return hashlib.sha256(data.encode()).hexdigest()


def cache_lookup(messages: list[dict], model: str) -> dict | None:
    """Look up a cached response. Returns response dict or None on miss."""
    if _cache is None:
        return None

    try:
        key = _make_cache_key(messages, model)
        result = _cache.get(key)
        if result is not None:
            log.info(f"Cache HIT for model={model}")
            return json.loads(result) if isinstance(result, str) else result
    except Exception as e:
        log.debug(f"Cache lookup error: {e}")

    return None


def cache_store(messages: list[dict], model: str, response_dict: dict) -> None:
    """Store a response in the cache."""
    if _cache is None:
        return

    try:
        key = _make_cache_key(messages, model)
        value = json.dumps(response_dict, default=str)
        _cache.set(key, value)
        log.debug(f"Cache STORE for model={model}")
    except Exception as e:
        log.debug(f"Cache store error: {e}")


def is_cacheable(stream: bool, tools: list | None) -> bool:
    """Check if a request is eligible for caching."""
    return not stream and not tools
