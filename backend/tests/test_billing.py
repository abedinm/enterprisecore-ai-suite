"""Tests for the billing module — plans, subscription CRUD, RBAC, isolation."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.billing import TenantSubscription, UsageMeter
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# /plans
# ---------------------------------------------------------------------------
def test_plans_endpoint_returns_three_plans(client, auth_headers):
    r = client.get("/api/v1/billing/plans", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    plans = {p["plan"] for p in body["plans"]}
    assert plans == {"core", "edu", "verticals"}
    # Self-managed mode when STRIPE_SECRET_KEY is unset (which is always
    # the case in CI).
    assert body["self_managed"] is True
    assert body["additional_seat_usd_monthly"] == 12.0
    assert body["ai_overage_usd_per_1k_tokens"] == 0.5


# ---------------------------------------------------------------------------
# /subscription
# ---------------------------------------------------------------------------
def test_subscription_endpoint_returns_none_initially(client, auth_headers, session_factory):
    """A freshly seeded tenant has no subscription row → endpoint returns null."""
    # Wipe any rows so the default tenant looks fresh for this test.
    from sqlalchemy import delete
    with session_factory() as db, bypass_tenant_filter():
        db.execute(delete(TenantSubscription))
        db.commit()
    r = client.get("/api/v1/billing/subscription", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json() in (None, {})


def test_subscription_endpoint_shows_current_sub(client, auth_headers, session_factory, default_tenant):
    with session_factory() as db, tenant_scope(default_tenant.id):
        sub = TenantSubscription(
            tenant_id=default_tenant.id,
            plan="core", status="active",
            seat_count=3, seat_quota=5, overage_seats=0,
            interval="month",
            currency="USD",
            amount_per_period=Decimal("99.00"),
            stripe_subscription_id="sub_test_visible",
            stripe_customer_id="cus_test_visible",
        )
        db.add(sub)
        db.commit()

    r = client.get("/api/v1/billing/subscription", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body is not None
    assert body["plan"] == "core"
    assert body["status"] == "active"


# ---------------------------------------------------------------------------
# /checkout — self-managed fallback + mocked stripe
# ---------------------------------------------------------------------------
def test_checkout_returns_self_managed_url_without_stripe(client, auth_headers):
    r = client.post(
        "/api/v1/billing/checkout",
        headers=auth_headers,
        json={"plan": "core", "interval": "month"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["self_managed"] is True
    assert body["checkout_url"].startswith("http")  # docs URL


def test_checkout_uses_stripe_when_configured(client, auth_headers, monkeypatch):
    """When STRIPE_SECRET_KEY is set, the service returns the Stripe URL."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_PRICE_CORE_MONTHLY", "price_test_core_monthly")

    fake_stripe = MagicMock()
    fake_session = MagicMock()
    fake_session.url = "https://checkout.stripe.com/test_fake"
    fake_stripe.checkout.Session.create.return_value = fake_session
    fake_customer = MagicMock()
    fake_customer.id = "cus_test_new"
    fake_stripe.Customer.create.return_value = fake_customer

    with patch("app.services.stripe_service.get_stripe_client", return_value=fake_stripe):
        r = client.post(
            "/api/v1/billing/checkout",
            headers=auth_headers,
            json={"plan": "core", "interval": "month",
                  "success_url": "https://app.test/ok",
                  "cancel_url": "https://app.test/cancel"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["self_managed"] is False
    assert "checkout.stripe.com" in body["checkout_url"]


# ---------------------------------------------------------------------------
# /cancel + /resume
# ---------------------------------------------------------------------------
def _seed_active_sub(session_factory, tenant_id: str, **fields) -> str:
    """Create an active TenantSubscription, return its id."""
    with session_factory() as db, tenant_scope(tenant_id):
        sub = TenantSubscription(
            tenant_id=tenant_id,
            plan="core", status="active",
            seat_count=1, seat_quota=5, overage_seats=0,
            interval="month", currency="USD",
            amount_per_period=Decimal("99.00"),
            **fields,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub.id


def test_cancel_and_resume_flow(client, auth_headers, session_factory, default_tenant):
    # Fresh subscription.
    from sqlalchemy import delete
    with session_factory() as db, bypass_tenant_filter():
        db.execute(delete(TenantSubscription))
        db.commit()
    sub_id = _seed_active_sub(session_factory, default_tenant.id)

    r = client.post("/api/v1/billing/cancel", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["subscription"]["cancel_at_period_end"] is True

    r = client.post("/api/v1/billing/resume", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["subscription"]["cancel_at_period_end"] is False


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------
def test_cross_tenant_isolation(client, make_tenant, session_factory):
    tenant_a, _user_a, token_a = make_tenant("billing-a")
    tenant_b, _user_b, token_b = make_tenant("billing-b")

    # Seed a sub for tenant A only.
    _seed_active_sub(session_factory, tenant_a.id,
                     stripe_subscription_id="sub_A_secret")

    # A can see it.
    r = client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200
    assert r.json() is not None
    assert r.json()["stripe_subscription_id"] == "sub_A_secret"

    # B cannot.
    r = client.get(
        "/api/v1/billing/subscription",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 200
    assert r.json() in (None, {})


# ---------------------------------------------------------------------------
# RBAC — non-admin can't hit portal / cancel / resume.
# ---------------------------------------------------------------------------
def test_non_admin_cannot_open_portal(client, make_tenant, session_factory):
    tenant, _admin, _ = make_tenant("rbac-billing")
    # Create an Employee user in the same tenant.
    from app.core.security import hash_password
    with session_factory() as db, tenant_scope(tenant.id):
        emp = User(
            email="emp@rbac-billing.test",
            full_name="Employee Joe",
            password_hash=hash_password("EmployeePass123!"),
            role=UserRole.employee,
            is_active=True,
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
        emp_token = create_access_token(emp.id, emp.role.value)

    headers = {"Authorization": f"Bearer {emp_token}"}
    r = client.post("/api/v1/billing/portal", headers=headers, json={"return_url": None})
    assert r.status_code == 403, r.text

    r = client.post("/api/v1/billing/cancel", headers=headers)
    assert r.status_code == 403, r.text

    r = client.post("/api/v1/billing/resume", headers=headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# /usage
# ---------------------------------------------------------------------------
def test_usage_endpoint_aggregates_meters(client, auth_headers, session_factory, default_tenant):
    """Seed a UsageMeter for the current period and confirm the endpoint sees it."""
    from sqlalchemy import delete
    from app.services.stripe_service import _current_period_bounds
    p_start, p_end = _current_period_bounds()
    with session_factory() as db, tenant_scope(default_tenant.id):
        db.execute(delete(UsageMeter))
        db.commit()
        db.add(UsageMeter(
            tenant_id=default_tenant.id,
            meter_key="ai_paid_tokens",
            period_start=p_start, period_end=p_end,
            quantity=Decimal("12.345"),
        ))
        db.commit()

    r = client.get("/api/v1/billing/usage", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_paid_usd_this_period"] == pytest.approx(12.345, rel=1e-3)
    assert body["ai_monthly_cap_usd"] >= 0
    assert any(m["meter_key"] == "ai_paid_tokens" for m in body["meters"])


# ---------------------------------------------------------------------------
# /invoices — empty list in self-managed mode.
# ---------------------------------------------------------------------------
def test_invoices_returns_empty_in_self_managed_mode(client, auth_headers):
    r = client.get("/api/v1/billing/invoices", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["self_managed"] is True
    assert body["invoices"] == []
