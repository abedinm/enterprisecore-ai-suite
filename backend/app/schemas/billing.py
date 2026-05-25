"""Pydantic schemas for the billing module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PlanCatalogItem(BaseModel):
    """One row in the public pricing catalog returned by ``GET /billing/plans``."""

    plan: str
    monthly_price_id: str
    yearly_price_id: str
    base_seats: int
    monthly_usd: float
    yearly_usd: float
    formatted_monthly: str  # e.g. "$99/mo"
    formatted_yearly: str   # e.g. "$990/yr (save 17%)"


class PlanCatalogResponse(BaseModel):
    plans: list[PlanCatalogItem]
    additional_seat_usd_monthly: float
    ai_overage_usd_per_1k_tokens: float
    self_managed: bool  # True when STRIPE_SECRET_KEY isn't set


class TenantSubscriptionRead(ORMModel):
    id: str
    plan: str
    status: str
    seat_count: int
    seat_quota: int
    overage_seats: int
    interval: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool
    canceled_at: datetime | None = None
    trial_end: datetime | None = None
    currency: str
    amount_per_period: Decimal
    stripe_subscription_id: str | None = None
    stripe_customer_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CheckoutIn(BaseModel):
    plan: Literal["core", "edu", "verticals"]
    interval: Literal["month", "year"] = "month"
    success_url: str | None = Field(default=None, max_length=512)
    cancel_url: str | None = Field(default=None, max_length=512)


class CheckoutOut(BaseModel):
    checkout_url: str
    self_managed: bool  # True when Stripe isn't configured — URL points at docs


class PortalIn(BaseModel):
    return_url: str | None = Field(default=None, max_length=512)


class PortalOut(BaseModel):
    portal_url: str
    self_managed: bool


class UsageMeterRead(ORMModel):
    meter_key: str
    period_start: date
    period_end: date
    quantity: Decimal
    reported_to_stripe_at: datetime | None = None


class UsageResponse(BaseModel):
    meters: list[UsageMeterRead]
    # Plain-language convenience field — sum of paid AI cost this period.
    ai_paid_usd_this_period: float = 0.0
    ai_monthly_cap_usd: float = 0.0


class InvoiceRead(BaseModel):
    """Subset of the Stripe Invoice object we surface to the UI."""

    id: str
    number: str | None = None
    status: str
    amount_due_usd: float
    amount_paid_usd: float
    currency: str
    created: int
    period_start: int | None = None
    period_end: int | None = None
    hosted_invoice_url: str | None = None
    invoice_pdf: str | None = None


class InvoiceListResponse(BaseModel):
    invoices: list[InvoiceRead]
    self_managed: bool


class BillingActionResponse(BaseModel):
    """Generic response for cancel / resume."""

    subscription: TenantSubscriptionRead | None = None
    message: str
