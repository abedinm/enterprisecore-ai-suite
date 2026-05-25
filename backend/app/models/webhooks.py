"""Webhook subscription + delivery + GDPR job/receipt models.

These tables underpin Phase 8 — outbound webhooks for an external system to
react to in-app events, and GDPR-mandated data export + erasure receipts.

Every row carries ``tenant_id`` like the rest of the suite, so the auto-filter
keeps tenants' webhook configs (and the receipts that prove their GDPR
compliance) strictly isolated.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class WebhookSubscription(IdMixin, TenantMixin, TimestampMixin, Base):
    """A tenant's standing subscription to outbound webhooks.

    ``secret_encrypted`` is the Fernet-encrypted shared secret used to sign
    every delivery's body with HMAC-SHA256. Receivers verify by recomputing.
    ``event_types`` is a whitelist; ``["*"]`` means "every event". Wildcards
    like ``"crm.*"`` are supported and matched in the dispatcher.

    Backoff state lives on the row so the dispatcher can decide whether to
    skip the next fire without a join: ``disabled_until`` pauses delivery
    until that timestamp, and ``consecutive_failures`` is bumped on 4xx/5xx
    + reset on a 2xx.
    """

    __tablename__ = "webhook_subscriptions"

    name: Mapped[str] = mapped_column(String(180), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_delivery_status: Mapped[int | None] = mapped_column(Integer)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disabled_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(IdMixin, TenantMixin, TimestampMixin, Base):
    """One outbound HTTP attempt for a (subscription, event) pair.

    Keeps a permanent record of the payload, signature, response status, and
    timing for each attempt — visible via ``GET /webhooks/subscriptions/{id}/deliveries``.
    On non-2xx ``next_retry_at`` is set to the next exponential backoff slot;
    a successful retry creates a new row with ``attempt_number`` bumped.
    """

    __tablename__ = "webhook_deliveries"

    subscription_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    request_signature: Mapped[str] = mapped_column(String(160), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body_excerpt: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GdprExportJob(IdMixin, TenantMixin, TimestampMixin, Base):
    """Async (currently synchronous) data-export job.

    ``status`` ladder: ``pending`` → ``running`` → ``ready`` | ``failed``.
    ``download_path`` is a relative path inside ``storage/exports/`` once the
    job completes. ``expires_at`` is when the bundle is purged + the signed
    download URL stops working.
    """

    __tablename__ = "gdpr_export_jobs"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requested_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    download_path: Mapped[str | None] = mapped_column(String(500))
    download_token: Mapped[str | None] = mapped_column(String(120), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GdprErasureReceipt(IdMixin, TenantMixin, TimestampMixin, Base):
    """Proof-of-compliance receipt after a GDPR erasure request was honoured.

    Kept indefinitely (the whole point — auditors need to see we did the work).
    ``user_id`` is the *original* user id; the user record itself is
    anonymized rather than deleted so audit-log FKs survive.
    """

    __tablename__ = "gdpr_erasure_receipts"

    user_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    user_email_anonymized: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    fields_cleared: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    records_anonymized: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
