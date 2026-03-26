import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from a1.common.logging import setup_logging
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.debug)

    # Initialize OpenTelemetry (no-op if otlp_endpoint is empty)
    from a1.common.telemetry import setup_telemetry
    setup_telemetry(app, settings)

    # Initialize GPTCache (no-op if cache_enabled is False)
    from a1.proxy.cache import init_cache
    init_cache(settings)

    # Register LLM providers
    from a1.providers.registry import provider_registry
    await provider_registry.initialize()

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

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
