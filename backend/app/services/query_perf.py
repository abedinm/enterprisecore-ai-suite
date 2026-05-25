"""Query-performance helpers + a test/debug query-counter.

This module centralises three concerns:

1.  **N+1 detection** — :class:`QueryCounter` is a context manager that hooks
    SQLAlchemy's ``before_cursor_execute`` event and records every statement
    fired during the block. Tests use it to assert that an endpoint stays
    under a query budget; manual debugging uses it to dump the slow trace.

2.  **Eager-load shorthand** — :func:`with_eager` is a tiny wrapper around
    ``selectinload`` / ``joinedload`` that prevents lazy-load chains during
    rollups. We use ``selectinload`` by default because it's a flat IN-list
    second query rather than an outer join (better when the parent rowset
    is small but each child collection is large, which matches our
    dashboard shape).

3.  **Bulk fetch + group** — :func:`bulk_by_parent` runs a single
    ``WHERE parent_id IN (...)`` query and groups the children into a dict
    keyed by parent id, so callers can replace per-parent N+1 loops with a
    single bulk lookup.

None of these helpers import FastAPI or app routing — they're pure
SQLAlchemy utilities so the service layer can use them without dragging
the web framework into tests.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Sequence

from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, joinedload, selectinload


# ---------------------------------------------------------------------------
# Query counter
# ---------------------------------------------------------------------------
class QueryCounter:
    """Counts SQL statements fired during a block.

    Attributes:
        count: Number of statements executed inside the block.
        statements: Raw SQL text of each statement (for debug dumps). Each
            entry is the compiled string the cursor saw — bind values are
            NOT inlined, so ``?`` / ``%s`` placeholders survive.
        durations_ms: Per-statement wall-clock durations.
    """

    def __init__(self) -> None:
        self.count: int = 0
        self.statements: list[str] = []
        self.durations_ms: list[float] = []
        self._start_times: list[float] = []

    def _before(self, conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        self.count += 1
        self.statements.append(statement)
        self._start_times.append(time.perf_counter())

    def _after(self, conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001
        if self._start_times:
            start = self._start_times.pop()
            self.durations_ms.append((time.perf_counter() - start) * 1000.0)

    # Convenience surfaces ---------------------------------------------------
    def by_table(self) -> dict[str, int]:
        """Group statement counts by the first table name they touch.

        Heuristic-only — strips after the first ``FROM``/``UPDATE``/``INSERT``
        keyword. Good enough to spot ``SELECT * FROM tasks`` repeated 50x.
        """
        counts: dict[str, int] = {}
        for s in self.statements:
            tail = ""
            up = s.upper()
            for kw in (" FROM ", " UPDATE ", " INTO "):
                idx = up.find(kw)
                if idx >= 0:
                    tail = s[idx + len(kw):].strip()
                    break
            tbl = tail.split()[0].strip('"`') if tail else "?"
            counts[tbl] = counts.get(tbl, 0) + 1
        return counts

    def slowest(self, n: int = 5) -> list[tuple[str, float]]:
        """Return the slowest ``n`` statements as ``(sql, ms)`` pairs."""
        pairs = list(zip(self.statements, self.durations_ms))
        pairs.sort(key=lambda p: p[1], reverse=True)
        return pairs[:n]


@contextmanager
def count_queries(engine: Engine) -> Iterator[QueryCounter]:
    """Counts SQL statements fired against ``engine`` inside the block.

    Usage:
        >>> with count_queries(engine) as q:
        ...     resp = client.get("/api/v1/dashboard")
        >>> assert q.count <= 10, q.by_table()
    """
    counter = QueryCounter()
    event.listen(engine, "before_cursor_execute", counter._before)
    event.listen(engine, "after_cursor_execute", counter._after)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", counter._before)
        event.remove(engine, "after_cursor_execute", counter._after)


# ---------------------------------------------------------------------------
# Eager-load helpers
# ---------------------------------------------------------------------------
def with_eager(stmt, *relationships, strategy: str = "selectin"):
    """Attach eager-loading options to ``stmt`` for one or more relationships.

    Args:
        stmt: A ``select(...)`` statement.
        relationships: Mapper-attribute relationships to eager-load
            (e.g. ``Invoice.lines``).
        strategy: ``"selectin"`` (default — flat IN-list follow-up query)
            or ``"joined"`` (single outer-join). Pick joined when the
            child collection is tiny (one-to-one) and selectin when the
            collection is bigger or you're loading lots of parents.

    Returns:
        The same statement with eager-load options applied.
    """
    loader: Callable
    loader = selectinload if strategy == "selectin" else joinedload
    for rel in relationships:
        stmt = stmt.options(loader(rel))
    return stmt


# ---------------------------------------------------------------------------
# Bulk fetch + group
# ---------------------------------------------------------------------------
def bulk_by_parent(
    db: Session,
    child_cls,
    parent_col,
    parent_ids: Sequence[str],
    *,
    extra_where=None,
) -> dict[str, list[Any]]:
    """One query: ``SELECT * FROM child WHERE parent_id IN (...)`` grouped by parent.

    Args:
        db: Active session.
        child_cls: The child model class (e.g. ``Task``).
        parent_col: The FK column on the child (e.g. ``Task.project_id``).
        parent_ids: Distinct parent ids to fetch children for.
        extra_where: Optional additional ``where(...)`` clause to apply
            (e.g. ``Task.status != "done"``).

    Returns:
        A dict mapping each ``parent_id`` to a list of child rows. Parents
        with no children are present with an empty list — callers can rely
        on ``out[pid]`` being non-throwing.
    """
    out: dict[str, list[Any]] = {pid: [] for pid in parent_ids}
    if not parent_ids:
        return out
    stmt = select(child_cls).where(parent_col.in_(list(parent_ids)))
    if extra_where is not None:
        stmt = stmt.where(extra_where)
    for row in db.scalars(stmt).all():
        key = getattr(row, parent_col.key)
        if key in out:
            out[key].append(row)
    return out
