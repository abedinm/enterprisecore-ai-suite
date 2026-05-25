"""Gamification: achievements, user_achievements, user_streaks.

Three new tables that power EnterpriseCore's positive-reinforcement layer:

* ``achievements``       — global catalogue (no tenant_id; same key across
                          every tenant). Seeded from
                          ``app.services.gamification.SEED_ACHIEVEMENTS``
                          on app startup.
* ``user_achievements``  — per-user unlock rows, tenant-scoped.
* ``user_streaks``       — per-user, per-kind streak counters.

Idempotent: every create is gated on an inspector lookup so the migration
is safe to re-run against a DB built via ``Base.metadata.create_all`` (the
test suite's pattern).

Revision ID: 0028_gamification
Revises:     0027_refresh_token_device
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_gamification"
down_revision: str | None = "0027_refresh_token_device"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _table_names()

    if "achievements" not in existing:
        op.create_table(
            "achievements",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("key", sa.String(80), nullable=False, unique=True),
            sa.Column("label", sa.String(140), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("icon", sa.String(40), nullable=False, server_default="Trophy"),
            sa.Column("color", sa.String(8), nullable=False, server_default="6366f1"),
            sa.Column("xp", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("tier", sa.String(16), nullable=False, server_default="common"),
            sa.Column("is_admin_only", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_achievements_key", "achievements", ["key"])

    if "user_achievements" not in existing:
        op.create_table(
            "user_achievements",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("achievement_key", sa.String(80), nullable=False, index=True),
            sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "user_id", "achievement_key",
                                name="uq_user_achievements_tenant_user_key"),
        )

    if "user_streaks" not in existing:
        op.create_table(
            "user_streaks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("kind", sa.String(40), nullable=False, index=True),
            sa.Column("current", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("best", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_event_on", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "user_id", "kind",
                                name="uq_user_streaks_tenant_user_kind"),
        )


def downgrade() -> None:
    existing = _table_names()
    if "user_streaks" in existing:
        op.drop_table("user_streaks")
    if "user_achievements" in existing:
        op.drop_table("user_achievements")
    if "achievements" in existing:
        op.drop_table("achievements")
