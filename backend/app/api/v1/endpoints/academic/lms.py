"""LMS library — anyone signed in may browse; teacher/admin may write.

Workflow features layered on top of the CRUD scaffold:
- ``GET /lms/resources/search`` — fuzzy match across title/description with
  optional column filters; used by the "search box" on the library UI.
- ``POST /lms/resources/{id}/download`` — increments ``download_count`` and
  returns the file_path/url so the client can stream or redirect.
- ``GET /lms/resources/popular`` — top-N by download_count, for the
  "popular this week" widget.

The download counter is intentionally trust-the-client: we don't proxy the
file ourselves, so the increment fires when the UI requests the endpoint
rather than when the file actually downloads. Good enough for ranking.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.endpoints.academic._common import (
    TEACHER_OR_ADMIN, _apply_update, _get_or_404, require_any_role,
)
from app.db.session import get_db
from app.models.academic.lms import AcademicLmsResource
from app.models.user import User
from app.schemas.academic.lms import (
    LmsDownloadOut, LmsResourceCreate, LmsResourceOut, LmsResourceUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Read paths — search + popular sit BEFORE the {resource_id} routes so
# FastAPI doesn't treat "search" as an id.
# ---------------------------------------------------------------------------
@router.get("/resources/search", response_model=list[LmsResourceOut])
def search_resources(
    q: str | None = None,
    department: str | None = None,
    course_code: str | None = None,
    type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Library-wide search across title + description with column filters.

    SQLite has no full-text by default so we use case-insensitive ``LIKE`` —
    fine for the per-tenant resource counts we expect here (hundreds to low
    thousands). When a tenant outgrows that, swap this for ``MATCH`` against
    a FTS5 mirror table without changing the URL.
    """
    stmt = select(AcademicLmsResource).order_by(
        AcademicLmsResource.created_at.desc()
    )
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                AcademicLmsResource.title.ilike(pat),
                AcademicLmsResource.description.ilike(pat),
            )
        )
    if department:
        stmt = stmt.where(AcademicLmsResource.department == department)
    if course_code:
        stmt = stmt.where(AcademicLmsResource.course_code == course_code)
    if type:
        # Param is named ``type`` to match the public spec; map to the column.
        stmt = stmt.where(AcademicLmsResource.resource_type == type)
    return db.scalars(stmt.limit(max(1, min(limit, 200)))).all()


@router.get("/resources/popular", response_model=list[LmsResourceOut])
def popular_resources(
    limit: int = 10,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Top-N resources ordered by download_count descending."""
    return db.scalars(
        select(AcademicLmsResource)
        .order_by(
            AcademicLmsResource.download_count.desc(),
            AcademicLmsResource.created_at.desc(),
        )
        .limit(max(1, min(limit, 50)))
    ).all()


@router.get("/resources", response_model=list[LmsResourceOut])
def list_resources(
    course_code: str | None = None,
    resource_type: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(AcademicLmsResource).order_by(
        AcademicLmsResource.created_at.desc()
    )
    if course_code:
        stmt = stmt.where(AcademicLmsResource.course_code == course_code)
    if resource_type:
        stmt = stmt.where(AcademicLmsResource.resource_type == resource_type)
    return db.scalars(stmt).all()


@router.post(
    "/resources",
    response_model=LmsResourceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_resource(
    payload: LmsResourceCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_any_role(*TEACHER_OR_ADMIN)),
):
    obj = AcademicLmsResource(uploaded_by_id=current.id, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/resources/{resource_id}", response_model=LmsResourceOut)
def get_resource(resource_id: str, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    return _get_or_404(db, AcademicLmsResource, resource_id, "Resource")


@router.post(
    "/resources/{resource_id}/download",
    response_model=LmsDownloadOut,
)
def download_resource(
    resource_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Record a download and return where the file lives.

    We don't redirect with a 302 here — most academic apps want to wrap the
    URL in their own analytics/security layer, so we hand the caller the raw
    location and let them decide.
    """
    obj = _get_or_404(db, AcademicLmsResource, resource_id, "Resource")
    obj.download_count = (obj.download_count or 0) + 1
    db.commit()
    db.refresh(obj)
    return LmsDownloadOut(
        resource_id=obj.id,
        file_path=obj.file_path,
        url=obj.url,
        download_count=obj.download_count,
    )


@router.patch(
    "/resources/{resource_id}",
    response_model=LmsResourceOut,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def update_resource(
    resource_id: str, payload: LmsResourceUpdate, db: Session = Depends(get_db),
):
    obj = _get_or_404(db, AcademicLmsResource, resource_id, "Resource")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete(
    "/resources/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_any_role(*TEACHER_OR_ADMIN))],
)
def delete_resource(resource_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, AcademicLmsResource, resource_id, "Resource")
    db.delete(obj)
    db.commit()
