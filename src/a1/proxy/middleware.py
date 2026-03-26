import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from a1.common.logging import get_logger

log = get_logger("middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed = (time.time() - start) * 1000
        log.info(f"{request.method} {request.url.path} -> {response.status_code} ({elapsed:.0f}ms)")
        return response
