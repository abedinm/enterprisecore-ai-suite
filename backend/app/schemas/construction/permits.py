"""Schemas for permits."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


PermitStatus = Literal[
    "draft", "submitted", "under_review", "approved", "rejected", "expired",
]


class PermitCreate(BaseModel):
    permit_type: str = Field(default="", max_length=120)
    issuing_authority: str = ""
    application_date: date | None = None
    approval_date: date | None = None
    expiry_date: date | None = None
    status: PermitStatus = "draft"
    reference_number: str = ""
    conditions: str = ""
    document_id: str | None = None


class PermitUpdate(BaseModel):
    permit_type: str | None = None
    issuing_authority: str | None = None
    application_date: date | None = None
    approval_date: date | None = None
    expiry_date: date | None = None
    status: PermitStatus | None = None
    reference_number: str | None = None
    conditions: str | None = None
    document_id: str | None = None


class PermitOut(ORMModel):
    id: str
    construction_project_id: str
    permit_type: str
    issuing_authority: str
    application_date: date | None
    approval_date: date | None
    expiry_date: date | None
    status: str
    reference_number: str
    conditions: str
    document_id: str | None
    created_at: datetime
    updated_at: datetime
