from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import UniqueConstraint

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class PasswordVaultEntry(IdMixin, TenantMixin, TimestampMixin, Base):
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    username: Mapped[str | None] = mapped_column(String(180))
    encrypted_password: Mapped[str] = mapped_column(Text)
    encrypted_notes: Mapped[str | None] = mapped_column(Text)


class BackupSchedule(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180))
    cadence: Mapped[str] = mapped_column(String(40), default="daily")
    target_path: Mapped[str] = mapped_column(String(500))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_backup_schedules_tenant_name"),)


class LoginAttempt(IdMixin, TenantMixin, TimestampMixin, Base):
    email: Mapped[str] = mapped_column(String(255), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(180))


class ComplianceCheck(IdMixin, TenantMixin, TimestampMixin, Base):
    framework: Mapped[str] = mapped_column(String(80), index=True)
    item: Mapped[str] = mapped_column(String(220))
    status: Mapped[str] = mapped_column(String(40), default="open")
    evidence: Mapped[str] = mapped_column(Text, default="")
