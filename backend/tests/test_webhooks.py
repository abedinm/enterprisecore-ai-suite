"""Tests for outbound webhook subscriptions + dispatcher + signature verification."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.security import decrypt_text
from app.models.webhooks import WebhookDelivery, WebhookSubscription
from app.services import webhook_dispatcher
from app.services.event_bus import publish_event, reset_subscribers
from app.services.webhook_dispatcher import set_http_client_factory


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """In-memory replacement for httpx.Client used in dispatcher tests.

    Records every POST so tests can assert on URL, headers, body, signature.
    Configurable per-instance: pass ``next_status`` and ``next_text``.
    """

    instances: list = []

    def __init__(self):
        self.posts: list[dict] = []
        self.next_status = 200
        self.next_text = "ok"
        _FakeClient.instances.append(self)

    def post(self, url, content=None, headers=None, timeout=None):
        self.posts.append({
            "url": url, "content": content,
            "headers": dict(headers or {}), "timeout": timeout,
        })
        return _FakeResponse(self.next_status, self.next_text)

    def close(self):
        pass


@pytest.fixture()
def fake_http():
    _FakeClient.instances.clear()
    holder = {"status": 200, "text": "ok"}

    def factory():
        c = _FakeClient()
        c.next_status = holder["status"]
        c.next_text = holder["text"]
        return c

    set_http_client_factory(factory)
    yield holder
    set_http_client_factory(None)


@pytest.fixture(autouse=True)
def _clean_state():
    """Wipe webhook subscriptions + in-process subscribers between tests so
    earlier tests' subscriptions don't trigger extra deliveries on later
    tests' events."""

    reset_subscribers()
    # Drop any subscriptions left over from other test modules / previous
    # tests in this file. We bypass the tenant filter so we see all of them.
    from app.core.tenant_context import bypass_tenant_filter
    from app.db.session import SessionLocal

    with SessionLocal() as cleanup_db, bypass_tenant_filter():
        cleanup_db.query(WebhookDelivery).delete()
        cleanup_db.query(WebhookSubscription).delete()
        cleanup_db.commit()
    yield
    reset_subscribers()
    with SessionLocal() as cleanup_db, bypass_tenant_filter():
        cleanup_db.query(WebhookDelivery).delete()
        cleanup_db.query(WebhookSubscription).delete()
        cleanup_db.commit()


def _create_sub(client, auth_headers, *, event_types=None, url="https://hooks.test/in"):
    body = {
        "name": "Test sub",
        "url": url,
        "event_types": event_types or ["*"],
    }
    r = client.post("/api/v1/webhooks/subscriptions", json=body, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_event_types_endpoint(client, auth_headers):
    r = client.get("/api/v1/webhooks/event-types", headers=auth_headers)
    assert r.status_code == 200
    types = {e["type"] for e in r.json()}
    assert "crm.lead.created" in types
    assert "webhook.test" in types


def test_create_subscription_returns_secret_once(client, auth_headers):
    payload = _create_sub(client, auth_headers)
    assert "secret" in payload
    assert len(payload["secret"]) >= 32

    sub_id = payload["id"]
    # GET must not expose the secret.
    r = client.get(f"/api/v1/webhooks/subscriptions/{sub_id}", headers=auth_headers)
    assert r.status_code == 200
    assert "secret" not in r.json()


def test_dispatch_records_delivery_with_valid_signature(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["crm.lead.created"])
    sub_id, secret = sub["id"], sub["secret"]

    publish_event(
        "crm.lead.created",
        payload={"lead_id": "L1", "name": "Acme"},
        tenant_id=db.scalar(select(WebhookSubscription).where(WebhookSubscription.id == sub_id)).tenant_id,
    )

    # Exactly one outbound POST happened.
    posts = []
    for inst in _FakeClient.instances:
        posts.extend(inst.posts)
    assert len(posts) == 1
    post = posts[0]
    assert post["url"] == "https://hooks.test/in"

    headers = post["headers"]
    assert headers["Content-Type"] == "application/json"
    assert headers["X-EC-Event-Type"] == "crm.lead.created"
    assert headers["X-EC-Signature"].startswith("sha256=")

    # Signature verifies against the secret + body.
    expected = hmac.new(secret.encode(), post["content"], hashlib.sha256).hexdigest()
    assert headers["X-EC-Signature"] == f"sha256={expected}"

    # A WebhookDelivery row exists for the attempt.
    deliveries = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    ).all()
    assert len(deliveries) == 1
    d = deliveries[0]
    assert d.response_status == 200
    assert d.attempt_number == 1
    assert d.next_retry_at is None  # successful delivery clears retry


def test_5xx_response_schedules_retry(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["webhook.test"])
    sub_id = sub["id"]
    fake_http["status"] = 502
    fake_http["text"] = "bad gateway"

    tenant_id = db.scalar(
        select(WebhookSubscription).where(WebhookSubscription.id == sub_id)
    ).tenant_id
    publish_event("webhook.test", payload={}, tenant_id=tenant_id)

    deliveries = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    ).all()
    assert len(deliveries) == 1
    assert deliveries[0].response_status == 502
    assert deliveries[0].next_retry_at is not None

    db.refresh(db.get(WebhookSubscription, sub_id))
    sub_obj = db.get(WebhookSubscription, sub_id)
    assert sub_obj.consecutive_failures == 1


def test_exhaust_retry_budget_pauses_subscription(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["webhook.test"])
    sub_id = sub["id"]
    fake_http["status"] = 500

    sub_obj = db.get(WebhookSubscription, sub_id)
    tenant_id = sub_obj.tenant_id

    # Fire 7 attempts (1 publish + 6 manual retries) — the 7th attempt is the
    # one that crosses _MAX_ATTEMPTS and triggers the pause.
    publish_event("webhook.test", payload={}, tenant_id=tenant_id)
    db.expire_all()
    deliveries = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    ).all()
    last_id = deliveries[-1].id
    for _ in range(6):
        new_id = webhook_dispatcher.retry_delivery(db, last_id)
        if new_id:
            last_id = new_id

    db.expire_all()
    sub_obj = db.get(WebhookSubscription, sub_id)
    assert sub_obj.consecutive_failures >= 6
    assert sub_obj.disabled_until is not None


def test_cross_tenant_isolation(client, auth_headers, fake_http, db, make_tenant):
    # tenant A creates a sub
    sub_a = _create_sub(client, auth_headers, event_types=["webhook.test"])
    a_sub_id = sub_a["id"]
    tenant_a_id = db.get(WebhookSubscription, a_sub_id).tenant_id

    # tenant B creates a sub via a separate client login
    tenant_b, _, token_b = make_tenant("tenant-b-webhook")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    sub_b = _create_sub(client, headers_b, event_types=["*"], url="https://hooks.test/b")

    # Fire an event scoped to tenant A only.
    publish_event("webhook.test", payload={}, tenant_id=tenant_a_id)

    deliveries_b = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_b["id"])
    ).all()
    assert deliveries_b == []


def test_event_type_filter_only_matches_whitelisted(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["crm.*"])
    sub_id = sub["id"]
    tenant_id = db.get(WebhookSubscription, sub_id).tenant_id

    publish_event("finance.invoice.paid", payload={}, tenant_id=tenant_id)
    publish_event("crm.lead.created", payload={}, tenant_id=tenant_id)

    deliveries = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    ).all()
    assert len(deliveries) == 1
    assert deliveries[0].event_type == "crm.lead.created"


def test_test_endpoint_fires_event(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["webhook.test"])
    sub_id = sub["id"]
    r = client.post(f"/api/v1/webhooks/subscriptions/{sub_id}/test", headers=auth_headers)
    assert r.status_code == 200
    assert "event_id" in r.json()
    deliveries = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    ).all()
    assert len(deliveries) == 1
    assert deliveries[0].event_type == "webhook.test"


def test_rotate_secret(client, auth_headers):
    sub = _create_sub(client, auth_headers)
    original = sub["secret"]
    r = client.patch(
        f"/api/v1/webhooks/subscriptions/{sub['id']}",
        json={"rotate_secret": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    new = r.json()["secret"]
    assert new and new != original


def test_manual_retry_endpoint(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["webhook.test"])
    sub_id = sub["id"]
    fake_http["status"] = 500
    tenant_id = db.get(WebhookSubscription, sub_id).tenant_id
    publish_event("webhook.test", payload={}, tenant_id=tenant_id)
    delivery = db.scalars(
        select(WebhookDelivery).where(WebhookDelivery.subscription_id == sub_id)
    ).first()
    fake_http["status"] = 200
    r = client.post(
        f"/api/v1/webhooks/deliveries/{delivery.id}/retry", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "retried"


def test_list_deliveries_endpoint(client, auth_headers, fake_http, db):
    sub = _create_sub(client, auth_headers, event_types=["webhook.test"])
    tenant_id = db.get(WebhookSubscription, sub["id"]).tenant_id
    publish_event("webhook.test", payload={"i": 1}, tenant_id=tenant_id)
    publish_event("webhook.test", payload={"i": 2}, tenant_id=tenant_id)
    r = client.get(
        f"/api/v1/webhooks/subscriptions/{sub['id']}/deliveries", headers=auth_headers
    )
    assert r.status_code == 200
    assert len(r.json()) == 2
