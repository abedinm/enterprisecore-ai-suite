"""Schemas for the top-level ConstructionProject record."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


ProjectType = Literal["residential", "commercial", "industrial", "infrastructure"]
ProjectStatus = Literal[
    "planning", "active", "on_hold", "completed", "cancelled",
]


class ConstructionProjectCreate(BaseModel):
    generic_project_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    client_name: str = ""
    location: str = ""
    project_type: ProjectType
    contract_value: Decimal = Decimal("0")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    start_date: date | None = None
    expected_end_date: date | None = None
    actual_end_date: date | None = None
    status: ProjectStatus = "planning"
    description: str = ""


class ConstructionProjectUpdate(BaseModel):
    generic_project_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    client_name: str | None = None
    location: str | None = None
    project_type: ProjectType | None = None
    contract_value: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    start_date: date | None = None
    expected_end_date: date | None = None
    actual_end_date: date | None = None
    status: ProjectStatus | None = None
    description: str | None = None


class ConstructionProjectOut(ORMModel):
    id: str
    generic_project_id: str | None
    name: str
    client_name: str
    location: str
    project_type: str
    contract_value: Decimal
    currency: str
    start_date: date | None
    expected_end_date: date | None
    actual_end_date: date | None
    status: str
    description: str
    created_at: datetime
    updated_at: datetime
