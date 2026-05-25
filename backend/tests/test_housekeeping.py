"""Housekeeping job tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.ai import AiUsageRecord
from app.models.security import LoginAttempt
from app.models.user import RefreshToken
from app.services.housekeeping import (
    cleanup_ai_usage,
    cleanup_login_attempts,
    cleanup_refresh_tokens,
    run_all,
)


def _admin_id(db) -> str:
    from sqlalchemy import select
    from app.models.user import User
    return db.scalar(select(User).where(User.email == "admin@local")).id


def test_cleanup_refresh_tokens_removes_expired(db):
    admin_id = _admin_id(db)
    now = datetime.now(timezone.utc)
    # 1 valid (future expiry) — must survive
    db.add(RefreshToken(user_id=admin_id, token_hash="valid-" + str(now.timestamp()),
                        expires_at=now + timedelta(days=1)))
    # 1 expired — must go
    db.add(RefreshToken(user_id=admin_id, token_hash="expired-" + str(now.timestamp()),
                        expires_at=now - timedelta(days=1)))
    # 1 revoked recently — must survive (within 90-day grace)
    db.add(RefreshToken(user_id=admin_id, token_hash="recent-revoked-" + str(now.timestamp()),
                        expires_at=now + timedelta(days=30),
                        revoked_at=now - timedelta(days=5)))
    # 1 revoked long ago — must go
    db.add(RefreshToken(user_id=admin_id, token_hash="old-revoked-" + str(now.timestamp()),
                        expires_at=now + timedelta(days=30),
                        revoked_at=now - timedelta(days=120)))
    db.commit()

    removed = cleanup_refresh_tokens()
    assert removed >= 2  # at least the two stale rows

    from sqlalchemy import select
    surviving = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == admin_id)
    ).all()
    hashes = [t.token_hash for t in surviving]
    assert any(h.startswith("valid-") for h in hashes)
    assert any(h.startswith("recent-revoked-") for h in hashes)
    assert not any(h.startswith("expired-") for h in hashes)
    assert not any(h.startswith("old-revoked-") for h in hashes)


def test_cleanup_login_attempts_drops_old(db):
    now = datetime.now(timezone.utc)
    db.add(LoginAttempt(email="recent@x.test", success=True, created_at=now - timedelta(days=10)))
    db.add(LoginAttempt(email="ancient@x.test", success=False, created_at=now - timedelta(days=200)))
    db.commit()

    removed = cleanup_login_attempts()
    assert removed >= 1

    from sqlalchemy import select
    survivors = db.scalars(select(LoginAttempt).where(LoginAttempt.email.in_(
        ("recent@x.test", "ancient@x.test")
    ))).all()
    assert any(s.email == "recent@x.test" for s in survivors)
    assert not any(s.email == "ancient@x.test" for s in survivors)


def test_cleanup_ai_usage_drops_old(db):
    admin_id = _admin_id(db)
    now = datetime.now(timezone.utc)
    db.add(AiUsageRecord(user_id=admin_id, provider="anthropic", model="x",
                         feature="recent", tokens_in=1, tokens_out=1,
                         cost_usd=Decimal("0.01"), latency_ms=10, success=True,
                         occurred_at=now - timedelta(days=10)))
    db.add(AiUsageRecord(user_id=admin_id, provider="anthropic", model="x",
                         feature="ancient", tokens_in=1, tokens_out=1,
                         cost_usd=Decimal("0.01"), latency_ms=10, success=True,
                         occurred_at=now - timedelta(days=180)))
    db.commit()

    removed = cleanup_ai_usage()
    assert removed >= 1

    from sqlalchemy import select
    survivors = db.scalars(select(AiUsageRecord).where(AiUsageRecord.feature.in_(
        ("recent", "ancient")
    ))).all()
    features = [s.feature for s in survivors]
    assert "recent" in features
    assert "ancient" not in features


def test_run_all_returns_counts(db):
    out = run_all()
    # Phase-7 billing added the ``trials_expired`` job. Anchor on the
    # minimal set so future jobs can join without breaking this test.
    expected = {"refresh_tokens", "login_attempts", "ai_usage", "trials_expired"}
    assert expected.issubset(out.keys())
    assert all(isinstance(v, int) for v in out.values())
