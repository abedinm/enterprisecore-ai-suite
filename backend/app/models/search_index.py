"""FTS5 virtual-table backing store for cross-module search.

This module declares the ``search_index_fts`` SQLite FTS5 virtual table as a
DDL string and wires its creation onto ``Base.metadata`` so it is emitted
whenever ``create_all`` runs (tests, fresh installs without alembic) and at
the end of the 0021 alembic migration for production deploys.

Why a DDL string and not a SQLAlchemy ``Table``?

  FTS5 is a virtual table — SQLAlchemy's ``Table`` doesn't know how to
  declare ``USING fts5(...)`` natively. We could subclass ``Table`` and add
  a custom DDL compiler, but for a single tenant-scoped index a raw
  ``CREATE VIRTUAL TABLE IF NOT EXISTS`` is simpler and just as correct.

Columns
-------
* ``entity_type`` — e.g. ``"crm.contact"``, ``"finance.invoice"``. Stored
  as a *non-indexed* UNINDEXED column because we filter by it, not search
  it.
* ``entity_id`` — opaque FK string back to the source row. UNINDEXED.
* ``tenant_id`` — tenant scoping. UNINDEXED — we filter on equality, never
  match on the value.
* ``title`` / ``subtitle`` / ``body`` — the searchable text columns. All
  three are tokenised with ``porter unicode61`` so stemming + accent
  folding work out of the box.

Ranking
-------
FTS5's built-in ``bm25(...)`` MATCH ranking is used; lower is better. The
service layer (``app/services/search.py``) ORDER-BYs by ``bm25(...)`` and
inverts to a positive score for the API response so the JSON is intuitive.
"""
from __future__ import annotations

from sqlalchemy import DDL, event

from app.db.base import Base


# UNINDEXED columns let us filter rows efficiently without polluting the
# token vocabulary or paying the indexing cost on values we never MATCH on.
# tokenize='porter unicode61 remove_diacritics 2' gives us stemming +
# accent folding + lowercasing, which is what most ERP-style search expects.
SEARCH_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_index_fts USING fts5(
    entity_type UNINDEXED,
    entity_id UNINDEXED,
    tenant_id UNINDEXED,
    title,
    subtitle,
    body,
    tokenize = 'porter unicode61 remove_diacritics 2'
);
"""


def _emit_fts5_after_create(target, connection, **kw):  # noqa: ANN001
    """Issue the FTS5 ``CREATE VIRTUAL TABLE`` only on SQLite backends.

    Bound to ``Base.metadata`` ``after_create`` so it fires once after the
    regular ``create_all`` pass. Skips silently on non-SQLite engines —
    Postgres deployments should use ``pg_trgm`` / ``tsvector`` instead and
    will get their own migration path in a future phase.
    """
    if connection.dialect.name != "sqlite":
        return
    connection.exec_driver_sql(SEARCH_FTS_DDL)


# Register the DDL hook once at import time. ``insert=False`` (default) so
# it runs after every regular table is created.
event.listen(Base.metadata, "after_create", _emit_fts5_after_create)
