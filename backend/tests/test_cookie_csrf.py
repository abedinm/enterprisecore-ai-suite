"""HTTP-only cookie auth + CSRF double-submit tests.

NOTE: ``client`` is session-scoped (see conftest.py), so its cookie jar
persists across tests. The autouse ``_reset_client_cookies`` fixture below
clears the jar before each test so a prior ``/auth/login`` from another
file doesn't poison results.

Three contracts to defend:

1. Successful ``/auth/login`` sets ``access_token`` + ``refresh_token`` cookies
   with httpOnly + SameSite, AND mints a readable ``csrf_token`` cookie.
2. ``/auth/refresh`` can be called with NO body when the refresh cookie is
   present, and rotates both auth cookies + the CSRF cookie.
3. Mutating requests authenticated by COOKIE must present the CSRF header;
   Bearer-authenticated requests bypass CSRF (they're immune by design).

CSRF middleware enforcement is exercised by spinning up a fresh app with
``ENTERPRISECORE_DISABLE_CSRF`` cleared. The default test client runs with
CSRF disabled so the legacy Bearer-token suite stays green.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Default-test-client (CSRF disabled) — cookie smoke tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_client_cookies(client):
    """Wipe the TestClient cookie jar before each test.

    The session-scoped client persists cookies across tests; without this
    reset, a prior login's ``access_token`` / ``refresh_token`` cookie may
    short-circuit the call we're trying to verify here.
    """
    client.cookies.clear()
    yield
    client.cookies.clear()


def test_login_sets_auth_and_csrf_cookies(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@local", "password": "ChangeMe123!"})
    assert r.status_code == 200, r.text
    cookie_keys = {k.lower() for k in r.cookies.keys()}
    # Either the legacy or __Host- prefixed name should be present.
    assert any(k.endswith("access_token") for k in cookie_keys), cookie_keys
    assert any(k.endswith("refresh_token") for k in cookie_keys), cookie_keys
    assert "csrf_token" in cookie_keys, cookie_keys
    # CSRF cookie MUST be readable (not httpOnly) so the SPA can echo it.
    # FastAPI TestClient exposes Set-Cookie headers raw via .headers
    set_cookies = [v for k, v in r.headers.raw if k.lower() == b"set-cookie"]
    csrf_line = next((sc for sc in set_cookies if sc.lower().startswith(b"csrf_token=")), None)
    assert csrf_line is not None
    assert b"httponly" not in csrf_line.lower(), csrf_line
    # Auth cookies MUST be httpOnly.
    access_line = next((sc for sc in set_cookies if b"access_token=" in sc.lower()), None)
    assert access_line is not None and b"httponly" in access_line.lower(), access_line


def test_refresh_works_with_cookie_only_no_body(client):
    # Login to seed cookies on the client jar.
    login = client.post("/api/v1/auth/login",
                        json={"email": "admin@local", "password": "ChangeMe123!"})
    assert login.status_code == 200
    # Refresh with NO body — the refresh cookie should carry the token.
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and "refresh_token" in body
    # New CSRF cookie should be issued on every successful refresh.
    set_cookies = [v for k, v in r.headers.raw if k.lower() == b"set-cookie"]
    assert any(b"csrf_token=" in sc.lower() for sc in set_cookies)


def test_logout_clears_cookies(client):
    client.post("/api/v1/auth/login",
                json={"email": "admin@local", "password": "ChangeMe123!"})
    r = client.post("/api/v1/auth/logout")
    assert r.status_code in (200, 204)
    set_cookies = [v.lower() for k, v in r.headers.raw if k.lower() == b"set-cookie"]
    # Delete-cookie sends max-age=0 / expires in the past.
    assert any(b"access_token=" in sc and (b"max-age=0" in sc or b"1970" in sc)
               for sc in set_cookies), set_cookies


# ---------------------------------------------------------------------------
# CSRF enforcement — uses a private TestClient with the middleware ENABLED.
# ---------------------------------------------------------------------------

@pytest.fixture()
def csrf_client(session_factory):
    """Fresh TestClient with the CSRF middleware ENABLED.

    We monkey-patch the middleware's ``enabled`` flag instead of rebuilding
    the FastAPI app (which would re-run startup hooks and cost ~3s per
    test). The previous value is restored on teardown.
    """
    from app.api.deps import get_db
    from app.core.csrf import CSRFMiddleware
    from app.main import app

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    # Flip the middleware on. Starlette wraps middleware as a chain;
    # we walk it and flip the .enabled attribute on the CSRFMiddleware frame.
    flipped = []
    mw = app.middleware_stack
    while mw is not None:
        inner = getattr(mw, "app", None)
        if isinstance(inner, CSRFMiddleware):
            flipped.append((inner, inner.enabled))
            inner.enabled = True
        mw = inner if hasattr(mw, "app") else None
    try:
        with TestClient(app) as c:
            yield c
    finally:
        for inner, prev in flipped:
            inner.enabled = prev
        app.dependency_overrides.clear()


def test_csrf_blocks_mutation_without_header(csrf_client):
    login = csrf_client.post("/api/v1/auth/login",
                              json={"email": "admin@local", "password": "ChangeMe123!"})
    assert login.status_code == 200
    # Mutating call WITHOUT the X-CSRF-Token header — should be 403.
    # We deliberately don't send the Bearer header either; the client jar
    # carries the access cookie, so this is a cookie-authenticated call.
    r = csrf_client.post("/api/v1/finance/customers",
                          json={"name": "csrf-test", "email": "csrf@test.io", "currency": "USD"})
    # The CSRF middleware should short-circuit before the endpoint runs.
    assert r.status_code == 403, r.text
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("code") == "csrf_failed", body


def test_csrf_passes_with_matching_header(csrf_client):
    login = csrf_client.post("/api/v1/auth/login",
                              json={"email": "admin@local", "password": "ChangeMe123!"})
    assert login.status_code == 200
    csrf = csrf_client.cookies.get("csrf_token")
    assert csrf, "login should mint csrf_token"
    r = csrf_client.post(
        "/api/v1/finance/customers",
        json={"name": "csrf-ok", "email": "csrf-ok@test.io", "currency": "USD"},
        headers={"X-CSRF-Token": csrf},
    )
    # Either 200/201 (created) or 422 if our schema differs — what we MUST not
    # see is the 403 csrf_failed code.
    assert r.status_code != 403 or r.json().get("code") != "csrf_failed", r.text


def test_csrf_bypass_for_bearer_authenticated_requests(csrf_client, admin_token):
    """Bearer-token (API/SDK) clients can never be tricked into mounting a
    CSRF attack — there's no automatic header injection like the cookie. So
    the middleware exempts them entirely."""
    r = csrf_client.post(
        "/api/v1/finance/customers",
        json={"name": "bearer-ok", "email": "bearer-ok@test.io", "currency": "USD"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code != 403 or r.json().get("code") != "csrf_failed", r.text


def test_csrf_exempts_login_and_refresh(csrf_client):
    """Login + refresh are pre-session — there's no token to compare against
    yet. Middleware must let them through."""
    r1 = csrf_client.post("/api/v1/auth/login",
                          json={"email": "admin@local", "password": "ChangeMe123!"})
    assert r1.status_code == 200, r1.text
    r2 = csrf_client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200, r2.text
