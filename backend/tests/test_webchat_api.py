"""Web Chat Widget — bot CRUD, public chat flow, rate limiting, CRM linking,
language detection. AI provider calls are mocked so no real API keys are needed.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.services import ai as ai_svc
from app.services import webchat as webchat_svc


API = "/api/v1/webchat"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fake_reply(text: str = "Hello there!") -> ai_svc.AiResponse:
    return ai_svc.AiResponse(
        text=text, provider="anthropic", model="claude-haiku-4-5-20251001",
        tokens_in=10, tokens_out=20,
        cost_usd=Decimal("0.000123"), latency_ms=42,
    )


def _make_second_user(client, email: str = "second@local"):
    """Create + log in a second user so we can test owner isolation."""
    # The default admin already exists. Register the second user via the admin
    # JWT so role checks (if any) pass, then log them in to get their own token.
    from app.core.security import hash_password
    from sqlalchemy.orm import sessionmaker

    from tests.conftest import _TEST_DB

    # Use the session factory directly — registering via API would also work
    # but is slower and pollutes the audit log.
    from sqlalchemy import create_engine
    eng = create_engine(f"sqlite:///{_TEST_DB.as_posix()}",
                        connect_args={"check_same_thread": False})
    SessionMaker = sessionmaker(bind=eng, autoflush=False, autocommit=False,
                                expire_on_commit=False, future=True)
    from app.models.user import User, UserRole
    with SessionMaker() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if not existing:
            db.add(User(
                email=email, full_name="Second User",
                password_hash=hash_password("ChangeMe123!"),
                role=UserRole.admin, is_active=True,
            ))
            db.commit()
    resp = client.post("/api/v1/auth/login",
                       json={"email": email, "password": "ChangeMe123!"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_bot(client, auth_headers, **overrides):
    payload = {
        "name": "Support Bot",
        "description": "Helps customers",
        "language_preset": "auto",
        "system_prompt": "Be friendly.",
        "model": "claude-haiku-4-5-20251001",
        "provider": "anthropic",
        "is_public": True,
        "rate_limit_per_min": 20,
    }
    payload.update(overrides)
    r = client.post(f"{API}/bots", headers=auth_headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Bot CRUD + owner isolation
# ---------------------------------------------------------------------------
def test_create_and_get_bot(client, auth_headers):
    bot = _make_bot(client, auth_headers, name="Bot A")
    assert bot["name"] == "Bot A"
    assert bot["is_public"] is True
    assert bot["has_byo_key"] is False
    # Embed snippet computed field references the bot id
    assert bot["id"] in bot["embed_snippet"]
    assert "<script" in bot["embed_snippet"]

    r = client.get(f"{API}/bots/{bot['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == bot["id"]


def test_list_bots_returns_only_owned(client, auth_headers):
    bot_a = _make_bot(client, auth_headers, name="Owned A")
    headers_b = _make_second_user(client, email="isolation_b@local")
    _make_bot(client, headers_b, name="Owned by B")

    r = client.get(f"{API}/bots", headers=auth_headers)
    assert r.status_code == 200
    ids = {b["id"] for b in r.json()}
    assert bot_a["id"] in ids
    # admin@local should never see B's bot
    names = {b["name"] for b in r.json()}
    assert "Owned by B" not in names


def test_other_users_bot_returns_404(client, auth_headers):
    headers_b = _make_second_user(client, email="isolation_c@local")
    bot_b = _make_bot(client, headers_b, name="Private")
    # Admin tries to read B's bot → 404, not 403, to avoid leaking existence.
    r = client.get(f"{API}/bots/{bot_b['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_update_bot(client, auth_headers):
    bot = _make_bot(client, auth_headers, name="Original")
    r = client.patch(
        f"{API}/bots/{bot['id']}", headers=auth_headers,
        json={"name": "Updated", "system_prompt": "New prompt"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Updated"
    assert body["system_prompt"] == "New prompt"


def test_update_bot_stores_byo_key_encrypted(client, auth_headers, db):
    bot = _make_bot(client, auth_headers)
    r = client.patch(
        f"{API}/bots/{bot['id']}", headers=auth_headers,
        json={"api_key": "sk-byo-test-key-1234"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["has_byo_key"] is True
    # The actual key is encrypted in storage; verify we get the plaintext back
    # via the decrypt helper.
    from app.models.webchat import Bot
    db_bot = db.get(Bot, bot["id"])
    assert db_bot.api_key_encrypted
    assert db_bot.api_key_encrypted != "sk-byo-test-key-1234"
    decrypted = webchat_svc.decrypt_bot_api_key(db_bot.api_key_encrypted)
    assert decrypted == "sk-byo-test-key-1234"


def test_delete_bot_cascades(client, auth_headers, db):
    bot = _make_bot(client, auth_headers)
    # Run one chat to create a conversation + messages
    with patch("app.services.ai.call_anthropic", return_value=_fake_reply()):
        r = client.post(
            f"{API}/chat/{bot['id']}",
            json={"visitor_session_id": "vs-delete-1", "message": "Hi"},
        )
        assert r.status_code == 200, r.text

    r = client.delete(f"{API}/bots/{bot['id']}", headers=auth_headers)
    assert r.status_code == 204

    # Bot and its conversations are gone
    from app.models.webchat import Bot as BotModel
    from app.models.webchat import Conversation
    assert db.get(BotModel, bot["id"]) is None
    remaining = db.scalars(
        select(Conversation).where(Conversation.bot_id == bot["id"])
    ).all()
    assert remaining == []


# ---------------------------------------------------------------------------
# Public chat flow
# ---------------------------------------------------------------------------
def test_public_chat_creates_conversation_and_messages(client, auth_headers):
    bot = _make_bot(client, auth_headers, name="ChatBot")
    fake = _fake_reply("Hi! How can I help you?")
    with patch("app.services.ai.call_anthropic", return_value=fake):
        r = client.post(
            f"{API}/chat/{bot['id']}",
            json={"visitor_session_id": "vs-1", "message": "Hello"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "Hi! How can I help you?"
    assert body["language_detected"] == "en"
    assert body["conversation_id"]
    assert body["message_id"]

    # Owner can view the conversation
    r2 = client.get(
        f"{API}/bots/{bot['id']}/conversations", headers=auth_headers,
    )
    assert r2.status_code == 200
    convos = r2.json()
    assert len(convos) == 1
    convo_id = convos[0]["id"]

    r3 = client.get(f"{API}/conversations/{convo_id}", headers=auth_headers)
    assert r3.status_code == 200
    full = r3.json()
    assert full["bot_id"] == bot["id"]
    # 2 messages — the visitor's "Hello" and the assistant's reply
    roles = [m["role"] for m in full["messages"]]
    assert roles == ["user", "assistant"]


def test_public_chat_rejects_private_bot(client, auth_headers):
    bot = _make_bot(client, auth_headers, is_public=False, name="Private bot")
    r = client.post(
        f"{API}/chat/{bot['id']}",
        json={"visitor_session_id": "vs-priv", "message": "Hi"},
    )
    assert r.status_code == 404


def test_public_chat_rejects_unknown_bot(client):
    r = client.post(
        f"{API}/chat/unknownbotid",
        json={"visitor_session_id": "vs-x", "message": "Hi"},
    )
    assert r.status_code == 404


def test_public_bot_metadata_returns_safe_subset(client, auth_headers):
    bot = _make_bot(client, auth_headers, name="My Public Bot")
    # Public endpoint — no auth headers
    r = client.get(f"{API}/bots/public/{bot['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == bot["id"]
    assert body["name"] == "My Public Bot"
    assert "language_preset" in body
    assert body["is_public"] is True
    # Must NOT leak operator config
    for sensitive in ("owner_id", "system_prompt", "provider", "model",
                      "has_byo_key", "rate_limit_per_min", "system_messages_count"):
        assert sensitive not in body, f"public bot leaked {sensitive}"


def test_public_bot_metadata_404_for_private_bot(client, auth_headers):
    bot = _make_bot(client, auth_headers, is_public=False, name="Hidden")
    r = client.get(f"{API}/bots/public/{bot['id']}")
    assert r.status_code == 404


def test_public_bot_metadata_404_for_unknown(client):
    r = client.get(f"{API}/bots/public/does-not-exist")
    assert r.status_code == 404


def test_other_user_cannot_see_my_conversation(client, auth_headers):
    bot = _make_bot(client, auth_headers, name="Mine")
    with patch("app.services.ai.call_anthropic", return_value=_fake_reply()):
        client.post(
            f"{API}/chat/{bot['id']}",
            json={"visitor_session_id": "vs-iso", "message": "Hi"},
        )
    r = client.get(
        f"{API}/bots/{bot['id']}/conversations", headers=auth_headers,
    )
    convo_id = r.json()[0]["id"]
    headers_b = _make_second_user(client, email="convo_iso@local")
    r2 = client.get(f"{API}/conversations/{convo_id}", headers=headers_b)
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def test_per_bot_rate_limit_enforced(client, auth_headers):
    """The 21st request from the same visitor session in 60s returns 429."""
    bot = _make_bot(client, auth_headers, rate_limit_per_min=20,
                    name="Limited Bot")
    fake = _fake_reply("ok")
    with patch("app.services.ai.call_anthropic", return_value=fake):
        for i in range(20):
            r = client.post(
                f"{API}/chat/{bot['id']}",
                json={"visitor_session_id": "vs-limit", "message": f"msg {i}"},
            )
            assert r.status_code == 200, f"call {i + 1}: {r.text}"

        # 21st must trip the per-bot/per-session limit
        r = client.post(
            f"{API}/chat/{bot['id']}",
            json={"visitor_session_id": "vs-limit", "message": "msg 21"},
        )
    assert r.status_code == 429, r.text
    assert r.json().get("code") == "rate_limited"


# ---------------------------------------------------------------------------
# CRM linking
# ---------------------------------------------------------------------------
def test_contact_hint_creates_contact_and_communication(client, auth_headers, db):
    bot = _make_bot(client, auth_headers, name="CRM Bot")
    fake = _fake_reply("Hi!")
    with patch("app.services.ai.call_anthropic", return_value=fake):
        r = client.post(
            f"{API}/chat/{bot['id']}",
            json={
                "visitor_session_id": "vs-crm",
                "message": "Please call me back.",
                "contact_hint": {
                    "email": "leadcustomer@example.com",
                    "name": "Lead Customer",
                },
            },
        )
    assert r.status_code == 200, r.text

    from app.models.crm import CommunicationEntry, Contact
    from app.models.webchat import Conversation

    contact = db.scalar(
        select(Contact).where(Contact.email == "leadcustomer@example.com")
    )
    assert contact is not None
    assert contact.name in ("Lead Customer", "leadcustomer@example.com")

    convo = db.scalar(
        select(Conversation).where(Conversation.bot_id == bot["id"])
    )
    assert convo is not None
    assert convo.contact_id == contact.id

    comm = db.scalar(
        select(CommunicationEntry).where(
            CommunicationEntry.contact_id == contact.id,
            CommunicationEntry.channel == "webchat",
        )
    )
    assert comm is not None
    assert "call me back" in (comm.body or "")


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
def test_detect_language_english():
    assert webchat_svc.detect_language("Hello there, how are you?") == "en"


def test_detect_language_bengali():
    # "How are you?" in Bengali
    assert webchat_svc.detect_language("আপনি কেমন আছেন?") == "bn"


def test_detect_language_hindi():
    # "How are you?" in Hindi (Devanagari)
    assert webchat_svc.detect_language("आप कैसे हैं?") == "hi"


def test_detect_language_urdu():
    # "How are you?" in Urdu (Arabic script)
    assert webchat_svc.detect_language("آپ کیسے ہیں؟") == "ur"


def test_detect_language_defaults_to_english_on_empty():
    assert webchat_svc.detect_language("") == "en"
    assert webchat_svc.detect_language("123 !!!") == "en"


def test_public_chat_records_detected_language(client, auth_headers, db):
    bot = _make_bot(client, auth_headers, name="Lang Bot")
    fake = _fake_reply("ঠিক আছে!")
    with patch("app.services.ai.call_anthropic", return_value=fake):
        r = client.post(
            f"{API}/chat/{bot['id']}",
            json={"visitor_session_id": "vs-lang",
                  "message": "আপনি কেমন আছেন?"},
        )
    assert r.status_code == 200
    assert r.json()["language_detected"] == "bn"


# ---------------------------------------------------------------------------
# Plan gating — webchat must be in the active plan or the route returns 403
# ---------------------------------------------------------------------------
def test_webchat_gated_off_when_feature_removed(client, auth_headers, monkeypatch):
    """Temporarily strip webchat from every plan so require_plan_feature
    refuses every route — both authenticated and public — with 403."""
    from app.core import plans as plans_mod

    patched = {plan: set(feats) for plan, feats in plans_mod.PLAN_FEATURES.items()}
    for feats in patched.values():
        feats.discard("webchat")
    monkeypatch.setattr(plans_mod, "PLAN_FEATURES", patched)

    r = client.get(f"{API}/bots", headers=auth_headers)
    assert r.status_code == 403
    assert r.json().get("code") == "permission_denied"

    # Public chat is also gated even though it has no auth
    r2 = client.post(
        f"{API}/chat/anything",
        json={"visitor_session_id": "v", "message": "hi"},
    )
    assert r2.status_code == 403
