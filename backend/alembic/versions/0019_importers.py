"""Phase 9 — data-migration importer tables.

Creates two tables that back the customer-facing "move your data in from
HubSpot / Salesforce / QuickBooks / generic CSV" flow:

* ``import_jobs`` — one row per uploaded file, captures status + counts
  + the trail of imported record ids for rollback.
* ``import_errors`` — per-row failures the dry-run or commit produced.

Both are tenant-scoped (CASCADE on ``tenants.id``) so cancelling a tenant
cleanly wipes their import history alongside everything else.

Idempotent: each ``create_table`` is gated by ``_has_table`` so the
migration is safe to re-run against a DB built via
``Base.metadata.create_all`` (the test pattern).

Revision ID: 0019_importers
Revises: 0017_rbac_security  (siblings 0018_integrations may rebase
                              their own ``down_revision`` to chain
                              whichever lands last)
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0019_importers"
down_revision: str | None = "0017_rbac_security"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("import_jobs"):
        op.create_table(
            "import_jobs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("source", sa.String(length=40), nullable=False, index=True),
            sa.Column("target_module", sa.String(length=40), nullable=False),
            sa.Column("target_entity", sa.String(length=60), nullable=False, index=True),
            sa.Column("status", sa.String(length=20), server_default="uploaded", nullable=False, index=True),
            sa.Column("source_file_path", sa.String(length=500)),
            sa.Column("column_mapping", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("row_count_total", sa.Integer, server_default="0", nullable=False),
            sa.Column("row_count_imported", sa.Integer, server_default="0", nullable=False),
            sa.Column("row_count_skipped", sa.Integer, server_default="0", nullable=False),
            sa.Column("row_count_failed", sa.Integer, server_default="0", nullable=False),
            sa.Column(
                "started_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True, nullable=True,
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("config", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("options", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("can_rollback", sa.Boolean, server_default=sa.text("1"), nullable=False),
            sa.Column("imported_record_ids", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("import_errors"):
        op.create_table(
            "import_errors",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "import_job_id", sa.String(length=32),
                sa.ForeignKey("import_jobs.id", ondelete="CASCADE"),
                index=True, nullable=False,
            ),
            sa.Column("row_number", sa.Integer, nullable=False),
            sa.Column("source_data", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error_type", sa.String(length=40), nullable=False, index=True),
            sa.Column("error_message", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for tbl in ("import_errors", "import_jobs"):
        if _has_table(tbl):
            op.drop_table(tbl)
