"""ASGI middleware that puts the request's tenant_id onto a ContextVar.

Read the JWT (header or cookie), resolve the user, copy their tenant_id onto
``tenant_id_ctx``. The auto-filter in ``app/core/tenant_orm.py`` then scopes
every ORM query for the rest of the request. On the way out (or on
exception) the contextvar is reset so concurrent requests for different
tenants stay isolated.

Why a custom middleware instead of a FastAPI dependency: the auto-filter
relies on the contextvar being set BEFORE any ORM session opens. A FastAPI
``Depends(...)`` runs after middleware but before the handler, which is too
late if any startup code (e.g. router-level dependencies) opens a session
first. Doing it at middleware ASGI level is the earliest hookable point
that's still inside a per-request scope.

Public endpoints (signup, /widget.js, /site/*, /api/health, /metrics) carry
no JWT, so the contextvar stays at its default of None — the auto-filter
skips its WHERE injection when tenant_id_ctx.get() is None, which keeps
those flows working without modification.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.tenant_context import tenant_id_ctx


class TenantMiddleware:
    """Sets the per-request tenant context from the JWT subject's tenant_id.

    Implementation note: we accept failure silently. If the JWT is missing,
    malformed, expired, or points at a deleted user, we leave the contextvar
    as None. The auth dependency further down the stack is responsible for
    rejecting the request — this middleware's job is only to copy the tenant
    binding onto the context, not to enforce auth.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        token_value = tenant_id_ctx.set(self._resolve_tenant_id(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            tenant_id_ctx.reset(token_value)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _resolve_tenant_id(scope: Scope) -> str | None:
        """Resolve the tenant id from this request's auth credentials.

        Looks at the Authorization header first (used by the SPA + tests),
        falls back to httpOnly cookies (browser session). Returns None for
        any anonymous, malformed, or unknown-user request.
        """
        try:
            jwt_token = TenantMiddleware._extract_token(scope)
            if not jwt_token:
                return None
            from app.core.security import decode_token
            payload = decode_token(jwt_token)
        except Exception:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        # Open a short-lived DB session just to look up the user's tenant_id.
        # We deliberately do this with the auto-filter bypassed because the
        # session opens before the contextvar is set; otherwise the WHERE
        # clause would force a tenant scope we don't have yet.
        try:
            from app.core.tenant_context import bypass_tenant_filter
            from app.db.session import SessionLocal
            from app.models.user import User
            with bypass_tenant_filter():
                with SessionLocal() as db:
                    user = db.get(User, user_id)
                    if user is None or not user.is_active:
                        return None
                    return user.tenant_id
        except Exception:
            return None

    @staticmethod
    def _extract_token(scope: Scope) -> str | None:
        """Pluck the JWT from the Authorization header or the legacy/__Host-
        access cookie. Returns None when neither is present."""
        headers = dict(scope.get("headers", []))
        # Headers are bytes; standard ASGI header names are lowercased.
        auth_header = headers.get(b"authorization") or headers.get(b"Authorization")
        if auth_header:
            raw = auth_header.decode("latin-1") if isinstance(auth_header, bytes) else str(auth_header)
            if raw.lower().startswith("bearer "):
                return raw[7:].strip() or None
        cookie_header = headers.get(b"cookie") or headers.get(b"Cookie")
        if not cookie_header:
            return None
        raw = cookie_header.decode("latin-1") if isinstance(cookie_header, bytes) else str(cookie_header)
        cookies: dict[str, str] = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies.get("__Host-access_token") or cookies.get("access_token")
