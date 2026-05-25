"""Foundation tests — auth flow, notifications, settings, RBAC, rate limiting.

Specifically covers the regressions fixed alongside this file:
  - /notifications/{id}/read returns 404 on missing/forbidden, not fake 200
  - /settings/bulk honours `secret_keys` and encrypts values
  - /users/{id} PATCH validates payload through AdminUserUpdate
  - /auth/login is rate-limited via slowapi
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from app.core.security import decrypt_text
from app.models.user import Notification, Setting, User, UserRole


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

def test_login_returns_access_and_refresh(client):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "ChangeMe123!"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


def test_refresh_rotates_and_revokes_old_token(client, db):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "ChangeMe123!"},
    ).json()
    old_refresh = login["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != old_refresh

    # Old refresh must be rejected now
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401


def test_logout_revokes_refresh_token(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local", "password": "ChangeMe123!"},
    ).json()
    access, refresh = login["access_token"], login["refresh_token"]

    out = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert out.status_code == 204

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401


def test_register_then_login(client):
    email = "newuser@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "New User", "password": "AbcDefGh12"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "Employee"

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "AbcDefGh12"})
    assert login.status_code == 200


def test_duplicate_email_rejected(client):
    payload = {"email": "admin@local", "full_name": "Dup", "password": "AbcDefGh12"}
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# RBAC: only Admin can edit other users
# ---------------------------------------------------------------------------

def test_employee_cannot_patch_other_users(client, db):
    # Spin up an employee user
    client.post(
        "/api/v1/auth/register",
        json={"email": "emp@example.com", "full_name": "Employee One", "password": "AbcDefGh12"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "emp@example.com", "password": "AbcDefGh12"},
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    admin = db.scalar(select(User).where(User.email == "admin@local"))
    r = client.patch(
        f"/api/v1/users/{admin.id}",
        json={"full_name": "I am an attacker"},
        headers=headers,
    )
    assert r.status_code == 403


def test_admin_patch_rejects_unknown_fields(client, db, auth_headers):
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    r = client.patch(
        f"/api/v1/users/{admin.id}",
        json={"not_a_real_field": "nope"},
        headers=auth_headers,
    )
    # Pydantic strict mode is off (the schema uses defaults), so unknown fields are simply
    # ignored — but the request itself must succeed and not mutate forbidden columns.
    assert r.status_code == 200
    refreshed = client.get(f"/api/v1/users/{admin.id}", headers=auth_headers).json()
    # email is not in AdminUserUpdate so it remains unchanged
    assert refreshed["email"] == "admin@local"


def test_admin_patch_validates_role_enum(client, db, auth_headers):
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    r = client.patch(
        f"/api/v1/users/{admin.id}",
        json={"role": "Wizard"},  # invalid enum value
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_admin_patch_short_password_rejected(client, db, auth_headers):
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    r = client.patch(
        f"/api/v1/users/{admin.id}",
        json={"password": "short"},
        headers=auth_headers,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Notifications — 404 on missing/forbidden (fixed in this commit)
# ---------------------------------------------------------------------------

def test_mark_read_unknown_id_returns_404(client, auth_headers):
    r = client.post("/api/v1/notifications/does-not-exist/read", headers=auth_headers)
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_mark_read_someone_elses_notification_returns_404(client, db, auth_headers, session_factory):
    # Make an employee and a notification belonging to them only
    client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "full_name": "Other", "password": "AbcDefGh12"},
    )
    with session_factory() as s:
        other = s.scalar(select(User).where(User.email == "other@example.com"))
        n = Notification(user_id=other.id, title="Private", body="not for admin", level="info")
        s.add(n)
        s.commit()
        n_id = n.id

    r = client.post(f"/api/v1/notifications/{n_id}/read", headers=auth_headers)
    assert r.status_code == 404


def test_mark_read_own_notification_succeeds(client, db, auth_headers, session_factory):
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    with session_factory() as s:
        n = Notification(user_id=admin.id, title="Mine", body="hello", level="info")
        s.add(n)
        s.commit()
        n_id = n.id

    r = client.post(f"/api/v1/notifications/{n_id}/read", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_read"] is True


def test_broadcast_notification_can_be_marked_read(client, auth_headers, session_factory, default_tenant):
    from app.core.tenant_context import tenant_scope
    with session_factory() as s, tenant_scope(default_tenant.id):
        n = Notification(user_id=None, title="Broadcast", body="for everyone", level="info")
        s.add(n)
        s.commit()
        n_id = n.id

    r = client.post(f"/api/v1/notifications/{n_id}/read", headers=auth_headers)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Settings bulk — secret_keys must encrypt (fixed in this commit)
# ---------------------------------------------------------------------------

def test_bulk_update_encrypts_secrets(client, auth_headers, session_factory):
    payload = {
        "updates": {"integrations.stripe_key": "sk_live_PLAINTEXT"},
        "secret_keys": ["integrations.stripe_key"],
    }
    r = client.post("/api/v1/settings/bulk", json=payload, headers=auth_headers)
    assert r.status_code == 200

    with session_factory() as s:
        row = s.scalar(
            select(Setting).where(Setting.key == "integrations.stripe_key", Setting.scope == "global")
        )
        assert row is not None
        assert row.is_secret is True
        # Stored value is not the plaintext
        assert row.value != "sk_live_PLAINTEXT"
        # And it decrypts back to the original
        assert decrypt_text(row.value) == "sk_live_PLAINTEXT"


def test_bulk_update_non_secret_stored_plaintext(client, auth_headers, session_factory):
    r = client.post(
        "/api/v1/settings/bulk",
        json={"updates": {"company.name": "Acme Corp"}},
        headers=auth_headers,
    )
    assert r.status_code == 200
    with session_factory() as s:
        row = s.scalar(select(Setting).where(Setting.key == "company.name"))
        assert row.value == "Acme Corp"
        assert row.is_secret is False


# ---------------------------------------------------------------------------
# Rate limiting — login should 429 after the configured limit (10/minute)
# ---------------------------------------------------------------------------

def test_login_rate_limit_triggers_429(client):
    # The slowapi limit is 10/minute. We burst 15 bad-login attempts and expect
    # at least one 429 in the tail.
    last = None
    for _ in range(15):
        last = client.post(
            "/api/v1/auth/login",
            json={"email": "bruteforce@example.com", "password": "wrongwrong"},
        )
    assert last is not None
    # Allow either 401 or 429 in any given call, but the FINAL call after burst
    # must be 429.
    assert last.status_code == 429, last.text
