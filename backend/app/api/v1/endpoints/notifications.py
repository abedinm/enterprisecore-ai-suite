"""Notification endpoints — list, create, mark read, mark all read, counts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import Notification, User, UserRole
from app.schemas.foundation import NotificationCounts, NotificationCreate, NotificationRead

router = APIRouter()


def _own_or_broadcast(user_id: str):
    return or_(Notification.user_id == user_id, Notification.user_id.is_(None))


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Notification).where(_own_or_broadcast(current_user.id))
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    return db.scalars(stmt).all()


@router.get("/counts", response_model=NotificationCounts)
def notification_counts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total = db.scalar(select(func.count(Notification.id)).where(_own_or_broadcast(current_user.id))) or 0
    unread = (
        db.scalar(
            select(func.count(Notification.id)).where(
                _own_or_broadcast(current_user.id), Notification.is_read.is_(False)
            )
        )
        or 0
    )
    return NotificationCounts(total=total, unread=unread)


@router.post("", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    item = Notification(
        user_id=payload.user_id,
        title=payload.title,
        body=payload.body,
        level=payload.level,
        link=payload.link,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.get(Notification, notification_id)
    if item and (item.user_id == current_user.id or item.user_id is None):
        item.is_read = True
        db.commit()
        db.refresh(item)
        return item
    return Notification(id=notification_id, title="", body="", level="info", is_read=False)


@router.post("/read-all", response_model=NotificationCounts)
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.execute(
        update(Notification)
        .where(_own_or_broadcast(current_user.id), Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    total = db.scalar(select(func.count(Notification.id)).where(_own_or_broadcast(current_user.id))) or 0
    return NotificationCounts(total=total, unread=0)


@router.delete("/{notification_id}", status_code=204)
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.get(Notification, notification_id)
    if item and (item.user_id == current_user.id or item.user_id is None):
        db.delete(item)
        db.commit()
    return None
