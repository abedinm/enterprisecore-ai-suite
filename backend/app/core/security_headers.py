"""Security headers middleware.

Wraps every HTTP response with a defense-in-depth set of headers (CSP, HSTS,
COOP, CORP, Permissions-Policy, X-Frame-Options, X-Content-Type-Options,
Referrer-Policy). Configured as a pure ASGI middleware so it composes
cleanly after the CORS middleware: CORS runs first (and can emit its own
preflight response), this middleware then layers safety headers on the
outgoing message.

Path-aware exceptions:

* ``/site/*`` (public marketing renderer): drop ``frame-ancestors 'none'`` from
  the CSP and downgrade ``X-Frame-Options`` to ``SAMEORIGIN`` so the customer
  can embed their own marketing site if they choose.
* ``/widget.js`` (embeddable chat widget): use ``Cross-Origin-Resource-Policy:
  cross-origin`` and skip HSTS — third-party sites need to load the asset
  cross-origin. The existing ``Access-Control-Allow-Origin: *`` header set on
  the handler is preserved (this middleware never overwrites an existing
  header it would otherwise set).

HSTS is only emitted in production. In dev / staging we keep the response
permissive so localhost flows aren't broken by a stale HSTS pin.

CSP nonces
----------

For every request a 16-byte cryptographic random nonce is generated and
base64-encoded. The nonce is placed on ``scope["state"]["csp_nonce"]`` (which
Starlette surfaces as ``request.state.csp_nonce``) so Jinja2 templates that
render HTML directly (e.g. ``/site/*``) can emit
``<script nonce="{{ csp_nonce }}">`` and survive the strict CSP. The same
nonce is folded into the ``script-src`` directive of the outgoing
``Content-Security-Policy`` header. Style nonces are left out because
Tailwind's runtime injection of inline ``<style>`` blocks requires
``'unsafe-inline'`` for now — folding that into a future commit is tracked in
``docs/SECURITY_HARDENING.md``.
"""
from __future__ import annotations

import base64
import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# ---------------------------------------------------------------------------
# Header values
# ---------------------------------------------------------------------------
# Template for the static portion of the CSP. The ``script-src`` directive is
# rendered per-request with the nonce filled in so inline scripts emitted by
# server-rendered templates can opt into execution without re-enabling
# ``'unsafe-inline'`` globally.
def _csp_for(nonce: str, *, with_frame_ancestors: bool) -> str:
    """Render the Content-Security-Policy for a given per-request nonce."""
    parts = [
        "default-src 'self'",
        "img-src 'self' data: blob:",
        # style-src keeps 'unsafe-inline' for Tailwind compatibility — see
        # docs/SECURITY_HARDENING.md for the migration plan to nonce'd styles.
        "style-src 'self' 'unsafe-inline'",
        f"script-src 'self' 'nonce-{nonce}'",
        "font-src 'self' data:",
        "connect-src 'self' ws: wss:",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
    if with_frame_ancestors:
        parts.append("frame-ancestors 'none'")
    return "; ".join(parts)


def _new_nonce() -> str:
    """16 bytes of cryptographic random, base64-encoded (no padding stripped)."""
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")

_HSTS = "max-age=63072000; includeSubDomains; preload"
_PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)


def _is_marketing_site_path(path: str) -> bool:
    """True for the public marketing renderer (mounted at /site)."""
    return path == "/site" or path.startswith("/site/")


def _is_widget_path(path: str) -> bool:
    """True for the embeddable chat widget static asset."""
    return path == "/widget.js"


def _is_public_webchat_path(path: str) -> bool:
    """True for cross-origin webchat endpoints (kept permissive)."""
    return path.startswith("/api/v1/webchat/chat/") or path.startswith(
        "/api/v1/webchat/bots/public/"
    )


def _headers_for(path: str, nonce: str) -> dict[str, str]:
    """Compute the static security headers for a request path."""
    on_site = _is_marketing_site_path(path)
    on_widget = _is_widget_path(path)
    on_public_chat = _is_public_webchat_path(path)

    headers: dict[str, str] = {
        "Content-Security-Policy": _csp_for(
            nonce, with_frame_ancestors=not on_site
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN" if on_site else "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": _PERMISSIONS_POLICY,
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": (
            "cross-origin" if (on_widget or on_public_chat) else "same-site"
        ),
    }

    # HSTS only in production — localhost dev would otherwise pin HSTS on
    # the test client's URL bar for two years.
    if settings.app_env == "production" and not on_widget:
        headers["Strict-Transport-Security"] = _HSTS

    return headers


class SecurityHeadersMiddleware:
    """Pure ASGI middleware: layer security headers onto outgoing responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "") or ""
        nonce = _new_nonce()
        # Surface the nonce via scope["state"] so it reaches the FastAPI
        # request.state. Starlette merges scope["state"] into the State
        # object on first access — see starlette.requests.HTTPConnection.state.
        state = scope.setdefault("state", {})
        state["csp_nonce"] = nonce
        extra = _headers_for(path, nonce)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # ``headers`` is a list of (b"name", b"value") tuples. Build a
                # lowercase-name set so we don't clobber a header the route
                # explicitly set (e.g. Access-Control-Allow-Origin on /widget.js).
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers") or [])
                existing = {name.decode("latin-1").lower() for name, _ in raw_headers}
                for header_name, header_value in extra.items():
                    if header_name.lower() in existing:
                        continue
                    raw_headers.append(
                        (header_name.encode("latin-1"), header_value.encode("latin-1"))
                    )
                message["headers"] = raw_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


__all__ = ["SecurityHeadersMiddleware"]
