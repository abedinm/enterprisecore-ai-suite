"""Extension of Time (EOT) requests — schedule slip claims."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionEOTRequest(IdMixin, TenantMixin, TimestampMixin, Base):
    """A formal claim for additional contract time.

    ``granted_days`` is nullable so an in-flight request can persist without
    a decision yet. Once the request is decided, the dashboard rollup totals
    the pending and approved days separately.
    """

    __tablename__ = "construction_eot_requests"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    requested_days: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    supporting_evidence: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )
    claim_date: Mapped[date | None] = mapped_column(Date)
    # submitted | under_review | approved | rejected | partial
    status: Mapped[str] = mapped_column(
        String(16), default="submitted", nullable=False, index=True,
    )
    granted_days: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )
    decision_notes: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )
