"""Tenant-aware SQLAlchemy ORM auto-filter.

Two event listeners cooperate to make multi-tenancy invisible to the rest
of the code base:

1. ``do_orm_execute`` runs before every ORM SELECT/UPDATE/DELETE. We walk
   the statement's entities, and for any model that has a ``tenant_id``
   column we splice in ``WHERE tenant_id = :current_tenant_id``. Skipped
   when the tenant context is None (public/system) or the bypass flag is
   set (sysadmin).

2. ``before_insert`` fires when a new row is being flushed. If the model
   has a ``tenant_id`` column and the row hasn't been given one already,
   we copy the current tenant id onto it. This is what makes endpoint
   code like ``db.add(Customer(name="..."))`` Just Work without a manual
   ``tenant_id=...`` argument everywhere.

Edge cases handled:

* Joined / aliased entities — the loop walks every entity column-bearing
  mapper in the statement, not just the primary one. Eager loads piggy-back
  on the parent SELECT so they don't need separate handling.
* Raw SQL (``db.execute(text("SELECT ..."))``) — bypassed, since we have
  no mapper to inspect. Service code that uses raw SQL must filter
  manually.
* Models without a ``tenant_id`` column — Tenant itself, alembic_version
  view, and any genuinely cross-tenant table — are detected at runtime
  and left untouched.
* Bulk inserts via ``Session.execute(insert(...).values(...))`` — also
  bypassed for the same reason as raw SQL. The few internal callers go
  through bypass_tenant_filter().
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Mapper, ORMExecuteState, Session, with_loader_criteria

from app.core.tenant_context import (
    get_current_tenant_id,
    is_filter_bypassed,
)


def _has_tenant_column(mapper: Mapper) -> bool:
    """Cheap check — does this mapper expose a ``tenant_id`` column?"""
    return "tenant_id" in mapper.columns


def _make_criteria(klass, tenant_id: str):
    """Return a fresh closure for ``with_loader_criteria`` that bakes in the
    given tenant_id literal.

    SQLAlchemy 2.x caches with_loader_criteria callables by identity, so we
    can't reuse a single top-level lambda — different tenant ids would all
    map to the first one cached. A factory that returns a brand-new function
    per request side-steps the cache: each function is a distinct object
    even though the bytecode is identical.
    """
    def _criteria(cls):
        return cls.tenant_id == tenant_id
    return _criteria


def _install_select_filter() -> None:
    """Register the ``do_orm_execute`` listener that filters SELECTs by tenant.

    We use ``with_loader_criteria`` because it is the SQLAlchemy 2.x sanctioned
    way to inject a WHERE clause that travels through every join and eager
    load. The criteria are evaluated per-mapper, so a SELECT that joins
    Customer and Invoice gets two separate filter predicates added — one for
    each — which is what we want.
    """

    @event.listens_for(Session, "do_orm_execute")
    def _filter_by_tenant(orm_execute_state: ORMExecuteState) -> None:
        # Bypass for raw SQL, bulk insert/update statements, and explicit
        # opt-outs.
        if not orm_execute_state.is_select:
            return
        if is_filter_bypassed():
            return
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            # No tenant context → public endpoint, signup, or system task.
            return
        # ``execution_options(skip_tenant_filter=True)`` is the per-call
        # escape hatch for queries that genuinely need cross-tenant scope.
        if orm_execute_state.execution_options.get("skip_tenant_filter"):
            return

        # Add a with_loader_criteria for every tenant-scoped mapper in the
        # registry. with_loader_criteria only fires when that class actually
        # participates in the query, so blanket-adding is cheap and covers
        # joins / eager loads / subqueries without us having to walk the
        # statement tree by hand.
        #
        # Why we use a closure factory instead of a top-level lambda:
        # SQLAlchemy compiles each with_loader_criteria callable once and
        # caches the result keyed by the callable's identity. If we pass a
        # plain ``lambda cls: cls.tenant_id == tenant_id`` the closure
        # variable ``tenant_id`` is *baked in* at compile time, so requests
        # from different tenants would all get the first-seen value. We
        # sidestep that by closing over a per-call factory that bakes the
        # CURRENT tenant_id literal into a fresh lambda each request.
        from app.db.base import Base
        for mapper in Base.registry.mappers:
            klass = mapper.class_
            if "tenant_id" not in mapper.columns:
                continue
            orm_execute_state.statement = orm_execute_state.statement.options(
                with_loader_criteria(
                    klass,
                    _make_criteria(klass, tenant_id),
                    include_aliases=True,
                )
            )


def _install_insert_listener() -> None:
    """Register a ``before_insert`` listener on every mapped class that has a
    ``tenant_id`` column. Fires when ``Session.flush()`` is about to INSERT a
    row, gives us a chance to backfill ``tenant_id`` from the contextvar."""

    from app.db.base import Base

    @event.listens_for(Base, "mapper_configured", propagate=True)
    def _attach_insert_hook(mapper: Mapper, class_):
        if not _has_tenant_column(mapper):
            return

        @event.listens_for(class_, "before_insert", propagate=True)
        def _set_tenant_on_insert(_mapper, _connection, target):
            current_value = getattr(target, "tenant_id", None)
            if current_value:
                return  # honour explicit tenant_id set by the caller
            if is_filter_bypassed():
                # Bypass context means the caller is operating cross-tenant
                # on purpose — never auto-set tenant_id under bypass.
                return
            tid = get_current_tenant_id()
            if tid:
                target.tenant_id = tid


# Idempotency guard — installing twice would double-register every listener
# and run the filter twice per query.
_INSTALLED = False


def install_tenant_orm_hooks() -> None:
    """Wire both event listeners exactly once.

    Called from ``app.main`` at import time so every ORM session created after
    boot is tenant-aware. Tests import this lazily through ``app.main`` so
    fixtures pick up the same behaviour.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _install_select_filter()
    _install_insert_listener()
    _INSTALLED = True
