"""Group projects + assignments (per-student role + weight for fairness)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicGroupProject(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_group_projects"

    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class AcademicGroupProjectAssignment(IdMixin, TenantMixin, TimestampMixin, Base):
    """One student's slot on a group project — role + workload weight.

    ``weight`` is a 0.00..1.00 share so the sum across all assignments on one
    project should be ~1.00; the fairness check is a UI surface, not a DB
    constraint, so we don't reject a temporarily-unbalanced plan.
    """

    __tablename__ = "academic_group_project_assignments"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("academic_group_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    weight: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("0"), nullable=False
    )
