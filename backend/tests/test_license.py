"""License-key validation tests."""
from __future__ import annotations

from app.core.license_key import make_demo_key, verify_license


def test_empty_key_returns_evaluation(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.license_key", "")
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["state"] == "evaluation"


def test_malformed_key_marked_invalid(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.license_key", "not-a-license")
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["state"] == "invalid"


def test_signed_key_marked_active(client, auth_headers, monkeypatch):
    """A key signed by the local issuer (make_demo_key) verifies cleanly."""
    key = make_demo_key("Acme Corp", plan="enterprise", days=180)
    monkeypatch.setattr("app.core.config.settings.license_key", key)
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "active", body
    assert body["valid"] is True
    assert body["customer"] == "Acme Corp"
    assert body["plan"] == "enterprise"
    assert body["days_remaining"] is not None
    assert 170 <= body["days_remaining"] <= 180


def test_expired_key_rejected(client, auth_headers, monkeypatch):
    key = make_demo_key("Old Customer", days=-30)
    monkeypatch.setattr("app.core.config.settings.license_key", key)
    r = client.get("/api/v1/license/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "expired"
    assert body["valid"] is False
    assert body["days_remaining"] < 0


def test_status_requires_authentication(client):
    r = client.get("/api/v1/license/status")
    assert r.status_code == 401
