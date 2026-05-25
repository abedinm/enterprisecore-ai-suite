"""Phase 9 — data-migration import endpoints.

REST surface for the customer-facing "move your data in from HubSpot /
Salesforce / QuickBooks / generic CSV" flow. The job moves through:

    upload → detect-schema → suggest-mapping → PATCH mapping
          → validate → preview → commit → (optional rollback)

Every endpoint is tenant-scoped: the auto-filter restricts list/get to
the current tenant, and the before_insert listener fills tenant_id on the
ImportJob row when we create it. The commit endpoint routes through the
background-job queue (``app.services.jobs.enqueue_or_run``) so a 100K-row
file doesn't block the HTTP worker; the queue falls back to synchronous
in-process execution when ``REDIS_URL`` isn't configured.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.cache import cache_response
from app.core.exceptions import AuthenticationError, NotFoundError, ValidationFailed
from app.db.session import get_db
from app.models.import_jobs import ImportError as ImportErrorModel
from app.models.import_jobs import ImportJob
from app.models.user import User, UserRole
from app.schemas.importers import (
    DetectSchemaOut,
    ImportErrorOut,
    ImportJobCreateOut,
    ImportJobOut,
    ImporterInfo,
    ImporterListOut,
    MappingUpdateIn,
    PreviewOut,
    SuggestMappingOut,
    ValidationIssue,
    ValidationOut,
)
from app.services.audit import record_audit
from app.services.importers import IMPORTERS, get_importer
from app.services.importers import salesforce_rest, quickbooks_online
from app.services.importers.column_mapping import target_fields_for
from app.services.importers.csv_generic import ENTITY_TARGETS

router = APIRouter()


# Upload size cap — task spec says 25 MB. Enforce by chunked copy.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Where uploaded files land. Created lazily so test runs without prior setup work.
STORAGE_ROOT = Path("storage/imports")


def _storage_dir() -> Path:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return STORAGE_ROOT


def _get_job_or_404(db: Session, job_id: str) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if not job:
        raise NotFoundError("Import job not found")
    return job


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
@router.get("", response_model=ImporterListOut)
@router.get("/", response_model=ImporterListOut)
@cache_response(ttl=3600, namespace="importers:list")
def list_importers(response: Response, _: User = Depends(get_current_user)):
    """List available source importers and the entities each one supports."""
    items: list[ImporterInfo] = []
    for source, cls in IMPORTERS.items():
        instance = cls()
        items.append(
            ImporterInfo(
                source=source,
                supported_entities=list(instance.supported_entities),
                description=instance.description,
            )
        )
    return ImporterListOut(importers=items)


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------
@router.post("/jobs", response_model=ImportJobCreateOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    source: str = Form(...),
    target_entity: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Multipart upload that kicks off an import. Saves the file under
    ``storage/imports/<job_id>.csv`` and creates an ``ImportJob`` row."""
    if source not in IMPORTERS:
        raise ValidationFailed(f"Unknown source '{source}'. Available: {list(IMPORTERS)}")
    importer = get_importer(source)
    if target_entity not in importer.supported_entities:
        raise ValidationFailed(
            f"Importer '{source}' does not support entity '{target_entity}'. "
            f"Supported: {importer.supported_entities}"
        )

    job_id = uuid.uuid4().hex
    dest = _storage_dir() / f"{job_id}.csv"

    written = 0
    with dest.open("wb") as fh:
        while True:
            chunk = await file.read(1024 * 64)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                fh.close()
                dest.unlink(missing_ok=True)
                raise ValidationFailed(
                    f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit"
                )
            fh.write(chunk)

    target_module = _module_for_entity(target_entity)
    job = ImportJob(
        id=job_id,
        source=source,
        target_module=target_module,
        target_entity=target_entity,
        status="uploaded",
        source_file_path=str(dest),
        started_by_id=user.id,
        column_mapping={},
        options={},
        config={},
        imported_record_ids=[],
    )
    db.add(job)
    db.flush()
    record_audit(db, actor=user, action="create", entity_type="import_job",
                 entity_id=job.id, detail={"source": source, "target_entity": target_entity})
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# API-mode job creation (no file upload)
# ---------------------------------------------------------------------------
class ApiJobCreateIn(BaseModel):
    """JSON body for creating an import job that pulls via REST API.

    Use this instead of the multipart endpoint when the source supports
    an API mode and the customer has supplied credentials (Salesforce
    REST, QuickBooks Online). ``source_credentials`` is stored on the
    job's ``config`` JSON column and the commit step uses it to mint a
    short-lived access token + page through results.
    """
    source: str = Field(..., description="Importer source key, e.g. 'salesforce' or 'quickbooks'")
    target_entity: str
    source_credentials: dict = Field(default_factory=dict)


_API_MODE_SOURCES = {"salesforce", "salesforce-rest", "quickbooks", "quickbooks-online"}


def _normalise_api_source(source: str) -> str:
    if source in ("salesforce-rest",):
        return "salesforce"
    if source in ("quickbooks-online",):
        return "quickbooks"
    return source


@router.post("/jobs/api", response_model=ImportJobCreateOut, status_code=status.HTTP_201_CREATED)
def create_api_job(
    payload: ApiJobCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create an import job that pulls directly from a SaaS API.

    Required ``source_credentials`` differs per source:

    * **salesforce**: ``{instance_url, access_token?, refresh_token?, sandbox?}``
    * **quickbooks**: ``{realm_id, access_token?, refresh_token?, sandbox?}``

    If ``access_token`` is missing we mint one on commit using the
    refresh_token and the server-configured client_id/client_secret.
    If both tokens are missing the commit step returns 401 with
    ``"Refresh <vendor> credentials"``.
    """
    source = _normalise_api_source(payload.source)
    if payload.source not in _API_MODE_SOURCES and source not in _API_MODE_SOURCES:
        raise ValidationFailed(
            f"Source '{payload.source}' does not support API mode. "
            "Use the multipart /jobs endpoint with a CSV file instead."
        )
    if source not in IMPORTERS:
        raise ValidationFailed(f"Unknown source '{source}'")
    importer = get_importer(source)
    if payload.target_entity not in importer.supported_entities:
        raise ValidationFailed(
            f"Importer '{source}' does not support entity '{payload.target_entity}'. "
            f"Supported: {importer.supported_entities}"
        )

    # Source-specific credential validation
    creds = dict(payload.source_credentials or {})
    if source == "salesforce":
        if not creds.get("instance_url"):
            raise ValidationFailed("Salesforce REST mode requires 'instance_url'")
        if not (creds.get("access_token") or creds.get("refresh_token")):
            raise AuthenticationError("Refresh Salesforce credentials")
    elif source == "quickbooks":
        if not creds.get("realm_id"):
            raise ValidationFailed("QuickBooks Online mode requires 'realm_id'")
        if not (creds.get("access_token") or creds.get("refresh_token")):
            raise AuthenticationError("Refresh QuickBooks credentials")

    job_id = uuid.uuid4().hex
    target_module = _module_for_entity(payload.target_entity)
    job = ImportJob(
        id=job_id,
        source=source,
        target_module=target_module,
        target_entity=payload.target_entity,
        status="uploaded",  # consistent with file-mode initial state
        source_file_path=None,
        started_by_id=user.id,
        column_mapping={},
        options={},
        config=creds,
        imported_record_ids=[],
    )
    db.add(job)
    db.flush()
    record_audit(
        db, actor=user, action="create", entity_type="import_job",
        entity_id=job.id,
        detail={"source": source, "target_entity": payload.target_entity, "mode": "api"},
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[ImportJobOut])
def list_jobs(
    source: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(ImportJob).order_by(ImportJob.created_at.desc())
    if source:
        stmt = stmt.where(ImportJob.source == source)
    if status:
        stmt = stmt.where(ImportJob.status == status)
    return list(db.scalars(stmt.limit(500)))


@router.get("/jobs/{job_id}", response_model=ImportJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get_job_or_404(db, job_id)


def _api_mode_columns(job: ImportJob) -> list[str] | None:
    """If the job is in API mode, return the canonical column names the
    importer produces — without hitting the remote API."""
    if job.source == "salesforce" and salesforce_rest.is_rest_mode_configured(job.config):
        return salesforce_rest.detect_columns(job.target_entity)
    if job.source == "quickbooks" and quickbooks_online.is_api_mode_configured(job.config):
        return quickbooks_online.detect_columns(job.target_entity)
    return None


@router.post("/jobs/{job_id}/detect-schema", response_model=DetectSchemaOut)
def detect_schema(job_id: str, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    job = _get_job_or_404(db, job_id)
    importer = get_importer(job.source)
    api_cols = _api_mode_columns(job)
    if api_cols is not None:
        # No file to sample — return the known column set so the caller
        # can still proceed to suggest-mapping + commit.
        return DetectSchemaOut(
            columns=api_cols,
            sample_rows=[],
            inferred_types={c: "string" for c in api_cols},
        )
    if not job.source_file_path:
        raise ValidationFailed("Job has no uploaded file")
    schema = importer.detect_schema(Path(job.source_file_path))
    return DetectSchemaOut(**schema)


@router.post("/jobs/{job_id}/suggest-mapping", response_model=SuggestMappingOut)
def suggest_mapping(job_id: str, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    job = _get_job_or_404(db, job_id)
    importer = get_importer(job.source)
    api_cols = _api_mode_columns(job)
    if api_cols is not None:
        columns = api_cols
    else:
        if not job.source_file_path:
            raise ValidationFailed("Job has no uploaded file")
        schema = importer.detect_schema(Path(job.source_file_path))
        columns = schema["columns"]
    mapping = importer.suggest_mapping(columns, job.target_entity)
    unmapped = [c for c in columns if c not in mapping]
    return SuggestMappingOut(
        mapping=mapping,
        unmapped_columns=unmapped,
        target_fields=target_fields_for(job.target_entity),
    )


@router.patch("/jobs/{job_id}/mapping", response_model=ImportJobOut)
def update_mapping(
    job_id: str,
    payload: MappingUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _get_job_or_404(db, job_id)
    job.column_mapping = dict(payload.column_mapping)
    if payload.options is not None:
        job.options = dict(payload.options)
    record_audit(db, actor=user, action="update", entity_type="import_job",
                 entity_id=job.id, detail={"mapping_keys": list(payload.column_mapping)})
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/validate", response_model=ValidationOut)
def validate_job(job_id: str, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    job = _get_job_or_404(db, job_id)
    importer = get_importer(job.source)
    previous_status = job.status
    job.status = "validating"
    db.flush()
    try:
        issues_raw = importer.validate(job, db)
    finally:
        job.status = previous_status if previous_status not in ("uploaded",) else "uploaded"
    issues = [ValidationIssue(**i) for i in issues_raw]
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    db.commit()
    return ValidationOut(
        issues=issues,
        error_count=errors,
        warning_count=warnings,
        row_count=job.row_count_total,
    )


@router.post("/jobs/{job_id}/preview", response_model=PreviewOut)
def preview_job(job_id: str, limit: int = 10, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    job = _get_job_or_404(db, job_id)
    importer = get_importer(job.source)
    job.status = "previewing"
    db.flush()
    rows = importer.preview(job, db, limit=limit)
    job.status = "uploaded"
    db.commit()
    return PreviewOut(rows=rows, column_mapping=dict(job.column_mapping or {}))


@router.post("/jobs/{job_id}/commit", response_model=ImportJobOut)
def commit_job(job_id: str, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Run the import.

    When the background-job queue is enabled (``REDIS_URL`` set) the work
    is pushed onto the queue via :func:`enqueue_or_run` so a 100K-row
    file doesn't block the HTTP worker; when running in sync mode we
    take the fast path and run the importer inline against the request
    session so the response carries the committed row counts.
    """

    job = _get_job_or_404(db, job_id)
    if job.status in ("completed", "rolled_back"):
        raise ValidationFailed(f"Job is already {job.status}")
    importer = get_importer(job.source)

    from app.services.jobs import enqueue_or_run, is_async_enabled
    from app.services.jobs_tasks import run_importer_commit

    if is_async_enabled():
        handle = enqueue_or_run(run_importer_commit, job.id, created_by_id=user.id)
        db.refresh(job)
        record_audit(db, actor=user, action="commit", entity_type="import_job",
                     entity_id=job.id, detail={
                         "queued_job_id": handle.job_id, "async": True,
                     })
        db.commit()
        db.refresh(job)
        return job

    # Sync path — run inline against the request session so the test
    # client + small-install dev mode see the committed counts in the
    # response without needing a worker process.
    job.status = "importing"
    db.flush()
    try:
        importer.import_rows(job, db)
    except AuthenticationError:
        job.status = "failed"
        db.commit()
        # Surface auth failures distinctly so the UI can prompt for credential refresh.
        raise HTTPException(status_code=401, detail="Refresh credentials")
    except Exception as exc:
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")
    record_audit(db, actor=user, action="commit", entity_type="import_job",
                 entity_id=job.id, detail={
                     "imported": job.row_count_imported,
                     "skipped": job.row_count_skipped,
                     "failed": job.row_count_failed,
                 })
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/rollback", response_model=ImportJobOut)
def rollback_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    job = _get_job_or_404(db, job_id)
    if not job.can_rollback:
        raise ValidationFailed("This job is not eligible for rollback")
    if job.status == "rolled_back":
        raise ValidationFailed("Job has already been rolled back")
    importer = get_importer(job.source)
    importer.rollback(job, db)
    record_audit(db, actor=user, action="rollback", entity_type="import_job",
                 entity_id=job.id, detail={})
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}/errors", response_model=list[ImportErrorOut])
def list_job_errors(
    job_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_job_or_404(db, job_id)
    stmt = (
        select(ImportErrorModel)
        .where(ImportErrorModel.import_job_id == job_id)
        .order_by(ImportErrorModel.row_number)
        .limit(max(1, min(limit, 500)))
    )
    return list(db.scalars(stmt))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _module_for_entity(entity: str) -> str:
    if entity in ENTITY_TARGETS:
        cls = ENTITY_TARGETS[entity]["model"]
        return cls.__module__.rsplit(".", 1)[-1]
    # Project-management importers (Asana/Notion/Trello/MSP)
    if entity in {"project", "tasks", "board", "cards", "resources", "dependencies", "notes"}:
        if entity == "notes":
            return "documents"
        return "projects"
    return "crm"
