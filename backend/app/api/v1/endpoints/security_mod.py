"""Security & compliance endpoints — vault, backups, login monitor, compliance, access."""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.security import decrypt_text, encrypt_text
from app.db.session import get_db
from app.models.security import (
    BackupSchedule, ComplianceCheck, LoginAttempt, PasswordVaultEntry,
)
from app.models.user import AuditLog, User, UserRole
from app.schemas.security import (
    AccessGrantIn, AuditLogOut, BackupRunOut, BackupScheduleIn, BackupScheduleOut,
    ComplianceCheckIn, ComplianceCheckOut, ComplianceReportOut, LoginAttemptOut,
    VaultEntryIn, VaultEntryOut, VaultEntryReveal,
)

router = APIRouter()


# ---- Password vault -----------------------------------------------------
@router.get("/vault", response_model=list[VaultEntryOut])
def list_vault(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return db.scalars(
        select(PasswordVaultEntry).where(PasswordVaultEntry.owner_id == current.id)
        .order_by(PasswordVaultEntry.title)
    ).all()


@router.post("/vault", response_model=VaultEntryOut)
def create_vault_entry(payload: VaultEntryIn, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    entry = PasswordVaultEntry(
        owner_id=current.id,
        title=payload.title,
        username=payload.username,
        encrypted_password=encrypt_text(payload.password),
        encrypted_notes=encrypt_text(payload.notes) if payload.notes else None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/vault/{vid}/reveal", response_model=VaultEntryReveal)
def reveal_vault_entry(vid: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    entry = db.get(PasswordVaultEntry, vid)
    if not entry or entry.owner_id != current.id:
        raise NotFoundError("Entry not found")
    return VaultEntryReveal(
        id=entry.id, title=entry.title, username=entry.username,
        password=decrypt_text(entry.encrypted_password),
        notes=decrypt_text(entry.encrypted_notes) if entry.encrypted_notes else None,
    )


@router.delete("/vault/{vid}", status_code=204)
def delete_vault_entry(vid: str, db: Session = Depends(get_db),
                       current: User = Depends(get_current_user)):
    entry = db.get(PasswordVaultEntry, vid)
    if entry and entry.owner_id == current.id:
        db.delete(entry)
        db.commit()


# ---- Backups ------------------------------------------------------------
@router.get("/backups", response_model=list[BackupScheduleOut])
def list_backups(db: Session = Depends(get_db),
                 _: User = Depends(require_roles(UserRole.admin))):
    return db.scalars(select(BackupSchedule).order_by(BackupSchedule.created_at.desc())).all()


@router.post("/backups", response_model=BackupScheduleOut)
def create_backup_schedule(payload: BackupScheduleIn, db: Session = Depends(get_db),
                           _: User = Depends(require_roles(UserRole.admin))):
    obj = BackupSchedule(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/backups/{bid}/run", response_model=BackupRunOut)
def run_backup(bid: str, db: Session = Depends(get_db),
               _: User = Depends(require_roles(UserRole.admin))):
    schedule = db.get(BackupSchedule, bid)
    if not schedule:
        raise NotFoundError("Backup schedule not found")
    target = Path(schedule.target_path) if schedule.target_path else settings.storage_dir / "backups"
    target.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_file = target / f"enterprisecore-{ts}.zip"
    storage_dir = settings.storage_dir
    with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as z:
        # SQLite DB
        for p in storage_dir.glob("enterprisecore.db*"):
            z.write(p, arcname=p.name)
        # User uploads
        for p in (storage_dir / "uploads").rglob("*"):
            if p.is_file():
                z.write(p, arcname=f"uploads/{p.relative_to(storage_dir / 'uploads')}")
    schedule.last_run_at = datetime.now(timezone.utc)
    db.commit()
    return BackupRunOut(
        schedule_id=schedule.id, backup_path=str(backup_file),
        size_bytes=backup_file.stat().st_size, completed_at=datetime.now(timezone.utc),
    )


# ---- Login monitor ------------------------------------------------------
@router.get("/login-attempts", response_model=list[LoginAttemptOut])
def login_attempts(success: bool | None = None, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin))):
    stmt = select(LoginAttempt).order_by(LoginAttempt.created_at.desc())
    if success is not None:
        stmt = stmt.where(LoginAttempt.success == success)
    return db.scalars(stmt.limit(500)).all()


@router.get("/login-attempts/summary")
def login_summary(db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin))):
    total = db.scalar(select(func.count(LoginAttempt.id))) or 0
    succ = db.scalar(select(func.count(LoginAttempt.id)).where(LoginAttempt.success.is_(True))) or 0
    fail = total - succ
    top_failing = db.execute(
        select(LoginAttempt.email, func.count(LoginAttempt.id))
        .where(LoginAttempt.success.is_(False))
        .group_by(LoginAttempt.email)
        .order_by(func.count(LoginAttempt.id).desc())
        .limit(10)
    ).all()
    return {
        "total": total, "success": succ, "failure": fail,
        "top_failing_emails": [{"email": e, "count": c} for e, c in top_failing],
    }


# ---- Compliance ---------------------------------------------------------
@router.get("/compliance", response_model=list[ComplianceCheckOut])
def list_compliance(framework: str | None = None, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    stmt = select(ComplianceCheck).order_by(ComplianceCheck.framework, ComplianceCheck.item)
    if framework:
        stmt = stmt.where(ComplianceCheck.framework == framework)
    return db.scalars(stmt).all()


@router.post("/compliance", response_model=ComplianceCheckOut)
def add_compliance(payload: ComplianceCheckIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = ComplianceCheck(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/compliance/{cid}/status", response_model=ComplianceCheckOut)
def update_compliance_status(cid: str, payload: dict, db: Session = Depends(get_db),
                             _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(ComplianceCheck, cid)
    if not obj:
        raise NotFoundError("Compliance check not found")
    obj.status = payload.get("status", obj.status)
    if "evidence" in payload:
        obj.evidence = payload["evidence"]
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/compliance/report/{framework}", response_model=ComplianceReportOut)
def compliance_report(framework: str, db: Session = Depends(get_db),
                      _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    counts = {s: c for s, c in db.execute(
        select(ComplianceCheck.status, func.count(ComplianceCheck.id))
        .where(ComplianceCheck.framework == framework)
        .group_by(ComplianceCheck.status)
    ).all()}
    total = sum(counts.values())
    met = counts.get("met", 0)
    partial = counts.get("partial", 0)
    missed = counts.get("missed", 0)
    pending = counts.get("pending", 0) + counts.get("open", 0)
    score = round(((met + 0.5 * partial) / total) * 100, 2) if total > 0 else 0.0
    return ComplianceReportOut(
        framework=framework, total=total, met=met, partial=partial,
        missed=missed, pending=pending, score=score,
    )


# ---- Access control -----------------------------------------------------
@router.get("/access")
def list_access(db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.admin))):
    users = db.scalars(select(User).order_by(User.email)).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name,
             "role": u.role.value if hasattr(u.role, "value") else str(u.role),
             "is_active": u.is_active} for u in users]


@router.post("/access/grant")
def grant_role(payload: AccessGrantIn, db: Session = Depends(get_db),
               _: User = Depends(require_roles(UserRole.admin))):
    user = db.get(User, payload.user_id)
    if not user:
        raise NotFoundError("User not found")
    role_map = {r.value: r for r in UserRole}
    role_map.update({r.name: r for r in UserRole})
    role = role_map.get(payload.role)
    if not role:
        raise NotFoundError(f"Unknown role: {payload.role}")
    user.role = role
    db.commit()
    return {"id": user.id, "role": user.role.value if hasattr(user.role, "value") else str(user.role)}


@router.post("/access/{user_id}/disable", status_code=204)
def disable_user(user_id: str, db: Session = Depends(get_db),
                 current: User = Depends(require_roles(UserRole.admin))):
    if user_id == current.id:
        raise NotFoundError("You cannot disable your own account")
    user = db.get(User, user_id)
    if user:
        user.is_active = False
        db.commit()


# ---- Audit log ----------------------------------------------------------
@router.get("/audit", response_model=list[AuditLogOut])
def audit_logs(entity_type: str | None = None, action: str | None = None,
               limit: int = 100, db: Session = Depends(get_db),
               _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return db.scalars(stmt.limit(min(limit, 500))).all()


# ---- GDPR ---------------------------------------------------------------
@router.get("/gdpr/checklist")
def gdpr_checklist(_: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return {
        "framework": "GDPR",
        "items": [
            {"id": "art5", "item": "Data minimization principle applied", "category": "principles"},
            {"id": "art6", "item": "Lawful basis documented for each processing activity", "category": "principles"},
            {"id": "art12", "item": "Privacy notice readily accessible to data subjects", "category": "rights"},
            {"id": "art15", "item": "Subject access requests can be fulfilled within 30 days", "category": "rights"},
            {"id": "art17", "item": "Right-to-erasure procedure documented", "category": "rights"},
            {"id": "art20", "item": "Data portability export available", "category": "rights"},
            {"id": "art25", "item": "Privacy by design baked into product roadmap", "category": "governance"},
            {"id": "art28", "item": "Data processor agreements in place with vendors", "category": "vendors"},
            {"id": "art30", "item": "Records of processing activities maintained", "category": "governance"},
            {"id": "art32", "item": "Encryption at rest and in transit", "category": "security"},
            {"id": "art33", "item": "Breach notification procedure (72h) ready", "category": "incidents"},
            {"id": "art35", "item": "DPIA performed for high-risk processing", "category": "governance"},
        ],
    }
