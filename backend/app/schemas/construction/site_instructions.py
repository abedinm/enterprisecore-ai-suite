"""Schemas for site instructions (SI-NNN)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


SiStatus = Literal[
    "issued", "acknowledged", "in_progress", "completed", "disputed",
]


class SiteInstructionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    issued_to: str = ""
    issued_at: datetime | None = None
    response_required_by: date | None = None
    status: SiStatus = "issued"
    response: str | None = None
    responded_at: datetime | None = None


class SiteInstructionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    issued_to: str | None = None
    issued_at: datetime | None = None
    response_required_by: date | None = None
    status: SiStatus | None = None
    response: str | None = None
    responded_at: datetime | None = None


class SiteInstructionOut(ORMModel):
    id: str
    construction_project_id: str
    number: str
    title: str
    description: str
    issued_by_id: str | None
    issued_to: str
    issued_at: datetime | None
    response_required_by: date | None
    status: str
    response: str | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime
