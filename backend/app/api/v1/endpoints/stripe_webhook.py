"""Stripe webhook endpoint — POST /stripe/webhook (NOT under /api/v1).

Public endpoint, no auth. Verifies the ``Stripe-Signature`` header against
``STRIPE_WEBHOOK_SECRET`` and dispatches recognised events to local
handlers. Always returns 200 once we've recorded (or failed to record)
the event so Stripe stops retrying — we don't want a transient DB error
to cause indefinite redelivery.

Idempotency is enforced via the ``BillingEvent.stripe_event_id`` UNIQUE
constraint: a duplicate delivery is detected, logged, and short-circuited.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import get_db
from app.models.billing import BillingEvent
from app.models.tenant import Tenant
from app.services import stripe_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_tenant(db: Session, event_obj: dict) -> Tenant | None:
    """Find the Tenant a Stripe event belongs to.

    Tries (in order):
      1. ``metadata.tenant_id`` on the event object itself.
      2. ``client_reference_id`` (set by Checkout).
      3. ``customer`` → look up by ``stripe_customer_id`` in our table.
    """
    metadata = (event_obj.get("metadata") or {}) if isinstance(event_obj, dict) else {}
    tid = metadata.get("tenant_id")
    if not tid:
        tid = event_obj.get("client_reference_id")

    with bypass_tenant_filter():
        if tid:
            tenant = db.get(Tenant, tid)
            if tenant:
                return tenant

        customer_id = event_obj.get("customer")
        if customer_id:
            from app.models.billing import TenantSubscription
            sub = db.scalar(
                select(TenantSubscription).where(
                    TenantSubscription.stripe_customer_id == customer_id
                )
            )
            if sub:
                return db.get(Tenant, sub.tenant_id)
    return None


def _already_processed(db: Session, stripe_event_id: str | None) -> bool:
    if not stripe_event_id:
        return False
    with bypass_tenant_filter():
        existing = db.scalar(
            select(BillingEvent).where(BillingEvent.stripe_event_id == stripe_event_id)
        )
    return existing is not None


# ---------------------------------------------------------------------------
# Per-event handlers.
# ---------------------------------------------------------------------------
def _handle_subscription_change(tenant: Tenant, event_obj: dict, db: Session) -> None:
    """customer.subscription.created / updated."""
    stripe_service.sync_subscription_from_stripe(tenant, event_obj, db)


def _handle_subscription_deleted(tenant: Tenant, event_obj: dict, db: Session) -> None:
    """customer.subscription.deleted — downgrade to evaluation."""
    # sync_subscription_from_stripe already handles the canceled status, but
    # we want to be explicit about the downgrade even if the Stripe payload
    # doesn't have ``status="canceled"`` set yet.
    stripe_service.sync_subscription_from_stripe(tenant, event_obj, db)
    tenant.plan = "evaluation"
    tenant.status = "cancelled"
    db.commit()


def _handle_invoice_paid(tenant: Tenant, event_obj: dict, db: Session) -> None:
    """Invoice paid — informational only, BillingEvent already captured."""
    pass


def _handle_invoice_payment_failed(tenant: Tenant, event_obj: dict, db: Session) -> None:
    """Mark tenant past_due so the UI can show a dunning banner."""
    tenant.status = "past_due"
    # Also flip the subscription row's status if we have one.
    with bypass_tenant_filter():
        from app.models.billing import TenantSubscription
        sub = db.scalar(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
        )
    if sub:
        sub.status = "past_due"
    db.commit()


def _handle_trial_will_end(tenant: Tenant, event_obj: dict, db: Session) -> None:
    """Send the tenant admin a reminder that their trial is about to expire.

    Email delivery is best-effort — if ``app.services.email`` exists we
    call it; otherwise we just log the reminder so an operator can see
    the event went through.
    """
    try:
        from app.services import email as email_service  # type: ignore
        send_fn = getattr(email_service, "send", None) or getattr(email_service, "send_email", None)
        if send_fn:
            send_fn(
                to=tenant.primary_contact_email,
                subject="Your EnterpriseCore trial ends soon",
                body=(
                    f"Hi — the trial for {tenant.name} ends shortly. "
                    f"Upgrade now to keep your data and avoid being downgraded."
                ),
            )
            return
    except Exception as exc:  # pragma: no cover
        logger.info("Trial-end email service unavailable ({}), logging instead", exc)
    logger.info(
        "Trial-will-end reminder for tenant={} email={}",
        tenant.id, tenant.primary_contact_email,
    )


EVENT_HANDLERS = {
    "customer.subscription.created": _handle_subscription_change,
    "customer.subscription.updated": _handle_subscription_change,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    "customer.subscription.trial_will_end": _handle_trial_will_end,
}


# ---------------------------------------------------------------------------
# Endpoint.
# ---------------------------------------------------------------------------
@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receive a Stripe webhook event.

    Returns 200 once we've persisted the event (or skipped a duplicate),
    so Stripe stops retrying. Returns 400 only when the signature header
    is present but doesn't verify — that's the one case where we want
    Stripe to know the delivery was rejected.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    # Signature verification. Self-managed mode (no STRIPE_WEBHOOK_SECRET)
    # skips verification and parses the body as plain JSON — fine for
    # internal forwarders but never reachable from public Stripe.
    try:
        event = stripe_service.verify_webhook_signature(payload, sig_header)
    except ValueError as exc:
        logger.warning("Stripe webhook signature rejected: {}", exc)
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    event_id = event.get("id")
    event_type = event.get("type", "unknown")
    data_obj = ((event.get("data") or {}).get("object")) or {}

    # Count every signed event we accepted. Dedup logic below may short-
    # circuit, but the counter records the raw delivery rate so dashboards
    # can spot a Stripe retry storm.
    try:
        from app.core.metrics import stripe_events_total
        stripe_events_total.labels(event_type=event_type or "unknown").inc()
    except Exception:
        pass

    # Idempotency check — skip duplicates silently.
    if _already_processed(db, event_id):
        logger.info("Stripe webhook duplicate event_id={} type={}", event_id, event_type)
        return {"received": True, "duplicate": True}

    tenant = _resolve_tenant(db, data_obj)
    if not tenant:
        # Log the orphan event but still return 200 — we don't want Stripe
        # retrying forever on an event we can't attribute.
        logger.info(
            "Stripe webhook unresolved tenant: event_id={} type={}",
            event_id, event_type,
        )
        return {"received": True, "unattributed": True}

    # Switch the tenant context so any nested ORM writes scope correctly.
    with tenant_scope(tenant.id):
        # Persist the audit row FIRST so the UNIQUE(stripe_event_id) guard
        # blocks any in-flight duplicate. Wrap the whole handler in a try
        # so a handler failure doesn't lose the audit row.
        try:
            stripe_service.log_billing_event(
                db, tenant.id, event_type,
                stripe_event_id=event_id,
                metadata={"source": "stripe_webhook", "data_id": data_obj.get("id")},
                occurred_at=datetime.fromtimestamp(
                    event.get("created", datetime.now(timezone.utc).timestamp()),
                    tz=timezone.utc,
                ) if isinstance(event.get("created"), int) else None,
            )
        except Exception as exc:
            # If the audit row insert collided on UNIQUE, treat as duplicate.
            logger.info("Stripe webhook audit-insert failed (likely duplicate): {}", exc)
            return {"received": True, "duplicate": True}

        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            try:
                handler(tenant, data_obj, db)
            except Exception as exc:
                # Don't 500 — log and ACK. Stripe shouldn't retry on app bugs.
                logger.exception("Stripe webhook handler failed for {}: {}", event_type, exc)
        else:
            logger.info("Stripe webhook unhandled event_type={}", event_type)

    return {"received": True}
