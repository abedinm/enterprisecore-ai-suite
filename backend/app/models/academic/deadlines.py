"""Assignment deadlines + per-student submission state."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicAssignment(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_assignments"

    class_id: Mapped[str] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Weight as 0..100 (percentage of final grade). Numeric(4,2) handles up to
    # 99.99 which is the realistic ceiling for a single assignment.
    weight: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("0"), nullable=False
    )
    submission_link: Mapped[str] = mapped_column(
        String(500), default="", nullable=False
    )


class AcademicAssignmentSubmission(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_assignment_submissions"

    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("academic_assignments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # not_started | in_progress | submitted | late
    status: Mapped[str] = mapped_column(
        String(16), default="not_started", nullable=False, index=True
    )
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submission_url: Mapped[str] = mapped_column(
        String(500), default="", nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "student_id",
            name="uq_academic_submission_assignment_student",
        ),
    )
