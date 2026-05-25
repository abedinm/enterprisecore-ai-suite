"""Webhook subscription + delivery endpoints.

Tenants manage their outbound webhook subscriptions here. The secret is
shown exactly once at creation; rotating it requires a PATCH with
``rotate_secret=true`` and returns the new value once.

A test fire (``POST /webhooks/subscriptions/{id}/test``) publishes a
``webhook.test`` event so the user can verify their endpoint receives
properly-signed payloads before depending on real events.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.core.security import encrypt_text
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.webhooks import WebhookDelivery, WebhookSubscription
from app.schemas.webhooks import (
    EventTypeInfo, WebhookDeliveryOut, WebhookSubscriptionCreated,
    WebhookSubscriptionIn, WebhookSubscriptionOut, WebhookSubscriptionUpdate,
)
from app.services.audit import record_audit
from app.services.event_bus import EVENT_TYPES, list_event_types, publish_event
from app.services.webhook_dispatcher import generate_secret, retry_delivery

router = APIRouter()


def _to_out(sub: WebhookSubscription) -> dict:
    return {
        "id": sub.id,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
        "name": sub.name,
        "url": sub.url,
        "event_types": sub.event_types or [],
        "is_active": sub.is_active,
        "created_by_id": sub.created_by_id,
        "last_delivered_at": sub.last_delivered_at,
        "last_delivery_status": sub.last_delivery_status,
        "consecutive_failures": sub.consecutive_failures,
        "disabled_until": sub.disabled_until,
    }


@router.get("/event-types", response_model=list[EventTypeInfo])
def get_event_types(_: User = Depends(get_current_user)):
    """Return the canonical catalog of event types subscribers can listen to."""

    return list_event_types()


@router.get("/subscriptions", response_model=list[WebhookSubscriptionOut])
def list_subscriptions(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    subs = db.scalars(
        select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
    ).all()
    return [_to_out(s) for s in subs]


@router.post(
    "/subscriptions",
    response_model=WebhookSubscriptionCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_subscription(
    payload: WebhookSubscriptionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    # Validate event types — reject unknown patterns up front so a typo
    # doesn't silently match zero events.
    for et in payload.event_types or []:
        if et == "*" or any(t == et or t.startswith(et.rstrip("*")) for t in EVENT_TYPES):
            continue
        raise HTTPException(
            status_code=400, detail=f"Unknown event type pattern: {et}"
        )

    secret = payload.secret or generate_secret()
    sub = WebhookSubscription(
        name=payload.name,
        url=str(payload.url),
        secret_encrypted=encrypt_text(secret),
        event_types=payload.event_types or ["*"],
        is_active=payload.is_active,
        created_by_id=user.id,
    )
    db.add(sub)
    db.flush()
    record_audit(db, actor=user, action="create", entity_type="webhook_subscription",
                 entity_id=sub.id, detail={"name": sub.name, "url": sub.url})
    db.commit()
    db.refresh(sub)
    out = _to_out(sub)
    out["secret"] = secret
    return out


@router.get("/subscriptions/{sub_id}", response_model=WebhookSubscriptionOut)
def get_subscription(sub_id: str, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    sub = db.get(WebhookSubscription, sub_id)
    if not sub:
        raise NotFoundError("Webhook subscription not found")
    return _to_out(sub)


@router.patch("/subscriptions/{sub_id}", response_model=WebhookSubscriptionCreated)
def update_subscription(
    sub_id: str,
    payload: WebhookSubscriptionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    sub = db.get(WebhookSubscription, sub_id)
    if not sub:
        raise NotFoundError("Webhook subscription not found")
    if payload.name is not None:
        sub.name = payload.name
    if payload.url is not None:
        sub.url = str(payload.url)
    if payload.event_types is not None:
        sub.event_types = payload.event_types
    if payload.is_active is not None:
        sub.is_active = payload.is_active
        if payload.is_active:
            # Re-enabling clears the cool-down so the next fire goes out
            # immediately.
            sub.disabled_until = None
            sub.consecutive_failures = 0

    new_secret: str | None = None
    if payload.rotate_secret:
        new_secret = generate_secret()
        sub.secret_encrypted = encrypt_text(new_secret)

    record_audit(db, actor=user, action="update", entity_type="webhook_subscription",
                 entity_id=sub.id, detail={"rotate_secret": payload.rotate_secret})
    db.commit()
    db.refresh(sub)
    out = _to_out(sub)
    out["secret"] = new_secret or ""
    return out


@router.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    sub = db.get(WebhookSubscription, sub_id)
    if sub:
        record_audit(db, actor=user, action="delete", entity_type="webhook_subscription",
                     entity_id=sub.id)
        db.delete(sub)
        db.commit()
    return None


@router.post("/subscriptions/{sub_id}/test")
def fire_test(
    sub_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Publish a ``webhook.test`` event scoped to this tenant. Every active
    subscription (including this one if it matches ``webhook.test`` or ``*``)
    will receive it, so it's the same code path real events go through."""

    sub = db.get(WebhookSubscription, sub_id)
    if not sub:
        raise NotFoundError("Webhook subscription not found")
    event = publish_event(
        "webhook.test",
        payload={
            "subscription_id": sub.id,
            "subscription_name": sub.name,
            "fired_by": user.email,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        },
        user_id=user.id,
    )
    return {"event_id": event.id, "status": "queued"}


@router.get(
    "/subscriptions/{sub_id}/deliveries",
    response_model=list[WebhookDeliveryOut],
)
def list_deliveries(
    sub_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    sub = db.get(WebhookSubscription, sub_id)
    if not sub:
        raise NotFoundError("Webhook subscription not found")
    deliveries = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == sub_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    ).all()
    return deliveries


@router.post("/deliveries/{delivery_id}/retry")
def retry(
    delivery_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Re-fire a recorded delivery. Useful when the receiver was down +
    you don't want to wait for the scheduled backoff."""

    delivery = db.get(WebhookDelivery, delivery_id)
    if not delivery:
        raise NotFoundError("Delivery not found")
    new_id = retry_delivery(db, delivery_id)
    if new_id is None:
        raise HTTPException(status_code=400, detail="Retry not possible — subscription inactive or missing")
    record_audit(db, actor=user, action="retry", entity_type="webhook_delivery",
                 entity_id=new_id, detail={"original_id": delivery_id})
    db.commit()
    return {"delivery_id": new_id, "status": "retried"}
