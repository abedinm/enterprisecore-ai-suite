"""WebSocket notifications channel — auth, tenant isolation, fan-out."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.event_bus import publish_event, reset_subscribers
from app.services.realtime import manager


@pytest.fixture(autouse=True)
def _wipe_subscribers_between_tests():
    reset_subscribers()
    # Force the realtime manager to re-wire on next connect so we don't
    # accumulate event-bus subscribers across tests.
    manager._event_bus_wired = False  # noqa: SLF001
    yield
    reset_subscribers()


def test_ws_notifications_rejects_without_token(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/api/v1/ws/notifications") as ws:
        # Server accepts, then closes 1008 because no token was supplied.
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


def test_ws_notifications_accepts_valid_token(client: TestClient, admin_token: str):
    with client.websocket_connect(
        f"/api/v1/ws/notifications?token={admin_token}"
    ) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["channel"] == "notifications"


def test_ws_notifications_ping_pong(client: TestClient, admin_token: str):
    with client.websocket_connect(
        f"/api/v1/ws/notifications?token={admin_token}"
    ) as ws:
        # Consume the hello frame.
        ws.receive_json()
        ws.send_json({"type": "ping"})
        # The server may interleave its own ping with our pong; loop
        # until we get our pong reply.
        for _ in range(5):
            msg = ws.receive_json()
            if msg.get("type") == "pong":
                break
        else:
            raise AssertionError("never received pong")


def test_ws_notifications_receives_event(client: TestClient, admin_token: str, default_tenant):
    with client.websocket_connect(
        f"/api/v1/ws/notifications?token={admin_token}"
    ) as ws:
        # Drain hello.
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        # Fire an event that the realtime bridge should fan-out.
        publish_event(
            "crm.deal.won",
            payload={"deal_name": "Acme Corp", "amount": 50000},
            tenant_id=default_tenant.id,
        )

        # Loop because the heartbeat ping may arrive first.
        got = None
        for _ in range(10):
            msg = ws.receive_json()
            if msg.get("type") == "notification":
                got = msg
                break
        assert got is not None, "notification frame never arrived"
        assert got["event_type"] == "crm.deal.won"
        assert got["title"] == "Deal won"
        assert "Acme Corp" in got["body"]


def test_ws_notifications_cross_tenant_isolation(
    client: TestClient, admin_token: str, default_tenant, make_tenant
):
    """An event published in tenant B must NOT reach a socket in tenant A."""
    _other_tenant, _other_user, _other_token = make_tenant("other-tenant")

    with client.websocket_connect(
        f"/api/v1/ws/notifications?token={admin_token}"
    ) as ws:
        ws.receive_json()  # hello
        # Publish into the OTHER tenant.
        publish_event(
            "crm.deal.won",
            payload={"deal_name": "Other Co"},
            tenant_id=_other_tenant.id,
        )
        # Send a ping so the server has SOMETHING to reply with —
        # otherwise the connection just sits idle and we can't tell if
        # the absence of a notification is right or if we just gave up
        # too early.
        ws.send_json({"type": "ping"})
        for _ in range(5):
            msg = ws.receive_json()
            if msg.get("type") == "notification":
                raise AssertionError(
                    f"received cross-tenant notification: {msg}"
                )
            if msg.get("type") == "pong":
                break
