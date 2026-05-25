"""Security-headers middleware coverage.

Verifies the headers emitted by :class:`app.core.security_headers.SecurityHeadersMiddleware`
on the three traffic profiles it knows about:

* Default API (``/api/health``) — full CSP w/ ``frame-ancestors 'none'``,
  ``X-Frame-Options: DENY``, ``Cross-Origin-Resource-Policy: same-site``,
  no HSTS in dev.
* Public marketing renderer (``/site``) — CSP without ``frame-ancestors``,
  ``X-Frame-Options: SAMEORIGIN``.
* Widget script (``/widget.js``) — ``Cross-Origin-Resource-Policy: cross-origin``,
  existing ``Access-Control-Allow-Origin: *`` preserved, no HSTS in dev.
"""
from __future__ import annotations


def test_api_response_includes_security_headers(client):
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    h = r.headers

    csp = h.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp, "default CSP must deny framing"
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp

    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert h.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in h.get("permissions-policy", "")
    assert h.get("cross-origin-opener-policy") == "same-origin"
    assert h.get("cross-origin-resource-policy") == "same-site"


def test_dev_environment_omits_hsts(client):
    """HSTS pins the browser for 2 years — never emit it in development."""
    r = client.get("/api/health")
    assert "strict-transport-security" not in {k.lower() for k in r.headers.keys()}


def test_widget_route_allows_cross_origin(client):
    """The embeddable widget must be loadable from any third-party origin."""
    r = client.get("/widget.js")
    assert r.status_code == 200
    h = r.headers
    assert h.get("cross-origin-resource-policy") == "cross-origin"
    # The route itself sets CORS; middleware must not overwrite it.
    assert h.get("access-control-allow-origin") == "*"
    # HSTS not emitted in dev regardless of the path.
    assert "strict-transport-security" not in {k.lower() for k in h.keys()}


def test_widget_head_request_also_has_headers(client):
    """HEAD must carry the same hardening as GET."""
    r = client.head("/widget.js")
    assert r.status_code == 200
    h = r.headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("cross-origin-resource-policy") == "cross-origin"


def test_marketing_site_relaxes_frame_ancestors(client):
    """``/site/*`` is the public marketing renderer — it must be embeddable
    by the customer's own pages, so ``frame-ancestors`` is dropped and
    ``X-Frame-Options`` is downgraded to SAMEORIGIN."""
    r = client.get("/site/")
    # 200 if the marketing module is on the test plan, 403/404 if gated —
    # either way the middleware response has run.
    h = r.headers
    csp = h.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors" not in csp, (
        f"/site CSP should omit frame-ancestors so the customer can embed; got {csp!r}"
    )
    assert h.get("x-frame-options") == "SAMEORIGIN"


def test_security_headers_do_not_overwrite_existing(client):
    """The widget handler explicitly sets ``Access-Control-Allow-Origin: *``.
    The middleware must respect any header already present on the outgoing
    response and not clobber it."""
    r = client.get("/widget.js")
    assert r.headers.get("access-control-allow-origin") == "*"
    assert r.headers.get("cache-control", "").startswith("public,")


def test_security_headers_on_api_v1_route(client):
    """Pick an authenticated API endpoint to confirm hardening reaches /api/v1/*."""
    r = client.get("/api/v1/license/status")
    # 200 or 401 (depending on whether the test session is authed at module level)
    # — what matters is the headers landed.
    h = r.headers
    assert "default-src 'self'" in h.get("content-security-policy", "")
    assert h.get("x-content-type-options") == "nosniff"
