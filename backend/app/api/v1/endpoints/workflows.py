"""Workflow CRUD + run inspection endpoints.

A workflow is a no-code 'if-this-then-that' rule the tenant builds in
the UI. The execution engine subscribes to every event and runs every
matching active workflow; this module just exposes the CRUD surface +
a synthetic test-fire endpoint.

Per-tenant caps live here rather than in the engine so the user gets a
422 at create time instead of a silent ignore at execution.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.cache import cache_response
from app.core.exceptions import NotFoundError, ValidationFailed
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.workflows import Workflow, WorkflowRun
from app.schemas.workflows import (
    WorkflowActionTypeInfo, WorkflowIn, WorkflowOut, WorkflowRunOut,
    WorkflowUpdate,
)
from app.services.audit import record_audit
from app.services.event_bus import EVENT_TYPES, publish_event
from app.services.workflow_engine import ACTION_TYPES, _ACTION_DISPATCH, list_action_types

router = APIRouter()


_MAX_ACTIVE_WORKFLOWS = 100
_MAX_ACTIONS_PER_WORKFLOW = 10


def _to_out(wf: Workflow) -> dict:
    return {
        "id": wf.id,
        "created_at": wf.created_at,
        "updated_at": wf.updated_at,
        "name": wf.name,
        "description": wf.description,
        "is_active": wf.is_active,
        "trigger_event_type": wf.trigger_event_type,
        "trigger_filter": wf.trigger_filter or {},
        "actions": wf.actions or [],
        "last_run_at": wf.last_run_at,
        "runs_count": wf.runs_count or 0,
        "failures_count": wf.failures_count or 0,
        "created_by_id": wf.created_by_id,
    }


def _validate_event_type(event_type: str) -> None:
    """Allow wildcard patterns + bare prefix patterns + exact catalog keys.

    Rejects garbage like 'crm.foo.bar' that no event will ever match, so
    a typo doesn't silently produce a dead workflow."""
    if event_type == "*":
        return
    if event_type in EVENT_TYPES:
        return
    if "*" in event_type:
        prefix = event_type.split("*", 1)[0].rstrip(".")
        if any(t.startswith(prefix) for t in EVENT_TYPES):
            return
    raise ValidationFailed(f"Unknown trigger_event_type: {event_type}")


def _validate_actions(actions: list) -> None:
    if len(actions) > _MAX_ACTIONS_PER_WORKFLOW:
        raise ValidationFailed(
            f"Too many actions ({len(actions)} > {_MAX_ACTIONS_PER_WORKFLOW})"
        )
    known = set(_ACTION_DISPATCH.keys())
    for a in actions:
        a_type = getattr(a, "type", None) if not isinstance(a, dict) else a.get("type")
        if a_type not in known:
            raise ValidationFailed(f"Unknown action type: {a_type}")


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.scalars(select(Workflow).order_by(Workflow.created_at.desc())).all()
    return [_to_out(w) for w in rows]


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(
    payload: WorkflowIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    _validate_event_type(payload.trigger_event_type)
    _validate_actions(payload.actions)

    # Per-tenant cap on active workflows.
    if payload.is_active:
        active_count = db.scalar(
            select(func.count()).select_from(Workflow).where(Workflow.is_active.is_(True))
        ) or 0
        if active_count >= _MAX_ACTIVE_WORKFLOWS:
            raise ValidationFailed(
                f"Active workflow cap reached ({_MAX_ACTIVE_WORKFLOWS}). "
                "Disable an existing workflow first."
            )

    wf = Workflow(
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        trigger_event_type=payload.trigger_event_type,
        trigger_filter=payload.trigger_filter or {},
        actions=[a.model_dump() for a in payload.actions],
        created_by_id=user.id,
    )
    db.add(wf)
    db.flush()
    record_audit(
        db, actor=user, action="create", entity_type="workflow",
        entity_id=wf.id, detail={"name": wf.name},
    )
    db.commit()
    db.refresh(wf)
    return _to_out(wf)


@router.get("/action-types", response_model=list[WorkflowActionTypeInfo])
@cache_response(ttl=3600, namespace="workflows:action-types")
def get_action_types(response: Response, _: User = Depends(get_current_user)):
    return list_action_types()


@router.get("/{wf_id}", response_model=WorkflowOut)
def get_workflow(
    wf_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise NotFoundError("Workflow not found")
    return _to_out(wf)


@router.patch("/{wf_id}", response_model=WorkflowOut)
def update_workflow(
    wf_id: str,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise NotFoundError("Workflow not found")
    if payload.name is not None:
        wf.name = payload.name
    if payload.description is not None:
        wf.description = payload.description
    if payload.is_active is not None:
        wf.is_active = payload.is_active
    if payload.trigger_event_type is not None:
        _validate_event_type(payload.trigger_event_type)
        wf.trigger_event_type = payload.trigger_event_type
    if payload.trigger_filter is not None:
        wf.trigger_filter = payload.trigger_filter
    if payload.actions is not None:
        _validate_actions(payload.actions)
        wf.actions = [a.model_dump() for a in payload.actions]
    record_audit(
        db, actor=user, action="update", entity_type="workflow",
        entity_id=wf.id,
    )
    db.commit()
    db.refresh(wf)
    return _to_out(wf)


@router.delete("/{wf_id}", status_code=204)
def delete_workflow(
    wf_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    wf = db.get(Workflow, wf_id)
    if wf:
        record_audit(
            db, actor=user, action="delete", entity_type="workflow",
            entity_id=wf.id,
        )
        db.delete(wf)
        db.commit()
    return None


@router.post("/{wf_id}/test")
def test_workflow(
    wf_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Fire a synthetic event that matches the workflow's trigger. Useful
    for smoke-testing template rendering + action wiring without waiting
    for a real business event."""
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise NotFoundError("Workflow not found")
    event_type = wf.trigger_event_type
    if event_type == "*" or "*" in event_type:
        # Pick the first concrete event type that matches the pattern.
        import fnmatch
        for t in EVENT_TYPES:
            if event_type == "*" or fnmatch.fnmatch(t, event_type):
                event_type = t
                break
        else:
            event_type = "webhook.test"
    ev = publish_event(
        event_type,
        payload={"test": True, "workflow_id": wf.id, "fired_by": user.email},
        user_id=user.id,
        tenant_id=wf.tenant_id,
    )
    return {"event_id": ev.id, "status": "queued"}


@router.get("/{wf_id}/runs", response_model=list[WorkflowRunOut])
def list_runs(
    wf_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    wf = db.get(Workflow, wf_id)
    if not wf:
        raise NotFoundError("Workflow not found")
    rows = db.scalars(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == wf_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    ).all()
    return rows
