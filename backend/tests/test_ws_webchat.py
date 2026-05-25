"""WebSocket webchat channel — bot ownership + broadcast on new message."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.webchat import Bot
from app.services.event_bus import publish_event, reset_subscribers
from app.services.realtime import manager


@pytest.fixture(autouse=True)
def _wipe_subscribers_between_tests():
    reset_subscribers()
    manager._event_bus_wired = False  # noqa: SLF001
    yield
    reset_subscribers()


def _make_bot(db, owner_id: str) -> Bot:
    bot = Bot(
        owner_id=owner_id,
        name="Test Bot",
        description="t",
        language_preset="auto",
        system_prompt="be helpful",
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        is_public=True,
        api_key_encrypted=None,
        rate_limit_per_min=20,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


def test_ws_webchat_rejects_non_owner(client: TestClient, db, make_tenant):
    """A user from another tenant cannot subscribe to a bot they don't own."""
    # Bot belongs to the default-tenant admin (from auto-scope fixture).
    from sqlalchemy import select

    from app.models.user import User

    admin = db.scalar(select(User).where(User.email == "admin@local"))
    bot = _make_bot(db, admin.id)

    # Open the WS as a DIFFERENT tenant's admin.
    _other_tenant, _other_user, other_token = make_tenant("webchat-other")
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect(
        f"/api/v1/ws/webchat/{bot.id}?token={other_token}"
    ) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


def test_ws_webchat_owner_connects(client: TestClient, db, admin_token: str):
    from sqlalchemy import select

    from app.models.user import User

    admin = db.scalar(select(User).where(User.email == "admin@local"))
    bot = _make_bot(db, admin.id)

    with client.websocket_connect(
        f"/api/v1/ws/webchat/{bot.id}?token={admin_token}"
    ) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["bot_id"] == bot.id


def test_ws_webchat_receives_message_event(
    client: TestClient, db, admin_token: str, default_tenant
):
    from sqlalchemy import select

    from app.models.user import User

    admin = db.scalar(select(User).where(User.email == "admin@local"))
    bot = _make_bot(db, admin.id)

    with client.websocket_connect(
        f"/api/v1/ws/webchat/{bot.id}?token={admin_token}"
    ) as ws:
        ws.receive_json()  # hello
        publish_event(
            "webchat.message.received",
            payload={"bot_id": bot.id, "conversation_id": "abc"},
            tenant_id=default_tenant.id,
        )
        got = None
        for _ in range(10):
            msg = ws.receive_json()
            if msg.get("type") == "webchat.update":
                got = msg
                break
        assert got is not None
        assert got["bot_id"] == bot.id
        assert got["event_type"] == "webchat.message.received"
