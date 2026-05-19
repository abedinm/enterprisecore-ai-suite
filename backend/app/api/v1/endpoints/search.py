"""Global search.

The SearchIndex table is the canonical store and is kept in sync via SQLAlchemy
event listeners (see `app.services.search_index`). If the index is empty for a
given module (e.g. fresh install, or the module hasn't started writing yet)
this endpoint falls back to scanning the live tables so users still get hits.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
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
from app.services.search_index import rebuild_index

router = APIRouter()


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


@router.post("/reindex")
def reindex(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict:
    """Re-project every indexed model into SearchIndex from scratch.

    Returns count and rebuilds in the request thread; for large datasets this
    should be moved to a background job — but for the offline-first single-user
    deployment this targets, a synchronous rebuild is fine.
    """
    count = rebuild_index(db)
    return {"indexed": count}


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
