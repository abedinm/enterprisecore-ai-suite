"""Tests for the /stripe/webhook endpoint — signing, idempotency, dispatch."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from app.core.tenant_context import bypass_tenant_filter
from app.models.billing import BillingEvent, TenantSubscription
from app.models.tenant import Tenant


def _build_event(*, event_id: str, event_type: str, tenant_id: str,
                 sub_id: str = "sub_test_xyz",
                 customer_id: str = "cus_test_xyz",
                 status: str = "active",
                 plan: str = "core") -> dict:
    """Construct a Stripe-shaped event payload for tests."""
    return {
        "id": event_id,
        "type": event_type,
        "created": int(datetime.now(timezone.utc).timestamp()),
        "data": {
            "object": {
                "id": sub_id,
                "object": "subscription",
                "customer": customer_id,
                "status": status,
                "current_period_start": int(datetime.now(timezone.utc).timestamp()),
                "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 30 * 86400,
                "cancel_at_period_end": False,
                "canceled_at": None,
                "trial_end": None,
                "currency": "usd",
                "metadata": {"tenant_id": tenant_id, "plan": plan},
                "items": {
                    "data": [{
                        "id": "si_test",
                        "price": {
                            "id": "price_core_monthly",
                            "unit_amount": 9900,
                            "recurring": {"interval": "month"},
                            "metadata": {"plan": plan},
                        },
                    }],
                },
            },
        },
    }


def test_webhook_invalid_signature_returns_400(client, monkeypatch):
    """When STRIPE_WEBHOOK_SECRET is set, an unsigned/forged request → 400."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy")
    event = _build_event(event_id="evt_bad_sig", event_type="customer.subscription.created",
                         tenant_id="anything")
    r = client.post(
        "/stripe/webhook",
        content=json.dumps(event).encode(),
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},  # not a valid signature
    )
    assert r.status_code == 400, r.text


def test_webhook_subscription_created_updates_tenant(client, make_tenant, session_factory):
    tenant, _, _ = make_tenant("wh-sub-create")
    event = _build_event(event_id="evt_create_1",
                         event_type="customer.subscription.created",
                         tenant_id=tenant.id, status="active", plan="core")
    # Self-managed mode → no signature check.
    r = client.post("/stripe/webhook", content=json.dumps(event).encode())
    assert r.status_code == 200, r.text
    assert r.json().get("received") is True

    with session_factory() as db, bypass_tenant_filter():
        sub = db.scalar(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
        )
        assert sub is not None
        assert sub.plan == "core"
        assert sub.status == "active"
        # Tenant should be updated too.
        t = db.get(Tenant, tenant.id)
        assert t.plan == "core"


def test_webhook_duplicate_event_id_is_idempotent(client, make_tenant, session_factory):
    tenant, _, _ = make_tenant("wh-dup")
    event = _build_event(event_id="evt_dup_X",
                         event_type="customer.subscription.created",
                         tenant_id=tenant.id, status="active", plan="core")
    r1 = client.post("/stripe/webhook", content=json.dumps(event).encode())
    assert r1.status_code == 200, r1.text

    r2 = client.post("/stripe/webhook", content=json.dumps(event).encode())
    assert r2.status_code == 200, r2.text
    assert r2.json().get("duplicate") is True

    # Only ONE BillingEvent row for this stripe_event_id.
    with session_factory() as db, bypass_tenant_filter():
        rows = db.scalars(
            select(BillingEvent).where(BillingEvent.stripe_event_id == "evt_dup_X")
        ).all()
        assert len(rows) == 1


def test_webhook_payment_failed_sets_past_due(client, make_tenant, session_factory):
    tenant, _, _ = make_tenant("wh-past-due")
    # Seed an active subscription first.
    create_evt = _build_event(event_id="evt_pd_create",
                              event_type="customer.subscription.created",
                              tenant_id=tenant.id, status="active", plan="core")
    r = client.post("/stripe/webhook", content=json.dumps(create_evt).encode())
    assert r.status_code == 200

    # Now an invoice.payment_failed event for the same customer.
    fail_evt = {
        "id": "evt_pd_fail_1",
        "type": "invoice.payment_failed",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "data": {
            "object": {
                "id": "in_test_failed",
                "object": "invoice",
                "customer": "cus_test_xyz",
                "metadata": {"tenant_id": tenant.id},
                "amount_due": 9900,
                "currency": "usd",
            },
        },
    }
    r = client.post("/stripe/webhook", content=json.dumps(fail_evt).encode())
    assert r.status_code == 200, r.text

    with session_factory() as db, bypass_tenant_filter():
        t = db.get(Tenant, tenant.id)
        assert t.status == "past_due"


def test_webhook_unknown_event_is_acked(client, make_tenant):
    tenant, _, _ = make_tenant("wh-unknown")
    event = {
        "id": "evt_unknown_1",
        "type": "some.future.event_type",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "data": {"object": {"metadata": {"tenant_id": tenant.id}}},
    }
    r = client.post("/stripe/webhook", content=json.dumps(event).encode())
    assert r.status_code == 200, r.text
    assert r.json().get("received") is True


def test_webhook_unattributed_event_acked_without_changes(client):
    """An event we can't tie to any tenant gets 200 with unattributed=True."""
    event = {
        "id": "evt_orphan_1",
        "type": "customer.subscription.created",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "data": {"object": {"id": "sub_orphan", "customer": "cus_nobody"}},
    }
    r = client.post("/stripe/webhook", content=json.dumps(event).encode())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("received") is True
    assert body.get("unattributed") is True
