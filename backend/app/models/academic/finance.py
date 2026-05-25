"""Student finance — per-student income/expense entries and a scholarship board."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicStudentFinanceRecord(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_student_finance_records"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # allowance | expense | scholarship | loan
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # ISO 4217 (matches the rest of the suite)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, index=True
    )
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class AcademicScholarship(IdMixin, TenantMixin, TimestampMixin, Base):
    """Public scholarship board — listed by registrar/admin, viewed by anyone."""

    __tablename__ = "academic_scholarships"

    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String(180), default="", nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    eligibility: Mapped[str] = mapped_column(Text, default="", nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date, index=True)
    url: Mapped[str | None] = mapped_column(String(500))


class AcademicStudentBudget(IdMixin, TenantMixin, TimestampMixin, Base):
    """A student's monthly spending limit for one category (e.g. ``food``).

    One row per (student, category). The "over budget" warning compares this
    against the sum of ``AcademicStudentFinanceRecord`` rows with kind
    ``expense`` in the current month.
    """

    __tablename__ = "academic_student_budgets"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    category: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True,
    )
    monthly_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id", "category",
            name="uq_academic_student_budget_student_category",
        ),
    )
