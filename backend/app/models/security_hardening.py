"""Phase 9 — enterprise security hardening models.

Three tables live here:

* :class:`TenantEncryptionKey` — per-tenant Data Encryption Key (DEK) for
  field-level encryption with BYOK envelope support.
* :class:`TenantSecurityPolicy` — per-tenant policy bag for IP allowlist
  and similar enforcement knobs.
* :class:`AuditStreamDestination` — outbound destination(s) that the
  audit-log streamer pushes events to (SIEM/webhook/SplunkHEC/etc.).

Separate file from :mod:`app.models.security` (the existing module
covers password vault / backups / compliance checks) so the new
hardening tables don't blur with the old "security & compliance"
operational records.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class TenantEncryptionKey(IdMixin, TenantMixin, TimestampMixin, Base):
    """Per-tenant DEK wrapped by either the server master key or a customer
    KMS (BYOK). The unwrapped DEK never persists — it's loaded into a
    contextvar at request start by :mod:`app.core.encryption` and used to
    encrypt/decrypt Fernet payloads in-process.

    Rotation lifecycle:
      * v1 created with the tenant.
      * ``rotate_tenant_dek`` mints v(n+1), re-encrypts existing fields,
        flips ``is_active`` on the old row to False once migration is done.
      * The version prefix on the ciphertext ("v3:...") tells the
        decryption path which row's DEK to unwrap.
    """

    __tablename__ = "tenant_encryption_keys"

    key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    # The DEK ciphertext (wrapped by either the server master key or KMS).
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # server | aws_kms | gcp_kms | azure_kv | hcv_transit
    kms_provider: Mapped[str] = mapped_column(String(20), default="server", nullable=False)
    # ARN / resource name / key id when BYOK. NULL when server-managed.
    kms_key_ref: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "key_version", name="uq_tenant_dek_version"),
    )


class TenantSecurityPolicy(IdMixin, TenantMixin, TimestampMixin, Base):
    """Per-tenant security policy.

    At most one row per tenant. Wraps a few enforcement knobs that don't
    each warrant their own table.

    * ``ip_allowlist_cidrs`` — list of CIDR blocks (IPv4 or IPv6). Empty
      list means "no restriction".
    * ``ip_allowlist_enforced`` — master switch. When False, the
      middleware skips enforcement entirely (default OFF so tenants
      don't accidentally lock themselves out on day one).
    """

    __tablename__ = "tenant_security_policies"

    ip_allowlist_cidrs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ip_allowlist_enforced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_security_policy"),
    )


class AuditStreamDestination(IdMixin, TenantMixin, TimestampMixin, Base):
    """An outbound destination the audit streamer pushes events to.

    The credentials (HEC token / API key / bearer) are encrypted with
    the tenant DEK before being stored, and decrypted in-process when
    the streamer builds the outbound request.
    """

    __tablename__ = "audit_stream_destinations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # webhook | splunk_hec | datadog_logs | sumo_logic
    destination_type: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Last successful POST + last error, surfaced via the API for support.
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
