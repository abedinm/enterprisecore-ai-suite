"""Rate limiting.

slowapi's @limiter.limit decorator wraps endpoint functions in a way that
breaks FastAPI's body-parameter detection (see auth.py). Instead, we expose
a small dependency-based sliding-window limiter that works as a
``Depends(RateLimit("5/minute"))`` argument on individual endpoints and never
touches the function signature.

The slowapi ``limiter`` instance is kept around for compatibility with the
existing rate-limit-reset test fixture, but no endpoint uses its decorator
anymore.
"""
# NOTE: `from __future__ import annotations` is intentionally NOT used.
# With PEP 563 string annotations, FastAPI's class-dependency introspection
# fails to recognise `Request` as the Starlette-injection type and falls back
# to treating the parameter as a query field — same root cause as the slowapi
# bug documented in auth.py.

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.exceptions import AppError

# Legacy slowapi limiter, kept for the test reset hook.
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


# ---- Dependency-based sliding-window limiter ----------------------------
class _SlidingWindow:
    """One sliding window per (limit_id, client_key). Thread-safe.

    Keeps a deque of request timestamps; drops anything older than the
    window when a new request is checked.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def hit(self, limit_id: str, key: str, count: int, window_seconds: float) -> tuple[bool, int]:
        """Record a hit. Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            dq = self._hits[(limit_id, key)]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= count:
                # Earliest hit + window = when we'll be allowed again
                retry = max(1, int((dq[0] + window_seconds) - now))
                return False, retry
            dq.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_window = _SlidingWindow()


def reset_dependency_limiter() -> None:
    """Clear all sliding windows. Used by the test fixture."""
    _window.reset()


def _parse_rule(rule: str) -> tuple[int, float]:
    """Parse '5/minute' or '20/hour' or '100/second'. Returns (count, window_seconds)."""
    try:
        count_str, unit = rule.split("/")
        count = int(count_str.strip())
    except ValueError as e:
        raise ValueError(f"Bad rate-limit rule {rule!r}; expected 'N/unit'") from e
    unit = unit.strip().lower().rstrip("s")
    seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}.get(unit)
    if seconds is None:
        raise ValueError(f"Unknown unit in rate-limit rule {rule!r}")
    return count, float(seconds)


class RateLimit:
    """FastAPI dependency that limits an endpoint to ``rule`` per client IP.

    Usage::

        @router.post("/login", dependencies=[Depends(RateLimit("5/minute"))])
        def login(...): ...

    Implementation note: the dependency call uses a non-`Request`-annotated
    parameter name (``http_req``) and relies on FastAPI's Starlette-Request
    injection by *type*, not by name. Doing it this way avoids a known
    FastAPI bug where a dependency taking ``request: Request`` shadows the
    endpoint's own ``request: Request`` parameter and FastAPI then treats
    the endpoint's request as a query string field named "request".
    """

    def __init__(self, rule: str, *, id: str | None = None):
        self.rule = rule
        self.count, self.window = _parse_rule(rule)
        self.id = id or rule

    def __call__(self, http_req: Request) -> None:  # NB: parameter name is NOT 'request'
        client_ip = get_remote_address(http_req) or "unknown"
        allowed, retry_after = _window.hit(self.id, client_ip, self.count, self.window)
        if not allowed:
            raise AppError(
                f"Too many requests. Limit is {self.rule} per IP. Retry in {retry_after}s.",
                code="rate_limited",
                status_code=429,
            )


# ---------------------------------------------------------------------------
# Convenience factory for per-module write limits
# ---------------------------------------------------------------------------
# Each business module (finance, hr, crm, ...) gets its own write bucket so a
# burst against one module doesn't starve writes against another. The default
# allowance of 60/minute is generous for normal operator use but still tight
# enough to slow down a stolen-token enumeration attack.
DEFAULT_WRITE_RULE = "60/minute"

# Methods considered "writes" for the per-module limiter. GET and HEAD pass
# through untouched — reads are governed at the app level (or not at all).
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class WriteRateLimit(RateLimit):
    """Rate-limiter that only counts mutation requests (POST/PUT/PATCH/DELETE).

    Designed to be applied at router level as a single dependency::

        router = APIRouter(dependencies=[Depends(WriteRateLimit("finance"))])

    GETs and HEADs are no-ops so list/detail endpoints aren't affected. The
    bucket id is ``<module>-write`` so every mutation across the module
    shares one sliding window — which is the right behaviour for blocking
    stolen-token enumeration sprees.
    """

    def __init__(self, module: str, *, rule: str = DEFAULT_WRITE_RULE):
        super().__init__(rule, id=f"{module}-write")
        self.module = module

    def __call__(self, http_req: Request) -> None:  # type: ignore[override]
        if http_req.method.upper() not in _WRITE_METHODS:
            return
        super().__call__(http_req)


def write_rate_limit(module: str, *, rule: str = DEFAULT_WRITE_RULE) -> "WriteRateLimit":
    """Return a ``WriteRateLimit`` for ``module``. See class docstring."""
    return WriteRateLimit(module, rule=rule)
