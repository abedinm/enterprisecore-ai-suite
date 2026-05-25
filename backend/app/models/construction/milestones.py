"""Construction project milestones — often tied to a payment claim."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionMilestone(IdMixin, TenantMixin, TimestampMixin, Base):
    """One milestone on the project timeline.

    Construction milestones frequently trigger a payment release (when
    ``payment_trigger`` is True), so the model carries an optional
    ``payment_amount``. The finance/CRM modules can listen for milestone
    achievements to raise an invoice — out of scope here, but the data shape
    supports that.
    """

    __tablename__ = "construction_milestones"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    actual_date: Mapped[date | None] = mapped_column(Date)
    # upcoming | achieved | missed | cancelled
    status: Mapped[str] = mapped_column(
        String(16), default="upcoming", nullable=False, index=True,
    )
    payment_trigger: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
