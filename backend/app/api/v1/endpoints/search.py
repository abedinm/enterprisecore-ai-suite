"""Global search — searches index plus live tables (users, invoices, customers, tasks, projects, documents)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.crm import Contact
from app.models.documents import Document
from app.models.finance import Customer, Invoice
from app.models.projects import Project, Task
from app.models.user import SearchHistory, SearchIndex, User
from app.schemas.foundation import SearchHistoryItem, SearchHit, SearchRequest, SearchResponse

router = APIRouter()


def _like(term: str) -> str:
    return f"%{term.strip()}%"


@router.post("", response_model=SearchResponse)
def search(payload: SearchRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    term = _like(payload.query)
    items: list[SearchHit] = []

    if payload.module in (None, "indexed"):
        stmt = select(SearchIndex).where(or_(SearchIndex.title.ilike(term), SearchIndex.body.ilike(term)))
        if payload.module and payload.module != "indexed":
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

    if payload.module in (None, "finance"):
        for inv in db.scalars(
            select(Invoice)
            .where(or_(Invoice.invoice_number.ilike(term), Invoice.notes.ilike(term)))
            .order_by(Invoice.issue_date.desc())
            .limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=inv.id,
                    module="finance",
                    entity_type="invoice",
                    entity_id=inv.id,
                    title=f"Invoice {inv.invoice_number}",
                    body=(inv.notes or "")[:240],
                    updated_at=inv.updated_at,
                )
            )
        for cust in db.scalars(
            select(Customer).where(or_(Customer.name.ilike(term), Customer.email.ilike(term))).limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=cust.id,
                    module="finance",
                    entity_type="customer",
                    entity_id=cust.id,
                    title=cust.name,
                    body=cust.email or "",
                    updated_at=cust.updated_at,
                )
            )

    if payload.module in (None, "crm"):
        for c in db.scalars(
            select(Contact).where(or_(Contact.name.ilike(term), Contact.company.ilike(term))).limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=c.id,
                    module="crm",
                    entity_type="contact",
                    entity_id=c.id,
                    title=c.name,
                    body=c.company or "",
                    updated_at=c.updated_at,
                )
            )

    if payload.module in (None, "projects"):
        for proj in db.scalars(
            select(Project).where(or_(Project.name.ilike(term), Project.description.ilike(term))).limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=proj.id,
                    module="projects",
                    entity_type="project",
                    entity_id=proj.id,
                    title=proj.name,
                    body=(proj.description or "")[:240],
                    updated_at=proj.updated_at,
                )
            )
        for task in db.scalars(
            select(Task).where(or_(Task.title.ilike(term), Task.description.ilike(term))).limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=task.id,
                    module="projects",
                    entity_type="task",
                    entity_id=task.id,
                    title=task.title,
                    body=(task.description or "")[:240],
                    updated_at=task.updated_at,
                )
            )

    if payload.module in (None, "documents"):
        for doc in db.scalars(
            select(Document).where(or_(Document.title.ilike(term), Document.content.ilike(term))).limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=doc.id,
                    module="documents",
                    entity_type="document",
                    entity_id=doc.id,
                    title=doc.title,
                    body=(doc.content or "")[:240],
                    updated_at=doc.updated_at,
                )
            )

    if payload.module in (None, "users"):
        for u in db.scalars(
            select(User).where(or_(User.email.ilike(term), User.full_name.ilike(term))).limit(payload.limit)
        ).all():
            items.append(
                SearchHit(
                    id=u.id,
                    module="users",
                    entity_type="user",
                    entity_id=u.id,
                    title=u.full_name,
                    body=u.email,
                    updated_at=u.updated_at,
                )
            )

    items = items[: payload.limit]

    db.add(SearchHistory(user_id=current_user.id, query=payload.query, result_count=len(items)))
    db.commit()

    return SearchResponse(items=items, total=len(items), query=payload.query)


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
