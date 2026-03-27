import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from a1.common.logging import setup_logging
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.debug)

    # Auto-create tables for SQLite (dev mode)
    if "sqlite" in settings.database_url:
        from a1.db.engine import create_tables
        import a1.db.models  # noqa — ensure all models are registered
        await create_tables()
        from a1.common.logging import get_logger
        get_logger("startup").info("SQLite tables created")

    # Initialize OpenTelemetry (no-op if otlp_endpoint is empty)
    from a1.common.telemetry import setup_telemetry
    setup_telemetry(app, settings)

    # Initialize GPTCache (no-op if cache_enabled is False)
    from a1.proxy.cache import init_cache
    init_cache(settings)

    # Load multi-account key pool (skip if DB not ready)
    try:
        from a1.providers.key_pool import key_pool
        await key_pool.load_accounts()
    except Exception:
        pass  # key pool load fails gracefully without DB

    # Register LLM providers
    from a1.providers.registry import provider_registry
    await provider_registry.initialize()

    # Warm up local Ollama models (background, non-blocking)
    if settings.warm_up_models:
        from a1.common.logging import get_logger
        log = get_logger("startup")
        log.info(f"Warming up {len(settings.warm_up_models)} models...")

        async def _warm_up():
            import httpx
            for model in settings.warm_up_models:
                ollama = provider_registry.get_provider("ollama")
                if ollama:
                    server_url = ollama.get_server_for_model(model)
                    try:
                        async with httpx.AsyncClient(base_url=server_url, timeout=300.0) as client:
                            await client.post("/api/generate", json={"model": model, "prompt": "hi", "options": {"num_predict": 1}})
                        log.info(f"  Warmed up {model} on {server_url}")
                    except Exception as e:
                        log.warning(f"  Failed to warm up {model}: {e}")

        asyncio.create_task(_warm_up())

    yield

    # Cleanup
    from a1.dependencies import _redis
    if _redis:
        await _redis.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="OneDesk AI/LLM Middleware & Training Platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    from a1.proxy.router import router as proxy_router
    from a1.dashboard.router import router as dashboard_router

    app.include_router(proxy_router)
    app.include_router(dashboard_router)

    # Request logging middleware — log ALL incoming requests for debugging
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from a1.common.logging import get_logger
    _req_log = get_logger("requests")

    class RequestLogMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: StarletteRequest, call_next):
            _req_log.info(f">>> {request.method} {request.url.path} from {request.client.host if request.client else '?'}")
            response = await call_next(request)
            _req_log.info(f"<<< {request.method} {request.url.path} -> {response.status_code}")
            return response

    app.add_middleware(RequestLogMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
