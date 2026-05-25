"""Schemas for the RACI matrix."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RaciEntryCreate(BaseModel):
    activity: str = Field(min_length=1, max_length=300)
    responsible_user_id: str | None = None
    accountable_user_id: str | None = None
    consulted: list[str] = Field(default_factory=list)
    informed: list[str] = Field(default_factory=list)
    notes: str = ""


class RaciEntryUpdate(BaseModel):
    activity: str | None = Field(default=None, min_length=1, max_length=300)
    responsible_user_id: str | None = None
    accountable_user_id: str | None = None
    consulted: list[str] | None = None
    informed: list[str] | None = None
    notes: str | None = None


class RaciEntryOut(ORMModel):
    id: str
    construction_project_id: str
    activity: str
    responsible_user_id: str | None
    accountable_user_id: str | None
    consulted: list[str]
    informed: list[str]
    notes: str
    created_at: datetime
    updated_at: datetime
