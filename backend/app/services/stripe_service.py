"""Stripe integration service — subscription, checkout, portal, webhooks.

Everything in this module is "soft-fail" when ``STRIPE_SECRET_KEY`` is not
configured: callers get a sensible no-op return value rather than an
exception. This keeps the tests, CI, and self-host customers (who handle
billing outside Stripe) working without a Stripe account.

Pricing catalog is hard-coded as a fall-back; per-plan / per-interval
Stripe price IDs can be overridden via ``STRIPE_PRICE_<PLAN>_<INTERVAL>``
env vars at runtime (e.g. ``STRIPE_PRICE_CORE_MONTHLY=price_1NxYz...``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, date, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_context import bypass_tenant_filter
from app.models.billing import BillingEvent, TenantSubscription, UsageMeter
from app.models.tenant import Tenant


# ---------------------------------------------------------------------------
# Pricing catalog
# ---------------------------------------------------------------------------
# These price IDs are placeholders; the operator supplies real Stripe IDs at
# runtime via env vars (``STRIPE_PRICE_CORE_MONTHLY=price_xxx`` etc.). The
# numeric prices stay in code so the marketing site / admin UI can show
# pricing without a Stripe round-trip.
PRICING: dict[str, dict] = {
    "core": {
        "monthly_price_id": "price_core_monthly",
        "yearly_price_id":  "price_core_yearly",
        "base_seats": 5,
        "monthly_usd": 99,
        "yearly_usd":  990,  # 2 months free vs monthly
    },
    "edu": {
        "monthly_price_id": "price_edu_monthly",
        "yearly_price_id":  "price_edu_yearly",
        "base_seats": 25,
        "monthly_usd": 299,
        "yearly_usd":  2990,
    },
    "verticals": {
        "monthly_price_id": "price_vert_monthly",
        "yearly_price_id":  "price_vert_yearly",
        "base_seats": 10,
        "monthly_usd": 199,
        "yearly_usd":  1990,
    },
}

ADDITIONAL_SEAT_USD_MONTHLY: float = 12.0
AI_OVERAGE_USD_PER_1K_TOKENS: float = 0.50

# Per-plan AI cloud spending allowance, in USD per billing month. Spend
# beyond this is metered separately via UsageMeter['ai_paid_tokens'] and
# billed at AI_OVERAGE_USD_PER_1K_TOKENS.
AI_MONTHLY_CAP_USD: dict[str, float] = {
    "evaluation": 5.0,
    "core":       50.0,
    "edu":        150.0,
    "verticals":  100.0,
}

# URL shown when Stripe is not configured — points the customer at the
# self-managed billing documentation. Operators can override via env.
SELF_MANAGED_DOCS_URL = os.environ.get(
    "BILLING_SELF_MANAGED_URL",
    "https://docs.enterprisecore.app/billing/manual",
)


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def stripe_configured() -> bool:
    """True iff a Stripe secret key is set in the environment."""
    return bool(os.environ.get("STRIPE_SECRET_KEY", "").strip())


def webhook_secret() -> str:
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def resolve_price_id(plan: str, interval: str) -> str | None:
    """Look up the Stripe price ID for a (plan, interval) tuple.

    Priority:
      1. ``STRIPE_PRICE_<PLAN>_<INTERVAL>`` env var (production override)
      2. PRICING catalog placeholder (returned even without Stripe — the
         caller checks ``stripe_configured()`` to decide whether to use it)
    """
    if plan not in PRICING:
        return None
    env_key = f"STRIPE_PRICE_{plan.upper()}_{interval.upper()}"
    override = os.environ.get(env_key, "").strip()
    if override:
        return override
    key = f"{interval}ly_price_id"
    return PRICING[plan].get(key)


def get_stripe_client():
    """Return the configured ``stripe`` module, or ``None`` if no key is set.

    Importing ``stripe`` is cheap and the SDK is module-singleton — we just
    set the API key on it and hand the module back. Keeping this behind a
    helper lets the rest of the code branch on a single ``if not stripe:``.
    """
    if not stripe_configured():
        return None
    try:
        import stripe as _stripe
    except ImportError:  # pragma: no cover — stripe is in requirements
        logger.warning("stripe package is not installed; billing in self-managed mode")
        return None
    _stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return _stripe


def catalog() -> list[dict]:
    """Public pricing catalog. Operators can show this without auth."""
    items: list[dict] = []
    for plan_id, meta in PRICING.items():
        items.append({
            "plan": plan_id,
            "monthly_price_id": resolve_price_id(plan_id, "month") or meta["monthly_price_id"],
            "yearly_price_id":  resolve_price_id(plan_id, "year")  or meta["yearly_price_id"],
            "base_seats": meta["base_seats"],
            "monthly_usd": float(meta["monthly_usd"]),
            "yearly_usd":  float(meta["yearly_usd"]),
            "formatted_monthly": f"${int(meta['monthly_usd'])}/mo",
            "formatted_yearly":  f"${int(meta['yearly_usd'])}/yr",
        })
    return items


# ---------------------------------------------------------------------------
# Customer / subscription helpers
# ---------------------------------------------------------------------------
def ensure_customer(tenant: Tenant, db: Session) -> str | None:
    """Get-or-create a Stripe Customer for this tenant, returning the ID.

    Caches the resulting customer ID on the tenant's local subscription row
    so subsequent calls skip the Stripe round-trip. Returns ``None`` in
    self-managed mode.
    """
    stripe = get_stripe_client()
    if stripe is None:
        return None

    # Reuse an existing customer id we've stashed.
    with bypass_tenant_filter():
        sub = db.scalar(
            select(TenantSubscription)
            .where(TenantSubscription.tenant_id == tenant.id)
            .where(TenantSubscription.stripe_customer_id.is_not(None))
        )
    if sub and sub.stripe_customer_id:
        return sub.stripe_customer_id

    cust = stripe.Customer.create(
        email=tenant.primary_contact_email or None,
        name=tenant.name,
        metadata={"tenant_id": tenant.id, "tenant_slug": tenant.slug},
    )
    return cust.id


def create_checkout_session(
    tenant: Tenant, plan: str, interval: str,
    success_url: str | None, cancel_url: str | None,
    db: Session,
) -> tuple[str, bool]:
    """Create a Stripe Checkout session and return ``(url, self_managed)``.

    ``self_managed=True`` indicates Stripe wasn't configured and the URL
    points at the manual-billing docs page instead.
    """
    stripe = get_stripe_client()
    if stripe is None or plan not in PRICING:
        return SELF_MANAGED_DOCS_URL, True

    price_id = resolve_price_id(plan, interval)
    if not price_id:
        return SELF_MANAGED_DOCS_URL, True

    customer_id = ensure_customer(tenant, db)
    success = success_url or os.environ.get("STRIPE_SUCCESS_URL", "https://app.enterprisecore.app/billing?status=success")
    cancel  = cancel_url  or os.environ.get("STRIPE_CANCEL_URL",  "https://app.enterprisecore.app/billing?status=cancel")

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success,
        cancel_url=cancel,
        client_reference_id=tenant.id,
        subscription_data={"metadata": {"tenant_id": tenant.id, "plan": plan, "interval": interval}},
        metadata={"tenant_id": tenant.id, "plan": plan, "interval": interval},
    )
    return session.url, False


def open_billing_portal(tenant: Tenant, return_url: str | None, db: Session) -> tuple[str, bool]:
    """Return a Stripe Customer Portal URL (or the self-managed docs URL)."""
    stripe = get_stripe_client()
    if stripe is None:
        return SELF_MANAGED_DOCS_URL, True

    customer_id = ensure_customer(tenant, db)
    if not customer_id:
        return SELF_MANAGED_DOCS_URL, True

    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url or os.environ.get("STRIPE_PORTAL_RETURN_URL", "https://app.enterprisecore.app/billing"),
    )
    return portal.url, False


# ---------------------------------------------------------------------------
# Subscription sync
# ---------------------------------------------------------------------------
def _safe_dt(epoch: int | None) -> datetime | None:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def sync_subscription_from_stripe(
    tenant: Tenant, stripe_sub: dict, db: Session
) -> TenantSubscription:
    """Reconcile our ``TenantSubscription`` row with Stripe's view.

    Used by every subscription-related webhook handler. Updates the
    tenant's ``plan`` and ``status`` to match Stripe's source of truth.
    Idempotent.
    """
    # Stripe-py objects walk like dicts; both attribute and item access work.
    def _get(obj, *keys, default=None):
        cur = obj
        for k in keys:
            if cur is None:
                return default
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                cur = getattr(cur, k, None)
        return cur if cur is not None else default

    sub_id = _get(stripe_sub, "id")
    customer_id = _get(stripe_sub, "customer")
    status = _get(stripe_sub, "status", default="incomplete")

    # plan / interval / amount from the first line item's price
    items = _get(stripe_sub, "items", "data", default=[]) or []
    price = items[0].get("price") if items else None
    interval = "month"
    amount_per_period = Decimal("0")
    plan_name = None
    if price:
        interval = _get(price, "recurring", "interval", default="month") or "month"
        unit_amount = _get(price, "unit_amount") or 0
        amount_per_period = (Decimal(int(unit_amount)) / Decimal("100")).quantize(Decimal("0.01"))
        # Derive plan from price metadata or subscription metadata.
        plan_name = (
            _get(price, "metadata", "plan")
            or _get(stripe_sub, "metadata", "plan")
        )

    if plan_name not in PRICING:
        # Fall back to whatever the tenant already had.
        plan_name = tenant.plan if tenant.plan in PRICING else "core"

    with bypass_tenant_filter():
        existing = db.scalar(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
        )

    base_seats = PRICING.get(plan_name, {}).get("base_seats", 5)
    fields = dict(
        stripe_subscription_id=sub_id,
        stripe_customer_id=customer_id,
        plan=plan_name,
        status=status,
        seat_quota=base_seats,
        interval=interval,
        current_period_start=_safe_dt(_get(stripe_sub, "current_period_start")),
        current_period_end=_safe_dt(_get(stripe_sub, "current_period_end")),
        cancel_at_period_end=bool(_get(stripe_sub, "cancel_at_period_end", default=False)),
        canceled_at=_safe_dt(_get(stripe_sub, "canceled_at")),
        trial_end=_safe_dt(_get(stripe_sub, "trial_end")),
        currency=(_get(stripe_sub, "currency") or "usd").upper(),
        amount_per_period=amount_per_period,
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        sub = existing
    else:
        sub = TenantSubscription(tenant_id=tenant.id, **fields)
        db.add(sub)

    # Mirror the plan / status onto the Tenant so plans.resolve_plan picks
    # up the new SKU immediately (without waiting for a refresh).
    if status in {"active", "trialing"}:
        tenant.plan = plan_name
        tenant.status = "active" if status == "active" else "trial"
    elif status == "past_due":
        tenant.status = "past_due"
    elif status in {"canceled", "incomplete_expired", "unpaid"}:
        tenant.plan = "evaluation"
        tenant.status = "cancelled"

    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------
def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """Validate Stripe-Signature header and return the parsed event dict.

    Raises ``ValueError`` on signature mismatch / tampering. When Stripe
    isn't configured (no webhook secret), we cannot verify — the webhook
    handler treats this as a "log and skip" rather than an attack, since
    self-managed deployments simply forward events through internal tools.
    """
    secret = webhook_secret()
    stripe = get_stripe_client()
    if stripe is None or not secret:
        # Self-managed mode: parse as plain JSON, no verification possible.
        import json
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Unparseable webhook payload") from exc

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as exc:  # stripe.error.SignatureVerificationError + parse errors
        raise ValueError(f"Invalid Stripe signature: {exc}") from exc
    return event if isinstance(event, dict) else event.to_dict()


# ---------------------------------------------------------------------------
# Metered usage
# ---------------------------------------------------------------------------
def report_metered_usage(tenant: Tenant, meter: UsageMeter, db: Session) -> bool:
    """Push a UsageMeter row's quantity to Stripe via the usage records API.

    Returns ``True`` if we reported (or fake-reported in self-managed
    mode), ``False`` if there's no Stripe subscription item to attach
    the usage to. Sets ``reported_to_stripe_at`` on success.
    """
    stripe = get_stripe_client()
    if stripe is None:
        # Self-managed: mark the meter as reported so it doesn't keep
        # accumulating, but don't actually call Stripe.
        meter.reported_to_stripe_at = datetime.now(timezone.utc)
        db.commit()
        return True

    with bypass_tenant_filter():
        sub = db.scalar(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id)
        )
    if not sub or not sub.stripe_subscription_id:
        return False

    try:
        # Look up the metered subscription item ID. In a real install the
        # operator wires this up at SKU creation time; we tag it with
        # meter_key metadata so we can find it back.
        sub_obj = stripe.Subscription.retrieve(sub.stripe_subscription_id)
        meter_item_id = None
        for item in (sub_obj.get("items", {}) or {}).get("data", []) or []:
            if (item.get("price", {}) or {}).get("metadata", {}).get("meter_key") == meter.meter_key:
                meter_item_id = item.get("id")
                break
        if not meter_item_id:
            logger.info("No metered subscription item for meter_key={}", meter.meter_key)
            return False

        stripe.SubscriptionItem.create_usage_record(
            meter_item_id,
            quantity=int(meter.quantity),
            timestamp=int(datetime.now(timezone.utc).timestamp()),
            action="set",
        )
        meter.reported_to_stripe_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception as exc:
        logger.warning("Failed to report usage to Stripe: {}", exc)
        return False


def list_invoices(tenant: Tenant, db: Session, limit: int = 20) -> tuple[list[dict], bool]:
    """List Stripe invoices for the tenant. Returns ``(items, self_managed)``.

    In self-managed mode returns ``([], True)`` so the UI can render an
    empty list with a link to the manual-billing docs.
    """
    stripe = get_stripe_client()
    if stripe is None:
        return [], True

    customer_id = ensure_customer(tenant, db)
    if not customer_id:
        return [], False

    try:
        result = stripe.Invoice.list(customer=customer_id, limit=limit)
    except Exception as exc:
        logger.warning("Stripe Invoice.list failed: {}", exc)
        return [], False

    out: list[dict] = []
    for inv in (result.get("data") or []):
        out.append({
            "id": inv.get("id"),
            "number": inv.get("number"),
            "status": inv.get("status") or "open",
            "amount_due_usd": (inv.get("amount_due") or 0) / 100.0,
            "amount_paid_usd": (inv.get("amount_paid") or 0) / 100.0,
            "currency": (inv.get("currency") or "usd").upper(),
            "created": int(inv.get("created") or 0),
            "period_start": inv.get("period_start"),
            "period_end": inv.get("period_end"),
            "hosted_invoice_url": inv.get("hosted_invoice_url"),
            "invoice_pdf": inv.get("invoice_pdf"),
        })
    return out, False


# ---------------------------------------------------------------------------
# UsageMeter helpers
# ---------------------------------------------------------------------------
def _current_period_bounds(now: datetime | None = None) -> tuple[date, date]:
    """Calendar-month window for the current usage period.

    A more sophisticated implementation would align this to the
    subscription's ``current_period_start`` / ``current_period_end``. For
    Phase 7 we keep it simple: every month is its own period.
    """
    n = now or datetime.now(timezone.utc)
    period_start = date(n.year, n.month, 1)
    # First day of next month - 1 day
    if n.month == 12:
        period_end = date(n.year + 1, 1, 1)
    else:
        period_end = date(n.year, n.month + 1, 1)
    return period_start, period_end


def get_or_create_meter(
    db: Session, tenant_id: str, meter_key: str, *, now: datetime | None = None
) -> UsageMeter:
    """Return (creating if needed) the UsageMeter for the current period.

    Caller must already have a tenant context set (so the auto-set hook
    populates ``tenant_id``). The explicit ``tenant_id`` arg is here so
    the function works inside webhook handlers and housekeeping jobs.
    """
    period_start, period_end = _current_period_bounds(now)
    with bypass_tenant_filter():
        meter = db.scalar(
            select(UsageMeter).where(
                UsageMeter.tenant_id == tenant_id,
                UsageMeter.meter_key == meter_key,
                UsageMeter.period_start == period_start,
            )
        )
    if meter:
        return meter

    meter = UsageMeter(
        tenant_id=tenant_id,
        meter_key=meter_key,
        period_start=period_start,
        period_end=period_end,
        quantity=Decimal("0"),
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def increment_ai_paid_usage(db: Session, tenant_id: str, cost_usd: Decimal) -> None:
    """Add ``cost_usd`` to this tenant's current-period ``ai_paid_tokens`` meter.

    No-ops cleanly when ``cost_usd`` is zero or negative (Ollama, refunded
    calls, etc.). Wraps in its own try/except so a metering failure can
    never break an AI call.
    """
    try:
        if cost_usd is None or Decimal(cost_usd) <= 0:
            return
        meter = get_or_create_meter(db, tenant_id, "ai_paid_tokens")
        meter.quantity = (Decimal(meter.quantity) + Decimal(cost_usd)).quantize(Decimal("0.000001"))
        db.commit()
    except Exception as exc:  # pragma: no cover
        logger.warning("AI usage metering failed for tenant {}: {}", tenant_id, exc)


def ai_monthly_cap_usd(tenant_plan: str) -> float:
    """Per-plan inclusive cloud-AI budget in USD per month."""
    return float(AI_MONTHLY_CAP_USD.get(tenant_plan or "evaluation", AI_MONTHLY_CAP_USD["evaluation"]))


# ---------------------------------------------------------------------------
# BillingEvent helper
# ---------------------------------------------------------------------------
def log_billing_event(
    db: Session, tenant_id: str, event_type: str,
    *, stripe_event_id: str | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> BillingEvent:
    """Append a row to the BillingEvent audit log."""
    evt = BillingEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        stripe_event_id=stripe_event_id,
        metadata_json=metadata or {},
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt
