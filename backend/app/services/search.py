"""Cross-module full-text search powered by SQLite FTS5.

Layout
------
* ``search_index_fts`` is a SQLite FTS5 virtual table created by migration
  0021 (and by the DDL hook in ``app/models/search_index.py`` for test
  runs that bypass alembic). It mirrors a denormalised snapshot of every
  searchable record across the suite.
* The :class:`FTS_ADAPTERS` map declares the 15 indexed entity types and
  how to project a source row into FTS5 columns ``(entity_type,
  entity_id, tenant_id, title, subtitle, body)``.
* :func:`index_entity` / :func:`unindex_entity` are the write helpers.
  They use ``DELETE WHERE entity_id = ?`` + ``INSERT`` (an idempotent
  upsert) rather than FTS5's ``rowid``-based UPDATE because our entity ids
  are opaque ULIDs, not row numbers.
* :func:`search` runs a ``MATCH`` query, scoped to the current tenant,
  optionally filtered by entity types, ordered by ``bm25(...)`` (lower is
  better). Returns the rank as a positive score so the API JSON reads
  intuitively.
* :func:`reindex_all` truncates + rebuilds every indexed row from the
  source tables, in one transaction. Used by the
  ``POST /api/v1/search/reindex`` admin endpoint and by tests that want a
  clean slate.

Multi-tenancy
-------------
``tenant_id`` is stored as a column on every FTS5 row and is always
filtered in the WHERE clause of :func:`search`. The auto-set listeners
read ``tenant_id_ctx`` at write time so cross-tenant writes are
impossible from inside a request.

Why not just attach a `tenant_id` MATCH clause? Because tenant_id is an
opaque ULID, not a stem-friendly natural-language token — UNINDEXED +
equality filter is both correct and faster than dragging the value
through the tokenizer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_tenant_id
from app.db.session import SessionLocal
from app.models.communication import Announcement, WikiPage
from app.models.construction import ConstructionProject, ConstructionRisk
from app.models.crm import Contact, Deal, Lead
from app.models.documents import Document
from app.models.finance import Customer, Expense, Invoice, Vendor
from app.models.hr import Candidate, Employee, JobOpening
from app.models.inventory import Product
from app.models.knowledge import KnowledgeDocument
from app.models.marketing import MarketingPost, MarketingProject, MarketingTeamMember
from app.models.projects import Project, Task
from app.models.webchat import Bot

logger = logging.getLogger(__name__)

# Query length cap. Anything longer is almost certainly a bug or an attack,
# and FTS5's parser refuses tokens past a reasonable length anyway.
MAX_QUERY_LENGTH = 200


@dataclass(frozen=True)
class _FtsAdapter:
    """How to project a single source row into FTS5 columns.

    ``entity_type`` doubles as the API filter key and the human-readable
    label ("crm.contact", "finance.invoice").
    """

    entity_type: str
    title_fn: Callable[[Any], str]
    subtitle_fn: Callable[[Any], str] = lambda _: ""  # type: ignore[assignment]
    body_fn: Callable[[Any], str] = lambda _: ""  # type: ignore[assignment]


def _join(*parts: Any) -> str:
    return " ".join(filter(None, (str(p).strip() for p in parts if p is not None)))


# 15 indexed entity types. Picked for coverage of name/title/body fields
# across the most-used modules of the suite. Adding new types is a one-line
# adapter + a re-index.
FTS_ADAPTERS: dict[type, _FtsAdapter] = {
    # CRM
    Contact: _FtsAdapter(
        entity_type="crm.contact",
        title_fn=lambda r: r.name,
        subtitle_fn=lambda r: r.company or "",
        body_fn=lambda r: _join(r.email, r.phone),
    ),
    Lead: _FtsAdapter(
        entity_type="crm.lead",
        title_fn=lambda r: f"Lead {r.source or ''}".strip() or "Lead",
        subtitle_fn=lambda r: r.status or "",
        body_fn=lambda r: r.notes or "",
    ),
    Deal: _FtsAdapter(
        entity_type="crm.deal",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.stage or "",
    ),
    # HR
    Employee: _FtsAdapter(
        entity_type="hr.employee",
        title_fn=lambda r: r.full_name,
        subtitle_fn=lambda r: r.title or r.department or "",
        body_fn=lambda r: _join(r.email, r.employee_code, r.department),
    ),
    Candidate: _FtsAdapter(
        entity_type="hr.candidate",
        title_fn=lambda r: r.full_name,
        subtitle_fn=lambda r: r.stage or "",
        body_fn=lambda r: r.email or "",
    ),
    JobOpening: _FtsAdapter(
        entity_type="hr.job_opening",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.department or "",
        body_fn=lambda r: r.description or "",
    ),
    # Finance
    Customer: _FtsAdapter(
        entity_type="finance.customer",
        title_fn=lambda r: r.name,
        body_fn=lambda r: _join(r.email, r.phone, getattr(r, "billing_address", None)),
    ),
    Vendor: _FtsAdapter(
        entity_type="finance.vendor",
        title_fn=lambda r: r.name,
        body_fn=lambda r: _join(r.email, r.phone, getattr(r, "payment_terms", None)),
    ),
    Invoice: _FtsAdapter(
        entity_type="finance.invoice",
        title_fn=lambda r: f"Invoice {r.invoice_number}",
        subtitle_fn=lambda r: getattr(r, "status", "") or "",
        body_fn=lambda r: r.notes or "",
    ),
    Expense: _FtsAdapter(
        entity_type="finance.expense",
        title_fn=lambda r: getattr(r, "description", "") or "Expense",
        subtitle_fn=lambda r: getattr(r, "vendor", "") or "",
        body_fn=lambda r: getattr(r, "notes", "") or "",
    ),
    # Projects
    Project: _FtsAdapter(
        entity_type="projects.project",
        title_fn=lambda r: r.name,
        subtitle_fn=lambda r: r.status or "",
        body_fn=lambda r: r.description or "",
    ),
    Task: _FtsAdapter(
        entity_type="projects.task",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.status or "",
        body_fn=lambda r: r.description or "",
    ),
    # Inventory
    Product: _FtsAdapter(
        entity_type="inventory.product",
        title_fn=lambda r: r.name,
        subtitle_fn=lambda r: r.sku or "",
        body_fn=lambda r: _join(r.description, getattr(r, "barcode", None)),
    ),
    # Documents
    Document: _FtsAdapter(
        entity_type="documents.document",
        title_fn=lambda r: r.title,
        body_fn=lambda r: (r.content or "")[:4000],
    ),
    # Communication
    Announcement: _FtsAdapter(
        entity_type="communication.announcement",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.audience or "",
        body_fn=lambda r: r.body or "",
    ),
    WikiPage: _FtsAdapter(
        entity_type="communication.wiki_page",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.slug or "",
        body_fn=lambda r: r.body or "",
    ),
    # Knowledge Hub
    KnowledgeDocument: _FtsAdapter(
        entity_type="knowledge.document",
        title_fn=lambda r: r.name,
        subtitle_fn=lambda r: r.status or "",
    ),
    # Web Chat
    Bot: _FtsAdapter(
        entity_type="webchat.bot",
        title_fn=lambda r: r.name,
        subtitle_fn=lambda r: getattr(r, "status", "") or "",
        body_fn=lambda r: getattr(r, "description", "") or "",
    ),
    # Marketing
    MarketingPost: _FtsAdapter(
        entity_type="marketing.post",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.author or r.category or "",
        body_fn=lambda r: (r.body or r.excerpt or "")[:4000],
    ),
    MarketingProject: _FtsAdapter(
        entity_type="marketing.project",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: r.client or r.category or "",
        body_fn=lambda r: (r.body or r.summary or "")[:4000],
    ),
    MarketingTeamMember: _FtsAdapter(
        entity_type="marketing.team_member",
        title_fn=lambda r: getattr(r, "name", "") or "",
        subtitle_fn=lambda r: getattr(r, "role", "") or "",
        body_fn=lambda r: getattr(r, "bio", "") or "",
    ),
    # Construction
    ConstructionProject: _FtsAdapter(
        entity_type="construction.project",
        title_fn=lambda r: r.name,
        subtitle_fn=lambda r: r.client_name or r.location or "",
        body_fn=lambda r: r.description or "",
    ),
    ConstructionRisk: _FtsAdapter(
        entity_type="construction.risk",
        title_fn=lambda r: r.title,
        subtitle_fn=lambda r: f"{r.category} (score {r.score})",
        body_fn=lambda r: _join(r.description, r.mitigation_plan),
    ),
}


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------

def _is_sqlite(connection) -> bool:  # noqa: ANN001
    return connection.dialect.name == "sqlite"


def _delete_row(connection, entity_type: str, entity_id: str) -> None:  # noqa: ANN001
    connection.exec_driver_sql(
        "DELETE FROM search_index_fts WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    )


def _insert_row(  # noqa: ANN001
    connection,
    *,
    entity_type: str,
    entity_id: str,
    tenant_id: str,
    title: str,
    subtitle: str,
    body: str,
) -> None:
    connection.exec_driver_sql(
        "INSERT INTO search_index_fts (entity_type, entity_id, tenant_id, title, subtitle, body) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (entity_type, entity_id, tenant_id, title or "", subtitle or "", body or ""),
    )


def index_entity(
    connection,  # noqa: ANN001 — SQLAlchemy Connection or scoped Session.connection()
    *,
    entity_type: str,
    entity_id: str,
    tenant_id: str,
    title: str,
    subtitle: str = "",
    body: str = "",
) -> None:
    """Upsert a row into the FTS5 index. Idempotent."""
    if not _is_sqlite(connection):
        return
    if not entity_id or not tenant_id:
        return
    _delete_row(connection, entity_type, entity_id)
    _insert_row(
        connection,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        title=title,
        subtitle=subtitle,
        body=body,
    )


def unindex_entity(connection, *, entity_type: str, entity_id: str) -> None:  # noqa: ANN001
    """Remove a row from the FTS5 index. No-op if it isn't there."""
    if not _is_sqlite(connection):
        return
    if not entity_id:
        return
    _delete_row(connection, entity_type, entity_id)


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------

def _escape_fts5_query(q: str) -> str:
    """Make a user-supplied string safe to pass to FTS5 MATCH.

    FTS5 accepts an expression language (AND/OR/NOT/NEAR/-prefix/etc.). We
    don't want to expose that surface area to end users — a stray colon or
    parenthesis is a syntax error that crashes the query. Quoting each
    token individually is the documented escape: ``"foo" "bar"`` becomes an
    implicit AND of the two literals.

    Empty tokens (after stripping non-alphanumeric characters) are dropped.
    If everything gets stripped out we fall back to a single literal that
    matches nothing — better than raising a 500.
    """
    cleaned = []
    for raw in q.split():
        # Strip the quote character itself so we can wrap each token in ".."
        token = raw.replace('"', "").strip()
        if not token:
            continue
        # Allow a trailing * for prefix search ("foo*"), strip from token first
        prefix = ""
        if token.endswith("*"):
            prefix = "*"
            token = token[:-1]
        if not token:
            continue
        cleaned.append(f'"{token}"{prefix}')
    return " ".join(cleaned) if cleaned else '"__no_match__"'


def search(
    db: Session,
    query: str,
    *,
    tenant_id: str | None = None,
    entity_types: Iterable[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Run a tenant-scoped FTS5 MATCH.

    Returns rows ordered by bm25() ascending (best first), surfaced as a
    positive ``rank`` value so larger == better in the API response.
    """
    query = (query or "").strip()
    if not query:
        return []
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]

    tenant_id = tenant_id or get_current_tenant_id()
    if not tenant_id:
        return []

    types_list = [t for t in (entity_types or []) if t]
    match_expr = _escape_fts5_query(query)

    sql = (
        "SELECT entity_type, entity_id, tenant_id, title, subtitle, body, "
        "       bm25(search_index_fts) AS rank "
        "FROM search_index_fts "
        "WHERE search_index_fts MATCH :match "
        "  AND tenant_id = :tenant_id "
    )
    params: dict[str, Any] = {"match": match_expr, "tenant_id": tenant_id, "limit": int(limit)}
    if types_list:
        placeholders = ", ".join(f":t{i}" for i in range(len(types_list)))
        sql += f"  AND entity_type IN ({placeholders}) "
        for i, t in enumerate(types_list):
            params[f"t{i}"] = t
    sql += "ORDER BY rank LIMIT :limit"

    try:
        rows = db.execute(text(sql), params).mappings().all()
    except Exception as exc:  # FTS5 query syntax errors → empty result.
        logger.warning("FTS5 query failed for %r: %s", query, exc)
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        body = row.get("body") or ""
        excerpt = body[:240]
        # bm25 is lower-is-better; invert sign so the API gives "larger is
        # more relevant" without confusing callers.
        results.append(
            {
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "title": row.get("title") or "",
                "subtitle": row.get("subtitle") or "",
                "body_excerpt": excerpt,
                "rank": -float(row["rank"]) if row.get("rank") is not None else 0.0,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Rebuild
# ---------------------------------------------------------------------------

def reindex_all(db: Session) -> int:
    """Truncate the FTS5 index and re-project every adapter from scratch.

    Returns the number of rows inserted. Cheap on small installs — every
    indexed row is rewritten — but worth running as a background job for
    large datasets in a future phase.

    The truncation honours the current tenant scope: only this tenant's
    rows are wiped and re-built. Cross-tenant rebuilds require an
    explicit bypass at the call site.
    """
    connection = db.connection()
    if not _is_sqlite(connection):
        return 0

    tenant_id = get_current_tenant_id()
    # Clear existing rows for this tenant only — keeps cross-tenant data
    # intact when a single tenant clicks Re-index.
    if tenant_id:
        connection.exec_driver_sql(
            "DELETE FROM search_index_fts WHERE tenant_id = ?", (tenant_id,)
        )
    else:
        connection.exec_driver_sql("DELETE FROM search_index_fts")

    inserted = 0
    for model, adapter in FTS_ADAPTERS.items():
        # ORM SELECT honours the tenant auto-filter — so this only walks
        # rows the current tenant actually owns. Cross-tenant reindex
        # requires bypass_tenant_filter() at the call site.
        for row in db.query(model).all():
            entity_id = getattr(row, "id", None)
            row_tenant = getattr(row, "tenant_id", None)
            if not entity_id or not row_tenant:
                continue
            try:
                title = adapter.title_fn(row) or ""
                subtitle = adapter.subtitle_fn(row) or ""
                body = adapter.body_fn(row) or ""
            except Exception:  # adapter blew up — skip but don't crash.
                logger.exception("Adapter failed for %s id=%s", model.__name__, entity_id)
                continue
            _insert_row(
                connection,
                entity_type=adapter.entity_type,
                entity_id=entity_id,
                tenant_id=row_tenant,
                title=title,
                subtitle=subtitle,
                body=body,
            )
            inserted += 1
    db.commit()
    return inserted


# ---------------------------------------------------------------------------
# Sync hooks
# ---------------------------------------------------------------------------

_FTS_LISTENERS_REGISTERED = False


def _apply_adapter_after_io(connection, adapter: _FtsAdapter, target: Any) -> None:  # noqa: ANN001
    """Called from after_insert / after_update event handlers.

    Runs inside the same DBAPI connection as the parent flush so the FTS5
    write commits or rolls back atomically with the source row.
    """
    entity_id = getattr(target, "id", None)
    tenant_id = getattr(target, "tenant_id", None) or get_current_tenant_id()
    if not entity_id or not tenant_id:
        return
    try:
        title = adapter.title_fn(target) or ""
        subtitle = adapter.subtitle_fn(target) or ""
        body = adapter.body_fn(target) or ""
    except Exception:
        logger.exception("FTS5 adapter failed for %s id=%s", type(target).__name__, entity_id)
        return
    index_entity(
        connection,
        entity_type=adapter.entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        title=title,
        subtitle=subtitle,
        body=body,
    )


def _on_insert_or_update(_mapper, connection, target):  # noqa: ANN001
    adapter = FTS_ADAPTERS.get(type(target))
    if not adapter:
        return
    _apply_adapter_after_io(connection, adapter, target)


def _on_delete(_mapper, connection, target):  # noqa: ANN001
    adapter = FTS_ADAPTERS.get(type(target))
    if not adapter:
        return
    entity_id = getattr(target, "id", None)
    if not entity_id:
        return
    unindex_entity(connection, entity_type=adapter.entity_type, entity_id=entity_id)


def register_fts_listeners() -> None:
    """Attach SQLAlchemy event listeners exactly once per process.

    Called from ``app/db/session.py`` after the tenant_orm hooks are
    installed so the auto-set tenant_id is already on each row by the
    time we mirror it into FTS5.
    """
    global _FTS_LISTENERS_REGISTERED
    if _FTS_LISTENERS_REGISTERED:
        return
    for model in FTS_ADAPTERS:
        event.listen(model, "after_insert", _on_insert_or_update)
        event.listen(model, "after_update", _on_insert_or_update)
        event.listen(model, "after_delete", _on_delete)
    _FTS_LISTENERS_REGISTERED = True


def reindex_all_standalone() -> int:
    """Open a session and call :func:`reindex_all`.

    Convenience for scripts / admin CLIs that don't already have a Session.
    """
    with SessionLocal() as db:
        return reindex_all(db)
