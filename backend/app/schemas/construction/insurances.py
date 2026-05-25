"""Schemas for project insurances."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


InsuranceType = Literal["CAR", "PI", "PL", "EL", "marine", "other"]


class InsuranceCreate(BaseModel):
    insurance_type: InsuranceType = "other"
    provider: str = ""
    policy_number: str = ""
    sum_insured: Decimal = Decimal("0")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    start_date: date | None = None
    expiry_date: date | None = None
    premium_amount: Decimal = Decimal("0")
    renewal_reminder_days: int = 30
    document_id: str | None = None


class InsuranceUpdate(BaseModel):
    insurance_type: InsuranceType | None = None
    provider: str | None = None
    policy_number: str | None = None
    sum_insured: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    start_date: date | None = None
    expiry_date: date | None = None
    premium_amount: Decimal | None = None
    renewal_reminder_days: int | None = None
    document_id: str | None = None


class InsuranceOut(ORMModel):
    id: str
    construction_project_id: str
    insurance_type: str
    provider: str
    policy_number: str
    sum_insured: Decimal
    currency: str
    start_date: date | None
    expiry_date: date | None
    premium_amount: Decimal
    renewal_reminder_days: int
    document_id: str | None
    created_at: datetime
    updated_at: datetime
