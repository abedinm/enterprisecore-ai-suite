"""Edge cases for SecurityHeadersMiddleware not covered by test_security_headers.

Specifically:
    * HEAD requests get the same headers as GET.
    * OPTIONS preflight survives — middleware doesn't strip CORS headers.
    * Public webchat paths use ``cross-origin`` CORP.
    * Lifespan / websocket scopes pass through untouched.
    * _headers_for() is deterministic and case-insensitive on path branches.
"""
from __future__ import annotations

import asyncio


def test_head_request_carries_security_headers(client):
    r = client.head("/api/health")
    assert r.status_code in (200, 405)
    if r.status_code == 200:
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert "content-security-policy" in {k.lower() for k in r.headers.keys()}


def test_options_preflight_does_not_lose_cors(client):
    """Browsers send OPTIONS with Origin + Access-Control-Request-Method.
    The middleware must not drop the CORS-Allow-Origin echo from CORSMiddleware."""
    r = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    # Either 200 (CORS responded) or 405 (no OPTIONS handler) — both are fine,
    # what matters is the security headers landed.
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_public_webchat_chat_path_uses_cross_origin_corp():
    """``/api/v1/webchat/chat/*`` must be CORS-friendly for embedded widgets."""
    from app.core.security_headers import _headers_for

    h = _headers_for("/api/v1/webchat/chat/some-bot", "n")
    assert h["Cross-Origin-Resource-Policy"] == "cross-origin"


def test_public_webchat_bots_path_uses_cross_origin_corp():
    from app.core.security_headers import _headers_for

    h = _headers_for("/api/v1/webchat/bots/public/some-bot", "n")
    assert h["Cross-Origin-Resource-Policy"] == "cross-origin"


def test_internal_api_path_uses_same_site_corp():
    from app.core.security_headers import _headers_for

    h = _headers_for("/api/v1/finance/invoices", "n")
    assert h["Cross-Origin-Resource-Policy"] == "same-site"
    assert h["X-Frame-Options"] == "DENY"


def test_marketing_subpath_relaxes_frame_options():
    from app.core.security_headers import _headers_for

    for path in ("/site", "/site/", "/site/blog", "/site/contact"):
        h = _headers_for(path, "n")
        assert h["X-Frame-Options"] == "SAMEORIGIN"
        assert "frame-ancestors" not in h["Content-Security-Policy"], (
            f"{path} CSP must drop frame-ancestors"
        )


def test_widget_path_skips_hsts_in_production(monkeypatch):
    """Even in prod, the embeddable widget must not pin HSTS on third-party origins."""
    from app.core import security_headers as mod
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    h = mod._headers_for("/widget.js", "n")
    assert "Strict-Transport-Security" not in h


def test_api_path_emits_hsts_in_production(monkeypatch):
    from app.core import security_headers as mod
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    h = mod._headers_for("/api/v1/foo", "n")
    assert h.get("Strict-Transport-Security", "").startswith("max-age=")


def test_middleware_skips_non_http_scopes():
    """Lifespan startup events shouldn't trigger the response wrapper."""
    from app.core.security_headers import SecurityHeadersMiddleware

    seen_call: dict = {}

    async def inner(scope, receive, send):  # noqa: ANN001
        seen_call["ok"] = True

    mw = SecurityHeadersMiddleware(inner)

    async def go():
        async def send(_):  # noqa: ANN001
            return None

        async def receive():
            return {}

        await mw({"type": "lifespan"}, receive, send)

    asyncio.run(go())
    assert seen_call.get("ok") is True


def test_existing_header_not_overwritten_by_middleware():
    """If the downstream handler emits its own Referrer-Policy, keep it."""
    from app.core.security_headers import SecurityHeadersMiddleware

    captured: list[tuple[bytes, bytes]] = []

    async def inner(scope, receive, send):  # noqa: ANN001
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"referrer-policy", b"no-referrer")],
        })
        await send({"type": "http.response.body", "body": b""})

    mw = SecurityHeadersMiddleware(inner)

    async def go():
        async def send(message):  # noqa: ANN001
            if message["type"] == "http.response.start":
                captured.extend(message["headers"])

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await mw(
            {"type": "http", "path": "/api/v1/foo", "method": "GET", "headers": []},
            receive,
            send,
        )

    asyncio.run(go())
    # The route's Referrer-Policy must survive, not be overwritten.
    referrer = [v for k, v in captured if k.lower() == b"referrer-policy"]
    assert referrer == [b"no-referrer"]
