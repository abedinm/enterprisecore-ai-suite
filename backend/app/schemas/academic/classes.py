"""Schemas for AcademicClass and AcademicClassEnrollment."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


EnrollStatus = Literal["active", "dropped", "completed"]


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    course_code: str = Field(min_length=1, max_length=60)
    teacher_id: str
    semester_id: str
    credit_hours: int = Field(default=3, ge=0, le=20)


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    course_code: str | None = Field(default=None, min_length=1, max_length=60)
    teacher_id: str | None = None
    semester_id: str | None = None
    credit_hours: int | None = Field(default=None, ge=0, le=20)


class ClassOut(ORMModel):
    id: str
    name: str
    course_code: str
    teacher_id: str
    teacher_name: str | None = None  # Populated by endpoint via join on users
    semester_id: str
    credit_hours: int
    created_at: datetime
    updated_at: datetime


class EnrollmentCreate(BaseModel):
    class_id: str
    student_id: str
    status: EnrollStatus = "active"


class EnrollmentUpdate(BaseModel):
    status: EnrollStatus | None = None


class EnrollmentOut(ORMModel):
    id: str
    class_id: str
    student_id: str
    enrolled_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime
