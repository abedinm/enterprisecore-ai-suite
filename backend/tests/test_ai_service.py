"""Service-level AI tests — covers pure helpers, DB-backed spend tracking,
provider error paths, and high-level wrapper heuristics.

We intentionally avoid calling real remote providers (Anthropic/OpenAI/Ollama).
Network calls are either exercised via their "no key" error path or mocked with
unittest.mock.patch.

Target: raise app/services/ai.py coverage from 39% toward 80%+.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import uuid as _uuid_mod

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models.ai import AiUsageRecord
from app.models.user import User, UserRole
from app.services.ai import (
    AiMessage,
    AiResponse,
    _check_spending_limit,
    _cost,
    _format_messages_for_claude,
    _record_usage,
    _strip_json_fence,
    analyze_sentiment,
    available_providers,
    call,
    call_anthropic,
    call_ollama,
    call_openai,
    smart_json,
    stream_call,
    summarise_meeting,
    user_daily_spend_usd,
)


# ---------------------------------------------------------------------------
# _cost
# ---------------------------------------------------------------------------

def test_cost_known_model():
    # claude-sonnet-4-6: in=0.000003, out=0.000015
    # 1000 * 0.000003 = 0.003; 500 * 0.000015 = 0.0075 → total 0.0105
    c = _cost("claude-sonnet-4-6", 1000, 500)
    assert c == Decimal("0.000003") * 1000 + Decimal("0.000015") * 500
    assert c == Decimal("0.0105")


def test_cost_unknown_model_returns_zero():
    assert _cost("some-unknown-model", 9999, 9999) == Decimal("0")


def test_cost_zero_tokens():
    assert _cost("gpt-4o", 0, 0) == Decimal("0")


# ---------------------------------------------------------------------------
# _format_messages_for_claude
# ---------------------------------------------------------------------------

def test_format_messages_separates_system():
    msgs = [
        AiMessage(role="system", content="You are helpful."),
        AiMessage(role="user", content="Hello?"),
    ]
    system, conv = _format_messages_for_claude(msgs)
    assert system == "You are helpful."
    assert len(conv) == 1
    assert conv[0]["role"] == "user"
    assert conv[0]["content"] == "Hello?"


def test_format_messages_multiple_system_parts():
    msgs = [
        AiMessage(role="system", content="Rule 1."),
        AiMessage(role="system", content="Rule 2."),
        AiMessage(role="user", content="Go."),
    ]
    system, conv = _format_messages_for_claude(msgs)
    assert "Rule 1." in system and "Rule 2." in system
    assert len(conv) == 1


def test_format_messages_no_user_inserts_empty():
    """If all messages are system, add a blank user turn."""
    msgs = [AiMessage(role="system", content="Only system.")]
    system, conv = _format_messages_for_claude(msgs)
    assert len(conv) == 1
    assert conv[0]["role"] == "user"
    assert conv[0]["content"] == ""


def test_format_messages_no_system():
    msgs = [AiMessage(role="user", content="Hi")]
    system, conv = _format_messages_for_claude(msgs)
    assert system == ""
    assert conv[0]["content"] == "Hi"


# ---------------------------------------------------------------------------
# _strip_json_fence
# ---------------------------------------------------------------------------

def test_strip_json_fence_removes_backtick_block():
    text = "```json\n{\"key\": \"value\"}\n```"
    result = _strip_json_fence(text)
    assert result == '{"key": "value"}'


def test_strip_json_fence_no_fence_passthrough():
    text = '{"key": "value"}'
    assert _strip_json_fence(text) == text


def test_strip_json_fence_generic_triple_backtick():
    text = "```\n[1, 2, 3]\n```"
    result = _strip_json_fence(text)
    assert result == "[1, 2, 3]"


# ---------------------------------------------------------------------------
# available_providers
# ---------------------------------------------------------------------------

def test_available_providers_shape():
    result = available_providers()
    assert "anthropic" in result
    assert "openai" in result
    assert "ollama" in result
    # In test env, API keys are empty → both cloud providers are False
    assert result["anthropic"] is False
    assert result["openai"] is False
    # Ollama is always True (local)
    assert result["ollama"] is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ai_user(session_factory) -> str:
    """Create a throw-away User row and return its id.
    AiUsageRecord.user_id has a FK to users.id — tests that seed usage records
    must provide a real user_id.
    """
    sfx = _uuid_mod.uuid4().hex[:10]
    with session_factory() as db:
        u = User(
            email=f"ai-test-{sfx}@ai.test",
            full_name=f"AI Test {sfx}",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.employee,
            is_active=True,
        )
        db.add(u)
        db.commit()
        return u.id


# ---------------------------------------------------------------------------
# _record_usage
# ---------------------------------------------------------------------------

def test_record_usage_with_db(session_factory):
    with session_factory() as db:
        _record_usage(
            db, user_id=None, provider="ollama", model="llama3.1",
            feature="test", tin=100, tout=50, cost=Decimal("0"),
            latency_ms=200, success=True,
        )
        from sqlalchemy import select
        rows = db.scalars(select(AiUsageRecord).where(AiUsageRecord.provider == "ollama")).all()
    assert any(r.model == "llama3.1" for r in rows)


def test_record_usage_without_db_does_not_raise():
    """When db=None, _record_usage should silently skip."""
    _record_usage(None, user_id=None, provider="ollama", model="x",
                  feature="t", tin=0, tout=0, cost=Decimal("0"), latency_ms=0)


# ---------------------------------------------------------------------------
# user_daily_spend_usd
# ---------------------------------------------------------------------------

def test_user_daily_spend_usd_empty(session_factory):
    import uuid
    uid = uuid.uuid4().hex
    with session_factory() as db:
        result = user_daily_spend_usd(db, uid)
    assert result == Decimal("0")


def test_user_daily_spend_usd_sums_recent_records(session_factory):
    uid = _make_ai_user(session_factory)
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(AiUsageRecord(
            user_id=uid, provider="anthropic", model="claude-sonnet-4-6",
            feature="test", tokens_in=100, tokens_out=50,
            cost_usd=Decimal("0.001"), latency_ms=300, success=True,
            occurred_at=now - timedelta(hours=1),
        ))
        db.add(AiUsageRecord(
            user_id=uid, provider="openai", model="gpt-4o-mini",
            feature="test", tokens_in=200, tokens_out=100,
            cost_usd=Decimal("0.002"), latency_ms=200, success=True,
            occurred_at=now - timedelta(hours=2),
        ))
        # Old record outside 24h window — should not be counted
        db.add(AiUsageRecord(
            user_id=uid, provider="anthropic", model="claude-sonnet-4-6",
            feature="test", tokens_in=999, tokens_out=999,
            cost_usd=Decimal("9.999"), latency_ms=500, success=True,
            occurred_at=now - timedelta(hours=25),
        ))
        db.commit()

        result = user_daily_spend_usd(db, uid)

    assert result == Decimal("0.003")


# ---------------------------------------------------------------------------
# _check_spending_limit
# ---------------------------------------------------------------------------

def test_check_spending_limit_no_db():
    """No db → always passes."""
    _check_spending_limit(None, user_id="any", chosen="anthropic")


def test_check_spending_limit_no_user_id(session_factory):
    with session_factory() as db:
        _check_spending_limit(db, user_id=None, chosen="anthropic")


def test_check_spending_limit_ollama_is_exempt(session_factory):
    """Ollama never counts against the limit."""
    with session_factory() as db:
        _check_spending_limit(db, user_id="any", chosen="ollama")


def test_check_spending_limit_zero_limit_exempt(session_factory):
    """If the limit setting is 0, treat as disabled (no enforcement)."""
    with patch("app.services.ai.settings") as mock_settings:
        mock_settings.ai_daily_usd_limit_per_user = 0
        mock_settings.anthropic_api_key = ""
        mock_settings.openai_api_key = ""
        mock_settings.ai_default_provider = "ollama"
        mock_settings.ollama_host = "http://localhost:11434"
        with session_factory() as db:
            _check_spending_limit(db, user_id="any", chosen="anthropic")


def test_check_spending_limit_raises_when_exceeded(session_factory):
    uid = _make_ai_user(session_factory)
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        # Seed a big cost record within the 24h window
        db.add(AiUsageRecord(
            user_id=uid, provider="anthropic", model="claude-opus-4-7",
            feature="test", tokens_in=10000, tokens_out=5000,
            cost_usd=Decimal("5.00"), latency_ms=1000, success=True,
            occurred_at=now - timedelta(hours=1),
        ))
        db.commit()

        with patch("app.services.ai.settings") as mock_settings:
            mock_settings.ai_daily_usd_limit_per_user = 4.0  # limit $4, spent $5
            mock_settings.anthropic_api_key = ""
            mock_settings.openai_api_key = ""
            mock_settings.ai_default_provider = "ollama"
            mock_settings.ollama_host = "http://localhost:11434"
            with pytest.raises(AppError) as exc_info:
                _check_spending_limit(db, user_id=uid, chosen="anthropic")

    assert exc_info.value.code == "ai_spend_limit"
    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# call_anthropic / call_openai / call_ollama error paths
# ---------------------------------------------------------------------------

def test_call_anthropic_raises_when_no_key():
    with pytest.raises(AppError) as exc_info:
        call_anthropic([AiMessage(role="user", content="hi")], api_key_override=None)
    assert exc_info.value.code == "ai_provider_not_configured"


def test_call_openai_raises_when_no_key():
    with pytest.raises(AppError) as exc_info:
        call_openai([AiMessage(role="user", content="hi")], api_key_override=None)
    assert exc_info.value.code == "ai_provider_not_configured"


def test_call_ollama_raises_when_server_unreachable():
    """Ollama should raise AppError(ai_provider_unavailable) on connection errors."""
    with pytest.raises(AppError) as exc_info:
        call_ollama(
            [AiMessage(role="user", content="hi")],
            model="llama3.1",
        )
    assert exc_info.value.code == "ai_provider_unavailable"


# ---------------------------------------------------------------------------
# call() — with mocked provider
# ---------------------------------------------------------------------------

def _fake_ollama_response(text: str = "hello") -> AiResponse:
    return AiResponse(
        text=text, provider="ollama", model="llama3.1",
        tokens_in=5, tokens_out=2, cost_usd=Decimal("0"), latency_ms=100,
    )


def test_call_dispatches_to_ollama_when_no_cloud_keys():
    """In test env (no API keys), call() should route to Ollama."""
    with patch("app.services.ai.call_ollama", return_value=_fake_ollama_response()) as mock_ollama:
        result = call([AiMessage(role="user", content="test")], db=None)
    mock_ollama.assert_called_once()
    assert result.provider == "ollama"
    assert result.text == "hello"


def test_call_records_success_to_db(session_factory):
    uid = _make_ai_user(session_factory)
    with session_factory() as db:
        with patch("app.services.ai.call_ollama", return_value=_fake_ollama_response("ok")):
            result = call(
                [AiMessage(role="user", content="test")],
                provider="ollama", db=db, user_id=uid, feature="unit_test",
            )
        from sqlalchemy import select
        rows = db.scalars(
            select(AiUsageRecord).where(AiUsageRecord.user_id == uid)
        ).all()
    assert any(r.feature == "unit_test" and r.success is True for r in rows)


def test_call_ollama_failure_records_failure_and_reraises(session_factory):
    uid = _make_ai_user(session_factory)
    with session_factory() as db:
        with patch("app.services.ai.call_ollama",
                   side_effect=AppError("Ollama down", code="ai_provider_unavailable", status_code=503)):
            with pytest.raises(AppError):
                call([AiMessage(role="user", content="test")],
                     provider="ollama", db=db, user_id=uid)

        from sqlalchemy import select
        rows = db.scalars(
            select(AiUsageRecord).where(AiUsageRecord.user_id == uid)
        ).all()
    assert any(r.success is False for r in rows)


def test_call_with_anthropic_key_override_uses_anthropic():
    fake = AiResponse(text="claude says hi", provider="anthropic", model="claude-sonnet-4-6")
    with patch("app.services.ai.call_anthropic", return_value=fake) as mock_claude:
        result = call(
            [AiMessage(role="user", content="test")],
            provider="anthropic",
            api_key_override="sk-fake-test-key",
            db=None,
        )
    mock_claude.assert_called_once()
    assert result.text == "claude says hi"


def test_call_non_ollama_fails_falls_back_to_ollama():
    """When a cloud provider raises AppError, call() should try Ollama."""
    fallback = _fake_ollama_response("ollama fallback")
    with patch("app.services.ai.call_anthropic",
               side_effect=AppError("Anthropic error", code="ai_provider_not_configured")) as mock_ant, \
         patch("app.services.ai.call_ollama", return_value=fallback) as mock_ollama:
        result = call(
            [AiMessage(role="user", content="test")],
            provider="anthropic",
            api_key_override="sk-fake",
            db=None,
        )
    mock_ant.assert_called_once()
    mock_ollama.assert_called_once()
    assert result.text == "ollama fallback"


# ---------------------------------------------------------------------------
# smart_json
# ---------------------------------------------------------------------------

def test_smart_json_parses_clean_json():
    with patch("app.services.ai.call_ollama",
               return_value=_fake_ollama_response('{"answer": 42}')):
        result = smart_json("Give me JSON", provider="ollama")
    assert result["answer"] == 42


def test_smart_json_strips_fence():
    fenced = '```json\n{"answer": 99}\n```'
    with patch("app.services.ai.call_ollama",
               return_value=_fake_ollama_response(fenced)):
        result = smart_json("Give me JSON", provider="ollama")
    assert result["answer"] == 99


def test_smart_json_extracts_embedded_json():
    """JSON buried in prose text should still be extracted."""
    text = 'Here is the answer: {"status": "ok"} end of message.'
    with patch("app.services.ai.call_ollama",
               return_value=_fake_ollama_response(text)):
        result = smart_json("prompt", provider="ollama")
    assert result.get("status") == "ok"


def test_smart_json_fallback_raw_on_unparseable():
    with patch("app.services.ai.call_ollama",
               return_value=_fake_ollama_response("completely unparseable %%% text")):
        result = smart_json("prompt", provider="ollama")
    assert "_raw" in result


# ---------------------------------------------------------------------------
# analyze_sentiment — heuristic fallbacks
# ---------------------------------------------------------------------------

def test_analyze_sentiment_positive_heuristic():
    """When smart_json returns _raw, heuristic keyword matching fires."""
    with patch("app.services.ai.smart_json", return_value={"_raw": "irrelevant"}):
        result = analyze_sentiment("This product is excellent and amazing!")
    assert result["label"] == "positive"
    assert result["score"] == 0.8


def test_analyze_sentiment_negative_heuristic():
    with patch("app.services.ai.smart_json", return_value={"_raw": "irrelevant"}):
        result = analyze_sentiment("This is terrible and awful, I hate it.")
    assert result["label"] == "negative"


def test_analyze_sentiment_neutral_heuristic():
    with patch("app.services.ai.smart_json", return_value={"_raw": "irrelevant"}):
        result = analyze_sentiment("The package arrived on Tuesday.")
    assert result["label"] == "neutral"
    assert result["score"] == 0.5


def test_analyze_sentiment_uses_json_result():
    with patch("app.services.ai.smart_json",
               return_value={"label": "positive", "score": 0.95, "summary": "Very good."}):
        result = analyze_sentiment("Great product!")
    assert result["label"] == "positive"
    assert result["score"] == 0.95
    assert result["summary"] == "Very good."


# ---------------------------------------------------------------------------
# summarise_meeting
# ---------------------------------------------------------------------------

def test_summarise_meeting_uses_json_result():
    data = {
        "summary": "Team aligned on Q3 goals.",
        "key_decisions": ["Hire 3 engineers"],
        "action_items": [{"owner": "Alice", "task": "Write JDs", "due": "2026-06-01"}],
    }
    with patch("app.services.ai.smart_json", return_value=data):
        result = summarise_meeting("long transcript text...")
    assert result["summary"] == "Team aligned on Q3 goals."
    assert len(result["action_items"]) == 1


def test_summarise_meeting_fallback_on_raw():
    with patch("app.services.ai.smart_json", return_value={"_raw": "summary text here"}):
        result = summarise_meeting("transcript")
    assert result["summary"] == "summary text here"
    assert result["key_decisions"] == []
    assert result["action_items"] == []


# ---------------------------------------------------------------------------
# stream_call
# ---------------------------------------------------------------------------

def test_stream_call_yields_tokens_then_usage():
    def _fake_stream(*a, **kw):
        yield "token", {"text": "Hello"}
        yield "token", {"text": " world"}
        yield "usage", {
            "provider": "ollama", "model": "llama3.1",
            "tokens_in": 5, "tokens_out": 2,
            "cost_usd": "0", "latency_ms": 50,
            "text": "Hello world",
        }

    with patch("app.services.ai._stream_ollama", side_effect=_fake_stream):
        events = list(stream_call(
            messages=[AiMessage(role="user", content="hi")],
            provider="ollama",
            db=None,
        ))

    types = [e[0] for e in events]
    assert types.count("token") == 2
    assert types[-1] == "usage"
    combined = "".join(e[1]["text"] for e in events if e[0] == "token")
    assert combined == "Hello world"


def test_stream_call_yields_error_on_spend_limit(session_factory):
    uid = _make_ai_user(session_factory)
    now = datetime.now(timezone.utc)

    with session_factory() as db:
        db.add(AiUsageRecord(
            user_id=uid, provider="anthropic", model="claude-opus-4-7",
            feature="test", tokens_in=10000, tokens_out=5000,
            cost_usd=Decimal("10.00"), latency_ms=1000, success=True,
            occurred_at=now - timedelta(hours=1),
        ))
        db.commit()

        with patch("app.services.ai.settings") as mock_settings:
            mock_settings.ai_daily_usd_limit_per_user = 5.0  # $5 limit, $10 spent
            mock_settings.anthropic_api_key = ""
            mock_settings.openai_api_key = ""
            mock_settings.ai_default_provider = "anthropic"
            mock_settings.ollama_host = "http://localhost:11434"

            # api_key_override prevents the "no cloud key → fallback to ollama"
            # logic, ensuring we land on "anthropic" for the spend-limit check.
            events = list(stream_call(
                messages=[AiMessage(role="user", content="hi")],
                provider="anthropic",
                api_key_override="sk-fake-test-key",
                db=db, user_id=uid,
            ))

    error_events = [e for e in events if e[0] == "error"]
    assert len(error_events) == 1
    assert error_events[0][1]["code"] == "ai_spend_limit"
