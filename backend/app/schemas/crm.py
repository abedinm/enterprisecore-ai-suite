"""CRM pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from app.schemas.validators import (
    non_negative_money,
    validate_email_opt,
    validate_phone_opt,
)

_DEAL_STAGES = {"qualified", "discovery", "proposal", "negotiation", "won", "lost"}
_LEAD_STATUSES = {"new", "contacted", "qualified", "unqualified", "converted"}


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    company: str | None = Field(default=None, max_length=180)
    email: str | None = None
    phone: str | None = None
    tags: str = "[]"

    _v_email = field_validator("email")(staticmethod(validate_email_opt))
    _v_phone = field_validator("phone")(staticmethod(validate_phone_opt))

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Contact name can't be empty.")
        return v.strip()


class ContactOut(ORMModel):
    id: str
    name: str
    company: str | None
    email: str | None
    phone: str | None
    tags: str


class LeadIn(BaseModel):
    contact_id: str | None = None
    source: str | None = Field(default=None, max_length=120)
    status: str = "new"
    score: int = Field(default=0, ge=0, le=100)
    notes: str = Field(default="", max_length=4000)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        s = (v or "new").strip().lower()
        if s not in _LEAD_STATUSES:
            raise ValueError(f"Invalid lead status. Must be one of: {', '.join(sorted(_LEAD_STATUSES))}.")
        return s


class LeadOut(ORMModel):
    id: str
    contact_id: str | None
    source: str | None
    status: str
    score: int
    notes: str


class DealIn(BaseModel):
    contact_id: str | None = None
    title: str = Field(min_length=1, max_length=180)
    stage: str = "qualified"
    value: Decimal = Decimal("0")
    probability: Decimal = Decimal("0")
    expected_close_date: date | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Deal title can't be empty.")
        return v.strip()

    @field_validator("stage")
    @classmethod
    def _valid_stage(cls, v: str) -> str:
        s = (v or "qualified").strip().lower()
        if s not in _DEAL_STAGES:
            raise ValueError(f"Invalid deal stage. Must be one of: {', '.join(sorted(_DEAL_STAGES))}.")
        return s

    _v_value = field_validator("value")(staticmethod(lambda v: non_negative_money(v, "deal value")))

    @field_validator("probability")
    @classmethod
    def _valid_prob(cls, v: Decimal) -> Decimal:
        d = Decimal(str(v))
        if d < 0 or d > 100:
            raise ValueError("Probability must be between 0 and 100.")
        return d


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

    @field_validator("stage")
    @classmethod
    def _valid_stage(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if s not in _DEAL_STAGES:
            raise ValueError(f"Invalid deal stage. Must be one of: {', '.join(sorted(_DEAL_STAGES))}.")
        return s


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
