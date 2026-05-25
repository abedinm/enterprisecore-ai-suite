"""Schemas for study profiles + computed matches."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StudyProfileCreate(BaseModel):
    university: str = ""
    department: str = ""
    semester: str = ""
    courses: list[str] = Field(default_factory=list)
    goals: str = ""
    preferred_time: str = ""
    study_style: str = ""
    online_only: bool = False
    is_public: bool = True


class StudyProfileUpdate(BaseModel):
    university: str | None = None
    department: str | None = None
    semester: str | None = None
    courses: list[str] | None = None
    goals: str | None = None
    preferred_time: str | None = None
    study_style: str | None = None
    online_only: bool | None = None
    is_public: bool | None = None


class StudyProfileOut(ORMModel):
    id: str
    student_id: str
    university: str
    department: str
    semester: str
    courses: list[str]
    goals: str
    preferred_time: str
    study_style: str
    online_only: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime


class StudyMatchOut(ORMModel):
    id: str
    student_a_id: str
    student_b_id: str
    score: int
    created_at: datetime
    updated_at: datetime


class MatchPreview(BaseModel):
    """A match plus enough about the other student to render a card."""

    match_id: str
    score: int
    student_id: str
    full_name: str
    department: str
    semester: str
    shared_courses: list[str]


class CoursesUpdateIn(BaseModel):
    """Body for POST /study-match/profiles/me/courses — replaces the list
    wholesale (the UI shows a chip editor; partial-updates aren't needed)."""

    courses: list[str] = Field(default_factory=list)


class ConnectOut(BaseModel):
    notification_id: str
    other_student_id: str
