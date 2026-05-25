"""Schemas for toolbox talks."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ToolboxTalkCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    conducted_at: datetime | None = None
    attendees_count: int = Field(default=0, ge=0)
    key_points: str = ""
    attachments: list[str] = Field(default_factory=list)
    notes: str = ""


class ToolboxTalkUpdate(BaseModel):
    topic: str | None = Field(default=None, min_length=1, max_length=300)
    conducted_at: datetime | None = None
    attendees_count: int | None = Field(default=None, ge=0)
    key_points: str | None = None
    attachments: list[str] | None = None
    notes: str | None = None


class ToolboxTalkOut(ORMModel):
    id: str
    construction_project_id: str
    topic: str
    conducted_by_id: str | None
    conducted_at: datetime | None
    attendees_count: int
    key_points: str
    attachments: list[str]
    notes: str
    created_at: datetime
    updated_at: datetime
