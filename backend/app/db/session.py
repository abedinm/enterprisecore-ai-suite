"""SQLAlchemy session/engine factory."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _make_engine() -> Engine:
    url = settings.sqlalchemy_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
        future=True,
    )
    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _):  # noqa: ANN001
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    # Dev-mode slow-query log. Wires a ``before_cursor_execute`` /
    # ``after_cursor_execute`` pair that records each statement's wall-clock
    # time and emits a WARN log line for anything past the configured
    # threshold. Disabled in tests and production by default; flip on by
    # exporting QUERY_PERF_LOG=1.
    import logging
    import os
    import time as _time

    if os.environ.get("QUERY_PERF_LOG", "").lower() in ("1", "true", "yes"):
        from sqlalchemy import event as _event

        _qp_log = logging.getLogger("app.db.query_perf")
        _threshold_ms = float(os.environ.get("QUERY_PERF_THRESHOLD_MS", "50"))

        @_event.listens_for(engine, "before_cursor_execute")
        def _qp_before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            context._qp_start = _time.perf_counter()

        @_event.listens_for(engine, "after_cursor_execute")
        def _qp_after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            start = getattr(context, "_qp_start", None)
            if start is None:
                return
            elapsed_ms = (_time.perf_counter() - start) * 1000.0
            if elapsed_ms >= _threshold_ms:
                # Truncate so a giant IN clause doesn't blow up the log line.
                snippet = " ".join(statement.split())[:240]
                _qp_log.warning("slow_query ms=%.1f sql=%s", elapsed_ms, snippet)

    return engine


engine: Engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False, future=True)


# Install the tenant ORM hooks as soon as the session module loads — this
# ensures every Session created anywhere in the codebase (app.main, init_db,
# alembic, scripts, tests) gets the auto-filter + auto-set listeners. The
# call itself is idempotent.
def _install_hooks_lazily() -> None:
    try:
        from app.core.tenant_orm import install_tenant_orm_hooks
        install_tenant_orm_hooks()
    except Exception:  # pragma: no cover — defensive against import loops
        pass
    # FTS5 mirror hooks: must come AFTER the tenant_orm before_insert
    # listener so the auto-set tenant_id is already on the row when the
    # FTS5 after_insert handler reads it.
    try:
        from app.services.search import register_fts_listeners
        register_fts_listeners()
    except Exception:  # pragma: no cover
        pass


_install_hooks_lazily()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
