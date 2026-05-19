"""CRM pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    tags: str = "[]"


class ContactOut(ORMModel):
    id: str
    name: str
    company: str | None
    email: str | None
    phone: str | None
    tags: str


class LeadIn(BaseModel):
    contact_id: str | None = None
    source: str | None = None
    status: str = "new"
    score: int = 0
    notes: str = ""


class LeadOut(ORMModel):
    id: str
    contact_id: str | None
    source: str | None
    status: str
    score: int
    notes: str


class DealIn(BaseModel):
    contact_id: str | None = None
    title: str
    stage: str = "qualified"
    value: Decimal = Decimal("0")
    probability: Decimal = Decimal("0")
    expected_close_date: date | None = None


class DealOut(ORMModel):
    id: str
    contact_id: str | None
    title: str
    stage: str
    value: Decimal
    probability: Decimal
    expected_close_date: date | None


class DealStageUpdate(BaseModel):
    stage: str


class FollowUpIn(BaseModel):
    contact_id: str | None = None
    due_at: datetime
    status: str = "open"
    notes: str = ""


class FollowUpOut(ORMModel):
    id: str
    contact_id: str | None
    due_at: datetime
    status: str
    notes: str


class CommunicationIn(BaseModel):
    contact_id: str | None = None
    channel: str
    subject: str | None = None
    body: str = ""


class CommunicationOut(ORMModel):
    id: str
    contact_id: str | None
    channel: str
    subject: str | None
    body: str
    created_at: datetime


class ContractIn(BaseModel):
    contact_id: str | None = None
    title: str
    status: str = "draft"
    value: Decimal = Decimal("0")
    file_path: str | None = None


class ContractOut(ORMModel):
    id: str
    contact_id: str | None
    title: str
    status: str
    value: Decimal
    file_path: str | None


class ProposalIn(BaseModel):
    contact_id: str | None = None
    title: str
    status: str = "draft"
    amount: Decimal = Decimal("0")
    body: str = ""


class ProposalOut(ORMModel):
    id: str
    contact_id: str | None
    title: str
    status: str
    amount: Decimal
    body: str


class QuotationIn(BaseModel):
    quote_number: str | None = None
    contact_id: str | None = None
    status: str = "draft"
    total: Decimal = Decimal("0")


class QuotationOut(ORMModel):
    id: str
    quote_number: str
    contact_id: str | None
    status: str
    total: Decimal


class EmailCampaignIn(BaseModel):
    name: str
    status: str = "draft"


class EmailCampaignOut(ORMModel):
    id: str
    name: str
    status: str
    sent_count: int
    open_count: int
    click_count: int


class CustomerSegmentIn(BaseModel):
    name: str
    rules: str = "{}"


class CustomerSegmentOut(ORMModel):
    id: str
    name: str
    rules: str


class SalesAnalyticsOut(BaseModel):
    pipeline_value: Decimal
    weighted_pipeline: Decimal
    deals_by_stage: dict[str, int]
    won_value: Decimal
    lost_value: Decimal
    lead_count_by_status: dict[str, int]
    open_follow_ups: int


class SalesForecastOut(BaseModel):
    months: list[dict]
    method: str
