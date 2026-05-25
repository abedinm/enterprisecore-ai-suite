"""Top-level callables for the background job queue.

These are the dotted-path targets that endpoint code passes into
:func:`app.services.jobs.enqueue_or_run`. They share two properties that
let them be safely shipped over RQ:

1. **No live DB session is passed in.** Each task opens its own short-
   lived ``SessionLocal()`` so the worker side doesn't need to receive a
   non-pickleable object.

2. **Idempotent on the input.** Every task takes a row id (or other
   stable id) and re-resolves it inside the function, so a retry after
   a transient Redis blip lands on fresh state.

The functions here are deliberately thin — they wrap existing service
calls and exist purely as the asynchronous-friendly entry point. Tests
that exercise the sync path can keep calling the original service
directly; tests that exercise the queue path go through these.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Knowledge ingest
# ---------------------------------------------------------------------------

def process_knowledge_document(doc_id: str) -> dict:
    """Chunk + embed a knowledge document. Heavy: PDF parse + Ollama call.

    Looked up by id so retries don't need to round-trip the original row.
    """

    from app.services.knowledge import process_document

    with SessionLocal() as db, bypass_tenant_filter():
        ok = process_document(db, doc_id)
        return {"document_id": doc_id, "ok": bool(ok)}


# ---------------------------------------------------------------------------
# Importers — large CSV / external SaaS row commits
# ---------------------------------------------------------------------------

def run_importer_commit(import_job_id: str) -> dict:
    """Commit-phase of an ImportJob. ``import_rows()`` may take minutes."""

    from app.models.import_jobs import ImportJob
    from app.services.importers import get_importer

    with SessionLocal() as db:
        # Look up the job under bypass since the runner may be invoked with no
        # tenant context — but exit bypass before doing the actual import so
        # the before_insert auto-set listener can fill tenant_id on rows the
        # importer creates.
        with bypass_tenant_filter():
            job = db.get(ImportJob, import_job_id)
        if not job:
            return {"import_job_id": import_job_id, "ok": False, "error": "not found"}
        with tenant_scope(job.tenant_id):
            importer = get_importer(job.source)
            try:
                job.status = "importing"
                db.commit()
                importer.import_rows(job, db)
                db.commit()
                db.refresh(job)
                return {
                    "import_job_id": import_job_id,
                    "ok": True,
                    "imported": job.row_count_imported,
                    "failed": job.row_count_failed,
                }
            except Exception as exc:
                logger.exception("importer commit failed for %s", import_job_id)
                job.status = "failed"
                db.commit()
                raise


# ---------------------------------------------------------------------------
# Webhook dispatch — already had its own retry; route through queue now
# ---------------------------------------------------------------------------

def dispatch_webhook_event(event_payload: dict) -> dict:
    """Re-dispatch an Event from its serialised form.

    Callers pass the event as a plain dict (so it survives RQ pickling)
    and we rebuild the NamedTuple on the worker side.
    """

    from datetime import datetime

    from app.services.event_bus import Event
    from app.services.webhook_dispatcher import dispatch_for_event

    occurred = event_payload.get("occurred_at")
    if isinstance(occurred, str):
        try:
            occurred = datetime.fromisoformat(occurred)
        except Exception:
            from datetime import timezone

            occurred = datetime.now(timezone.utc)
    event = Event(
        id=event_payload["id"],
        type=event_payload["type"],
        tenant_id=event_payload.get("tenant_id"),
        user_id=event_payload.get("user_id"),
        occurred_at=occurred,
        payload=event_payload.get("payload", {}),
    )
    if event.tenant_id:
        with tenant_scope(event.tenant_id):
            ids = dispatch_for_event(event)
    else:
        ids = dispatch_for_event(event)
    return {"event_id": event.id, "delivery_ids": ids}


# ---------------------------------------------------------------------------
# Audit log streaming — batch dispatch to external SIEMs
# ---------------------------------------------------------------------------

def flush_audit_streams() -> dict:
    """Drain pending audit events to every configured destination."""

    from app.services.audit_streamer import flush_all

    with SessionLocal() as db, bypass_tenant_filter():
        sent = flush_all(db)
        return {"sent": sent}


# ---------------------------------------------------------------------------
# GDPR export — was synchronous, now queueable
# ---------------------------------------------------------------------------

def run_gdpr_export(export_job_id: str, storage_dir: str) -> dict:
    """Materialise a user-data export bundle to disk."""

    from app.models.webhooks import GdprExportJob
    from app.services.gdpr import run_export_job

    with SessionLocal() as db, bypass_tenant_filter():
        job = db.get(GdprExportJob, export_job_id)
        if not job:
            return {"export_job_id": export_job_id, "ok": False, "error": "not found"}
        with tenant_scope(job.tenant_id):
            run_export_job(db, job, Path(storage_dir))
        db.refresh(job)
        return {
            "export_job_id": export_job_id,
            "status": job.status,
            "record_count": job.record_count,
        }


# ---------------------------------------------------------------------------
# Workflow engine — execute one workflow action against one event
# ---------------------------------------------------------------------------

def execute_workflow_for_event(workflow_id: str, event_payload: dict) -> dict:
    """Run a single workflow against a serialised event."""

    from datetime import datetime, timezone

    from app.models.workflows import Workflow
    from app.services.event_bus import Event
    from app.services.workflow_engine import execute_workflow

    occurred = event_payload.get("occurred_at")
    if isinstance(occurred, str):
        try:
            occurred = datetime.fromisoformat(occurred)
        except Exception:
            occurred = datetime.now(timezone.utc)
    event = Event(
        id=event_payload["id"],
        type=event_payload["type"],
        tenant_id=event_payload.get("tenant_id"),
        user_id=event_payload.get("user_id"),
        occurred_at=occurred,
        payload=event_payload.get("payload", {}),
    )
    with SessionLocal() as db, bypass_tenant_filter():
        wf = db.get(Workflow, workflow_id)
        if not wf:
            return {"workflow_id": workflow_id, "ok": False, "error": "not found"}
        with tenant_scope(wf.tenant_id):
            run = execute_workflow(wf, event, db)
            return {"workflow_id": workflow_id, "run_id": run.id, "status": run.status}


# ---------------------------------------------------------------------------
# AI call wrapper — the only async heavy lifting that lives outside a job
# is the AI provider call. Endpoints can opt into queue mode by enqueuing
# this wrapper; nothing breaks if they don't.
# ---------------------------------------------------------------------------

def run_ai_completion(provider: str, model: str, prompt: str, **kwargs) -> dict:
    """Provider-agnostic AI completion entry point.

    Currently a thin wrapper around the existing AI service so that an
    endpoint can offload "this completion will take 90s" to the queue and
    return a job id to the client immediately.
    """

    try:
        from app.services.ai import generate_completion  # type: ignore[attr-defined]

        text = generate_completion(provider=provider, model=model, prompt=prompt, **kwargs)
    except Exception:
        # Fallback for installs where the AI service uses a different
        # entry name — we just record the failure so the job row carries
        # the real error instead of an ImportError.
        raise
    return {"provider": provider, "model": model, "text": text[:5000]}
