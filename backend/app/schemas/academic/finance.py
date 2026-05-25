"""Schemas for student finance + scholarship board."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


FinanceKind = Literal["allowance", "expense", "scholarship", "loan"]


class StudentFinanceCreate(BaseModel):
    kind: FinanceKind
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    occurred_on: date
    category: str = ""
    note: str = ""


class StudentFinanceUpdate(BaseModel):
    kind: FinanceKind | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    occurred_on: date | None = None
    category: str | None = None
    note: str | None = None


class StudentFinanceOut(ORMModel):
    id: str
    student_id: str
    kind: str
    amount: Decimal
    currency: str
    occurred_on: date
    category: str
    note: str
    created_at: datetime
    updated_at: datetime


class ScholarshipCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    provider: str = ""
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    eligibility: str = ""
    deadline: date | None = None
    url: str | None = None


class ScholarshipUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    provider: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    eligibility: str | None = None
    deadline: date | None = None
    url: str | None = None


class ScholarshipOut(ORMModel):
    id: str
    name: str
    provider: str
    amount: Decimal
    currency: str
    eligibility: str
    deadline: date | None
    url: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Monthly summary / trend / budgets
# ---------------------------------------------------------------------------


class FinanceCategoryTotal(BaseModel):
    category: str
    amount: Decimal


class MonthlySummary(BaseModel):
    month: str  # YYYY-MM
    currency: str
    total_allowance: Decimal
    total_scholarship: Decimal
    total_loan: Decimal
    total_expense: Decimal
    net: Decimal
    savings_rate: float  # 0..1, share of inflow not spent
    expense_by_category: list[FinanceCategoryTotal]


class TrendPoint(BaseModel):
    month: str  # YYYY-MM
    income: Decimal
    expense: Decimal
    net: Decimal


class FinanceTrend(BaseModel):
    currency: str
    points: list[TrendPoint]


class BudgetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=120)
    monthly_limit: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class BudgetUpdate(BaseModel):
    monthly_limit: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class BudgetOut(ORMModel):
    id: str
    student_id: str
    category: str
    monthly_limit: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


class BudgetStatusRow(BaseModel):
    """Per-category snapshot for the current month."""

    category: str
    monthly_limit: Decimal
    spent: Decimal
    remaining: Decimal
    over_budget: bool
    over_by: Decimal


class BudgetStatusOut(BaseModel):
    month: str
    currency: str
    rows: list[BudgetStatusRow]
