"""TenantIntegration model — Phase 8 mid-market integration layer.

One row per (tenant, integration_key) pair, storing the OAuth tokens (or
static API keys for connectors like Zapier that don't do OAuth), plus a
free-form JSON ``config`` bag for integration-specific knobs (default
Slack channel, target Google calendar id, Zapier webhook URL, etc.).

Tokens are stored in the ``*_encrypted`` columns as a versioned ciphertext
produced by :mod:`app.core.encryption` — i.e. wrapped with the tenant's
own DEK rather than the global server key. That keeps third-party access
tokens inside the BYOK boundary so a customer rotating their KMS key
re-protects them on the next read.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class TenantIntegration(IdMixin, TenantMixin, TimestampMixin, Base):
    """A tenant's installed third-party integration.

    ``key`` matches the ``Integration`` subclass identifier (``slack``,
    ``google_workspace``, ``zapier``). At most one active row per
    (tenant, key) — re-installing replaces the previous row's tokens.
    """

    __tablename__ = "tenant_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_tenant_integration"),
    )

    key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # OAuth bits — Fernet-encrypted via tenant DEK. Null when the
    # integration uses a static API key instead (Zapier) or before the
    # OAuth callback completes (install pending).
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Integration-specific settings. Schema lives on the Integration subclass;
    # not enforced in DB so connectors can evolve their config bag freely.
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    installed_by_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
