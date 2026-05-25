"""Schemas for lab reports."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


LabReportStatus = Literal["draft", "submitted", "graded"]


class LabReportCreate(BaseModel):
    class_id: str
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    status: LabReportStatus = "draft"


class LabReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None
    status: LabReportStatus | None = None


class LabReportGrade(BaseModel):
    grade: str = Field(min_length=1, max_length=16)
    feedback: str = ""


class LabReportOut(ORMModel):
    id: str
    student_id: str
    class_id: str
    title: str
    body: str
    submitted_at: datetime
    grade: str | None
    feedback: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class LabReportClassSummaryRow(BaseModel):
    """One row of the per-class breakdown a student sees on their dashboard.

    ``avg_numeric_grade`` is None when the grades for that class can't be
    parsed as numbers (e.g. letters), keeping the API honest rather than
    fabricating an average.
    """

    class_id: str
    total: int
    by_status: dict[str, int]
    avg_numeric_grade: float | None = None


class LabReportStudentSummary(BaseModel):
    student_id: str
    classes: list[LabReportClassSummaryRow]
