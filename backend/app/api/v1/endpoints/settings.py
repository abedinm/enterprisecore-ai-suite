"""Settings endpoints — list, upsert, bulk update, and current-user preferences."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.core.security import encrypt_text
from app.db.session import get_db
from app.models.user import Setting, User, UserRole
from app.schemas.foundation import SettingBulkUpdate, SettingRead, SettingUpdate

router = APIRouter()


@router.get("", response_model=list[SettingRead])
def list_settings(
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Setting).order_by(Setting.scope, Setting.key)
    if scope:
        stmt = stmt.where(Setting.scope == scope)
    return db.scalars(stmt).all()


@router.get("/{key}", response_model=SettingRead)
def get_setting(key: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    item = db.scalar(select(Setting).where(Setting.scope == "global", Setting.key == key))
    if not item:
        raise NotFoundError(f"Setting '{key}' not found")
    return item


@router.put("/{key}", response_model=SettingRead)
def upsert_setting(
    key: str,
    payload: SettingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    setting = db.scalar(select(Setting).where(Setting.scope == "global", Setting.key == key))
    value = encrypt_text(payload.value) if payload.is_secret else payload.value
    if not setting:
        setting = Setting(scope="global", key=key, value=value, is_secret=payload.is_secret)
        db.add(setting)
    else:
        setting.value = value
        setting.is_secret = payload.is_secret
    db.commit()
    db.refresh(setting)
    return setting


@router.post("/bulk", response_model=list[SettingRead])
def bulk_upsert_settings(
    payload: SettingBulkUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    updated: list[Setting] = []
    for key, value in payload.updates.items():
        setting = db.scalar(select(Setting).where(Setting.scope == "global", Setting.key == key))
        if not setting:
            setting = Setting(scope="global", key=key, value=value)
            db.add(setting)
        else:
            setting.value = value
        updated.append(setting)
    db.commit()
    for setting in updated:
        db.refresh(setting)
    return updated


@router.delete("/{key}", status_code=204)
def delete_setting(
    key: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    item = db.scalar(select(Setting).where(Setting.scope == "global", Setting.key == key))
    if item:
        db.delete(item)
        db.commit()
    return None
