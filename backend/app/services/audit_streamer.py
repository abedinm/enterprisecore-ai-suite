"""Audit log streaming service.

Watches the ``audit_logs`` table for new rows and POSTs them to every
active :class:`AuditStreamDestination` for the corresponding tenant.

Design:

* Polling-based. We considered hooking the SQLAlchemy ``after_insert``
  event but the event bus from the sibling agent isn't guaranteed to be
  ready, so we keep this independent.
* Batched: up to 100 events or 30 seconds of wall time, whichever first.
* Retries: 3 attempts with exponential backoff per destination per
  batch. On 3 consecutive *batch* failures (tracked on the
  ``consecutive_failures`` column) the destination is auto-disabled.
* Idempotent send: each event carries its ``audit_logs.id`` so a
  destination that already processed an id can dedupe.

The streamer can be invoked synchronously (the ``flush_once`` helper, used
by tests and the test-destination button) or via the background loop
(``start`` / ``stop``) which is launched from the FastAPI lifespan.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_field_for_current_tenant
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.security_hardening import AuditStreamDestination
from app.models.user import AuditLog

logger = logging.getLogger(__name__)

# Tunables. Module-level so tests can monkey-patch them.
BATCH_SIZE = 100
BATCH_INTERVAL_SECONDS = 30
MAX_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 0.5  # seconds — 0.5, 1.0, 2.0
DISABLE_AFTER_CONSECUTIVE_FAILURES = 3
HTTP_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Cursor tracking — we remember the last audit-log id pushed per
# destination in the destination row's own ``last_success_at`` /
# in-memory cursor map. Persisting an explicit "last_pushed_id" column
# was avoided to keep the migration small; the in-memory cursor is fine
# because audit logs are append-only and we re-read on restart.
# ---------------------------------------------------------------------------
_cursors: dict[str, str | None] = {}  # destination_id -> last audit_log id sent
_cursor_lock = threading.Lock()


def reset_for_tests() -> None:
    """Clear all module-level state so the next test starts clean.

    The cursor map persists across calls inside a single process — perfect
    in production, lethal in tests. The autouse fixture in conftest.py
    invokes this between every test so an earlier test's leftover state
    can't poison a later one (the splunk-HEC test in particular was
    sensitive to whatever id the previous flush had advanced the cursor to).
    """
    with _cursor_lock:
        _cursors.clear()


def _http_post(url: str, headers: dict, body: bytes) -> tuple[int, str]:
    """Send a POST. Returns (status_code, body_snippet).

    Uses ``requests`` if available (already a dependency for AI/Stripe
    integrations); falls back to urllib if not.
    """
    try:
        import requests  # type: ignore

        resp = requests.post(url, data=body, headers=headers, timeout=HTTP_TIMEOUT)
        return resp.status_code, (resp.text or "")[:500]
    except ImportError:  # pragma: no cover
        import urllib.request

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.status, resp.read(500).decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            return 599, str(exc)[:500]


def _serialize_event(event: AuditLog) -> dict:
    return {
        "id": event.id,
        "tenant_id": event.tenant_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "ip_address": event.ip_address,
        "detail": event.detail,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _build_request(
    dest: AuditStreamDestination,
    events: list[dict],
) -> tuple[bytes, dict[str, str]]:
    """Render the batch as the format the destination type expects."""
    creds = None
    if dest.credentials_encrypted:
        try:
            with tenant_scope(dest.tenant_id):
                creds = decrypt_field_for_current_tenant(dest.credentials_encrypted)
        except Exception:
            logger.exception("Failed to decrypt credentials for destination %s", dest.id)

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if dest.destination_type == "splunk_hec":
        # Splunk HEC: one JSON object per event, concatenated. Each has
        # the "event" wrapper. Auth header is "Splunk <token>".
        if creds:
            headers["Authorization"] = f"Splunk {creds}"
        body_chunks = [json.dumps({"event": e, "sourcetype": "enterprisecore:audit"}) for e in events]
        body = "\n".join(body_chunks).encode("utf-8")
    elif dest.destination_type == "datadog_logs":
        if creds:
            headers["DD-API-KEY"] = creds
        # Datadog Logs HTTP intake: array of records.
        body = json.dumps([
            {
                "ddsource": "enterprisecore",
                "service": "audit",
                "message": json.dumps(e),
                "ddtags": f"tenant:{e['tenant_id']},action:{e['action']}",
            }
            for e in events
        ]).encode("utf-8")
    elif dest.destination_type == "sumo_logic":
        # Sumo: newline-delimited JSON to an HTTP collector. URL itself
        # carries the auth token; no Authorization header.
        body = "\n".join(json.dumps(e) for e in events).encode("utf-8")
    else:  # webhook
        if creds:
            headers["Authorization"] = f"Bearer {creds}"
        body = json.dumps({"events": events}).encode("utf-8")
    return body, headers


def _send_with_retries(
    dest: AuditStreamDestination,
    events: list[dict],
) -> tuple[bool, str | None]:
    body, headers = _build_request(dest, events)
    last_err: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status, snippet = _http_post(dest.url, headers, body)
        if 200 <= status < 300:
            return True, None
        last_err = f"HTTP {status}: {snippet}"
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))
    return False, last_err


def _pending_events_for_tenant(
    db: Session,
    tenant_id: str,
    after_id: str | None,
    limit: int,
) -> list[AuditLog]:
    """Return up to ``limit`` audit events for the tenant whose id is
    strictly greater than ``after_id`` (or every event if no cursor yet).

    ULID-shaped ids are lexically sortable in chronological order, so a
    plain ``id > after_id`` comparison works on both SQLite and Postgres
    without joining back to the cursor row.
    """
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    if after_id is not None:
        stmt = stmt.where(AuditLog.id > after_id)
    stmt = stmt.order_by(AuditLog.created_at.asc(), AuditLog.id.asc()).limit(limit)
    return list(db.scalars(stmt).all())


def flush_destination(dest: AuditStreamDestination, db: Session) -> tuple[bool, str | None, int]:
    """Send any pending events for one destination. Returns
    ``(ok, error_message, sent_count)``.

    Tenant-scoped: pulls only events with matching ``tenant_id``.
    """
    with _cursor_lock:
        cursor = _cursors.get(dest.id)
    with bypass_tenant_filter():
        events = _pending_events_for_tenant(db, dest.tenant_id, cursor, BATCH_SIZE)
    if not events:
        return True, None, 0
    payload = [_serialize_event(e) for e in events]
    ok, err = _send_with_retries(dest, payload)
    now = datetime.now(timezone.utc)
    if ok:
        dest.last_success_at = now
        dest.last_error_message = None
        dest.consecutive_failures = 0
        with _cursor_lock:
            _cursors[dest.id] = events[-1].id
    else:
        dest.last_error_at = now
        dest.last_error_message = err
        dest.consecutive_failures = (dest.consecutive_failures or 0) + 1
        if dest.consecutive_failures >= DISABLE_AFTER_CONSECUTIVE_FAILURES:
            dest.is_active = False
            logger.warning(
                "Auto-disabling audit destination %s after %d consecutive failures",
                dest.id, dest.consecutive_failures,
            )
    db.commit()
    return ok, err, len(events) if ok else 0


def flush_all(db: Session) -> int:
    """Single pass over every active destination across every tenant."""
    with bypass_tenant_filter():
        dests = list(db.scalars(
            select(AuditStreamDestination).where(AuditStreamDestination.is_active.is_(True))
        ).all())
    total = 0
    for dest in dests:
        try:
            _, _, sent = flush_destination(dest, db)
            total += sent
        except Exception:
            logger.exception("Error flushing destination %s", dest.id)
    return total


def test_destination(dest: AuditStreamDestination, db: Session) -> tuple[bool, str | None]:
    """Send a synthetic canary event so an admin can confirm the
    destination is reachable. Does NOT advance the cursor."""
    canary = [{
        "id": "canary",
        "tenant_id": dest.tenant_id,
        "actor_id": None,
        "action": "audit_stream.test",
        "entity_type": "audit_stream",
        "entity_id": dest.id,
        "ip_address": None,
        "detail": {"message": "canary event from EnterpriseCore audit streamer"},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }]
    ok, err = _send_with_retries(dest, canary)
    now = datetime.now(timezone.utc)
    if ok:
        dest.last_success_at = now
        dest.last_error_message = None
    else:
        dest.last_error_at = now
        dest.last_error_message = err
    db.commit()
    return ok, err


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------
_thread: threading.Thread | None = None
_stop = threading.Event()


def _loop() -> None:
    from app.db.session import SessionLocal

    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                flush_all(db)
        except Exception:
            logger.exception("audit_streamer loop iteration failed")
        _stop.wait(BATCH_INTERVAL_SECONDS)


def start() -> None:
    """Start the background flush thread. Idempotent."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="audit-streamer", daemon=True)
    _thread.start()


def stop() -> None:
    """Stop the background loop (best-effort)."""
    _stop.set()
