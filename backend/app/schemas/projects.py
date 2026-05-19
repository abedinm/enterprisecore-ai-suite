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
    color: str = "#4F46E5"
    progress: int = 0


class ProjectOut(ORMModel):
    id: str
    name: str
    description: str
    status: str
    start_date: date | None
    end_date: date | None
    budget: Decimal
    color: str
    progress: int


class TaskIn(BaseModel):
    project_id: str | None = None
    sprint_id: str | None = None
    assignee_id: str | None = None
    title: str
    description: str = ""
    status: str = "todo"
    priority: str = "medium"
    due_date: date | None = None
    start_date: date | None = None
    estimated_hours: Decimal = Decimal("0")
    actual_hours: Decimal = Decimal("0")
    story_points: int = 0
    position: int = 0
    tags: str = ""


class TaskOut(ORMModel):
    id: str
    project_id: str | None
    sprint_id: str | None
    assignee_id: str | None
    title: str
    description: str
    status: str
    priority: str
    due_date: date | None
    start_date: date | None
    estimated_hours: Decimal
    actual_hours: Decimal
    story_points: int
    position: int
    tags: str


class TaskStatusUpdate(BaseModel):
    status: str
    position: int | None = None


class SprintIn(BaseModel):
    project_id: str
    name: str
    start_date: date
    end_date: date
    goal: str = ""
    status: str = "planned"
    capacity_points: int = 0


class SprintOut(ORMModel):
    id: str
    project_id: str
    name: str
    start_date: date
    end_date: date
    goal: str
    status: str
    capacity_points: int


class MilestoneIn(BaseModel):
    project_id: str
    title: str
    description: str = ""
    due_date: date | None = None
    status: str = "open"
    progress: int = 0


class MilestoneOut(ORMModel):
    id: str
    project_id: str
    title: str
    description: str
    due_date: date | None
    status: str
    progress: int


class TimeEntryIn(BaseModel):
    task_id: str | None = None
    user_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    minutes: int = 0
    notes: str = ""
    is_billable: bool = True


class TimeEntryOut(ORMModel):
    id: str
    task_id: str | None
    user_id: str | None
    started_at: datetime
    ended_at: datetime | None
    minutes: int
    notes: str
    is_billable: bool


class MeetingIn(BaseModel):
    project_id: str | None = None
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = None
    meeting_url: str | None = None
    agenda: str = ""
    attendees: str = ""
    status: str = "scheduled"


class MeetingOut(ORMModel):
    id: str
    project_id: str | None
    title: str
    starts_at: datetime
    ends_at: datetime | None
    location: str | None
    meeting_url: str | None
    agenda: str
    attendees: str
    status: str


class MeetingMinuteIn(BaseModel):
    meeting_id: str = ""
    author_id: str | None = None
    body: str = ""
    decisions: str = ""
    action_items: str = ""


class MeetingMinuteOut(ORMModel):
    id: str
    meeting_id: str
    author_id: str | None
    body: str
    decisions: str
    action_items: str


class ResourceIn(BaseModel):
    name: str
    role: str = ""
    hourly_rate: Decimal = Decimal("0")
    capacity_hours_per_week: Decimal = Decimal("40")
    skills: str = ""
    is_active: bool = True


class ResourceOut(ORMModel):
    id: str
    name: str
    role: str
    hourly_rate: Decimal
    capacity_hours_per_week: Decimal
    skills: str
    is_active: bool


class ResourceAllocationIn(BaseModel):
    resource_id: str
    project_id: str
    start_date: date
    end_date: date
    allocation_pct: Decimal = Decimal("100")
    notes: str = ""


class ResourceAllocationOut(ORMModel):
    id: str
    resource_id: str
    project_id: str
    start_date: date
    end_date: date
    allocation_pct: Decimal
    notes: str


class TaskDependencyIn(BaseModel):
    task_id: str
    depends_on_task_id: str
    dep_type: str = "finish_to_start"


class TaskDependencyOut(ORMModel):
    id: str
    task_id: str
    depends_on_task_id: str
    dep_type: str


class ProjectAnalyticsOut(BaseModel):
    total_projects: int
    active_projects: int
    completed_projects: int
    tasks_by_status: dict[str, int]
    tasks_by_priority: dict[str, int]
    overdue_tasks: int
    upcoming_milestones: int
    total_time_minutes: int
    total_tasks: int
    completed_tasks: int
    completion_rate: float
    avg_task_duration_days: float
    sprint_burn_rate: dict[str, int]
    workload_by_assignee: list[dict]
    project_progress: list[dict]
    upcoming_deadlines: list[dict]
