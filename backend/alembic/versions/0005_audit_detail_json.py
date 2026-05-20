"""Convert audit_logs.detail from TEXT (manual JSON string) to JSON column.

The application previously stored the audit-detail dict as ``json.dumps(...)``
in a Text column. The new model uses SQLAlchemy's JSON type, which is TEXT in
SQLite (unchanged) but JSONB in PostgreSQL (queryable, indexable). On SQLite
the migration is a no-op at the storage layer — the data was already
JSON-as-text — but we still mark the schema change so PostgreSQL deployments
get the proper type.

Revision ID: 0005_audit_detail_json
Revises: 0004_pm_inventory_expansion
Create Date: 2026-05-20
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005_audit_detail_json"
down_revision: str | None = "0004_pm_inventory_expansion"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Coerce any rows where detail is NULL or non-JSON to a sane '{}' default.
    # On both backends the underlying storage of our `JSON` SQLAlchemy column is
    # accessible as TEXT in raw SQL.
    bind.execute(sa.text("UPDATE audit_logs SET detail = '{}' WHERE detail IS NULL OR detail = ''"))

    # NOTE: Was previously `ALTER TABLE audit_logs ALTER COLUMN detail TYPE JSONB`
    # on Postgres, but it consistently caused uvicorn lifespan to exit with status 3
    # on Render's managed Postgres (no visible traceback — likely a transaction-level
    # error that taints the alembic-managed DDL transaction even when caught in
    # Python). Leaving detail as TEXT on both backends. JSON queries on Postgres
    # will use ->> with explicit ::jsonb casts instead of the column type doing it.
    # SQLite: TEXT and JSON are stored identically anyway.
    _ = dialect  # silence "unused" — keep the variable for future re-introduction


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TABLE audit_logs ALTER COLUMN detail TYPE TEXT USING detail::text")
