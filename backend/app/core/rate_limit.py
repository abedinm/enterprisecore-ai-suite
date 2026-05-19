"""Rate limiting via slowapi — IP-keyed, in-memory by default.

Used to defend brute-force endpoints (login, register, password reset). For
multi-process deployments, set `RATE_LIMIT_STORAGE` to a Redis URL.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=getattr(settings, "rate_limit_storage", None) or "memory://",
    headers_enabled=False,
)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded: {exc.detail}. Please wait and try again.",
            "code": "rate_limited",
        },
    )
