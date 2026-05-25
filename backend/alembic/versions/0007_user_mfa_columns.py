"""Add MFA columns to users.

Idempotent: skips column adds if the columns already exist (Base.metadata
.create_all on a fresh DB would have made them via the updated model).

Revision ID: 0007_user_mfa
Revises: 0006_knowledge_hub
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0007_user_mfa"
down_revision: str | None = "0006_knowledge_hub"
branch_labels: str | None = None
depends_on: str | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    add_secret = not _has_column("users", "mfa_secret")
    add_enabled = not _has_column("users", "mfa_enabled")
    if not (add_secret or add_enabled):
        return
    with op.batch_alter_table("users") as batch:
        if add_secret:
            batch.add_column(sa.Column("mfa_secret", sa.String(255), nullable=True))
        if add_enabled:
            batch.add_column(sa.Column("mfa_enabled", sa.Boolean(),
                                       server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        if _has_column("users", "mfa_enabled"):
            batch.drop_column("mfa_enabled")
        if _has_column("users", "mfa_secret"):
            batch.drop_column("mfa_secret")
