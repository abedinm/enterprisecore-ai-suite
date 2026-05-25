"""Request-scoped tenant context.

A ``ContextVar`` is the canonical Python primitive for per-request state in an
async server: it lives for the lifetime of the task that set it (Starlette
runs each request on its own task) and is invisible to other tasks. The
middleware in ``app/core/tenant_middleware.py`` sets it on the way in and
resets it on the way out so two concurrent requests for different tenants
can never see each other's data.

``None`` is a meaningful sentinel: it means "no tenant context" — either a
pre-auth public request (login, signup, /widget.js, /site/*) or a system task
(migrations, housekeeping, tests bootstrapping). The auto-filter in
``app/core/tenant_orm.py`` skips its WHERE injection when context is None so
those flows keep working.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# Active tenant id for the current async task. Defaults to None to allow
# bootstrap and public endpoints to operate without a tenant scope.
tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)

# When True, the auto-filter is suppressed for the duration of the call —
# used by sysadmin reports, migrations, the housekeeping scheduler, and the
# /tenants/signup flow that creates the first row in a brand-new tenant.
bypass_filter_ctx: ContextVar[bool] = ContextVar("bypass_tenant_filter", default=False)


def get_current_tenant_id() -> str | None:
    """Return the active tenant id, or None if no tenant context is set."""
    return tenant_id_ctx.get()


def set_current_tenant_id(tid: str | None):
    """Set the active tenant id and return the reset token. Callers should
    pass that token to ``tenant_id_ctx.reset(token)`` in a finally block, or
    use ``tenant_scope()`` which handles it.
    """
    return tenant_id_ctx.set(tid)


def is_filter_bypassed() -> bool:
    """True when the current context has explicitly opted out of the tenant
    auto-filter (sysadmin operations, migrations, signup bootstrap)."""
    return bypass_filter_ctx.get()


@contextmanager
def tenant_scope(tenant_id: str | None) -> Iterator[None]:
    """Run a block with ``tenant_id`` as the active tenant. Always resets
    afterwards, even on exception. Nests safely.
    """
    token = tenant_id_ctx.set(tenant_id)
    try:
        yield
    finally:
        tenant_id_ctx.reset(token)


@contextmanager
def bypass_tenant_filter() -> Iterator[None]:
    """Disable the tenant auto-filter for the duration of the block.

    Used for:
      * Sysadmin / cross-tenant reports (``GET /admin/usage``)
      * Alembic migrations + housekeeping background jobs
      * The signup flow that creates a brand-new Tenant + admin User before
        the request's auth has had a chance to set the contextvar.

    Nests safely: if a calling frame is already bypassing, this is a no-op.
    """
    token = bypass_filter_ctx.set(True)
    try:
        yield
    finally:
        bypass_filter_ctx.reset(token)
