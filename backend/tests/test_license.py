"""License-key validation tests.

The /api/v1/license/status endpoint now returns a wrapped envelope:
``{"remote": {...}, "legacy": {...}, "configured_key_preview": "...",
"license_api_url": "..."}``. The ``legacy`` key holds the offline HMAC
status (the original local check); ``remote`` holds the license-server
verification result. These tests cover the legacy/offline behaviour —
the remote layer is exercised separately and gracefully falls back to
``offline`` when no license server is reachable (which is the case in CI).
"""
from __future__ import annotations

from app.core.license_key import make_demo_key


def _legacy(body: dict) -> dict:
    """Pluck the legacy (offline HMAC) status out of the wrapped envelope."""
    assert "legacy" in body, f"missing 'legacy' key in license status envelope: {body}"
    return body["legacy"]


def test_empty_key_returns_evaluation(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.license_key", "")
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    legacy = _legacy(r.json())
    assert legacy["valid"] is False
    assert legacy["state"] == "evaluation"


def test_malformed_key_marked_invalid(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.license_key", "not-a-license")
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    legacy = _legacy(r.json())
    assert legacy["valid"] is False
    assert legacy["state"] == "invalid"


def test_signed_key_marked_active(client, auth_headers, monkeypatch):
    """A key signed by the local issuer (make_demo_key) verifies cleanly."""
    key = make_demo_key("Acme Corp", plan="enterprise", days=180)
    monkeypatch.setattr("app.core.config.settings.license_key", key)
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    legacy = _legacy(r.json())
    assert legacy["state"] == "active", legacy
    assert legacy["valid"] is True
    assert legacy["customer"] == "Acme Corp"
    assert legacy["plan"] == "enterprise"
    assert legacy["days_remaining"] is not None
    assert 170 <= legacy["days_remaining"] <= 180


def test_expired_key_rejected(client, auth_headers, monkeypatch):
    key = make_demo_key("Old Customer", days=-30)
    monkeypatch.setattr("app.core.config.settings.license_key", key)
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    legacy = _legacy(r.json())
    assert legacy["state"] == "expired"
    assert legacy["valid"] is False
    assert legacy["days_remaining"] < 0


def test_status_requires_authentication(client):
    # Clear any cookies left over from prior tests' login (TestClient persists
    # the access_token cookie across the session-scoped client fixture).
    client.cookies.clear()
    r = client.get("/api/v1/license/status")
    assert r.status_code == 401


def test_status_envelope_includes_remote_and_key_preview(client, auth_headers, monkeypatch):
    """The status envelope shape itself: remote, legacy, configured_key_preview, license_api_url."""
    monkeypatch.setattr("app.core.config.settings.license_key", "EC-AAAA-BBBB-CCCC-DDDD")
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert {"remote", "legacy", "configured_key_preview", "license_api_url"} <= set(body.keys())
    # The key preview should redact the middle of the key.
    assert body["configured_key_preview"].startswith("EC-A")
    assert body["configured_key_preview"].endswith("DDDD")
