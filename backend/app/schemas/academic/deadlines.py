"""Schemas for assignment deadlines + submissions."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


SubmissionStatus = Literal["not_started", "in_progress", "submitted", "late"]


class AssignmentCreate(BaseModel):
    class_id: str
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    deadline: datetime
    weight: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    submission_link: str = ""


class AssignmentUpdate(BaseModel):
    class_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    deadline: datetime | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=100)
    submission_link: str | None = None


class AssignmentOut(ORMModel):
    id: str
    class_id: str
    title: str
    description: str
    deadline: datetime
    weight: Decimal
    submission_link: str
    created_at: datetime
    updated_at: datetime


class SubmissionCreate(BaseModel):
    assignment_id: str
    status: SubmissionStatus = "in_progress"
    word_count: int = Field(default=0, ge=0)
    submission_url: str = ""
    notes: str = ""


class SubmissionUpdate(BaseModel):
    status: SubmissionStatus | None = None
    word_count: int | None = Field(default=None, ge=0)
    submission_url: str | None = None
    notes: str | None = None


class SubmissionOut(ORMModel):
    id: str
    assignment_id: str
    student_id: str
    submitted_at: datetime
    status: str
    word_count: int
    submission_url: str
    notes: str
    created_at: datetime
    updated_at: datetime


class StudentSubmissionUpsert(BaseModel):
    """Body for POST /deadlines/assignments/{id}/submissions — upserts the
    caller's submission rather than spawning duplicates. ``status`` is
    optional; the service infers ``submitted`` if a URL was supplied."""

    submission_url: str = ""
    notes: str = ""
    word_count: int = Field(default=0, ge=0)
    status: SubmissionStatus | None = None


class SubmissionStatusPatch(BaseModel):
    status: SubmissionStatus


class UpcomingAssignmentOut(BaseModel):
    """Augmented view of an assignment for the student dashboard.

    ``submission_status`` is the student's own state on that assignment
    ("not_started" if no submission row exists yet)."""

    assignment: AssignmentOut
    is_overdue: bool
    submission_status: str
