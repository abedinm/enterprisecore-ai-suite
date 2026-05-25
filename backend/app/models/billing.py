"""Billing & subscription models — Phase 7 Stripe layer.

These tables sit on top of the multi-tenancy graph: every row is scoped
to one tenant via ``TenantMixin``. Stripe is treated as the source of
truth for *what the customer agreed to pay*; this side mirrors the
relevant fields locally so the app can render the billing page, gate
plan features, and meter usage without hitting Stripe on every request.

Three entities:

* :class:`TenantSubscription` — current paid plan for a tenant.
  At most one *active* row per tenant; canceled rows stay around for
  history. ``stripe_subscription_id`` is nullable for tenants on the
  free / trial / self-managed tier (no Stripe customer yet).
* :class:`BillingEvent` — append-only audit log of every billing event
  (subscription change, invoice paid, dunning notice). De-duplicated by
  ``stripe_event_id`` so a Stripe webhook retry is idempotent.
* :class:`UsageMeter` — per-tenant metered-usage counter for a billing
  period. Currently tracks AI cloud spend; the same shape extends to
  storage, API calls, etc. ``reported_to_stripe_at`` flags whether the
  quantity has been pushed to Stripe's usage-records API for the
  metered SKU.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class TenantSubscription(IdMixin, TenantMixin, TimestampMixin, Base):
    """One row per active subscription for a tenant.

    The lifecycle mirrors Stripe's: ``trialing`` → ``active`` →
    (optionally) ``past_due`` → ``canceled``. ``incomplete`` is the
    pre-confirmation state right after a Checkout session is created
    but the SCA / 3DS step hasn't completed yet.
    """

    __tablename__ = "tenant_subscriptions"

    stripe_subscription_id: Mapped[str | None] = mapped_column(String(80), index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(80), index=True)
    # core | edu | verticals
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    # active | trialing | past_due | canceled | incomplete
    status: Mapped[str] = mapped_column(String(20), default="incomplete", nullable=False, index=True)
    # Number of seats currently consumed (== active users in tenant). Filled
    # by the seat-sync job; informational here.
    seat_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Seats included in the base price; users beyond this are charged the
    # per-seat overage rate.
    seat_quota: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    overage_seats: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # month | year
    interval: Mapped[str] = mapped_column(String(8), default="month", nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    amount_per_period: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )


class BillingEvent(IdMixin, TenantMixin, TimestampMixin, Base):
    """Audit log of every billing-related event.

    Includes both Stripe webhook events (``subscription.created``,
    ``invoice.paid``, ``invoice.payment_failed``, etc.) and internal
    transitions (``trial_expired``, ``plan_downgraded``). The
    ``stripe_event_id`` UNIQUE constraint provides the idempotency
    guard — a duplicate webhook delivery is a no-op.
    """

    __tablename__ = "billing_events"

    # subscription.created / .updated / .canceled / invoice.paid /
    # invoice.payment_failed / customer.subscription.trial_will_end /
    # trial_expired / plan_downgraded / ...
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    stripe_event_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class UsageMeter(IdMixin, TenantMixin, TimestampMixin, Base):
    """Per-tenant usage counter for a single metered dimension.

    One row per (tenant, meter_key, period). The current implementation
    tracks ``ai_paid_tokens`` (USD spent on Anthropic + OpenAI; Ollama is
    free and exempt). Storage and API-call dimensions slot in by adding
    another ``meter_key`` value — no schema change required.
    """

    __tablename__ = "usage_meters"

    # ai_paid_tokens | storage_gb | api_calls | ...
    meter_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    reported_to_stripe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
