"""Schemas for schedule tasks (WBS) and dependencies (Gantt edges)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


TaskStatus = Literal["not_started", "in_progress", "completed", "delayed"]
DepType = Literal[
    "finish_start", "start_start", "finish_finish", "start_finish",
]


class ScheduleTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = ""
    parent_task_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    duration_days: int = 0
    assigned_to_id: str | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    status: TaskStatus = "not_started"


class ScheduleTaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    parent_task_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    duration_days: int | None = None
    assigned_to_id: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    status: TaskStatus | None = None


class ScheduleTaskOut(ORMModel):
    id: str
    construction_project_id: str
    name: str
    description: str
    parent_task_id: str | None
    start_date: date | None
    end_date: date | None
    duration_days: int
    assigned_to_id: str | None
    progress_percent: int
    status: str
    created_at: datetime
    updated_at: datetime


class ScheduleDependencyCreate(BaseModel):
    predecessor_id: str
    successor_id: str
    dependency_type: DepType = "finish_start"
    lag_days: int = 0


class ScheduleDependencyUpdate(BaseModel):
    predecessor_id: str | None = None
    successor_id: str | None = None
    dependency_type: DepType | None = None
    lag_days: int | None = None


class ScheduleDependencyOut(ORMModel):
    id: str
    predecessor_id: str
    successor_id: str
    dependency_type: str
    lag_days: int
    created_at: datetime
    updated_at: datetime
