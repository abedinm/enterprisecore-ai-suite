"""IP allowlist enforcement middleware.

Runs AFTER the tenant middleware (it depends on ``tenant_id_ctx`` being
set). Inspects the active tenant's :class:`TenantSecurityPolicy` and, if
enforcement is on, blocks any request whose source IP is not in any of
the configured CIDR blocks.

Path skip list — these never get blocked, regardless of policy:

* ``/api/health`` — load-balancer health probe.
* ``/metrics`` — Prometheus scrape.
* ``/widget.js`` — embeddable chat widget (served to any visitor).
* ``/site/*`` — public marketing site renderer.
* ``/api/v1/auth/*`` — the customer must be able to log in from
  anywhere, so login itself isn't IP-gated. (MFA + tenant policy
  enforce the rest.)
* ``/scim/v2/*`` — SCIM provisioning from the IdP, typically configured
  with its own allowlist on the IdP side.

X-Forwarded-For: we trust the LEFTMOST entry (the original client). In
production behind a reverse proxy this is the right choice; the proxy
appends its own IP and the leftmost stays the customer's real address.
"""
from __future__ import annotations

import ipaddress
import logging
from typing import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.tenant_context import bypass_tenant_filter, tenant_id_ctx

logger = logging.getLogger(__name__)

# Path prefixes that bypass the allowlist. Match a request path against
# ``startswith`` on each entry.
_BYPASS_PREFIXES = (
    "/api/health",
    "/metrics",
    "/widget.js",
    "/site/",
    "/api/v1/auth/",
    "/scim/v2/",
    "/files/",  # static uploads
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1/webchat/public",  # public webchat endpoints
)


def _extract_client_ip(scope: Scope) -> str | None:
    """Resolve the request's source IP.

    Honors ``X-Forwarded-For`` first (leftmost entry) so deployments
    behind a reverse proxy still get the real client address.
    """
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    xff = headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    client = scope.get("client")
    if client and len(client) >= 1:
        return client[0]
    return None


def _ip_in_cidrs(ip: str, cidrs: Iterable[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            # A malformed CIDR is treated as "doesn't match" — operators
            # see the bad row in the API and the user is denied. We log
            # but don't crash because one bad row shouldn't take the
            # tenant offline.
            logger.warning("Malformed CIDR in tenant allowlist: %r", cidr)
            continue
        if addr in network:
            return True
    return False


class IPAllowlistMiddleware:
    """ASGI middleware that enforces a tenant's IP allowlist."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in _BYPASS_PREFIXES):
            await self.app(scope, receive, send)
            return

        tid = tenant_id_ctx.get()
        if not tid:
            # No tenant context — public/anonymous request. Already
            # covered by the bypass list for the known public paths;
            # anything else without context is the existing auth layer's
            # problem.
            await self.app(scope, receive, send)
            return

        # Look up the tenant policy. Short-lived session, auto-filter
        # bypassed so we can read the policy row by tenant_id directly.
        try:
            from app.db.session import SessionLocal
            from app.models.security_hardening import TenantSecurityPolicy
            from sqlalchemy import select

            with bypass_tenant_filter(), SessionLocal() as db:
                policy = db.scalar(
                    select(TenantSecurityPolicy).where(TenantSecurityPolicy.tenant_id == tid)
                )
        except Exception:
            logger.exception("Failed to load IP allowlist policy")
            policy = None

        if not policy or not policy.ip_allowlist_enforced or not policy.ip_allowlist_cidrs:
            await self.app(scope, receive, send)
            return

        ip = _extract_client_ip(scope)
        if not ip or not _ip_in_cidrs(ip, policy.ip_allowlist_cidrs):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Request source IP is not in the tenant allowlist"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
