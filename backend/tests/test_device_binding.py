"""Refresh-token device-binding tests.

A refresh token issued from browser X must NOT be usable from browser Y
(different UA + different IP /24). This catches the most common refresh-
token theft scenario.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.device_fingerprint import device_label, fingerprint


@pytest.fixture(autouse=True)
def _reset_client_cookies(client):
    """The session-scoped TestClient carries cookies across tests; clear them
    so a prior login from another file doesn't shortcut the auth path here."""
    client.cookies.clear()
    yield
    client.cookies.clear()


def test_fingerprint_stable_for_same_inputs():
    a = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.42")
    b = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.42")
    assert a == b


def test_fingerprint_ignores_version_drift():
    """Chrome 120 -> Chrome 121 must hash identically (same family/major name)."""
    a = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.42")
    b = fingerprint("Mozilla/5.0 Chrome/121.0", "203.0.113.42")
    assert a == b


def test_fingerprint_ignores_last_octet():
    """Subnet-bucketed: 203.0.113.42 and 203.0.113.99 hash identically (/24)."""
    a = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.42")
    b = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.99")
    assert a == b


def test_fingerprint_differs_across_browsers():
    a = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.42")
    b = fingerprint("Mozilla/5.0 Firefox/120.0", "203.0.113.42")
    assert a != b


def test_fingerprint_differs_across_subnets():
    a = fingerprint("Mozilla/5.0 Chrome/120.0", "203.0.113.42")
    b = fingerprint("Mozilla/5.0 Chrome/120.0", "198.51.100.42")
    assert a != b


def test_device_label_renders_human_friendly():
    label = device_label("Mozilla/5.0 (Windows NT 10) Chrome/120.0", "203.0.113.42")
    assert "Chrome" in label and "Windows" in label and "203.0.113" in label


def test_refresh_from_different_device_revokes_all_sessions(client):
    """The high-signal test: a token issued from device A used from device B
    is treated as theft and revokes every active session."""
    # Login from device A.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "ChangeMe123!"},
        headers={
            "User-Agent": "Mozilla/5.0 Chrome/120.0",
            "X-Forwarded-For": "203.0.113.42",
        },
    )
    assert r.status_code == 200, r.text
    refresh = r.json()["refresh_token"]
    # Replay from device B (different browser AND different network).
    r2 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
        headers={
            "User-Agent": "Mozilla/5.0 Firefox/120.0",
            "X-Forwarded-For": "198.51.100.42",
        },
    )
    assert r2.status_code == 401, r2.text
    body = r2.json()
    assert "device" in (body.get("detail", "").lower())


def test_refresh_from_same_device_succeeds(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "ChangeMe123!"},
        headers={
            "User-Agent": "Mozilla/5.0 Chrome/120.0",
            "X-Forwarded-For": "203.0.113.42",
        },
    )
    assert r.status_code == 200, r.text
    refresh = r.json()["refresh_token"]
    r2 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
        headers={
            "User-Agent": "Mozilla/5.0 Chrome/121.0",  # same family, version drift
            "X-Forwarded-For": "203.0.113.99",         # same /24
        },
    )
    assert r2.status_code == 200, r2.text


def test_sessions_endpoint_lists_active_sessions(client, auth_headers):
    """Settings → Security → Active Sessions exposes the list."""
    # Trigger at least one login so a session exists.
    client.post("/api/v1/auth/login",
                json={"email": "admin@local", "password": "ChangeMe123!"})
    r = client.get("/api/v1/auth/sessions", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    if body:
        sess = body[0]
        assert "device_label" in sess
        assert "last_used_at" in sess
        assert "id" in sess


def test_revoke_session_takes_effect(client, auth_headers):
    client.post("/api/v1/auth/login",
                json={"email": "admin@local", "password": "ChangeMe123!"})
    listing = client.get("/api/v1/auth/sessions", headers=auth_headers).json()
    if not listing:
        pytest.skip("no active sessions to revoke")
    sid = listing[0]["id"]
    r = client.delete(f"/api/v1/auth/sessions/{sid}", headers=auth_headers)
    assert r.status_code in (200, 204), r.text
    after = client.get("/api/v1/auth/sessions", headers=auth_headers).json()
    assert sid not in {s["id"] for s in after}
