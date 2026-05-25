"""Schemas for site progress reports."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ProgressReportCreate(BaseModel):
    report_date: date
    overall_progress_percent: int = Field(default=0, ge=0, le=100)
    narrative: str = ""
    photos: list[str] = Field(default_factory=list)
    weather_conditions: str = ""
    workforce_count: int = 0


class ProgressReportUpdate(BaseModel):
    report_date: date | None = None
    overall_progress_percent: int | None = Field(default=None, ge=0, le=100)
    narrative: str | None = None
    photos: list[str] | None = None
    weather_conditions: str | None = None
    workforce_count: int | None = None


class ProgressReportOut(ORMModel):
    id: str
    construction_project_id: str
    report_date: date
    overall_progress_percent: int
    narrative: str
    reported_by_id: str | None
    photos: list[str]
    weather_conditions: str
    workforce_count: int
    created_at: datetime
    updated_at: datetime
