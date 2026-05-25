"""Schemas for the project risk register."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


RiskCategory = Literal[
    "safety", "financial", "schedule", "quality", "regulatory", "environmental",
]
RiskStatus = Literal["open", "mitigated", "accepted", "closed"]


class RiskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    category: RiskCategory = "safety"
    probability: int = Field(default=1, ge=1, le=5)
    impact: int = Field(default=1, ge=1, le=5)
    mitigation_plan: str = ""
    owner_id: str | None = None
    status: RiskStatus = "open"
    identified_at: datetime | None = None
    due_date: date | None = None


class RiskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    category: RiskCategory | None = None
    probability: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    mitigation_plan: str | None = None
    owner_id: str | None = None
    status: RiskStatus | None = None
    identified_at: datetime | None = None
    due_date: date | None = None


class RiskOut(ORMModel):
    id: str
    construction_project_id: str
    title: str
    description: str
    category: str
    probability: int
    impact: int
    score: int
    mitigation_plan: str
    owner_id: str | None
    status: str
    identified_at: datetime | None
    due_date: date | None
    created_at: datetime
    updated_at: datetime
