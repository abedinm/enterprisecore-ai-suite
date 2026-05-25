"""Tests for OIDC SSO config + login/callback flow.

We don't talk to a real IdP. Authlib's heavy lifting (signature
verification, JWKS parsing) is exercised by routing the discovery and
JWKS calls through monkeypatch + httpx.MockTransport so the test can
control exactly what the IdP returns.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.sso import TenantSSOConfig
from app.models.user import User
from app.services import sso_oidc


# ---------------------------------------------------------------------------
# RSA key + JWKS fixture — built once for the module.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def rsa_keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwk_priv = JsonWebKey.import_key(pem, {"kty": "RSA", "kid": "test-kid", "alg": "RS256"})
    jwk_pub = jwk_priv.as_dict(is_private=False)
    return jwk_priv, jwk_pub


@pytest.fixture()
def patched_idp(monkeypatch, rsa_keypair):
    """Stub the discovery + JWKS HTTPS calls + token-exchange endpoint."""
    jwk_priv, jwk_pub = rsa_keypair
    sso_oidc.clear_caches()
    issuer = "https://idp.example.test"

    discovery_body = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
    }
    jwks_body = {"keys": [jwk_pub]}

    def _resp(url, body):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=body, request=req)

    def fake_get(url, **kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return _resp(url, discovery_body)
        if url.endswith("/jwks"):
            return _resp(url, jwks_body)
        raise AssertionError(f"unexpected GET to {url}")

    captured: dict[str, Any] = {}

    def fake_post(url, data=None, **kwargs):
        captured["last_token_request"] = data
        # Build an ID token signed by our test key.
        nonce = captured.get("expected_nonce")
        claims = {
            "iss": issuer,
            "aud": data["client_id"],
            "sub": "user-abc",
            "email": captured.get("email", "admin@local"),
            "name": "Admin User",
            "nonce": nonce,
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        }
        jwt = JsonWebToken(["RS256"])
        id_token = jwt.encode({"alg": "RS256", "kid": "test-kid"}, claims, jwk_priv).decode()
        req = httpx.Request("POST", url)
        return httpx.Response(200, json={"id_token": id_token, "access_token": "AT"}, request=req)

    monkeypatch.setattr(sso_oidc.httpx, "get", fake_get)
    monkeypatch.setattr(sso_oidc.httpx, "post", fake_post)
    return {"issuer": issuer, "captured": captured}


def _configure_oidc(client, auth_headers, issuer: str, **overrides):
    payload = {
        "provider_type": "oidc",
        "is_enabled": True,
        "issuer_url": issuer,
        "client_id": "test-client",
        "client_secret": "test-secret",
        "email_attribute": "email",
        "name_attribute": "name",
        "auto_provision_users": False,
    }
    payload.update(overrides)
    r = client.post("/api/v1/sso/config", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------
def test_oidc_config_crud_round_trip(client, auth_headers):
    payload = {
        "provider_type": "oidc", "is_enabled": True,
        "issuer_url": "https://issuer.example", "client_id": "abc",
        "client_secret": "secret-shh",
    }
    r = client.post("/api/v1/sso/config", json=payload, headers=auth_headers)
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["has_client_secret"] is True
    assert "client_secret" not in cfg
    # GET back
    r2 = client.get("/api/v1/sso/config", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["issuer_url"] == "https://issuer.example"


def test_oidc_config_requires_admin(client, make_tenant):
    """Employee role gets 403."""
    from app.core.security import create_access_token
    from app.models.user import UserRole
    tenant, _, _ = make_tenant("oidc-acl-test")
    from sqlalchemy.orm import Session
    from app.db.session import SessionLocal
    from app.core.security import hash_password
    with SessionLocal() as db, tenant_scope(tenant.id):
        u = User(
            email="emp@oidc-acl-test.test",
            full_name="Employee",
            password_hash=hash_password("x" * 12),
            role=UserRole.employee, is_active=True,
        )
        db.add(u); db.commit(); db.refresh(u)
        tok = create_access_token(u.id, u.role.value)
    r = client.post(
        "/api/v1/sso/config",
        json={"provider_type": "oidc", "issuer_url": "https://x", "client_id": "y"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Login redirect
# ---------------------------------------------------------------------------
def test_oidc_login_redirects_to_idp_with_state_nonce(client, auth_headers, patched_idp):
    _configure_oidc(client, auth_headers, patched_idp["issuer"])
    r = client.get(
        "/api/v1/sso/oidc/login?tenant_slug=default",
        follow_redirects=False,
    )
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith(patched_idp["issuer"] + "/authorize")
    assert "state=" in loc
    assert "nonce=" in loc
    # State cookie set
    assert "sso_oidc_state=" in r.headers.get("set-cookie", "")


def test_oidc_login_unknown_tenant_returns_404(client):
    r = client.get(
        "/api/v1/sso/oidc/login?tenant_slug=does-not-exist",
        follow_redirects=False,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------
def _run_callback(client, auth_headers, patched_idp, *, expect_email="admin@local", **cfg_overrides):
    """Drive the full /login → /callback round-trip in one helper."""
    _configure_oidc(client, auth_headers, patched_idp["issuer"], **cfg_overrides)
    r = client.get(
        "/api/v1/sso/oidc/login?tenant_slug=default",
        follow_redirects=False,
    )
    loc = r.headers["location"]
    state = loc.split("state=", 1)[1].split("&", 1)[0]
    nonce = loc.split("nonce=", 1)[1].split("&", 1)[0]
    patched_idp["captured"]["expected_nonce"] = nonce
    patched_idp["captured"]["email"] = expect_email
    state_cookie = r.headers["set-cookie"].split("sso_oidc_state=", 1)[1].split(";", 1)[0]
    r2 = client.get(
        f"/api/v1/sso/oidc/callback?code=fakecode&state={state}",
        cookies={"sso_oidc_state": state_cookie},
        follow_redirects=False,
    )
    return r2


def test_oidc_callback_creates_session_for_known_user(client, auth_headers, patched_idp):
    r = _run_callback(client, auth_headers, patched_idp, expect_email="admin@local")
    assert r.status_code in (200, 302), r.text
    if r.status_code == 200:
        body = r.json()
        assert body["access_token"]
        assert body["user_email"] == "admin@local"


def test_oidc_callback_rejects_state_mismatch(client, auth_headers, patched_idp):
    _configure_oidc(client, auth_headers, patched_idp["issuer"])
    r = client.get(
        "/api/v1/sso/oidc/login?tenant_slug=default", follow_redirects=False,
    )
    state_cookie = r.headers["set-cookie"].split("sso_oidc_state=", 1)[1].split(";", 1)[0]
    # Tamper — send a different state than the one we put in the cookie.
    r2 = client.get(
        "/api/v1/sso/oidc/callback?code=fakecode&state=DIFFERENT_STATE",
        cookies={"sso_oidc_state": state_cookie},
        follow_redirects=False,
    )
    assert r2.status_code == 401


def test_oidc_auto_provision_creates_new_user(client, auth_headers, patched_idp, session_factory):
    """auto_provision_users=True + unknown email → new User row created."""
    r = _run_callback(
        client, auth_headers, patched_idp,
        expect_email="new-sso-user@example.com",
        auto_provision_users=True,
    )
    assert r.status_code in (200, 302), r.text
    with session_factory() as db, bypass_tenant_filter():
        u = db.scalar(select(User).where(User.email == "new-sso-user@example.com"))
        assert u is not None


def test_oidc_auto_provision_off_rejects_unknown(client, auth_headers, patched_idp):
    r = _run_callback(
        client, auth_headers, patched_idp,
        expect_email="stranger@nowhere.invalid",
        auto_provision_users=False,
    )
    assert r.status_code in (401, 403)


def test_oidc_jwks_caching(client, auth_headers, patched_idp, monkeypatch):
    """JWKS is fetched at most once per issuer URL inside the cache TTL."""
    sso_oidc.clear_caches()
    calls = {"get": 0}
    original = sso_oidc.httpx.get

    def counting_get(url, **kw):
        calls["get"] += 1
        return original(url, **kw)

    monkeypatch.setattr(sso_oidc.httpx, "get", counting_get)
    # Drive two consecutive callbacks
    for _ in range(2):
        _run_callback(client, auth_headers, patched_idp, expect_email="admin@local")
    # Discovery + JWKS should each have been called at most once per issuer.
    # We saw 2 callbacks but should see <= 2 GETs total (1 discovery + 1 jwks).
    assert calls["get"] <= 2


def test_oidc_config_preset_google_fills_issuer(client, auth_headers):
    r = client.post(
        "/api/v1/sso/config",
        json={
            "provider_type": "oidc", "preset": "google",
            "client_id": "g-client", "client_secret": "g-secret",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["issuer_url"] == "https://accounts.google.com"
