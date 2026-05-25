"""Realtime / collaborative-editing persistence.

Adds a single table — ``yjs_documents`` — that holds the persisted
state of a Yjs collaborative document so reconnecting clients can
re-sync from disk rather than relying on another connected peer to
ship them the state.

Idempotent — if the table already exists (fresh DB built from
``metadata.create_all`` in tests), this migration is a no-op.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0025_realtime"
down_revision = "0024_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing = set(insp.get_table_names())

    if "yjs_documents" not in existing:
        op.create_table(
            "yjs_documents",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("document_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("document_kind", sa.String(length=40), nullable=False, server_default="doc"),
            sa.Column("state_vector", sa.LargeBinary()),
            sa.Column("update_log", sa.LargeBinary()),
            sa.Column(
                "last_modified_by_id", sa.String(length=32),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                index=True,
            ),
            sa.Column("active_user_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    raise NotImplementedError("downgrade not supported")
