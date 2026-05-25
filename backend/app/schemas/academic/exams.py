"""Schemas for exam scheduling."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


Difficulty = Literal["easy", "medium", "hard"]


class ExamCreate(BaseModel):
    course_code: str = Field(min_length=1, max_length=60)
    exam_date: date
    start_time: time
    duration_min: int = Field(default=120, ge=10, le=600)
    room_id: str | None = None
    syllabus_topics: list[str] = Field(default_factory=list)
    difficulty: Difficulty = "medium"


class ExamUpdate(BaseModel):
    course_code: str | None = Field(default=None, min_length=1, max_length=60)
    exam_date: date | None = None
    start_time: time | None = None
    duration_min: int | None = Field(default=None, ge=10, le=600)
    room_id: str | None = None
    syllabus_topics: list[str] | None = None
    difficulty: Difficulty | None = None


class ExamOut(ORMModel):
    id: str
    course_code: str
    exam_date: date
    start_time: time
    duration_min: int
    room_id: str | None
    syllabus_topics: list[str]
    difficulty: str
    created_at: datetime
    updated_at: datetime


class ExamScheduleRoomIn(BaseModel):
    room_id: str


class ExamCalendarDay(BaseModel):
    exam_date: date
    exams: list[ExamOut]
