"""Projects pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = ""
    status: str = "active"
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal = Decimal("0")


class ProjectOut(ORMModel):
    id: str
    name: str
    description: str
    status: str
    start_date: date | None
    end_date: date | None
    budget: Decimal


class TaskIn(BaseModel):
    project_id: str | None = None
    assignee_id: str | None = None
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    due_date: date | None = None


class TaskOut(ORMModel):
    id: str
    project_id: str | None
    assignee_id: str | None
    title: str
    description: str
    status: str
    priority: str
    due_date: date | None


class TaskStatusUpdate(BaseModel):
    status: str


class SprintIn(BaseModel):
    project_id: str
    name: str
    start_date: date
    end_date: date
    goal: str = ""


class SprintOut(ORMModel):
    id: str
    project_id: str
    name: str
    start_date: date
    end_date: date
    goal: str


class MilestoneIn(BaseModel):
    project_id: str
    title: str
    due_date: date | None = None
    status: str = "open"


class MilestoneOut(ORMModel):
    id: str
    project_id: str
    title: str
    due_date: date | None
    status: str


class TimeEntryIn(BaseModel):
    task_id: str | None = None
    user_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    minutes: int = 0


class TimeEntryOut(ORMModel):
    id: str
    task_id: str | None
    user_id: str | None
    started_at: datetime
    ended_at: datetime | None
    minutes: int


class MeetingIn(BaseModel):
    project_id: str | None = None
    title: str
    starts_at: datetime
    meeting_url: str | None = None


class MeetingOut(ORMModel):
    id: str
    project_id: str | None
    title: str
    starts_at: datetime
    meeting_url: str | None


class MeetingMinuteIn(BaseModel):
    meeting_id: str
    author_id: str | None = None
    body: str = ""


class MeetingMinuteOut(ORMModel):
    id: str
    meeting_id: str
    author_id: str | None
    body: str


class ProjectAnalyticsOut(BaseModel):
    total_projects: int
    active_projects: int
    tasks_by_status: dict[str, int]
    tasks_by_priority: dict[str, int]
    overdue_tasks: int
    upcoming_milestones: int
    total_time_minutes: int
