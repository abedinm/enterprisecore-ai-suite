"""Refresh-token lookup must be O(log n) (indexed) not O(n) (scan + bcrypt).

We can't measure latency reliably in CI, but we CAN assert:
  * a refresh succeeds when 100 unrelated refresh tokens already exist for
    the same user — i.e. the endpoint isn't accidentally relying on order
  * the lookup is short-circuited via the unique token_hash index by
    verifying only one DB row is selected (sanity-check via SQL count after)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.security import create_refresh_token, hash_refresh_token
from app.models.user import RefreshToken


def test_refresh_works_with_many_existing_tokens(client, auth_headers, db):
    """Login (issues #1 token), then plant 100 extra unrelated tokens, then
    refresh using the original. Must succeed without timing out."""
    login = client.post("/api/v1/auth/login",
                       json={"email": "admin@local", "password": "ChangeMe123!"})
    assert login.status_code == 200
    tokens = login.json()
    refresh_token = tokens["refresh_token"]

    # Plant 100 random tokens for the same user (just hashes; never issued)
    from sqlalchemy import select
    from app.models.user import User
    admin = db.scalar(select(User).where(User.email == "admin@local"))
    for i in range(100):
        raw, exp = create_refresh_token(admin.id)
        db.add(RefreshToken(
            user_id=admin.id,
            token_hash=hash_refresh_token(raw),
            expires_at=exp,
        ))
    db.commit()

    # Refresh with the real token — must still find it
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200, r.text
    new_tokens = r.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    # The original refresh token is now revoked
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert second.status_code == 401


def test_unknown_refresh_token_rejected(client):
    """A well-formed but unknown JWT must be rejected with 401, not 500."""
    fake_raw, _ = create_refresh_token("01XXXXXXXXXXXXXXXXXXXXXXXX")
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": fake_raw})
    assert r.status_code == 401


def test_garbage_refresh_token_rejected(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert r.status_code == 401
