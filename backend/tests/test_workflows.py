"""Workflow engine + endpoint tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter
from app.models.workflows import Workflow, WorkflowRun
from app.services.event_bus import publish_event, reset_subscribers
from app.services.workflow_engine import register_subscribers


@pytest.fixture(autouse=True)
def _wipe():
    reset_subscribers()
    register_subscribers()
    from app.db.session import SessionLocal

    with SessionLocal() as db, bypass_tenant_filter():
        db.query(WorkflowRun).delete()
        db.query(Workflow).delete()
        db.commit()
    yield
    reset_subscribers()
    with SessionLocal() as db, bypass_tenant_filter():
        db.query(WorkflowRun).delete()
        db.query(Workflow).delete()
        db.commit()


def _create_wf(client, auth_headers, **overrides):
    body = {
        "name": "Notify on lead",
        "trigger_event_type": "crm.lead.created",
        "trigger_filter": {},
        "actions": [
            {"type": "notify_user", "config": {
                "title": "Lead: {{payload.name}}",
                "body": "Source = {{payload.source}}",
            }},
        ],
    }
    body.update(overrides)
    r = client.post("/api/v1/workflows", json=body, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_and_run_synchronously(client, auth_headers, db):
    wf = _create_wf(client, auth_headers)

    # Listing returns it
    r = client.get("/api/v1/workflows", headers=auth_headers)
    assert r.status_code == 200
    assert any(w["id"] == wf["id"] for w in r.json())

    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    publish_event(
        "crm.lead.created",
        payload={"name": "Acme", "source": "google"},
        tenant_id=tenant.id,
    )
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == wf["id"])).all()
    assert len(runs) == 1
    assert runs[0].status == "success"
    # Notification was created
    from app.models.user import Notification
    notes = db.scalars(select(Notification).order_by(Notification.created_at.desc())).all()
    assert any("Acme" in (n.title or "") for n in notes)


def test_filter_excludes_non_matching_events(client, auth_headers, db):
    wf = _create_wf(
        client, auth_headers,
        name="Big deals only",
        trigger_event_type="crm.deal.won",
        trigger_filter={"amount": "> 10000"},
        actions=[{"type": "notify_user", "config": {"title": "Big deal!"}}],
    )
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    publish_event("crm.deal.won", payload={"amount": 500}, tenant_id=tenant.id)
    publish_event("crm.deal.won", payload={"amount": 99999}, tenant_id=tenant.id)
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == wf["id"])).all()
    assert len(runs) == 1
    assert runs[0].event_payload["amount"] == 99999


def test_template_rendering_substitutes_payload(client, auth_headers, db):
    wf = _create_wf(client, auth_headers)
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    publish_event(
        "crm.lead.created",
        payload={"name": "Globex", "source": "linkedin"},
        tenant_id=tenant.id,
    )
    from app.models.user import Notification
    note = db.scalars(
        select(Notification).order_by(Notification.created_at.desc())
    ).first()
    assert "Globex" in note.title
    assert "linkedin" in note.body


def test_action_failure_marks_partial(client, auth_headers, db):
    wf = _create_wf(
        client, auth_headers,
        actions=[
            {"type": "notify_user", "config": {"title": "ok"}},
            {"type": "post_webhook", "config": {"url": ""}},  # bad url → fail
        ],
    )
    from app.models.tenant import Tenant
    tenant = db.scalar(select(Tenant).limit(1))
    publish_event("crm.lead.created", payload={"name": "X"}, tenant_id=tenant.id)
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == wf["id"])).all()
    assert len(runs) == 1
    assert runs[0].status == "partial"
    # Workflow's failures_count bumped
    db.expire_all()
    wf_row = db.get(Workflow, wf["id"])
    assert wf_row.failures_count == 1


def test_cross_tenant_workflows_dont_fire_for_other_tenants(
    client, auth_headers, db, make_tenant,
):
    # Tenant A's workflow
    wf_a = _create_wf(client, auth_headers, name="A workflow")
    # Tenant B fires an event
    tenant_b, _user_b, token_b = make_tenant("wf-iso-b")
    publish_event("crm.lead.created", payload={"name": "B-lead"}, tenant_id=tenant_b.id)
    runs = db.scalars(select(WorkflowRun).where(WorkflowRun.workflow_id == wf_a["id"])).all()
    assert runs == []


def test_unknown_event_type_rejected(client, auth_headers):
    r = client.post(
        "/api/v1/workflows",
        json={
            "name": "Bad trigger",
            "trigger_event_type": "totally.fake.event",
            "actions": [{"type": "notify_user", "config": {"title": "x"}}],
        },
        headers=auth_headers,
    )
    assert r.status_code in (400, 422)


def test_action_types_endpoint(client, auth_headers):
    r = client.get("/api/v1/workflows/action-types", headers=auth_headers)
    assert r.status_code == 200
    types = {row["type"] for row in r.json()}
    assert {"send_slack_message", "send_email", "notify_user", "post_webhook"} <= types
