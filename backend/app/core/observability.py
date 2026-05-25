"""Observability middlewares: request ID propagation + Prometheus collection.

Both are pure ASGI middlewares so they compose cleanly with the existing
SecurityHeadersMiddleware and CORS layers. We avoid Starlette's BaseHTTPMiddleware
because it intercepts streaming bodies and breaks chunked SSE responses used by
``stream_call`` in the AI router.
"""
from __future__ import annotations

import time
from typing import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from ulid import ULID

from app.core.logging import request_id_ctx, tenant_id_ctx, user_id_ctx
from app.core.metrics import (
    http_in_flight,
    http_request_duration_seconds,
    http_requests_total,
)

# Routes excluded from the Prometheus middleware. ``/metrics`` would self-count
# every scrape; ``/api/health`` is high-volume liveness traffic that drowns
# real signal.
_METRICS_EXCLUDED_PATHS = frozenset({"/metrics", "/api/health"})


def _decode_header(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> str | None:
    for k, v in headers:
        if k.lower() == name:
            try:
                return v.decode("latin-1")
            except Exception:
                return None
    return None


class RequestIDMiddleware:
    """Read or mint ``X-Request-Id`` and stash it in context + response headers.

    Order matters: this middleware MUST run before any code that emits a log
    line for the request (otherwise the log line won't carry the correlation
    ID). It also runs before the Prometheus middleware so request_id is
    available for any debug logging during measurement.
    """

    HEADER = "x-request-id"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = _decode_header(scope.get("headers", ()), self.HEADER.encode("latin-1"))
        # Use the client-supplied ID only if it's a non-empty, reasonably short
        # string. Block obvious abuse (multi-kilobyte values would bloat logs).
        if incoming and 1 <= len(incoming) <= 200:
            rid = incoming
        else:
            rid = str(ULID())

        rid_token = request_id_ctx.set(rid)
        # tenant/user contextvars are populated by auth dependencies if the
        # request hits an authenticated endpoint. Reset them per-request so a
        # subsequent unauthenticated request doesn't inherit the previous
        # user's IDs.
        uid_token = user_id_ctx.set(None)
        tid_token = tenant_id_ctx.set(None)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers") or [])
                # Append (don't replace): some routes may set their own value,
                # but we'd rather have a guaranteed echo for clients.
                header_names = {k.lower() for k, _ in raw_headers}
                if self.HEADER.encode("latin-1") not in header_names:
                    raw_headers.append(
                        (self.HEADER.encode("latin-1"), rid.encode("latin-1"))
                    )
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_ctx.reset(rid_token)
            user_id_ctx.reset(uid_token)
            tenant_id_ctx.reset(tid_token)


class PrometheusMiddleware:
    """Count requests, measure duration, and track in-flight count.

    The ``path`` label uses the FastAPI route template (``request.scope["route"].path``)
    not the raw URL — so ``/api/v1/users/{user_id}`` collapses to a single
    series regardless of how many distinct user IDs visit. Unmatched paths
    (404s) fall back to a constant ``unmatched`` label, avoiding cardinality
    blowups from random URL probing by scanners.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_path = scope.get("path", "") or ""
        if raw_path in _METRICS_EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        status_holder: dict[str, int] = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message.get("status", 500))
            await send(message)

        http_in_flight.inc()
        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start
            http_in_flight.dec()

            # Resolve the route template AFTER the request — Starlette only
            # populates ``scope["route"]`` once routing has run. For 404s and
            # path-not-matched-yet conditions we fall back to "unmatched".
            route = scope.get("route")
            path_label = getattr(route, "path", None) or "unmatched"

            http_requests_total.labels(
                method=method, path=path_label, status=str(status_holder["status"])
            ).inc()
            http_request_duration_seconds.labels(
                method=method, path=path_label
            ).observe(elapsed)


__all__ = ["PrometheusMiddleware", "RequestIDMiddleware"]
