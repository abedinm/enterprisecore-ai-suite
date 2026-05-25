"""Gamification models: achievements, streaks, XP.

These don't change any business outcome — they're a layer of positive
reinforcement that makes EnterpriseCore *fun to use*. The goal is to make
the boring-but-important habits (logging in, paying invoices, closing
deals, keeping records current) more emotionally rewarding.

Design contract
---------------

* **Achievement** is a static catalogue entry (key, label, icon, criteria
  description, XP value). Seeded by a startup hook from a Python dict;
  no admin UI needed.
* **UserAchievement** is the runtime "X has earned Y" join row, scoped per
  tenant + user. Idempotent: re-awarding the same key is a no-op.
* **UserStreak** tracks the user's longest current streak per "streak
  kind" (login, invoice-sent, deal-won…). Updated by a small service
  helper that handles the date math and timezone math.
* XP totals are derived: ``SUM(achievements.xp) WHERE user_id = X``.

Why tenant-scoped
-----------------

Two users with the same name in two different companies must NOT see
each other's achievements. The auto-filter ORM hook handles this without
explicit ``tenant_scope`` calls.

Why not Postgres-only
---------------------

The schema is plain SQLAlchemy mapped columns — no JSONB-only operations,
no Postgres triggers. It runs identically on SQLite (the desktop SKU)
and Postgres (the SaaS SKU).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.user import User


class Achievement(IdMixin, TimestampMixin, Base):
    """Catalogue entry — global, not tenant-scoped. Same achievement key
    exists once per install; per-user awards are in ``UserAchievement``.
    """
    # No TenantMixin here; this is shared catalogue.
    __tablename__ = "achievements"
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Lucide icon name (e.g. "Trophy", "Star", "Crown"); rendered by the
    # frontend from the lucide-react map.
    icon: Mapped[str] = mapped_column(String(40), default="Trophy", nullable=False)
    # 6-character hex (no leading #) for the badge accent. Defaults to brand.
    color: Mapped[str] = mapped_column(String(8), default="6366f1", nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # "common" | "rare" | "epic" | "legendary" — drives the frontend halo.
    tier: Mapped[str] = mapped_column(String(16), default="common", nullable=False)
    # If True, only owners/admins can unlock (e.g. "Set up SSO").
    is_admin_only: Mapped[bool] = mapped_column(default=False, nullable=False)
    # If True, hide until earned — secret achievements ("Easter egg hunter").
    is_secret: Mapped[bool] = mapped_column(default=False, nullable=False)


class UserAchievement(IdMixin, TenantMixin, TimestampMixin, Base):
    """One row per (tenant, user, achievement key) that has been unlocked."""
    __tablename__ = "user_achievements"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    achievement_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user: Mapped[User] = relationship()
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "achievement_key",
                         name="uq_user_achievements_tenant_user_key"),
    )


class UserStreak(IdMixin, TenantMixin, TimestampMixin, Base):
    """Per-user, per-kind streak. Currently tracked kinds:

    * ``login``         — consecutive days the user has signed in
    * ``invoice_sent``  — consecutive business days an invoice was sent
    * ``deal_won``      — consecutive weeks a deal closed-won

    ``current`` resets to 0 if a day is missed. ``best`` is the all-time
    high-water mark, set whenever ``current`` exceeds it.
    """
    __tablename__ = "user_streaks"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_event_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    user: Mapped[User] = relationship()
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "kind",
                         name="uq_user_streaks_tenant_user_kind"),
    )
