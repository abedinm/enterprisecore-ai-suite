"""Add ``id`` column to ``marketing_settings`` (legacy DBs).

Background: the marketing_settings table predates multi-tenancy and used
the string ``key`` column as its primary key. The MarketingSettings model
now inherits IdMixin (ULID id) + TenantMixin so that multiple tenants
each have their own settings row. The 0013_multitenant migration was
supposed to add the ``id`` column for this table specifically (since the
PK shape changed), but it didn't — every other multi-tenant table only
needed a new tenant_id added because they already had id PKs.

This migration is the tail-of-the-tail fixup: add the ``id`` column to
marketing_settings, populate it with ULIDs for any pre-existing rows,
drop the old (key) PK, and reinstate it as a non-unique column with a
composite (tenant_id, key) unique constraint instead.

Idempotent — if the ``id`` column already exists, this migration is a
no-op.
"""

from __future__ import annotations

import secrets
import time

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0020_marketing_settings_id"
down_revision = "0018_integrations_workflows"
branch_labels = None
depends_on = None


def _ulid() -> str:
    """Minimal ULID-style 26-char id, sortable + unique enough for our use."""
    ts = int(time.time() * 1000)
    rand = secrets.token_hex(10)
    return f"{ts:013x}{rand}"[:26].upper()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "marketing_settings" not in insp.get_table_names():
        # Table not created yet (fresh DB built from metadata.create_all in tests)
        return
    if _has_column("marketing_settings", "id"):
        # Already migrated
        return

    # SQLite-safe column add via batch_alter_table
    with op.batch_alter_table("marketing_settings", recreate="always") as batch:
        batch.add_column(sa.Column("id", sa.String(length=26), nullable=True))

    # Backfill ULID ids for any existing rows
    rows = bind.execute(sa.text("SELECT rowid FROM marketing_settings")).fetchall()
    for (rowid,) in rows:
        bind.execute(
            sa.text("UPDATE marketing_settings SET id = :id WHERE rowid = :rowid"),
            {"id": _ulid(), "rowid": rowid},
        )

    # Make NOT NULL + primary key. SQLite forces a table rebuild via batch.
    with op.batch_alter_table("marketing_settings", recreate="always") as batch:
        batch.alter_column("id", existing_type=sa.String(length=26), nullable=False)
        # Drop the old PK on `key` if it exists. SQLite doesn't have named PKs we
        # can drop directly; the recreate above already rebuilds the table, so
        # we just need to declare the new PK.
        batch.create_primary_key("pk_marketing_settings", ["id"])
        # Add the composite uniqueness so a tenant can have multiple "sites"
        # under different keys (default/staging/main) without collisions.
        batch.create_unique_constraint(
            "uq_marketing_settings_tenant_key", ["tenant_id", "key"]
        )


def downgrade() -> None:
    # Forward-only; downgrade is a manual operation if ever needed.
    raise NotImplementedError("downgrade not supported")
