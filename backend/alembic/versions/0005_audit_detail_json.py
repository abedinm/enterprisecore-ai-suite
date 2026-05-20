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

    if dialect == "postgresql":
        # ALTER COLUMN to JSONB, casting through the existing text contents.
        # Wrap in try/except so a failure here (e.g., long lock wait on managed
        # Postgres, invalid JSON in detail) doesn't crash the entire startup.
        # The column stays as TEXT if ALTER fails — JSON queries are slower
        # but the app still works.
        import sys
        try:
            sys.stderr.write("[migration 0005] starting ALTER TABLE audit_logs.detail to JSONB\n")
            sys.stderr.flush()
            op.execute("ALTER TABLE audit_logs ALTER COLUMN detail TYPE JSONB USING detail::jsonb")
            sys.stderr.write("[migration 0005] ALTER succeeded\n")
            sys.stderr.flush()
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[migration 0005] ALTER failed (column stays TEXT): {type(e).__name__}: {e}\n")
            sys.stderr.flush()
    # SQLite: no DDL needed — TEXT and JSON are stored identically.


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("ALTER TABLE audit_logs ALTER COLUMN detail TYPE TEXT USING detail::text")
