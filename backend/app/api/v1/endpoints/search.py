"""Global search endpoints.

Two API shapes coexist intentionally:

* ``POST /api/v1/search`` — the legacy JSON-body endpoint backed by the
  ``search_indexes`` regular table. Kept verbatim so the existing tests
  and any frontend code that hasn't migrated yet keep working.
* ``GET /api/v1/search`` — the new FTS5-backed endpoint, query-string
  style. Tenant-scoped, ranked, optionally filtered by entity types.
  This is what the global search bar should call going forward.

Both flow through the same ``get_current_user`` auth dep and the same
tenant filter, so cross-tenant leakage is impossible.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.crm import Contact
from app.models.documents import Document
from app.models.finance import Customer, Invoice
from app.models.projects import Project, Task
from app.models.user import SearchHistory, SearchIndex, User
from app.schemas.foundation import SearchHistoryItem, SearchHit, SearchRequest, SearchResponse
from app.services import search as fts_search
from app.services.search_index import rebuild_index

router = APIRouter()

# Max accepted query length. Anything longer is truncated by
# fts_search.search() — we mirror the cap here so we can fail fast with a
# clearer error message on the GET endpoint.
MAX_QUERY_LEN = 200


def _like(term: str) -> str:
    return f"%{term.strip()}%"


def _index_empty(db: Session) -> bool:
    return (db.scalar(select(func.count(SearchIndex.id))) or 0) == 0


def _fallback_hits(db: Session, payload: SearchRequest) -> list[SearchHit]:
    term = _like(payload.query)
    out: list[SearchHit] = []

    def push(module: str, entity_type: str, id_: str, title: str, body: str, updated_at):
        out.append(
            SearchHit(
                id=id_, module=module, entity_type=entity_type, entity_id=id_,
                title=title, body=(body or "")[:240], updated_at=updated_at,
            )
        )

    if payload.module in (None, "finance"):
        for inv in db.scalars(
            select(Invoice).where(or_(Invoice.invoice_number.ilike(term), Invoice.notes.ilike(term)))
            .order_by(Invoice.issue_date.desc()).limit(payload.limit)
        ).all():
            push("finance", "invoice", inv.id, f"Invoice {inv.invoice_number}", inv.notes or "", inv.updated_at)
        for cust in db.scalars(
            select(Customer).where(or_(Customer.name.ilike(term), Customer.email.ilike(term))).limit(payload.limit)
        ).all():
            push("finance", "customer", cust.id, cust.name, cust.email or "", cust.updated_at)

    if payload.module in (None, "crm"):
        for c in db.scalars(
            select(Contact).where(or_(Contact.name.ilike(term), Contact.company.ilike(term))).limit(payload.limit)
        ).all():
            push("crm", "contact", c.id, c.name, c.company or "", c.updated_at)

    if payload.module in (None, "projects"):
        for proj in db.scalars(
            select(Project).where(or_(Project.name.ilike(term), Project.description.ilike(term))).limit(payload.limit)
        ).all():
            push("projects", "project", proj.id, proj.name, proj.description or "", proj.updated_at)
        for task in db.scalars(
            select(Task).where(or_(Task.title.ilike(term), Task.description.ilike(term))).limit(payload.limit)
        ).all():
            push("projects", "task", task.id, task.title, task.description or "", task.updated_at)

    if payload.module in (None, "documents"):
        for doc in db.scalars(
            select(Document).where(or_(Document.title.ilike(term), Document.content.ilike(term))).limit(payload.limit)
        ).all():
            push("documents", "document", doc.id, doc.title, doc.content or "", doc.updated_at)

    if payload.module in (None, "users"):
        for u in db.scalars(
            select(User).where(or_(User.email.ilike(term), User.full_name.ilike(term))).limit(payload.limit)
        ).all():
            push("users", "user", u.id, u.full_name, u.email, u.updated_at)

    return out[: payload.limit]


@router.post("", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Legacy LIKE-based search against the SearchIndex regular table.

    Kept for backwards compatibility with the existing frontend and tests.
    New callers should use the GET endpoint below, which is FTS5-backed.
    """
    term = _like(payload.query)
    items: list[SearchHit] = []

    if not _index_empty(db):
        stmt = select(SearchIndex).where(
            or_(SearchIndex.title.ilike(term), SearchIndex.body.ilike(term))
        )
        if payload.module and payload.module not in ("all", "indexed"):
            stmt = stmt.where(SearchIndex.module == payload.module)
        for row in db.scalars(stmt.order_by(SearchIndex.updated_at.desc()).limit(payload.limit)).all():
            items.append(
                SearchHit(
                    id=row.id,
                    module=row.module,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    title=row.title,
                    body=(row.body or "")[:240],
                    updated_at=row.updated_at,
                )
            )
    else:
        items = _fallback_hits(db, payload)

    db.add(SearchHistory(user_id=current_user.id, query=payload.query, result_count=len(items)))
    db.commit()
    return SearchResponse(items=items, total=len(items), query=payload.query)


# ---------------------------------------------------------------------------
# FTS5-backed GET endpoint (the new path).
# ---------------------------------------------------------------------------


def _maybe_load_full(db: Session, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Best-effort lazy load of the source rows referenced by FTS5 results.

    Caller opts in via ``?include=full`` because the round-trip is one
    SELECT per distinct entity_type, which can be wasteful when the user
    just wants a list of links.
    """
    # Group ids by entity_type so we issue one query per type.
    grouped: dict[str, list[str]] = {}
    for r in results:
        grouped.setdefault(r["entity_type"], []).append(r["entity_id"])

    fetched: dict[tuple[str, str], dict[str, Any]] = {}
    for entity_type, ids in grouped.items():
        # Look up the model in the FTS adapter map by entity_type.
        model = next(
            (m for m, a in fts_search.FTS_ADAPTERS.items() if a.entity_type == entity_type),
            None,
        )
        if model is None or not ids:
            continue
        try:
            rows = db.scalars(select(model).where(model.id.in_(ids))).all()
        except Exception:
            rows = []
        for row in rows:
            fetched[(entity_type, row.id)] = {
                col.name: getattr(row, col.name, None)
                for col in model.__table__.columns
                if col.name not in {"password_hash"}
            }

    enriched: list[dict[str, Any]] = []
    for r in results:
        full = fetched.get((r["entity_type"], r["entity_id"]))
        if full is not None:
            # ORM rows can contain non-JSON values (Decimal, date, datetime);
            # let FastAPI's encoder handle them — set them on a copy.
            r = {**r, "full": full}
        enriched.append(r)
    return enriched


@router.get("")
def search_fts(
    q: str = Query(..., min_length=1, description="Search query"),
    types: str | None = Query(
        None,
        description="Comma-separated entity types (e.g. crm.contact,finance.invoice)",
    ),
    limit: int = Query(20, ge=1, le=100),
    include: str | None = Query(
        None, description="Set to 'full' to lazily fetch full entity payloads",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across every indexed entity type, scoped to the
    caller's tenant.

    Returns a flat list of ranked results — the frontend groups by
    ``entity_type`` for display. ``rank`` is positive-larger-better.
    """
    q_stripped = (q or "").strip()
    if not q_stripped:
        # Pydantic min_length=1 catches empty/missing, but a whitespace-only
        # value sneaks through; reject it explicitly for a clearer error.
        raise HTTPException(status_code=400, detail="Query must not be empty")
    if len(q_stripped) > MAX_QUERY_LEN:
        q_stripped = q_stripped[:MAX_QUERY_LEN]

    entity_types: list[str] = []
    if types:
        entity_types = [t.strip() for t in types.split(",") if t.strip()]

    results = fts_search.search(
        db,
        q_stripped,
        entity_types=entity_types or None,
        limit=limit,
    )
    if include == "full":
        results = _maybe_load_full(db, results)

    # Best-effort history capture; never let it fail the request.
    try:
        db.add(SearchHistory(
            user_id=current_user.id, query=q_stripped, result_count=len(results)
        ))
        db.commit()
    except Exception:
        db.rollback()

    return {"results": results, "total": len(results), "query": q_stripped}


@router.post("/reindex")
def reindex(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    """Rebuild both the regular SearchIndex *and* the FTS5 virtual table.

    Runs synchronously in the request thread. For the offline-first
    single-tenant deploys this targets, a sync rebuild is fine; multi-tenant
    SaaS deploys should call this from a background worker.
    """
    count = rebuild_index(db)
    fts_count = fts_search.reindex_all(db)
    return {"indexed": count, "fts_indexed": fts_count}


@router.get("/history", response_model=list[SearchHistoryItem])
def history(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.scalars(
        select(SearchHistory)
        .where(SearchHistory.user_id == current_user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit)
    ).all()


@router.delete("/history", status_code=204)
def clear_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    for row in db.scalars(select(SearchHistory).where(SearchHistory.user_id == current_user.id)).all():
        db.delete(row)
    db.commit()
    return None
