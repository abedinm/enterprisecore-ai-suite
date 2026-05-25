"""Schemas for advising sessions."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AdvisingCreate(BaseModel):
    student_id: str
    advisor_id: str
    scheduled_at: datetime
    notes: str = ""
    current_cgpa: Decimal | None = Field(default=None, ge=0, le=5)
    target_cgpa: Decimal | None = Field(default=None, ge=0, le=5)
    credits_completed: int = Field(default=0, ge=0)
    credits_remaining: int = Field(default=0, ge=0)


class AdvisingUpdate(BaseModel):
    student_id: str | None = None
    advisor_id: str | None = None
    scheduled_at: datetime | None = None
    notes: str | None = None
    current_cgpa: Decimal | None = Field(default=None, ge=0, le=5)
    target_cgpa: Decimal | None = Field(default=None, ge=0, le=5)
    credits_completed: int | None = Field(default=None, ge=0)
    credits_remaining: int | None = Field(default=None, ge=0)


class AdvisingOut(ORMModel):
    id: str
    student_id: str
    advisor_id: str
    scheduled_at: datetime
    notes: str
    current_cgpa: Decimal | None
    target_cgpa: Decimal | None
    credits_completed: int
    credits_remaining: int
    created_at: datetime
    updated_at: datetime


class AdvisingNoteAppend(BaseModel):
    """Body for POST /advising/sessions/{id}/notes — appends a stamped line
    rather than replacing the whole notes field."""

    text: str = Field(min_length=1, max_length=4000)


class CgpaTrendPoint(BaseModel):
    scheduled_at: datetime
    current_cgpa: Decimal | None


class CgpaTrend(BaseModel):
    student_id: str
    points: list[CgpaTrendPoint]
