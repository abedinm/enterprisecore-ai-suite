"""Classes (course offerings) and student enrollments.

A ``Class`` is one offering of a course in a specific semester, taught by one
teacher. Attendance and timetable both hang off this row, so it sits in its
own module to keep the import graph readable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (DateTime, ForeignKey, Integer, String,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicClass(IdMixin, TenantMixin, TimestampMixin, Base):
    """One section of a course taught in one semester."""

    __tablename__ = "academic_classes"

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    course_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    teacher_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semester_id: Mapped[str] = mapped_column(
        ForeignKey("academic_semesters.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    credit_hours: Mapped[int] = mapped_column(Integer, default=3, nullable=False)


class AcademicClassEnrollment(IdMixin, TenantMixin, TimestampMixin, Base):
    """Many-to-many between a class and the students enrolled in it.

    The unique constraint on ``(class_id, student_id)`` is what makes the
    "is this student in this class?" check a single index lookup rather than
    a table scan, and is also the safeguard that catches a double-enroll.
    """

    __tablename__ = "academic_class_enrollments"

    class_id: Mapped[str] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # active | dropped | completed
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "class_id", "student_id",
            name="uq_academic_enrollment_class_student",
        ),
    )
