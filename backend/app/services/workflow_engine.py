"""Workflow execution engine — the no-code 'if X then Y' automation.

Subscribes to every event on the bus. For each incoming event:

  1. Find every active :class:`Workflow` in the event's tenant whose
     ``trigger_event_type`` matches (with fnmatch wildcards).
  2. Evaluate ``trigger_filter`` — a flat dict of ``{dotted.key: op_value}``
     comparisons against the event payload.
  3. For each surviving workflow, render every action's templated strings
     via a sandboxed Jinja2 environment seeded with the event payload.
  4. Execute the actions in order. Failures don't stop the workflow —
     the partial run is recorded so the admin can see exactly which
     action broke.

We deliberately keep the trigger-filter language small: a customer
shouldn't be writing JMESPath in a webform. Supported operators:

* ``"value"`` — exact equality (str or numeric)
* ``"> 1000"`` / ``">= 1000"`` / ``"< 1000"`` / ``"<= 1000"`` — numeric
* ``"!= value"`` — inequality
* ``"in:value1,value2"`` — membership test (str split on commas)

Action types live in :data:`ACTION_TYPES` and are dispatched via
:data:`_ACTION_DISPATCH`. Each action receives the rendered config + the
event + a DB session and returns a ``{ok, detail?, error?}`` dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, TYPE_CHECKING

from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import SessionLocal
from app.models.workflows import Workflow, WorkflowRun

if TYPE_CHECKING:  # pragma: no cover
    from app.services.event_bus import Event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action catalog. The UI renders forms from `config_schema`; the engine
# dispatches by `type`. Keep these in sync.
# ---------------------------------------------------------------------------
ACTION_TYPES: list[dict[str, Any]] = [
    {
        "type": "send_slack_message",
        "description": "Post a message to the tenant's Slack integration.",
        "config_schema": {
            "channel": {"type": "string", "required": False},
            "template": {"type": "string", "required": True},
        },
    },
    {
        "type": "send_email",
        "description": "Send an email to the configured recipient.",
        "config_schema": {
            "to": {"type": "string", "required": True},
            "subject": {"type": "string", "required": True},
            "body": {"type": "string", "required": True},
        },
    },
    {
        "type": "create_calendar_event",
        "description": "Create a calendar event via the Google Workspace integration.",
        "config_schema": {
            "title": {"type": "string", "required": True},
            "when": {"type": "string", "required": False},
        },
    },
    {
        "type": "create_crm_followup",
        "description": "Create a CRM follow-up task.",
        "config_schema": {
            "title": {"type": "string", "required": True},
            "due_at": {"type": "string", "required": False},
            "assigned_to_id": {"type": "string", "required": False},
        },
    },
    {
        "type": "create_task",
        "description": "Create a project task.",
        "config_schema": {
            "title": {"type": "string", "required": True},
            "project_id": {"type": "string", "required": False},
        },
    },
    {
        "type": "post_webhook",
        "description": "POST a JSON body to an arbitrary URL.",
        "config_schema": {
            "url": {"type": "string", "required": True},
            "body": {"type": "object", "required": False},
        },
    },
    {
        "type": "update_field",
        "description": "Patch a field on the triggering record (admin-only).",
        "config_schema": {
            "model": {"type": "string", "required": True},
            "record_id": {"type": "string", "required": True},
            "field": {"type": "string", "required": True},
            "value": {"type": "string", "required": True},
        },
    },
    {
        "type": "notify_user",
        "description": "Create an in-app Notification.",
        "config_schema": {
            "user_id": {"type": "string", "required": False},
            "title": {"type": "string", "required": True},
            "body": {"type": "string", "required": False},
            "level": {"type": "string", "required": False},
        },
    },
]


# ---------------------------------------------------------------------------
# Trigger filter evaluation.
# ---------------------------------------------------------------------------
def _resolve_dotted(payload: dict, path: str) -> Any:
    """Walk a dotted path. Returns None when any segment is missing."""
    cur: Any = payload
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _compare(actual: Any, op_spec: Any) -> bool:
    """Apply one operator comparison. See module docstring for the
    supported micro-language. ``op_spec`` may be a raw value (exact
    equality) or an ``"<op> <value>"`` string."""
    if not isinstance(op_spec, str):
        return actual == op_spec
    s = op_spec.strip()
    for op in (">=", "<=", "!=", ">", "<"):
        if s.startswith(op):
            rhs = s[len(op):].strip()
            try:
                a = float(actual)
                b = float(rhs)
            except (TypeError, ValueError):
                if op == "!=":
                    return str(actual) != rhs
                return False
            if op == ">":
                return a > b
            if op == "<":
                return a < b
            if op == ">=":
                return a >= b
            if op == "<=":
                return a <= b
            if op == "!=":
                return a != b
    if s.startswith("in:"):
        members = [m.strip() for m in s[3:].split(",")]
        return str(actual) in members
    return str(actual) == s


def _filter_matches(payload: dict, trig_filter: dict) -> bool:
    """Every clause must pass. Empty filter always matches."""
    if not trig_filter:
        return True
    for path, spec in trig_filter.items():
        actual = _resolve_dotted(payload, path)
        if not _compare(actual, spec):
            return False
    return True


# ---------------------------------------------------------------------------
# Jinja2 templating — sandboxed so a workflow can't execute arbitrary code.
# ---------------------------------------------------------------------------
def _render_template(value: Any, ctx: dict) -> Any:
    """Render a single string with Jinja2. Non-strings pass through.

    A SandboxedEnvironment prevents access to dunders / imports. We don't
    pre-compile templates because workflows are low-volume and the
    sandbox env is cheap to construct."""
    if not isinstance(value, str):
        return value
    if "{{" not in value and "{%" not in value:
        return value
    try:
        from jinja2.sandbox import SandboxedEnvironment

        env = SandboxedEnvironment(autoescape=False)
        return env.from_string(value).render(**ctx)
    except Exception:
        return value


def _render_config(config: dict, ctx: dict) -> dict:
    out = {}
    for k, v in (config or {}).items():
        if isinstance(v, str):
            out[k] = _render_template(v, ctx)
        elif isinstance(v, dict):
            out[k] = _render_config(v, ctx)
        elif isinstance(v, list):
            out[k] = [_render_template(item, ctx) for item in v]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Trigger matching.
# ---------------------------------------------------------------------------
def _trigger_matches(workflow: Workflow, event: "Event") -> bool:
    """Combine event-type wildcard + payload-filter check."""
    import fnmatch

    pat = workflow.trigger_event_type or ""
    if pat != "*" and pat != event.type and not fnmatch.fnmatch(event.type, pat):
        return False
    return _filter_matches(event.payload or {}, workflow.trigger_filter or {})


# ---------------------------------------------------------------------------
# Action dispatch.
# ---------------------------------------------------------------------------
def _action_send_slack_message(config: dict, event: "Event", db) -> dict:
    """Use the tenant's Slack integration to post a message."""
    from app.core.encryption import decrypt_field
    from app.models.integrations import TenantIntegration
    from app.services.integrations import slack as slack_mod

    with bypass_tenant_filter():
        integ = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == event.tenant_id,
                TenantIntegration.key == "slack",
                TenantIntegration.is_enabled.is_(True),
            )
        )
    if integ is None:
        return {"ok": False, "error": "Slack integration not installed for tenant"}
    token = decrypt_field(integ.access_token_encrypted or "", event.tenant_id, db=db)
    channel = config.get("channel") or (integ.config or {}).get("default_channel")
    text = config.get("template") or config.get("text") or ""
    if not channel or not text:
        return {"ok": False, "error": "channel + template are required"}
    import json as _json

    client = slack_mod._http_client()
    try:
        resp = client.post(
            slack_mod._CHAT_POST_MESSAGE,
            content=_json.dumps({"channel": channel, "text": text}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=10.0,
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    status = getattr(resp, "status_code", None)
    if status is not None and 200 <= status < 300:
        return {"ok": True, "detail": {"status": status}}
    return {"ok": False, "error": f"slack post failed status={status}"}


def _action_send_email(config: dict, event: "Event", db) -> dict:
    from app.services.email import send_email

    to = config.get("to", "")
    subject = config.get("subject", "")
    body = config.get("body", "")
    if not to or not subject:
        return {"ok": False, "error": "to + subject are required"}
    try:
        send_email(to=to, subject=subject, body_text=body)
        return {"ok": True, "detail": {"to": to}}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _action_create_calendar_event(config: dict, event: "Event", db) -> dict:
    """Republish a synthetic event so the Google Workspace handler reacts.

    Avoids duplicating Google API plumbing — the connector already knows
    how to create a calendar event from a ``projects.project.created``
    payload."""
    from app.services.event_bus import publish_event

    ev = publish_event(
        "projects.project.created",
        payload={
            "title": config.get("title", "Workflow calendar event"),
            "kickoff_at": config.get("when"),
            "description": config.get("description", ""),
            "source": "workflow",
        },
        tenant_id=event.tenant_id,
    )
    return {"ok": True, "detail": {"event_id": ev.id}}


def _action_create_crm_followup(config: dict, event: "Event", db) -> dict:
    """Create a CRM FollowUp. ``due_at`` is required by the model; if the
    config doesn't supply one we default to now (the user can edit it)."""
    from app.models.crm import FollowUp
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    due_at: _dt = _dt.now(_tz.utc)
    if config.get("due_at"):
        try:
            due_at = _dt.fromisoformat(str(config["due_at"]))
        except Exception:
            pass
    try:
        f = FollowUp(
            due_at=due_at,
            notes=config.get("notes") or config.get("title") or "Workflow follow-up",
            contact_id=config.get("contact_id"),
        )
        db.add(f)
        db.commit()
        db.refresh(f)
        return {"ok": True, "detail": {"followup_id": f.id}}
    except Exception as exc:
        db.rollback()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _action_create_task(config: dict, event: "Event", db) -> dict:
    from app.models.projects import Task

    try:
        t = Task(
            title=config.get("title", "Workflow task"),
            description=config.get("description", ""),
            project_id=config.get("project_id"),
            status="todo",
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        return {"ok": True, "detail": {"task_id": t.id}}
    except Exception as exc:
        db.rollback()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _action_post_webhook(config: dict, event: "Event", db) -> dict:
    import json as _json

    import httpx

    url = config.get("url")
    if not url:
        return {"ok": False, "error": "url required"}
    body = config.get("body") or {
        "event_type": event.type,
        "tenant_id": event.tenant_id,
        "payload": event.payload,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                content=_json.dumps(body, default=str).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
        return {"ok": 200 <= resp.status_code < 300, "detail": {"status": resp.status_code}}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _action_update_field(config: dict, event: "Event", db) -> dict:
    return {"ok": False, "error": "update_field action not implemented in this release"}


def _action_notify_user(config: dict, event: "Event", db) -> dict:
    from app.models.user import Notification

    try:
        note = Notification(
            user_id=config.get("user_id"),
            title=config.get("title", "Workflow notification"),
            body=config.get("body", ""),
            level=config.get("level", "info"),
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return {"ok": True, "detail": {"notification_id": note.id}}
    except Exception as exc:
        db.rollback()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


_ACTION_DISPATCH: dict[str, Callable] = {
    "send_slack_message": _action_send_slack_message,
    "send_email": _action_send_email,
    "create_calendar_event": _action_create_calendar_event,
    "create_crm_followup": _action_create_crm_followup,
    "create_task": _action_create_task,
    "post_webhook": _action_post_webhook,
    "update_field": _action_update_field,
    "notify_user": _action_notify_user,
}


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------
def execute_workflow(workflow: Workflow, event: "Event", db) -> WorkflowRun:
    """Run one workflow against one event. Returns the persisted WorkflowRun row."""
    started = datetime.now(timezone.utc)
    ctx = {"payload": event.payload, "event": {"type": event.type, "id": event.id}}

    results: list[dict] = []
    successes = 0
    for action in (workflow.actions or []):
        if not isinstance(action, dict):
            results.append({"ok": False, "error": "malformed action"})
            continue
        a_type = action.get("type")
        raw_cfg = action.get("config") or {}
        cfg = _render_config(raw_cfg, ctx)
        handler = _ACTION_DISPATCH.get(a_type)
        if handler is None:
            results.append({"type": a_type, "ok": False, "error": "unknown action type"})
            continue
        try:
            res = handler(cfg, event, db)
        except Exception as exc:
            logger.exception("workflow action %s crashed", a_type)
            res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        res["type"] = a_type
        results.append(res)
        if res.get("ok"):
            successes += 1

    finished = datetime.now(timezone.utc)
    total = len(results)
    if successes == 0 and total > 0:
        status = "failure"
    elif successes < total:
        status = "partial"
    else:
        status = "success"

    workflow.last_run_at = finished
    workflow.runs_count = (workflow.runs_count or 0) + 1
    if status != "success":
        workflow.failures_count = (workflow.failures_count or 0) + 1
    run = WorkflowRun(
        workflow_id=workflow.id,
        tenant_id=workflow.tenant_id,
        event_id=event.id,
        event_type=event.type,
        event_payload=event.payload or {},
        started_at=started,
        finished_at=finished,
        status=status,
        action_results=results,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _on_event(event: "Event") -> None:
    """Event-bus callback. Finds matching workflows in the event's tenant
    and executes each. Catches every exception so the publish loop is
    never disturbed."""
    if event.tenant_id is None:
        return
    db = SessionLocal()
    try:
        with bypass_tenant_filter():
            workflows = db.scalars(
                select(Workflow).where(
                    Workflow.tenant_id == event.tenant_id,
                    Workflow.is_active.is_(True),
                )
            ).all()
        for wf in workflows:
            if not _trigger_matches(wf, event):
                continue
            try:
                with tenant_scope(wf.tenant_id):
                    execute_workflow(wf, event, db)
            except Exception:
                logger.exception("workflow %s execution failed", wf.id)
    finally:
        db.close()


def register_subscribers() -> None:
    """Wire the engine into the event bus. Idempotent."""
    from app.services.event_bus import subscribe, unsubscribe

    unsubscribe("*", _on_event)
    subscribe("*", _on_event)


def list_action_types() -> list[dict[str, Any]]:
    return list(ACTION_TYPES)
