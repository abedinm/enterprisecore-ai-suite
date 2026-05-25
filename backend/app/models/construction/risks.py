"""Construction risk register — one row per identified risk."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionRisk(IdMixin, TenantMixin, TimestampMixin, Base):
    """A risk on the project's risk register.

    The ``score`` column is the cached product ``probability * impact`` (both
    1-5) so the dashboard can bucket risks into low/medium/high/critical
    without recomputing on every read. The service layer keeps it in sync.
    """

    __tablename__ = "construction_risks"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # safety | financial | schedule | quality | regulatory | environmental
    category: Mapped[str] = mapped_column(
        String(24), default="safety", nullable=False, index=True,
    )
    probability: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    impact: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Cached probability * impact, refreshed by the service layer.
    score: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    mitigation_plan: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    # open | mitigated | accepted | closed
    status: Mapped[str] = mapped_column(
        String(16), default="open", nullable=False, index=True,
    )
    identified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    due_date: Mapped[date | None] = mapped_column(Date)
