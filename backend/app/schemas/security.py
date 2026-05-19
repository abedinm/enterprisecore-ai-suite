"""Security & compliance schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class VaultEntryIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    username: str | None = None
    password: str = Field(min_length=1)
    notes: str | None = None


class VaultEntryOut(ORMModel):
    id: str
    title: str
    username: str | None
    created_at: datetime
    updated_at: datetime


class VaultEntryReveal(BaseModel):
    id: str
    title: str
    username: str | None
    password: str
    notes: str | None


class BackupScheduleIn(BaseModel):
    name: str
    cadence: str = "daily"
    target_path: str
    is_active: bool = True


class BackupScheduleOut(ORMModel):
    id: str
    name: str
    cadence: str
    target_path: str
    last_run_at: datetime | None
    is_active: bool


class BackupRunOut(BaseModel):
    schedule_id: str
    backup_path: str
    size_bytes: int
    completed_at: datetime


class LoginAttemptOut(ORMModel):
    id: str
    email: str
    ip_address: str | None
    success: bool
    reason: str | None
    created_at: datetime


class ComplianceCheckIn(BaseModel):
    framework: str
    item: str
    status: str = "open"
    evidence: str = ""


class ComplianceCheckOut(ORMModel):
    id: str
    framework: str
    item: str
    status: str
    evidence: str


class ComplianceReportOut(BaseModel):
    framework: str
    total: int
    met: int
    partial: int
    missed: int
    pending: int
    score: float


class AccessGrantIn(BaseModel):
    user_id: str
    role: str  # admin|manager|employee|developer


class AuditLogOut(ORMModel):
    id: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    ip_address: str | None
    created_at: datetime
