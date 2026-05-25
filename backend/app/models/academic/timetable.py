"""Timetable slots — one row per (class, day, start_time) inside a semester.

Conflict detection (room double-booked, teacher double-booked, class already
scheduled at that slot) is enforced in the service layer rather than as a
table-level constraint because a partial overlap test needs interval math
that SQLite doesn't express cleanly as a single CHECK.
"""
from __future__ import annotations

from datetime import time

from sqlalchemy import ForeignKey, Index, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicTimetableSlot(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_timetable_slots"

    class_id: Mapped[str] = mapped_column(
        ForeignKey("academic_classes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    room_id: Mapped[str] = mapped_column(
        ForeignKey("academic_rooms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    semester_id: Mapped[str] = mapped_column(
        ForeignKey("academic_semesters.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # 0 = Monday, 6 = Sunday (ISO weekday minus 1, matching Python's
    # datetime.weekday()). Store as int for cheap "all slots on day N" lookups.
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    __table_args__ = (
        # Composite index for the common "all of this semester's slots on this
        # day" query the schedule views run on every page load.
        Index(
            "ix_academic_timetable_semester_day",
            "semester_id", "day_of_week",
        ),
    )
