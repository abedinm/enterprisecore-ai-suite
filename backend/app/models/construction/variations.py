"""Variation orders — change requests with cost/time impact."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionVariation(IdMixin, TenantMixin, TimestampMixin, Base):
    """A variation request (VAR-NNN) — scope change with cost/time impact.

    ``cost_impact`` and ``time_impact_days`` are signed so a value-engineering
    variation that *reduces* cost or shortens the schedule fits the same
    model. The dashboard sums absolute totals separately from signed totals
    so customers can see both "exposure" and "net effect" at a glance.
    """

    __tablename__ = "construction_variations"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requested_by: Mapped[str] = mapped_column(
        String(200), default="", nullable=False,
    )
    cost_impact: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False,
    )
    time_impact_days: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    # pending | under_review | approved | rejected | implemented
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False, index=True,
    )
    justification: Mapped[str] = mapped_column(
        Text, default="", nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "construction_project_id", "number",
            name="uq_construction_var_project_number",
        ),
    )
