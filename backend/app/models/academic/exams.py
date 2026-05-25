"""Exam scheduling — one row per exam, linked to a course code + room."""
from __future__ import annotations

from datetime import date, time

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicExam(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "academic_exams"

    course_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    room_id: Mapped[str | None] = mapped_column(
        ForeignKey("academic_rooms.id", ondelete="SET NULL"), index=True
    )
    # JSON list[str] — topics/sections the exam will cover. Stored as JSON so
    # adding a topic doesn't require a join table for a list-of-strings.
    syllabus_topics: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # easy | medium | hard
    difficulty: Mapped[str] = mapped_column(
        String(16), default="medium", nullable=False
    )
