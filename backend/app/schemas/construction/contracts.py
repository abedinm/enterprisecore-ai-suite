"""Schemas for construction contracts."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


ContractType = Literal["FIDIC", "NEC", "JCT", "AIA", "custom"]


class ContractCreate(BaseModel):
    contract_number: str = ""
    contract_type: ContractType = "custom"
    counterparty: str = ""
    value: Decimal = Decimal("0")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    signed_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    retention_percent: Decimal = Decimal("0")
    defects_liability_period_days: int = 0
    payment_terms: str = ""
    document_id: str | None = None


class ContractUpdate(BaseModel):
    contract_number: str | None = None
    contract_type: ContractType | None = None
    counterparty: str | None = None
    value: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    signed_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    retention_percent: Decimal | None = None
    defects_liability_period_days: int | None = None
    payment_terms: str | None = None
    document_id: str | None = None


class ContractOut(ORMModel):
    id: str
    construction_project_id: str
    contract_number: str
    contract_type: str
    counterparty: str
    value: Decimal
    currency: str
    signed_date: date | None
    start_date: date | None
    end_date: date | None
    retention_percent: Decimal
    defects_liability_period_days: int
    payment_terms: str
    document_id: str | None
    created_at: datetime
    updated_at: datetime
