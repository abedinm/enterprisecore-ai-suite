"""Pydantic schemas for the multi-entity consolidation surface."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---- Subsidiary entities -------------------------------------------------
class SubsidiaryEntityIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=40)
    country: str = Field(default="US", min_length=2, max_length=2)
    functional_currency: str = Field(default="USD", min_length=3, max_length=3)
    reporting_currency: str = Field(default="USD", min_length=3, max_length=3)
    parent_entity_id: str | None = None
    is_main: bool = False
    inception_date: date | None = None
    is_active: bool = True


class SubsidiaryEntityPatch(BaseModel):
    name: str | None = None
    code: str | None = None
    country: str | None = None
    functional_currency: str | None = None
    reporting_currency: str | None = None
    parent_entity_id: str | None = None
    is_main: bool | None = None
    inception_date: date | None = None
    is_active: bool | None = None


class SubsidiaryEntityOut(ORMModel):
    id: str
    name: str
    code: str
    country: str
    functional_currency: str
    reporting_currency: str
    parent_entity_id: str | None = None
    is_main: bool
    inception_date: date | None = None
    is_active: bool


# ---- Intercompany transactions ------------------------------------------
class IntercompanyTransactionIn(BaseModel):
    from_entity_id: str
    to_entity_id: str
    kind: str = "transfer"  # loan | management_fee | cost_allocation | transfer
    amount: Decimal
    currency: str = "USD"
    transaction_date: date
    description: str | None = None
    eliminates_on_consolidation: bool = True
    matched_invoice_id: str | None = None


class IntercompanyTransactionOut(ORMModel):
    id: str
    from_entity_id: str
    to_entity_id: str
    kind: str
    amount: Decimal
    currency: str
    transaction_date: date
    description: str | None = None
    eliminates_on_consolidation: bool
    matched_invoice_id: str | None = None


# ---- FX adjustments -----------------------------------------------------
class FxRevaluationIn(BaseModel):
    entity_id: str
    period_end: date


class FxAdjustmentOut(ORMModel):
    id: str
    entity_id: str
    account_kind: str
    original_currency: str
    original_amount: Decimal
    reporting_currency: str
    opening_rate: Decimal
    closing_rate: Decimal
    fx_gain_loss: Decimal
    period_end: date


# ---- Consolidation report shapes ----------------------------------------
class ConsolidatedBalanceSheetOut(BaseModel):
    as_of: date
    target_currency: str
    entities: list[dict[str, Any]]
    eliminations: list[dict[str, Any]]
    consolidated: dict[str, Decimal]
    cta: Decimal


class ConsolidatedPnLOut(BaseModel):
    period_start: date
    period_end: date
    target_currency: str
    entities: list[dict[str, Any]]
    eliminations: list[dict[str, Any]]
    consolidated: dict[str, Decimal]
