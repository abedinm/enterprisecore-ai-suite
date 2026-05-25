"""Schemas for project milestones."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


MilestoneStatus = Literal["upcoming", "achieved", "missed", "cancelled"]


class MilestoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    planned_date: date
    actual_date: date | None = None
    status: MilestoneStatus = "upcoming"
    payment_trigger: bool = False
    payment_amount: Decimal | None = None
    notes: str = ""


class MilestoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    planned_date: date | None = None
    actual_date: date | None = None
    status: MilestoneStatus | None = None
    payment_trigger: bool | None = None
    payment_amount: Decimal | None = None
    notes: str | None = None


class MilestoneOut(ORMModel):
    id: str
    construction_project_id: str
    name: str
    planned_date: date
    actual_date: date | None
    status: str
    payment_trigger: bool
    payment_amount: Decimal | None
    notes: str
    created_at: datetime
    updated_at: datetime
