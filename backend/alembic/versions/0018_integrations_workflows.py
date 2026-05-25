"""Phase 8 mid-market integration layer — tenant_integrations + workflows.

Creates three tables backing the new Slack / Google Workspace / Zapier
connectors and the no-code workflow automation engine:

* ``tenant_integrations`` — one row per (tenant, connector_key) pair,
  carrying encrypted OAuth tokens + a JSON config bag.
* ``workflows`` — a tenant-defined 'if-this-then-that' rule.
* ``workflow_runs`` — per-execution audit row, one per matched event.

Idempotent: each ``create_table`` is gated by a ``_has_table`` probe so
the migration is safe to re-run against a DB built via
``Base.metadata.create_all`` (the test pattern).

Revision ID: 0018_integrations_workflows
Revises: 0019_importers  (rebased to chain after the importer migration,
                          which also descended from 0017_rbac_security —
                          alembic can't tolerate two heads, so this one
                          slots in after the importer head as the latest
                          revision)
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0018_integrations_workflows"
down_revision: str | None = "0019_importers"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. tenant_integrations
    # ------------------------------------------------------------------
    if not _has_table("tenant_integrations"):
        op.create_table(
            "tenant_integrations",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("key", sa.String(length=60), nullable=False, index=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("access_token_encrypted", sa.Text),
            sa.Column("refresh_token_encrypted", sa.Text),
            sa.Column("token_expires_at", sa.DateTime(timezone=True)),
            sa.Column("config", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "installed_by_user_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("installed_at", sa.DateTime(timezone=True)),
            sa.Column("last_used_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_integration"),
        )

    # ------------------------------------------------------------------
    # 2. workflows
    # ------------------------------------------------------------------
    if not _has_table("workflows"):
        op.create_table(
            "workflows",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("trigger_event_type", sa.String(length=120), nullable=False, index=True),
            sa.Column("trigger_filter", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("actions", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column(
                "created_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("last_run_at", sa.DateTime(timezone=True)),
            sa.Column("runs_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("failures_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 3. workflow_runs
    # ------------------------------------------------------------------
    if not _has_table("workflow_runs"):
        op.create_table(
            "workflow_runs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "workflow_id", sa.String(length=32),
                sa.ForeignKey("workflows.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("event_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("event_type", sa.String(length=120), nullable=False, index=True),
            sa.Column("event_payload", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="success", index=True),
            sa.Column("action_results", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for tbl in ("workflow_runs", "workflows", "tenant_integrations"):
        if _has_table(tbl):
            op.drop_table(tbl)
