"""Billing layer — TenantSubscription, BillingEvent, UsageMeter.

Creates the three Phase-7 billing tables on top of the multi-tenant
foundation laid by 0013_multitenant. Every table is tenant-scoped
(``tenant_id`` FK CASCADE) so cancelling a tenant cleanly wipes its
billing history alongside its business data.

Idempotent: each ``create_table`` is gated by a ``_has_table`` probe so
that a DB built via ``Base.metadata.create_all`` (which is what tests
do) can still be stamped and upgraded without duplicate-table errors.

Revision ID: 0015_billing
Revises: 0013_multitenant (or 0014_sso when SSO lands first)
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0015_billing"
# 0014_sso landed in parallel; we chain billing onto it so the alembic
# graph stays linear. The migration body is self-contained and
# order-independent against SSO and the still-pending webhooks/GDPR
# migration (0016) which can chain onto us.
down_revision: str | None = "0014_sso"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. tenant_subscriptions — one row per active sub.
    # ------------------------------------------------------------------
    if not _has_table("tenant_subscriptions"):
        op.create_table(
            "tenant_subscriptions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("stripe_subscription_id", sa.String(length=80), index=True),
            sa.Column("stripe_customer_id", sa.String(length=80), index=True),
            sa.Column("plan", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="incomplete", nullable=False, index=True),
            sa.Column("seat_count", sa.Integer, server_default="1", nullable=False),
            sa.Column("seat_quota", sa.Integer, server_default="5", nullable=False),
            sa.Column("overage_seats", sa.Integer, server_default="0", nullable=False),
            sa.Column("interval", sa.String(length=8), server_default="month", nullable=False),
            sa.Column("current_period_start", sa.DateTime(timezone=True)),
            sa.Column("current_period_end", sa.DateTime(timezone=True)),
            sa.Column("cancel_at_period_end", sa.Boolean, server_default=sa.text("0"), nullable=False),
            sa.Column("canceled_at", sa.DateTime(timezone=True)),
            sa.Column("trial_end", sa.DateTime(timezone=True)),
            sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
            sa.Column("amount_per_period", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 2. billing_events — append-only audit log, idempotent by stripe_event_id.
    # ------------------------------------------------------------------
    if not _has_table("billing_events"):
        op.create_table(
            "billing_events",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("event_type", sa.String(length=80), nullable=False, index=True),
            sa.Column("stripe_event_id", sa.String(length=120), unique=True, index=True),
            sa.Column("metadata_json", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 3. usage_meters — per-tenant metered usage counters.
    # ------------------------------------------------------------------
    if not _has_table("usage_meters"):
        op.create_table(
            "usage_meters",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("meter_key", sa.String(length=40), nullable=False, index=True),
            sa.Column("period_start", sa.Date, nullable=False, index=True),
            sa.Column("period_end", sa.Date, nullable=False),
            sa.Column("quantity", sa.Numeric(18, 6), server_default="0", nullable=False),
            sa.Column("reported_to_stripe_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    """Drop the three billing tables (lossy — billing history wiped)."""
    for tbl in ("usage_meters", "billing_events", "tenant_subscriptions"):
        if _has_table(tbl):
            op.drop_table(tbl)
