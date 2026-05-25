"""Schemas for group projects + assignments."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class GroupProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    class_id: str
    description: str = ""
    deadline: datetime


class GroupProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    class_id: str | None = None
    description: str | None = None
    deadline: datetime | None = None


class GroupProjectOut(ORMModel):
    id: str
    name: str
    class_id: str
    description: str
    deadline: datetime
    created_at: datetime
    updated_at: datetime


class GroupAssignmentCreate(BaseModel):
    project_id: str
    student_id: str
    role: str = ""
    weight: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class GroupAssignmentUpdate(BaseModel):
    role: str | None = None
    weight: Decimal | None = Field(default=None, ge=0, le=1)


class GroupAssignmentOut(ORMModel):
    id: str
    project_id: str
    student_id: str
    role: str
    weight: Decimal
    created_at: datetime
    updated_at: datetime


class AutoBalanceIn(BaseModel):
    """Body for POST /group-projects/{id}/auto-balance — caller passes the
    set of students to distribute roles across. The handler returns suggested
    assignments (and persists them when ``?commit=true`` is set)."""

    student_ids: list[str] = Field(min_length=1)
    # Optional explicit role list — caller can override the defaults. Empty
    # means the service falls back to a built-in role palette.
    roles: list[str] = Field(default_factory=list)


class AutoBalanceSuggestion(BaseModel):
    student_id: str
    role: str
    weight: Decimal


class AutoBalanceOut(BaseModel):
    project_id: str
    suggestions: list[AutoBalanceSuggestion]
    committed: bool


class FairnessOut(BaseModel):
    project_id: str
    balanced: bool
    weight_std_dev: float
    weight_total: float
    role_coverage: int
    suggestions: list[str]
