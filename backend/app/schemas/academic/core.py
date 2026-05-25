"""Schemas for AcademicSemester / AcademicRoom."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---- AcademicSemester ----------------------------------------------------
class SemesterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    is_current: bool = False


class SemesterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None


class SemesterOut(ORMModel):
    id: str
    name: str
    start_date: date
    end_date: date
    is_current: bool
    created_at: datetime
    updated_at: datetime


# ---- AcademicRoom ---------------------------------------------------------
class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    building: str | None = Field(default=None, max_length=120)
    capacity: int = Field(default=0, ge=0)


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    building: str | None = Field(default=None, max_length=120)
    capacity: int | None = Field(default=None, ge=0)


class RoomOut(ORMModel):
    id: str
    name: str
    building: str | None
    capacity: int
    created_at: datetime
    updated_at: datetime
