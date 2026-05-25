"""Schemas for variation orders (VAR-NNN)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


VariationStatus = Literal[
    "pending", "under_review", "approved", "rejected", "implemented",
]


class VariationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    requested_by: str = ""
    cost_impact: Decimal = Decimal("0")
    time_impact_days: int = 0
    status: VariationStatus = "pending"
    justification: str = ""
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by_id: str | None = None


class VariationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    requested_by: str | None = None
    cost_impact: Decimal | None = None
    time_impact_days: int | None = None
    status: VariationStatus | None = None
    justification: str | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by_id: str | None = None


class VariationOut(ORMModel):
    id: str
    construction_project_id: str
    number: str
    title: str
    description: str
    requested_by: str
    cost_impact: Decimal
    time_impact_days: int
    status: str
    justification: str
    submitted_at: datetime | None
    decided_at: datetime | None
    decided_by_id: str | None
    created_at: datetime
    updated_at: datetime
