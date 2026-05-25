"""Internal event bus + outbound-webhook trigger.

Most application changes in the suite should fire an event from here so:

  1. External systems (Zapier, Slack, billing) can subscribe via outbound
     webhook and react.
  2. Internal cross-module reactions (e.g. AI spend thresholds → email,
     marketing → search-index rebuild) can register a synchronous handler
     via ``subscribe()`` without coupling endpoint code to the consumer.

The default backend is in-process: ``publish(evt)`` writes a
``WebhookDelivery`` row for each matching subscription, dispatches via
``app.services.webhook_dispatcher.deliver``, then calls each in-process
``subscribe()`` handler synchronously in registration order.

If ``REDIS_URL`` is set, the publish call instead pushes onto a per-tenant
Redis stream (``events:<tenant_id>``) — see ``event_bus_redis.py`` for the
worker that drains it. The synchronous handlers still run regardless.
"""
from __future__ import annotations

import fnmatch
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)


# Canonical event catalog. KEEP NAMESPACES STABLE — third-party integrations
# subscribe to specific event types, and renaming an event silently breaks
# their workflow without any compile-time signal. New events: append.
EVENT_TYPES: dict[str, str] = {
    # CRM
    "crm.lead.created": "A new sales lead was created.",
    "crm.lead.updated": "A sales lead's details were updated.",
    "crm.deal.won": "A deal moved to the 'won' stage.",
    "crm.deal.lost": "A deal moved to the 'lost' stage.",
    # Finance
    "finance.invoice.created": "A new invoice was issued.",
    "finance.invoice.paid": "An invoice was marked paid.",
    "finance.invoice.overdue": "An invoice crossed its due date unpaid.",
    # HR
    "hr.employee.created": "A new employee record was created.",
    "hr.employee.terminated": "An employee was marked terminated.",
    "hr.leave.approved": "A leave request was approved.",
    # Projects + Tasks
    "projects.project.created": "A new project was created.",
    "projects.task.completed": "A task was marked completed.",
    # Webchat
    "webchat.conversation.created": "A new public webchat conversation started.",
    "webchat.contact_linked": "A webchat conversation was linked to a CRM contact.",
    "webchat.message.received": "A new user message arrived on a webchat conversation.",
    # Marketing
    "marketing.post.published": "A blog/marketing post was published.",
    "marketing.template.applied": "A marketing site template was applied.",
    # Construction
    "construction.project.created": "A new construction project was created.",
    "construction.risk.created": "A construction risk was logged.",
    "construction.variation.approved": "A construction variation order was approved.",
    # Knowledge
    "knowledge.document.ingested": "A knowledge-base document finished ingesting.",
    # Tenant lifecycle
    "tenant.created": "A new tenant signed up.",
    "tenant.plan.changed": "A tenant's plan was changed.",
    "tenant.cancelled": "A tenant cancelled their subscription.",
    # User lifecycle
    "user.invited": "A user was invited to a tenant.",
    "user.activated": "A user activated their account.",
    "user.deactivated": "A user was deactivated.",
    # AI usage
    "ai.spend.threshold_crossed": "Monthly AI spend crossed 50/80/100% of cap.",
    # Billing
    "billing.subscription.upgraded": "A subscription was upgraded.",
    "billing.payment.failed": "A payment attempt failed.",
    # Background jobs — used by the realtime channel so dashboards can show
    # job lifecycle without polling. Subscribers in app/services/realtime.py.
    "jobs.queued": "A background job was enqueued.",
    "jobs.started": "A background job started executing.",
    "jobs.completed": "A background job finished successfully.",
    "jobs.failed": "A background job failed.",
    # Internal test event — used by POST /webhooks/subscriptions/{id}/test.
    "webhook.test": "Test ping fired by the user from the dashboard.",
}


_EVENT_MODULE_PREFIX_RE = None  # populated lazily; not strictly needed


class Event(NamedTuple):
    """One published event.

    ``id`` is a ULID; consumers use it as an idempotency key. ``tenant_id``
    is populated from the current tenant context, so handlers + outbound
    webhooks scoped to a tenant don't cross beams. ``payload`` is event-
    specific JSON: schemas live in docs/WEBHOOKS.md, not enforced in code.
    """

    id: str
    type: str
    tenant_id: str | None
    user_id: str | None
    occurred_at: datetime
    payload: dict


# In-process subscriber registry. Maps event_type pattern → list of handlers.
# Patterns support fnmatch wildcards (``crm.*``, ``*.created``, ``*``).
_subscribers: dict[str, list[Callable[[Event], None]]] = {}


def subscribe(event_type: str, handler: Callable[[Event], None]) -> None:
    """Register a synchronous handler for matching events.

    Handlers run inside ``publish()`` in the caller's thread/transaction.
    Exceptions are caught + logged so a buggy handler can't break the
    publishing endpoint.
    """

    _subscribers.setdefault(event_type, []).append(handler)


def unsubscribe(event_type: str, handler: Callable[[Event], None]) -> None:
    """Remove a previously-registered handler. No-op if not present.
    Mainly used by tests to keep the global registry clean.
    """

    handlers = _subscribers.get(event_type, [])
    if handler in handlers:
        handlers.remove(handler)


def _matches(pattern: str, event_type: str) -> bool:
    """Pattern match supporting * wildcards (fnmatch style)."""

    if pattern == event_type or pattern == "*":
        return True
    return fnmatch.fnmatch(event_type, pattern)


def _new_event_id() -> str:
    try:
        from ulid import ULID

        return str(ULID())
    except Exception:
        import uuid

        return uuid.uuid4().hex


def _redis_enabled() -> bool:
    return bool(os.environ.get("REDIS_URL"))


def publish(event: Event) -> None:
    """Publish an event.

    Side effects (in order):

    1. ``WebhookSubscription`` rows whose ``event_types`` match are looked up;
       a ``WebhookDelivery`` row is created + dispatched via httpx.
    2. If ``REDIS_URL`` is set, the event is also pushed onto the per-tenant
       stream so cross-process workers can react.
    3. In-process ``subscribe()`` handlers are invoked synchronously.

    Failures in any of these are logged but never propagated — publishers
    (endpoint code) must not be impacted by a misbehaving subscriber.
    """

    # --- outbound webhooks (DB-backed subscribers) -------------------------
    try:
        from app.services.webhook_dispatcher import dispatch_for_event

        dispatch_for_event(event)
    except Exception:  # pragma: no cover — defensive
        logger.exception("webhook dispatch failed for event %s", event.type)

    # --- optional Redis stream (cross-process fanout) ---------------------
    if _redis_enabled():
        try:
            from app.services.event_bus_redis import push_to_stream

            push_to_stream(event)
        except Exception:  # pragma: no cover
            logger.exception("redis stream push failed for event %s", event.type)

    # --- in-process handlers ----------------------------------------------
    for pattern, handlers in list(_subscribers.items()):
        if not _matches(pattern, event.type):
            continue
        for handler in list(handlers):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "in-process subscriber for %s raised", event.type
                )


def publish_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    user_id: str | None = None,
    tenant_id: str | None = None,
) -> Event:
    """Shortcut used by endpoint code.

    Resolves ``tenant_id`` from the current tenant context when not passed.
    Returns the ``Event`` so callers can log the id if useful.
    """

    if tenant_id is None:
        try:
            from app.core.tenant_context import get_current_tenant_id

            tenant_id = get_current_tenant_id()
        except Exception:
            tenant_id = None

    event = Event(
        id=_new_event_id(),
        type=event_type,
        tenant_id=tenant_id,
        user_id=user_id,
        occurred_at=datetime.now(timezone.utc),
        payload=payload or {},
    )
    publish(event)
    return event


def list_event_types() -> list[dict[str, str]]:
    """Return the catalog as a list of ``{type, module, description}`` dicts."""

    out: list[dict[str, str]] = []
    for key, desc in EVENT_TYPES.items():
        module = key.split(".", 1)[0]
        out.append({"type": key, "module": module, "description": desc})
    return out


def reset_subscribers() -> None:
    """Test-only helper. Wipes the in-process subscriber registry."""

    _subscribers.clear()
