"""Pydantic schemas for the webhook subscription/delivery + GDPR endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.schemas.common import ORMModel, Timestamped


# ---- Webhook subscriptions ------------------------------------------------

class WebhookSubscriptionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=180)
    url: HttpUrl
    event_types: list[str] = Field(default_factory=lambda: ["*"])
    secret: str | None = Field(None, min_length=16, max_length=200)
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def _enforce_https(cls, v: HttpUrl) -> HttpUrl:
        # Webhooks travel public networks — refuse http:// outright. (We allow
        # http://localhost / 127.0.0.1 so tests + dev runners don't need TLS.)
        s = str(v)
        if s.startswith("http://") and not (
            "://localhost" in s or "://127.0.0.1" in s or "://0.0.0.0" in s
        ):
            raise ValueError("Webhook URL must use https://")
        return v


class WebhookSubscriptionUpdate(BaseModel):
    name: str | None = None
    url: HttpUrl | None = None
    event_types: list[str] | None = None
    is_active: bool | None = None
    rotate_secret: bool = False


class WebhookSubscriptionOut(Timestamped):
    name: str
    url: str
    event_types: list[str]
    is_active: bool
    created_by_id: str | None = None
    last_delivered_at: datetime | None = None
    last_delivery_status: int | None = None
    consecutive_failures: int
    disabled_until: datetime | None = None


class WebhookSubscriptionCreated(WebhookSubscriptionOut):
    """Returned once on POST — includes the plaintext secret so the caller
    can store it. Subsequent GETs never include the secret again."""

    secret: str


# ---- Webhook deliveries ---------------------------------------------------

class WebhookDeliveryOut(Timestamped):
    subscription_id: str
    event_id: str
    event_type: str
    payload_json: dict
    request_signature: str
    delivered_at: datetime | None = None
    response_status: int | None = None
    response_body_excerpt: str | None = None
    duration_ms: int | None = None
    attempt_number: int
    next_retry_at: datetime | None = None


# ---- Event catalog --------------------------------------------------------

class EventTypeInfo(BaseModel):
    type: str
    module: str
    description: str


# ---- GDPR -----------------------------------------------------------------

class GdprExportRequest(BaseModel):
    user_id: str | None = None
    """If omitted, exports the requesting user's own data."""


class GdprExportJobOut(ORMModel):
    id: str
    user_id: str
    status: str
    download_url: str | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    record_count: int
    created_at: datetime


class GdprErasureRequest(BaseModel):
    user_id: str
    reason: str = Field("", max_length=2000)


class GdprErasureReceiptOut(Timestamped):
    user_id: str
    user_email_anonymized: str
    requested_by_id: str | None = None
    reason: str
    fields_cleared: list[str]
    records_anonymized: int
    completed_at: datetime


class DataCategory(BaseModel):
    name: str
    description: str
    examples: list[str]
    retention: str
