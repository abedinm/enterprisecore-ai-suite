"""Webhooks + GDPR — outbound subscriptions, deliveries, export jobs, erasure receipts.

Creates the four Phase-8 tables that back outbound webhooks + GDPR data
export / erasure. Each table is tenant-scoped (``tenant_id`` FK CASCADE)
so cancelling a tenant cleanly wipes its webhook config + GDPR receipts
alongside everything else.

Idempotent: each ``create_table`` is gated by a ``_has_table`` probe so
the migration is safe to re-run against a DB built via
``Base.metadata.create_all`` (the test pattern).

Revision ID: 0016_webhooks_gdpr
Revises: 0015_billing
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0016_webhooks_gdpr"
down_revision: str | None = "0015_billing"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. webhook_subscriptions
    # ------------------------------------------------------------------
    if not _has_table("webhook_subscriptions"):
        op.create_table(
            "webhook_subscriptions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("secret_encrypted", sa.Text, nullable=False),
            sa.Column("event_types", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column("is_active", sa.Boolean, server_default=sa.text("1"), nullable=False),
            sa.Column(
                "created_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True, nullable=True,
            ),
            sa.Column("last_delivered_at", sa.DateTime(timezone=True)),
            sa.Column("last_delivery_status", sa.Integer),
            sa.Column("consecutive_failures", sa.Integer, server_default="0", nullable=False),
            sa.Column("disabled_until", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 2. webhook_deliveries
    # ------------------------------------------------------------------
    if not _has_table("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "subscription_id", sa.String(length=32),
                sa.ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
                index=True, nullable=False,
            ),
            sa.Column("event_id", sa.String(length=32), nullable=False, index=True),
            sa.Column("event_type", sa.String(length=120), nullable=False, index=True),
            sa.Column("payload_json", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("request_signature", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("delivered_at", sa.DateTime(timezone=True)),
            sa.Column("response_status", sa.Integer),
            sa.Column("response_body_excerpt", sa.Text),
            sa.Column("duration_ms", sa.Integer),
            sa.Column("attempt_number", sa.Integer, server_default="1", nullable=False),
            sa.Column("next_retry_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 3. gdpr_export_jobs
    # ------------------------------------------------------------------
    if not _has_table("gdpr_export_jobs"):
        op.create_table(
            "gdpr_export_jobs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "user_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                index=True, nullable=False,
            ),
            sa.Column(
                "requested_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False, index=True),
            sa.Column("download_path", sa.String(length=500)),
            sa.Column("download_token", sa.String(length=120), unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("error_message", sa.Text),
            sa.Column("record_count", sa.Integer, server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 4. gdpr_erasure_receipts
    # ------------------------------------------------------------------
    if not _has_table("gdpr_erasure_receipts"):
        op.create_table(
            "gdpr_erasure_receipts",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("user_id", sa.String(length=32), nullable=False, index=True),
            sa.Column("user_email_anonymized", sa.String(length=255), nullable=False),
            sa.Column(
                "requested_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("reason", sa.Text, server_default="", nullable=False),
            sa.Column("fields_cleared", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column("records_anonymized", sa.Integer, server_default="0", nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for tbl in (
        "gdpr_erasure_receipts",
        "gdpr_export_jobs",
        "webhook_deliveries",
        "webhook_subscriptions",
    ):
        if _has_table(tbl):
            op.drop_table(tbl)
