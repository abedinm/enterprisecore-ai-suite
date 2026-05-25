"""Schemas for Extension of Time (EOT) requests."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


EotStatus = Literal[
    "submitted", "under_review", "approved", "rejected", "partial",
]


class EOTRequestCreate(BaseModel):
    requested_days: int = Field(default=0, ge=0)
    reason: str = ""
    supporting_evidence: str = ""
    claim_date: date | None = None
    status: EotStatus = "submitted"
    granted_days: int | None = None
    decided_at: datetime | None = None
    decided_by_id: str | None = None
    decision_notes: str = ""


class EOTRequestUpdate(BaseModel):
    requested_days: int | None = Field(default=None, ge=0)
    reason: str | None = None
    supporting_evidence: str | None = None
    claim_date: date | None = None
    status: EotStatus | None = None
    granted_days: int | None = None
    decided_at: datetime | None = None
    decided_by_id: str | None = None
    decision_notes: str | None = None


class EOTRequestOut(ORMModel):
    id: str
    construction_project_id: str
    requested_days: int
    reason: str
    supporting_evidence: str
    claim_date: date | None
    status: str
    granted_days: int | None
    decided_at: datetime | None
    decided_by_id: str | None
    decision_notes: str
    created_at: datetime
    updated_at: datetime
