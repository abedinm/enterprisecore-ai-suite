"""Attendance — one row per (class, student, session date)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicAttendanceRecord(IdMixin, TenantMixin, TimestampMixin, Base):
    """A single attendance mark.

    Status is constrained at the service/schema layer to one of
    ``present | absent | late | excused`` rather than via a CHECK constraint
    so adding new statuses doesn't require a migration.
    """

    __tablename__ = "academic_attendance_records"

    class_id: Mapped[str] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # present | absent | late | excused
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "class_id", "student_id", "session_date",
            name="uq_academic_attendance_class_student_date",
        ),
    )
