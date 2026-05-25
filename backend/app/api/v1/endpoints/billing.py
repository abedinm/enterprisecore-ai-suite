"""Billing endpoints — subscription CRUD, checkout, portal, usage, invoices.

All endpoints require an authenticated user; admin-only actions
(``portal``, ``cancel``, ``resume``) additionally require ``UserRole.admin``.
Every query is tenant-scoped by the ORM auto-filter, so a user can never
see another tenant's billing data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Response, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.cache import cache_response
from app.core.exceptions import AppError, NotFoundError
from app.core.tenant_context import bypass_tenant_filter
from app.db.session import get_db
from app.models.billing import TenantSubscription, UsageMeter
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.billing import (
    BillingActionResponse, CheckoutIn, CheckoutOut, InvoiceListResponse,
    InvoiceRead, PlanCatalogItem, PlanCatalogResponse, PortalIn, PortalOut,
    TenantSubscriptionRead, UsageMeterRead, UsageResponse,
)
from app.services import stripe_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Plans catalog — public-ish (auth required but no admin role).
# ---------------------------------------------------------------------------
@router.get("/plans", response_model=PlanCatalogResponse)
@cache_response(ttl=3600, namespace="billing:plans")
def list_plans(
    response: Response,
    _: User = Depends(get_current_user),
) -> PlanCatalogResponse:
    """Pricing catalog. Cached 1 hour — prices change about as often as
    the deploy cycle, and we don't want every cold-load to roundtrip into
    the Stripe service when the answer is identical between deploys."""
    items = [PlanCatalogItem(**row) for row in stripe_service.catalog()]
    return PlanCatalogResponse(
        plans=items,
        additional_seat_usd_monthly=stripe_service.ADDITIONAL_SEAT_USD_MONTHLY,
        ai_overage_usd_per_1k_tokens=stripe_service.AI_OVERAGE_USD_PER_1K_TOKENS,
        self_managed=not stripe_service.stripe_configured(),
    )


# ---------------------------------------------------------------------------
# Current subscription.
# ---------------------------------------------------------------------------
def _current_subscription(db: Session, tenant_id: str) -> TenantSubscription | None:
    with bypass_tenant_filter():
        return db.scalar(
            select(TenantSubscription)
            .where(TenantSubscription.tenant_id == tenant_id)
            .order_by(TenantSubscription.created_at.desc())
        )


@router.get("/subscription", response_model=TenantSubscriptionRead | None)
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TenantSubscription | None:
    return _current_subscription(db, current_user.tenant_id)


# ---------------------------------------------------------------------------
# Checkout / Portal.
# ---------------------------------------------------------------------------
@router.post("/checkout", response_model=CheckoutOut)
def start_checkout(
    payload: CheckoutIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckoutOut:
    """Kick off a Stripe Checkout for the requested (plan, interval)."""
    tenant = db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise NotFoundError("Tenant not found")
    url, self_managed = stripe_service.create_checkout_session(
        tenant, payload.plan, payload.interval,
        success_url=payload.success_url, cancel_url=payload.cancel_url,
        db=db,
    )
    return CheckoutOut(checkout_url=url, self_managed=self_managed)


@router.post("/portal", response_model=PortalOut)
def open_portal(
    payload: PortalIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> PortalOut:
    tenant = db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise NotFoundError("Tenant not found")
    url, self_managed = stripe_service.open_billing_portal(tenant, payload.return_url, db)
    return PortalOut(portal_url=url, self_managed=self_managed)


# ---------------------------------------------------------------------------
# Cancel / Resume.
# ---------------------------------------------------------------------------
@router.post("/cancel", response_model=BillingActionResponse)
def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> BillingActionResponse:
    """Schedule cancel-at-period-end. Customer keeps access until the
    period rolls over, at which point Stripe fires
    ``customer.subscription.deleted`` and we downgrade to evaluation.
    """
    sub = _current_subscription(db, current_user.tenant_id)
    if not sub:
        raise NotFoundError("No active subscription")

    stripe = stripe_service.get_stripe_client()
    if stripe is not None and sub.stripe_subscription_id:
        try:
            stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
        except Exception as exc:  # pragma: no cover — surface as 502
            raise AppError(f"Stripe cancel failed: {exc}", code="stripe_error", status_code=502) from exc

    sub.cancel_at_period_end = True
    db.commit()
    db.refresh(sub)
    stripe_service.log_billing_event(
        db, current_user.tenant_id, "subscription.cancel_scheduled",
        metadata={"subscription_id": sub.id, "by_user": current_user.id},
    )
    return BillingActionResponse(
        subscription=TenantSubscriptionRead.model_validate(sub),
        message="Cancellation scheduled at end of current period",
    )


@router.post("/resume", response_model=BillingActionResponse)
def resume_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> BillingActionResponse:
    """Undo a pending cancellation."""
    sub = _current_subscription(db, current_user.tenant_id)
    if not sub:
        raise NotFoundError("No active subscription")
    if not sub.cancel_at_period_end:
        return BillingActionResponse(
            subscription=TenantSubscriptionRead.model_validate(sub),
            message="Subscription is not pending cancellation",
        )

    stripe = stripe_service.get_stripe_client()
    if stripe is not None and sub.stripe_subscription_id:
        try:
            stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=False)
        except Exception as exc:  # pragma: no cover
            raise AppError(f"Stripe resume failed: {exc}", code="stripe_error", status_code=502) from exc

    sub.cancel_at_period_end = False
    db.commit()
    db.refresh(sub)
    stripe_service.log_billing_event(
        db, current_user.tenant_id, "subscription.resumed",
        metadata={"subscription_id": sub.id, "by_user": current_user.id},
    )
    return BillingActionResponse(
        subscription=TenantSubscriptionRead.model_validate(sub),
        message="Subscription resumed",
    )


# ---------------------------------------------------------------------------
# Usage + invoices.
# ---------------------------------------------------------------------------
@router.get("/usage", response_model=UsageResponse)
def get_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UsageResponse:
    """Return this period's usage meters for the current tenant."""
    period_start, _ = stripe_service._current_period_bounds()
    with bypass_tenant_filter():
        rows = db.scalars(
            select(UsageMeter)
            .where(UsageMeter.tenant_id == current_user.tenant_id)
            .where(UsageMeter.period_start == period_start)
        ).all()
    ai_paid = float(sum(
        (Decimal(m.quantity) for m in rows if m.meter_key == "ai_paid_tokens"),
        Decimal("0"),
    ))
    tenant = db.get(Tenant, current_user.tenant_id)
    cap = stripe_service.ai_monthly_cap_usd(tenant.plan if tenant else "evaluation")
    return UsageResponse(
        meters=[UsageMeterRead.model_validate(m) for m in rows],
        ai_paid_usd_this_period=ai_paid,
        ai_monthly_cap_usd=cap,
    )


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InvoiceListResponse:
    tenant = db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise NotFoundError("Tenant not found")
    items, self_managed = stripe_service.list_invoices(tenant, db)
    return InvoiceListResponse(
        invoices=[InvoiceRead(**row) for row in items],
        self_managed=self_managed,
    )
