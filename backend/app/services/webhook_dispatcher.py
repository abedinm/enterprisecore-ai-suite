"""Outbound webhook delivery.

Given an ``Event``, look up matching ``WebhookSubscription`` rows for the
event's tenant, build a signed HTTP request, POST it, and record the
attempt as a ``WebhookDelivery`` row. On failure schedule a retry with
exponential backoff. After 6 consecutive failures the subscription is
paused for 24h; if failures persist past that it is deactivated.

The actual HTTP call goes through ``httpx`` with a 10s timeout. Calls are
made synchronously (the suite is largely sync-first), so an endpoint that
publishes an event waits for delivery before returning. For high-volume
endpoints, we expect the consumer to run a Redis worker (see
``event_bus_redis.py``) and not the in-process dispatcher.

Tests inject a ``set_http_client(...)`` mock so they don't actually POST.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.db.session import SessionLocal
from app.models.webhooks import WebhookDelivery, WebhookSubscription

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


# Retry schedule in seconds: 1st immediate (attempt 1), then 1m, 5m, 30m,
# 2h, 12h, 24h. After the 7th total attempt (6 retries) we stop retrying
# and mark the subscription paused for 24h.
_BACKOFF_SECONDS = [60, 300, 1800, 7200, 43200, 86400]
_MAX_ATTEMPTS = len(_BACKOFF_SECONDS) + 1  # 7

_HTTP_TIMEOUT = 10.0


# Injectable for tests. Module-level so a test can monkeypatch one call site.
_http_client_factory = None


def set_http_client_factory(factory) -> None:
    """Tests call this to substitute a fake httpx client.

    The factory is called with no args and must return an object exposing
    ``.post(url, content=..., headers=..., timeout=...)`` returning an
    object with ``.status_code`` + ``.text``.
    """

    global _http_client_factory
    _http_client_factory = factory


def _get_http_client():
    if _http_client_factory is not None:
        return _http_client_factory()
    import httpx

    return httpx.Client(timeout=_HTTP_TIMEOUT)


# ---- secret management ---------------------------------------------------

def generate_secret() -> str:
    """Return a fresh 48-char URL-safe secret. Caller is responsible for
    encrypting + persisting it on the subscription row + showing it to the
    user exactly once."""

    return secrets.token_urlsafe(32)


def _decrypt_secret(subscription: WebhookSubscription) -> str:
    """Return the plaintext secret. Decryption errors are logged and the
    delivery is recorded with an explanatory excerpt rather than crashing
    the publish loop."""

    from app.core.security import decrypt_text

    return decrypt_text(subscription.secret_encrypted)


def _sign(secret: str, body: bytes) -> str:
    """HMAC-SHA256 over the raw request body. Returned in
    ``X-EC-Signature: sha256=<hex>`` form."""

    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---- subscription matching -----------------------------------------------

def _matches_subscription(sub: WebhookSubscription, event_type: str) -> bool:
    """A subscription matches if any of its ``event_types`` patterns
    (fnmatch-style) matches ``event.type``. ``["*"]`` matches everything."""

    import fnmatch

    for pat in sub.event_types or []:
        if pat == "*" or pat == event_type:
            return True
        if fnmatch.fnmatch(event_type, pat):
            return True
    return False


# ---- main dispatch entry point -------------------------------------------

def dispatch_for_event(event: "Event") -> list[str]:
    """Look up + deliver to every matching subscription. Returns the list of
    ``WebhookDelivery.id`` values created (one per matched subscription)."""

    if event.tenant_id is None:
        # Cross-tenant / system events don't carry a tenant scope, so no
        # subscription can match them. Skip cleanly.
        return []

    db = SessionLocal()
    delivery_ids: list[str] = []
    try:
        # We must bypass the tenant auto-filter here: the publisher's request
        # is on the same tenant, but background jobs (housekeeping, Redis
        # worker) call into here without a tenant context set.
        with bypass_tenant_filter():
            stmt = (
                select(WebhookSubscription)
                .where(WebhookSubscription.tenant_id == event.tenant_id)
                .where(WebhookSubscription.is_active.is_(True))
            )
            subs = db.scalars(stmt).all()

        now = datetime.now(timezone.utc)
        for sub in subs:
            if sub.disabled_until and sub.disabled_until > now:
                continue
            if not _matches_subscription(sub, event.type):
                continue
            try:
                did = deliver(db, sub, event, attempt_number=1)
                if did:
                    delivery_ids.append(did)
            except Exception:
                logger.exception(
                    "deliver() crashed for sub=%s event=%s", sub.id, event.id
                )
        return delivery_ids
    finally:
        db.close()


def deliver(
    db,
    subscription: WebhookSubscription,
    event: "Event",
    *,
    attempt_number: int = 1,
) -> str | None:
    """Build the signed request, POST it, record the outcome. Returns the
    ``WebhookDelivery.id`` of the row written. ``None`` if secret decryption
    failed and the attempt couldn't be made."""

    body_obj: dict[str, Any] = {
        "id": event.id,
        "type": event.type,
        "tenant_id": event.tenant_id,
        "user_id": event.user_id,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event.payload,
    }
    body_bytes = json.dumps(body_obj, sort_keys=True, default=str).encode("utf-8")

    try:
        secret = _decrypt_secret(subscription)
    except Exception:
        logger.exception("could not decrypt secret for sub %s", subscription.id)
        # Still record the failed attempt so the user sees a meaningful row.
        d = WebhookDelivery(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            event_id=event.id,
            event_type=event.type,
            payload_json=body_obj,
            request_signature="",
            attempt_number=attempt_number,
            response_status=None,
            response_body_excerpt="secret decryption failed",
            next_retry_at=None,
        )
        db.add(d)
        db.commit()
        return d.id

    signature_hex = _sign(secret, body_bytes)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "EnterpriseCore-Webhook/1.0",
        "X-EC-Event-Id": event.id,
        "X-EC-Event-Type": event.type,
        "X-EC-Signature": f"sha256={signature_hex}",
        "X-EC-Timestamp": event.occurred_at.isoformat(),
        "X-EC-Attempt": str(attempt_number),
    }

    delivery = WebhookDelivery(
        tenant_id=subscription.tenant_id,
        subscription_id=subscription.id,
        event_id=event.id,
        event_type=event.type,
        payload_json=body_obj,
        request_signature=f"sha256={signature_hex}",
        attempt_number=attempt_number,
    )
    db.add(delivery)
    db.flush()

    started = datetime.now(timezone.utc)
    status_code: int | None = None
    body_excerpt: str | None = None
    try:
        client = _get_http_client()
        try:
            resp = client.post(
                subscription.url,
                content=body_bytes,
                headers=headers,
                timeout=_HTTP_TIMEOUT,
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        status_code = getattr(resp, "status_code", None)
        text = getattr(resp, "text", "") or ""
        body_excerpt = text[:500] if text else None
    except Exception as exc:
        body_excerpt = f"transport error: {type(exc).__name__}: {exc}"[:500]
        status_code = None
    duration_ms = int(
        (datetime.now(timezone.utc) - started).total_seconds() * 1000
    )

    delivery.delivered_at = datetime.now(timezone.utc)
    delivery.response_status = status_code
    delivery.response_body_excerpt = body_excerpt
    delivery.duration_ms = duration_ms

    success = status_code is not None and 200 <= status_code < 300
    subscription.last_delivered_at = delivery.delivered_at
    subscription.last_delivery_status = status_code

    if success:
        subscription.consecutive_failures = 0
        subscription.disabled_until = None
        delivery.next_retry_at = None
    else:
        subscription.consecutive_failures = (subscription.consecutive_failures or 0) + 1
        # Schedule next retry if budget remains
        if attempt_number < _MAX_ATTEMPTS:
            wait = _BACKOFF_SECONDS[attempt_number - 1]
            delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=wait)
        else:
            delivery.next_retry_at = None
            # Pause the subscription for 24h after exhausting the retry budget
            subscription.disabled_until = datetime.now(timezone.utc) + timedelta(hours=24)
        # After enough consecutive failures, hard-disable.
        if subscription.consecutive_failures >= 24:
            subscription.is_active = False

    db.commit()
    return delivery.id


def retry_delivery(db, delivery_id: str) -> str | None:
    """Re-fire a prior delivery by id. Used by the manual-retry endpoint and
    by the scheduled retry worker."""

    delivery = db.get(WebhookDelivery, delivery_id)
    if delivery is None:
        return None
    sub = db.get(WebhookSubscription, delivery.subscription_id)
    if sub is None or not sub.is_active:
        return None
    # Reconstruct the event from the stored payload so signature recomputes
    # against the same body. occurred_at is recovered from payload.
    from app.services.event_bus import Event

    payload = delivery.payload_json or {}
    occurred = payload.get("occurred_at")
    try:
        when = (
            datetime.fromisoformat(occurred)
            if isinstance(occurred, str)
            else datetime.now(timezone.utc)
        )
    except Exception:
        when = datetime.now(timezone.utc)
    event = Event(
        id=delivery.event_id,
        type=delivery.event_type,
        tenant_id=delivery.tenant_id,
        user_id=payload.get("user_id"),
        occurred_at=when,
        payload=payload.get("payload", {}),
    )
    return deliver(db, sub, event, attempt_number=delivery.attempt_number + 1)
