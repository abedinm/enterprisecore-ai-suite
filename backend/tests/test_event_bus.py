"""Tests for the in-process event bus."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from app.services import event_bus
from app.services.event_bus import (
    EVENT_TYPES, Event, list_event_types, publish, publish_event, reset_subscribers,
    subscribe, unsubscribe,
)


@pytest.fixture(autouse=True)
def _clean_subscribers():
    reset_subscribers()
    yield
    reset_subscribers()


def test_event_types_catalog_covers_required_modules():
    keys = set(EVENT_TYPES)
    # A subset that must always exist — tests pin the contract.
    required = {
        "crm.lead.created", "crm.deal.won", "crm.deal.lost",
        "finance.invoice.created", "finance.invoice.paid", "finance.invoice.overdue",
        "hr.employee.created", "hr.leave.approved",
        "projects.project.created", "projects.task.completed",
        "webchat.conversation.created", "webchat.contact_linked",
        "construction.project.created", "construction.risk.created",
        "construction.variation.approved",
        "marketing.post.published", "marketing.template.applied",
        "knowledge.document.ingested",
        "webhook.test",
    }
    missing = required - keys
    assert not missing, f"missing event types: {missing}"


def test_list_event_types_returns_modules():
    listed = list_event_types()
    by_type = {e["type"]: e for e in listed}
    assert by_type["crm.lead.created"]["module"] == "crm"
    assert "description" in by_type["crm.lead.created"]


def test_publish_invokes_synchronous_subscriber():
    seen: list[Event] = []

    def handler(ev: Event):
        seen.append(ev)

    subscribe("crm.lead.created", handler)
    event = publish_event(
        "crm.lead.created",
        payload={"lead_id": "abc"},
        tenant_id="t1",
        user_id="u1",
    )
    assert len(seen) == 1
    assert seen[0].type == "crm.lead.created"
    assert seen[0].payload == {"lead_id": "abc"}
    assert seen[0].id == event.id


def test_subscribe_wildcards_match():
    seen: list[str] = []

    def all_crm(ev: Event):
        seen.append(ev.type)

    subscribe("crm.*", all_crm)
    publish_event("crm.lead.created", tenant_id="t1")
    publish_event("crm.deal.won", tenant_id="t1")
    publish_event("finance.invoice.paid", tenant_id="t1")
    assert seen == ["crm.lead.created", "crm.deal.won"]


def test_unsubscribe_removes_handler():
    seen = []

    def handler(ev):
        seen.append(ev.type)

    subscribe("crm.lead.created", handler)
    unsubscribe("crm.lead.created", handler)
    publish_event("crm.lead.created", tenant_id="t1")
    assert seen == []


def test_publish_event_pulls_tenant_from_context():
    from app.core.tenant_context import tenant_scope

    captured: list[Event] = []
    subscribe("crm.lead.created", lambda e: captured.append(e))
    with tenant_scope("ctx-tenant-42"):
        publish_event("crm.lead.created", payload={"x": 1})
    assert captured[0].tenant_id == "ctx-tenant-42"


def test_failing_subscriber_does_not_break_publish():
    def bad(_ev):
        raise RuntimeError("boom")

    fine_seen = []

    def fine(_ev):
        fine_seen.append(1)

    subscribe("crm.lead.created", bad)
    subscribe("crm.lead.created", fine)
    # Must not raise.
    publish_event("crm.lead.created", tenant_id="t1")
    assert fine_seen == [1]


@pytest.mark.skipif(
    not os.environ.get("REDIS_URL"),
    reason="Redis not configured; skipping stream test in default CI.",
)
def test_redis_stream_push_when_configured():
    # Best-effort smoke test for the Redis backend. Skipped when no Redis.
    publish_event("webhook.test", payload={}, tenant_id="t-redis")
