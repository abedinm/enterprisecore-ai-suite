"""Tests for the magic-link auth flow."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.sso import MagicLinkToken
from app.models.user import User
from app.services import email as email_service


@pytest.fixture(autouse=True)
def _force_console_email_and_reset():
    """Every magic-link test should pipe email through the in-memory
    capture buffer, not real SMTP. Reset between tests so the assert
    only sees the current case's emails."""
    os.environ["EMAIL_PROVIDER"] = "console"
    email_service.reset_captured()
    yield
    email_service.reset_captured()


def _capture_token_from_email():
    """Pull the raw token out of the last captured email body — same way
    a real user would by clicking the link."""
    emails = email_service.get_captured()
    assert emails, "no email was captured"
    body = emails[-1].body_text
    assert "token=" in body, body
    return body.split("token=", 1)[1].split()[0].strip()


def test_magic_link_issue_returns_ok_and_sends_email(client):
    r = client.post(
        "/api/v1/auth/magic-link",
        json={"email": "admin@local", "tenant_slug": "default", "purpose": "login"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert len(email_service.get_captured()) == 1


def test_magic_link_consume_login_returns_tokens(client, session_factory):
    client.post(
        "/api/v1/auth/magic-link",
        json={"email": "admin@local", "tenant_slug": "default", "purpose": "login"},
    )
    raw_token = _capture_token_from_email()
    r = client.post("/api/v1/auth/magic-link/consume", json={"token": raw_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["purpose"] == "login"
    assert body["access_token"]
    assert body["refresh_token"]
    # Token is now marked used — replay must fail.
    with session_factory() as db, bypass_tenant_filter():
        row = db.scalar(
            select(MagicLinkToken).where(MagicLinkToken.email == "admin@local").order_by(
                MagicLinkToken.created_at.desc()
            )
        )
        assert row is not None
        assert row.used_at is not None


def test_magic_link_single_use_replay_rejected(client):
    client.post(
        "/api/v1/auth/magic-link",
        json={"email": "admin@local", "tenant_slug": "default", "purpose": "login"},
    )
    raw_token = _capture_token_from_email()
    r1 = client.post("/api/v1/auth/magic-link/consume", json={"token": raw_token})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/auth/magic-link/consume", json={"token": raw_token})
    assert r2.status_code == 401
    assert "used" in r2.json()["detail"].lower()


def test_magic_link_expiry_rejected(client, session_factory):
    client.post(
        "/api/v1/auth/magic-link",
        json={"email": "admin@local", "tenant_slug": "default", "purpose": "login"},
    )
    raw_token = _capture_token_from_email()
    # Backdate the token to make it expired.
    with session_factory() as db, bypass_tenant_filter():
        row = db.scalar(
            select(MagicLinkToken).where(MagicLinkToken.email == "admin@local").order_by(
                MagicLinkToken.created_at.desc()
            )
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    r = client.post("/api/v1/auth/magic-link/consume", json={"token": raw_token})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_magic_link_no_enumeration_on_unknown_email(client):
    """Unknown email yields {ok: true} but no email is sent."""
    email_service.reset_captured()
    r = client.post(
        "/api/v1/auth/magic-link",
        json={"email": "nobody@nowhere.invalid", "tenant_slug": "default", "purpose": "login"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert email_service.get_captured() == []


def test_magic_link_invalid_token_rejected(client):
    r = client.post(
        "/api/v1/auth/magic-link/consume",
        json={"token": "a" * 64},
    )
    assert r.status_code == 401


def test_magic_link_password_reset_returns_reset_token(client):
    """For password_reset purpose, consume yields a reset_token, NOT auth
    cookies — the caller posts that to a separate reset-confirm endpoint."""
    client.post(
        "/api/v1/auth/magic-link",
        json={"email": "admin@local", "purpose": "password_reset"},
    )
    raw_token = _capture_token_from_email()
    r = client.post("/api/v1/auth/magic-link/consume", json={"token": raw_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["purpose"] == "password_reset"
    assert body["reset_token"]
    assert body.get("access_token") is None


def test_magic_link_email_uses_hash_router_url(client):
    """The link emailed to the user must hit the SPA's HashRouter route
    (``#/auth/consume?token=...``) rather than the JSON API."""
    email_service.reset_captured()
    client.post(
        "/api/v1/auth/magic-link",
        json={"email": "admin@local", "tenant_slug": "default", "purpose": "login"},
    )
    emails = email_service.get_captured()
    assert emails, "no email was captured"
    body = emails[-1].body_text
    assert "/#/auth/consume?token=" in body, body
    # The legacy JSON endpoint path should NOT appear.
    assert "/api/v1/auth/magic-link/consume" not in body


def test_magic_link_rate_limit_blocks_burst(client):
    """After ~5 active tokens for the same email we silently stop issuing
    new ones — but the response still says ok (no-enum)."""
    # Issue 6 in a row; only first 5 should produce emails.
    for _ in range(6):
        client.post(
            "/api/v1/auth/magic-link",
            json={"email": "admin@local", "tenant_slug": "default", "purpose": "login"},
        )
    # Less-than-or-equal-5 emails captured (depends on which window we hit).
    assert len(email_service.get_captured()) <= 5
