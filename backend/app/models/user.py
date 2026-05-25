from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "Admin"
    manager = "Manager"
    employee = "Employee"
    developer = "Developer"
    # Academic SKU (+EDU) roles — gated through require_plan_feature("academic").
    student = "Student"
    teacher = "Teacher"
    registrar = "Registrar"
    dean = "Dean"


class User(IdMixin, TenantMixin, TimestampMixin, Base):
    # Email is unique *within* a tenant — the same person can be a user in
    # two separate companies. The composite uniqueness ``(tenant_id, email)``
    # is declared in ``__table_args__`` below.
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.employee, nullable=False)
    department: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    locale: Mapped[str] = mapped_column(String(12), default="en", nullable=False)
    theme: Mapped[str] = mapped_column(String(16), default="system", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # TOTP MFA. Secret stored Fernet-encrypted; flipped to True only after the
    # user verifies a fresh code, so an interrupted enrolment can't lock them out.
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)


class RefreshToken(IdMixin, TenantMixin, TimestampMixin, Base):
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Device binding — set on issue, checked on refresh. Stealing a refresh
    # token from one device and presenting it from another (different UA +
    # IP-network) will be rejected with "device mismatch" and the original
    # session revoked as a precaution. Nullable for back-compat with tokens
    # issued before this column existed.
    device_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_ip: Mapped[str | None] = mapped_column(String(64))
    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class Setting(IdMixin, TenantMixin, TimestampMixin, Base):
    scope: Mapped[str] = mapped_column(String(40), default="global", nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Settings are unique per (tenant, scope, key) — same key in two tenants
    # is fine, but a tenant can't have two rows with the same scope+key.
    __table_args__ = (UniqueConstraint("tenant_id", "scope", "key", name="uq_settings_tenant_scope_key"),)


class AuditLog(IdMixin, TenantMixin, TimestampMixin, Base):
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(120), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    # JSON column: SQLite stores as TEXT, PostgreSQL as JSONB → queryable.
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(IdMixin, TenantMixin, TimestampMixin, Base):
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    level: Mapped[str] = mapped_column(String(24), default="info", nullable=False)
    link: Mapped[str | None] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SearchIndex(IdMixin, TenantMixin, TimestampMixin, Base):
    module: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class SearchHistory(IdMixin, TenantMixin, TimestampMixin, Base):
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(255), nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
