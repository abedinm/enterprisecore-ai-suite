"""Academic core entities — semesters and rooms.

These are the shared building blocks every other academic submodule references
(classes, timetable, exams). Kept in their own module so the dependency graph
stays simple: ``core`` has no FK out to other academic tables.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class AcademicSemester(IdMixin, TenantMixin, TimestampMixin, Base):
    """One academic semester / term. Only one row should carry ``is_current``;
    the service layer enforces the singleton when promoting a new one."""

    __tablename__ = "academic_semesters"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )


class AcademicRoom(IdMixin, TenantMixin, TimestampMixin, Base):
    """A physical (or virtual) room available for scheduling classes/exams."""

    __tablename__ = "academic_rooms"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    building: Mapped[str | None] = mapped_column(String(120))
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
