"""Schemas for attendance — bulk-mark payloads + report summaries."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


AttendanceStatus = Literal["present", "absent", "late", "excused"]


class AttendanceRecordIn(BaseModel):
    """One entry in the bulk-mark payload — student + status."""

    student_id: str
    status: AttendanceStatus


class BulkAttendanceIn(BaseModel):
    """Mark attendance for a whole class session in one call.

    ``session_date`` is the calendar day the class met; ``records`` is the
    list of (student, status) pairs. Existing rows for the same
    (class, student, date) are overwritten so a teacher can correct a mark
    by re-submitting.
    """

    session_date: date
    records: list[AttendanceRecordIn] = Field(min_length=1)


class AttendanceOut(ORMModel):
    id: str
    class_id: str
    student_id: str
    session_date: date
    status: str
    recorded_by_id: str | None
    created_at: datetime
    updated_at: datetime


class AttendanceSummary(BaseModel):
    """Roll-up for one student in one class."""

    student_id: str
    present: int
    absent: int
    late: int
    excused: int
    total: int
    percentage: float


class ClassAttendanceReport(BaseModel):
    """Per-student rollup for one class — used by the teacher's report view."""

    class_id: str
    students: list[AttendanceSummary]
