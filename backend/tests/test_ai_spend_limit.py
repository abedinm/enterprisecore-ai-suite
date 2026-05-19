"""Per-user 24h AI spending cap test."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.models.ai import AiUsageRecord
from app.models.user import User


def _admin(db) -> User:
    from sqlalchemy import select
    return db.scalar(select(User).where(User.email == "admin@local"))


def test_limit_enforced_for_paid_providers(client, auth_headers, db, monkeypatch):
    """If the user has already hit the daily $ cap on a paid provider, the
    next paid request must be rejected with 429."""
    monkeypatch.setattr("app.core.config.settings.ai_daily_usd_limit_per_user", 1.0)
    admin = _admin(db)
    # Plant historic usage = $1.50 on anthropic today
    db.add(AiUsageRecord(
        user_id=admin.id, provider="anthropic", model="claude-sonnet-4-6",
        feature="chat", tokens_in=1000, tokens_out=500,
        cost_usd=Decimal("1.5"), latency_ms=1000,
        success=True, occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()

    # Mock anthropic key to make it "available" so the provider isn't auto-swapped to ollama
    monkeypatch.setattr("app.core.config.settings.anthropic_api_key", "test-key")

    fake_resp = {"text": "ignored", "provider": "anthropic", "model": "x",
                 "tokens_in": 0, "tokens_out": 0, "cost_usd": Decimal("0"),
                 "latency_ms": 0}
    with patch("app.services.ai.call_anthropic", return_value=type("R", (), fake_resp)()):
        r = client.post("/api/v1/ai/chat", headers=auth_headers, json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "anthropic",
            "max_tokens": 50,
        })
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["code"] == "ai_spend_limit"
    assert "Daily AI spending limit reached" in body["detail"]


def test_limit_does_not_apply_to_ollama(client, auth_headers, db, monkeypatch):
    """Local Ollama calls are free and must not count against the cap."""
    monkeypatch.setattr("app.core.config.settings.ai_daily_usd_limit_per_user", 1.0)
    admin = _admin(db)
    db.add(AiUsageRecord(
        user_id=admin.id, provider="anthropic", model="x", feature="chat",
        tokens_in=0, tokens_out=0, cost_usd=Decimal("999"), latency_ms=0,
        success=True, occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()

    fake_resp = type("R", (), {
        "text": "from ollama", "provider": "ollama", "model": "llama3.1",
        "tokens_in": 10, "tokens_out": 5, "cost_usd": Decimal("0"),
        "latency_ms": 100,
    })()
    with patch("app.services.ai.call_ollama", return_value=fake_resp):
        r = client.post("/api/v1/ai/chat", headers=auth_headers, json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "ollama",
            "max_tokens": 50,
        })
    assert r.status_code == 200, r.text


def test_limit_disabled_when_zero(client, auth_headers, db, monkeypatch):
    """Setting the limit to 0 disables the check entirely."""
    monkeypatch.setattr("app.core.config.settings.ai_daily_usd_limit_per_user", 0.0)
    monkeypatch.setattr("app.core.config.settings.anthropic_api_key", "test-key")
    admin = _admin(db)
    db.add(AiUsageRecord(
        user_id=admin.id, provider="anthropic", model="x", feature="chat",
        tokens_in=0, tokens_out=0, cost_usd=Decimal("100"), latency_ms=0,
        success=True, occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()

    fake_resp = type("R", (), {
        "text": "ok", "provider": "anthropic", "model": "x",
        "tokens_in": 0, "tokens_out": 0, "cost_usd": Decimal("0"),
        "latency_ms": 0,
    })()
    with patch("app.services.ai.call_anthropic", return_value=fake_resp):
        r = client.post("/api/v1/ai/chat", headers=auth_headers, json={
            "messages": [{"role": "user", "content": "Hi"}],
            "provider": "anthropic",
            "max_tokens": 50,
        })
    assert r.status_code == 200
