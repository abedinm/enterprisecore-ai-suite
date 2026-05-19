"""Maintain the SearchIndex table as a denormalised inverted view of the
records people actually search for.

How it works
------------
* Each indexed model declares a small adapter (`SEARCH_ADAPTERS`) that knows how
  to project the row to (module, entity_type, title, body, owner_id).
* SQLAlchemy `after_insert` / `after_update` / `after_delete` event listeners
  invoke the adapter and upsert/delete a matching SearchIndex row.
* `rebuild_index()` re-projects every adapter — useful after a data import or
  schema-changing migration.

The /search endpoint queries SearchIndex first; live-table fallback only runs
when the index is empty (e.g. brand-new install before the first write).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.crm import Contact, Deal, Lead
from app.models.documents import Document
from app.models.finance import Customer, Invoice, Vendor
from app.models.inventory import Product
from app.models.projects import Project, Task
from app.models.user import SearchIndex, User


@dataclass
class _Adapter:
    module: str
    entity_type: str
    title_fn: Callable[[Any], str]
    body_fn: Callable[[Any], str]
    owner_fn: Callable[[Any], str | None] = lambda _: None  # type: ignore[assignment]


SEARCH_ADAPTERS: dict[type, _Adapter] = {
    Invoice: _Adapter(
        module="finance",
        entity_type="invoice",
        title_fn=lambda r: f"Invoice {r.invoice_number}",
        body_fn=lambda r: r.notes or "",
    ),
    Customer: _Adapter(
        module="finance",
        entity_type="customer",
        title_fn=lambda r: r.name,
        body_fn=lambda r: " ".join(filter(None, [r.email, r.phone, r.billing_address])),
    ),
    Vendor: _Adapter(
        module="finance",
        entity_type="vendor",
        title_fn=lambda r: r.name,
        body_fn=lambda r: " ".join(filter(None, [r.email, r.phone, r.payment_terms])),
    ),
    Contact: _Adapter(
        module="crm",
        entity_type="contact",
        title_fn=lambda r: r.name,
        body_fn=lambda r: " ".join(filter(None, [r.company, r.email, r.phone])),
    ),
    Lead: _Adapter(
        module="crm",
        entity_type="lead",
        title_fn=lambda r: f"Lead {r.source or ''}".strip(),
        body_fn=lambda r: r.notes or "",
    ),
    Deal: _Adapter(
        module="crm",
        entity_type="deal",
        title_fn=lambda r: r.title,
        body_fn=lambda r: r.stage or "",
    ),
    Project: _Adapter(
        module="projects",
        entity_type="project",
        title_fn=lambda r: r.name,
        body_fn=lambda r: r.description or "",
    ),
    Task: _Adapter(
        module="projects",
        entity_type="task",
        title_fn=lambda r: r.title,
        body_fn=lambda r: r.description or "",
        owner_fn=lambda r: getattr(r, "assignee_id", None),
    ),
    Document: _Adapter(
        module="documents",
        entity_type="document",
        title_fn=lambda r: r.title,
        body_fn=lambda r: (r.content or "")[:2000],
        owner_fn=lambda r: getattr(r, "owner_id", None),
    ),
    Product: _Adapter(
        module="inventory",
        entity_type="product",
        title_fn=lambda r: r.name,
        body_fn=lambda r: " ".join(filter(None, [r.sku, r.description, r.barcode])),
    ),
    User: _Adapter(
        module="users",
        entity_type="user",
        title_fn=lambda r: r.full_name,
        body_fn=lambda r: " ".join(filter(None, [r.email, r.department or ""])),
    ),
}


def _upsert(db: Session, adapter: _Adapter, row: Any) -> None:
    entity_id = getattr(row, "id", None)
    if not entity_id:
        return
    existing = db.scalar(
        select(SearchIndex).where(
            SearchIndex.module == adapter.module,
            SearchIndex.entity_type == adapter.entity_type,
            SearchIndex.entity_id == entity_id,
        )
    )
    title = adapter.title_fn(row) or ""
    body = adapter.body_fn(row) or ""
    owner = adapter.owner_fn(row)
    if existing:
        existing.title = title
        existing.body = body
        existing.owner_id = owner
    else:
        db.add(
            SearchIndex(
                module=adapter.module,
                entity_type=adapter.entity_type,
                entity_id=entity_id,
                title=title,
                body=body,
                tags="[]",
                owner_id=owner,
            )
        )


def _remove(db: Session, adapter: _Adapter, row: Any) -> None:
    entity_id = getattr(row, "id", None)
    if not entity_id:
        return
    db.execute(
        delete(SearchIndex).where(
            SearchIndex.module == adapter.module,
            SearchIndex.entity_type == adapter.entity_type,
            SearchIndex.entity_id == entity_id,
        )
    )


def _on_insert_or_update(mapper, connection, target):  # noqa: ANN001
    adapter = SEARCH_ADAPTERS.get(type(target))
    if not adapter:
        return
    with Session(bind=connection) as inner:
        _upsert(inner, adapter, target)
        inner.commit()


def _on_delete(mapper, connection, target):  # noqa: ANN001
    adapter = SEARCH_ADAPTERS.get(type(target))
    if not adapter:
        return
    with Session(bind=connection) as inner:
        _remove(inner, adapter, target)
        inner.commit()


_LISTENERS_REGISTERED = False


def register_search_listeners() -> None:
    """Attach SQLAlchemy event listeners exactly once per process."""
    global _LISTENERS_REGISTERED
    if _LISTENERS_REGISTERED:
        return
    for model in SEARCH_ADAPTERS:
        event.listen(model, "after_insert", _on_insert_or_update)
        event.listen(model, "after_update", _on_insert_or_update)
        event.listen(model, "after_delete", _on_delete)
    _LISTENERS_REGISTERED = True


def rebuild_index(db: Session | None = None) -> int:
    """Re-project every indexed model into SearchIndex from scratch.

    Returns the number of rows indexed. Safe to call on a populated install;
    existing rows are updated in place, missing ones are inserted, and stale
    rows whose source row was deleted are pruned at the end.
    """
    owns_session = db is None
    db = db or SessionLocal()
    try:
        seen_ids: set[tuple[str, str, str]] = set()
        count = 0
        for model, adapter in SEARCH_ADAPTERS.items():
            for row in db.scalars(select(model)).all():
                _upsert(db, adapter, row)
                seen_ids.add((adapter.module, adapter.entity_type, row.id))
                count += 1
        # Prune index rows whose source disappeared.
        for stale in db.scalars(select(SearchIndex)).all():
            key = (stale.module, stale.entity_type, stale.entity_id)
            if key not in seen_ids:
                db.delete(stale)
        db.commit()
        return count
    finally:
        if owns_session:
            db.close()
