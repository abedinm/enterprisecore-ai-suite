"""Project insurances — CAR, PI, PL, EL, marine, etc."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ConstructionInsurance(IdMixin, TenantMixin, TimestampMixin, Base):
    """An insurance policy on the project.

    Standard policy types:
        - CAR (Contractor's All Risks)
        - PI (Professional Indemnity)
        - PL (Public Liability)
        - EL (Employer's Liability)
        - marine
        - other
    ``renewal_reminder_days`` controls how far ahead the dashboard surfaces
    an "expiring soon" warning. Default 30 days.
    """

    __tablename__ = "construction_insurances"

    construction_project_id: Mapped[str] = mapped_column(
        ForeignKey("construction_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # CAR | PI | PL | EL | marine | other
    insurance_type: Mapped[str] = mapped_column(
        String(16), default="other", nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(200), default="", nullable=False,
    )
    policy_number: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, index=True,
    )
    sum_insured: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    premium_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False,
    )
    renewal_reminder_days: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False,
    )
    document_id: Mapped[str | None] = mapped_column(String(64))
