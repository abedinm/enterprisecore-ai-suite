"""Coverage for the per-request CSP nonce.

The ``SecurityHeadersMiddleware`` generates a fresh nonce on every request,
folds it into the ``Content-Security-Policy`` header's ``script-src``
directive, and stashes the raw nonce on ``request.state.csp_nonce`` so
server-rendered templates (e.g. ``/site/*``) can emit
``<script nonce="{{ csp_nonce }}">`` and survive the strict CSP.

What this module verifies:

* Every response has a ``script-src 'self' 'nonce-...'`` directive.
* The nonce changes on each request (no static value baked into the
  middleware).
* ``'unsafe-inline'`` is **not** present on ``script-src`` (the nonce
  replaces the need for it).
* The nonce reaches ``request.state.csp_nonce`` from a route's perspective.
* The ``/site/*`` path keeps the nonce and still omits ``frame-ancestors``.
* The nonce is base64-decodable and at least 16 bytes of entropy.
"""
from __future__ import annotations

import base64
import re


_NONCE_RE = re.compile(r"'nonce-([A-Za-z0-9+/=]+)'")


def _extract_nonce(csp: str) -> str:
    m = _NONCE_RE.search(csp)
    assert m, f"CSP missing nonce directive: {csp!r}"
    return m.group(1)


def test_csp_contains_script_src_nonce(client):
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    csp = r.headers.get("content-security-policy", "")
    assert "script-src 'self' 'nonce-" in csp, csp
    # 'unsafe-inline' must not be present on script-src — the nonce replaces
    # the need for it. (style-src may still carry it for Tailwind.)
    script_src = next(
        (d for d in csp.split(";") if d.strip().startswith("script-src")),
        "",
    )
    assert "'unsafe-inline'" not in script_src, script_src


def test_csp_nonce_changes_per_request(client):
    r1 = client.get("/api/health")
    r2 = client.get("/api/health")
    n1 = _extract_nonce(r1.headers.get("content-security-policy", ""))
    n2 = _extract_nonce(r2.headers.get("content-security-policy", ""))
    assert n1 != n2, "nonce must rotate per request"


def test_csp_nonce_is_high_entropy_base64(client):
    r = client.get("/api/health")
    nonce = _extract_nonce(r.headers.get("content-security-policy", ""))
    # Base64 of 16 bytes is 24 chars with padding. Allow any length >= 16
    # to leave headroom for future expansion.
    assert len(nonce) >= 16, nonce
    decoded = base64.b64decode(nonce + "==", validate=False)
    assert len(decoded) >= 16


def test_csp_nonce_reaches_request_state(client):
    """A handler that introspects request.state.csp_nonce sees the same
    value the middleware put into the CSP header."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from app.main import app

    async def _probe(request: Request) -> JSONResponse:
        return JSONResponse(
            {"nonce": getattr(request.state, "csp_nonce", "")}
        )

    route = Route("/__test_csp_nonce__", _probe, methods=["GET"])
    app.router.routes.append(route)
    try:
        r = client.get("/__test_csp_nonce__")
        assert r.status_code == 200, r.text
        body_nonce = r.json()["nonce"]
        header_nonce = _extract_nonce(
            r.headers.get("content-security-policy", "")
        )
        assert body_nonce, "request.state.csp_nonce not populated"
        assert body_nonce == header_nonce, (
            f"state nonce {body_nonce!r} != header nonce {header_nonce!r}"
        )
    finally:
        app.router.routes.remove(route)


def test_csp_nonce_on_site_path_keeps_no_frame_ancestors(client):
    r = client.get("/site/")
    csp = r.headers.get("content-security-policy", "")
    assert "script-src 'self' 'nonce-" in csp, csp
    assert "frame-ancestors" not in csp, (
        "/site CSP must still omit frame-ancestors so customers can embed"
    )
