"""Granular RBAC — permission catalog + resolver + FastAPI dependency.

The existing :class:`~app.models.user.UserRole` enum has eight built-in
roles. They're convenient defaults but too coarse for enterprise — a
customer wants to grant "read every finance entity but never mutate"
without giving someone the full Manager role.

This module owns the permission layer on top:

* :data:`PERMISSION_CATALOG` — every permission key the suite knows
  about, grouped by category. Seeded into the ``permissions`` table by
  migration 0017.
* :data:`BUILT_IN_ROLE_PERMISSIONS` — the static mapping from each
  ``UserRole`` to the permission keys it inherits. Used by
  :func:`has_permission` so existing endpoints keep working without any
  custom-role assignment.
* :func:`has_permission` — resolves a user's effective permission set
  by unioning the built-in role's keys with every assigned custom role.
* :func:`require_permission` — FastAPI dep factory that raises 403 when
  the current user lacks the key.

The existing ``require_roles(...)`` in :mod:`app.api.deps` is preserved
intact. New endpoints should prefer ``require_permission(...)`` for
fine-grained gating; legacy endpoints stay on role checks.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Iterable

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import PermissionDenied
from app.db.session import get_db
from app.models.rbac import CustomRole, UserRoleAssignment
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Permission catalog
# ---------------------------------------------------------------------------
# Each entry is (key, category, description). Keys follow
# "<module>.<entity>.<verb>" — verbs are read / write / delete / admin /
# export / sign / publish / terminate. Built-in roles map to subsets.
# ---------------------------------------------------------------------------
PERMISSION_CATALOG: list[tuple[str, str, str]] = [
    # --- Tenant administration -------------------------------------------
    ("tenant.admin", "tenant", "Full tenant administration (users, billing, settings)"),
    ("tenant.settings.read", "tenant", "Read tenant-wide settings"),
    ("tenant.settings.write", "tenant", "Modify tenant-wide settings"),
    ("tenant.users.read", "tenant", "List tenant users"),
    ("tenant.users.write", "tenant", "Invite / edit tenant users"),
    ("tenant.billing.read", "tenant", "View subscription + invoices"),
    ("tenant.billing.write", "tenant", "Change subscription / payment method"),
    ("tenant.audit.read", "tenant", "Read the audit log"),
    ("tenant.security.read", "tenant", "Read security policies (IP allowlist, audit streams)"),
    ("tenant.security.write", "tenant", "Modify security policies"),
    ("tenant.encryption.admin", "tenant", "Manage tenant DEK + BYOK configuration"),
    # --- Finance ----------------------------------------------------------
    ("finance.invoices.read", "finance", "Read invoices"),
    ("finance.invoices.write", "finance", "Create / edit invoices"),
    ("finance.invoices.delete", "finance", "Delete invoices"),
    ("finance.invoices.export", "finance", "Export invoice data"),
    ("finance.expenses.read", "finance", "Read expenses"),
    ("finance.expenses.write", "finance", "Create / edit expenses"),
    ("finance.expenses.delete", "finance", "Delete expenses"),
    ("finance.payroll.read", "finance", "Read payroll runs"),
    ("finance.payroll.write", "finance", "Run / edit payroll"),
    ("finance.budgets.read", "finance", "Read budgets"),
    ("finance.budgets.write", "finance", "Edit budgets"),
    ("finance.tax.read", "finance", "Read tax rates"),
    ("finance.tax.write", "finance", "Edit tax rates"),
    ("finance.journal.read", "finance", "Read general ledger"),
    ("finance.journal.write", "finance", "Post journal entries"),
    ("finance.customers.read", "finance", "Read customers"),
    ("finance.customers.write", "finance", "Edit customers"),
    ("finance.vendors.read", "finance", "Read vendors"),
    ("finance.vendors.write", "finance", "Edit vendors"),
    # --- HR ---------------------------------------------------------------
    ("hr.employees.read", "hr", "Read employee records"),
    ("hr.employees.write", "hr", "Edit employee records"),
    ("hr.employees.terminate", "hr", "Terminate employees"),
    ("hr.attendance.read", "hr", "Read attendance"),
    ("hr.attendance.write", "hr", "Record attendance"),
    ("hr.leave.read", "hr", "Read leave requests"),
    ("hr.leave.approve", "hr", "Approve leave requests"),
    ("hr.reviews.read", "hr", "Read performance reviews"),
    ("hr.reviews.write", "hr", "Conduct performance reviews"),
    ("hr.recruiting.read", "hr", "Read jobs / candidates"),
    ("hr.recruiting.write", "hr", "Manage jobs / candidates"),
    # --- CRM --------------------------------------------------------------
    ("crm.leads.read", "crm", "Read leads"),
    ("crm.leads.write", "crm", "Edit leads"),
    ("crm.deals.read", "crm", "Read deals"),
    ("crm.deals.write", "crm", "Edit deals"),
    ("crm.deals.export", "crm", "Export deal data"),
    ("crm.contacts.read", "crm", "Read contacts"),
    ("crm.contacts.write", "crm", "Edit contacts"),
    ("crm.contracts.read", "crm", "Read contracts"),
    ("crm.contracts.write", "crm", "Edit contracts"),
    ("crm.contracts.sign", "crm", "Sign contracts"),
    ("crm.campaigns.read", "crm", "Read campaigns"),
    ("crm.campaigns.write", "crm", "Edit / launch campaigns"),
    # --- Projects ---------------------------------------------------------
    ("projects.projects.read", "projects", "Read projects"),
    ("projects.projects.write", "projects", "Edit projects"),
    ("projects.tasks.read", "projects", "Read tasks"),
    ("projects.tasks.write", "projects", "Edit tasks"),
    ("projects.time.read", "projects", "Read time entries"),
    ("projects.time.write", "projects", "Log time entries"),
    # --- Inventory --------------------------------------------------------
    ("inventory.products.read", "inventory", "Read products"),
    ("inventory.products.write", "inventory", "Edit products"),
    ("inventory.stock.read", "inventory", "Read stock movements"),
    ("inventory.stock.write", "inventory", "Adjust stock"),
    ("inventory.po.read", "inventory", "Read purchase orders"),
    ("inventory.po.write", "inventory", "Create / edit purchase orders"),
    ("inventory.suppliers.read", "inventory", "Read suppliers"),
    ("inventory.suppliers.write", "inventory", "Edit suppliers"),
    # --- Documents --------------------------------------------------------
    ("documents.documents.read", "documents", "Read documents"),
    ("documents.documents.write", "documents", "Upload / edit documents"),
    ("documents.documents.delete", "documents", "Delete documents"),
    ("documents.documents.share", "documents", "Share documents externally"),
    ("documents.esign.sign", "documents", "Sign e-signature requests"),
    # --- Communication ----------------------------------------------------
    ("communication.messages.read", "communication", "Read messages"),
    ("communication.messages.write", "communication", "Send messages"),
    ("communication.announcements.write", "communication", "Publish announcements"),
    ("communication.wiki.read", "communication", "Read wiki"),
    ("communication.wiki.write", "communication", "Edit wiki"),
    # --- Marketing --------------------------------------------------------
    ("marketing.posts.read", "marketing", "Read posts"),
    ("marketing.posts.write", "marketing", "Edit posts"),
    ("marketing.publish", "marketing", "Publish to the marketing site"),
    ("marketing.site.write", "marketing", "Edit marketing site settings"),
    # --- Construction -----------------------------------------------------
    ("construction.projects.read", "construction", "Read construction projects"),
    ("construction.projects.write", "construction", "Edit construction projects"),
    ("construction.contracts.read", "construction", "Read contracts"),
    ("construction.contracts.write", "construction", "Edit contracts"),
    ("construction.contracts.sign", "construction", "Sign construction contracts"),
    ("construction.permits.read", "construction", "Read permits"),
    ("construction.permits.write", "construction", "Edit permits"),
    ("construction.risks.read", "construction", "Read risks"),
    ("construction.risks.write", "construction", "Edit risks"),
    # --- Academic --------------------------------------------------------
    ("academic.classes.read", "academic", "Read classes"),
    ("academic.classes.write", "academic", "Edit classes"),
    ("academic.grades.read", "academic", "Read grades"),
    ("academic.grades.write", "academic", "Enter grades"),
    ("academic.attendance.write", "academic", "Record attendance"),
    ("academic.enroll.write", "academic", "Enroll students"),
    # --- Coding / AI / Knowledge -----------------------------------------
    ("coding.projects.read", "coding", "Read code projects"),
    ("coding.projects.write", "coding", "Edit code projects"),
    ("ai.chat.use", "ai", "Use AI chat"),
    ("ai.usage.read", "ai", "Read AI usage records"),
    ("knowledge.bases.read", "knowledge", "Read knowledge bases"),
    ("knowledge.bases.write", "knowledge", "Edit knowledge bases"),
    # --- Webchat ---------------------------------------------------------
    ("webchat.bots.read", "webchat", "Read webchat bots"),
    ("webchat.bots.write", "webchat", "Edit webchat bots"),
]


def _category(prefix: str) -> set[str]:
    """All catalog keys whose key starts with ``prefix``."""
    return {key for key, _, _ in PERMISSION_CATALOG if key.startswith(prefix)}


def _reads(category_prefix: str) -> set[str]:
    """Every ``*.read`` key in a category."""
    return {key for key, _, _ in PERMISSION_CATALOG
            if key.startswith(category_prefix) and key.endswith(".read")}


# ---------------------------------------------------------------------------
# Built-in role → permission mapping
# ---------------------------------------------------------------------------
# Computed once at import time. Admin gets the whole catalog. Manager gets
# every read + every business-module write but not tenant admin. Employee
# gets reads on the modules they typically touch + write on their own
# attendance / time / messages. Developer gets coding/AI/knowledge writes
# plus reads. Academic roles get only academic perms (gated separately by
# require_plan_feature("academic")).
# ---------------------------------------------------------------------------
_ALL_KEYS: set[str] = {key for key, _, _ in PERMISSION_CATALOG}

_MANAGER_KEYS: set[str] = (
    {k for k in _ALL_KEYS if k.endswith(".read")}
    | _category("finance.") | _category("hr.") | _category("crm.")
    | _category("projects.") | _category("inventory.") | _category("documents.")
    | _category("communication.") | _category("marketing.")
    | _category("construction.")
    | {"ai.chat.use"}
) - {
    # Manager can't terminate without explicit grant, can't admin tenant,
    # can't manage encryption / billing.
    "hr.employees.terminate",
    "tenant.admin",
    "tenant.users.write",
    "tenant.billing.write",
    "tenant.encryption.admin",
    "tenant.security.write",
}

_EMPLOYEE_KEYS: set[str] = (
    _reads("finance.")
    | _reads("hr.")
    | _reads("crm.")
    | _reads("projects.")
    | _reads("inventory.")
    | _reads("documents.")
    | _reads("communication.")
    | _reads("marketing.")
    | _reads("construction.")
    | _reads("knowledge.")
    | {
        "hr.attendance.write",
        "projects.tasks.read",
        "projects.tasks.write",
        "projects.time.write",
        "communication.messages.write",
        "documents.esign.sign",
        "ai.chat.use",
    }
)

_DEVELOPER_KEYS: set[str] = _EMPLOYEE_KEYS | (
    _category("coding.")
    | _category("knowledge.")
    | {"ai.usage.read"}
)

_STUDENT_KEYS: set[str] = {
    "academic.classes.read", "academic.grades.read",
    "communication.messages.read", "communication.messages.write",
    "documents.documents.read",
    "knowledge.bases.read",
    "ai.chat.use",
}

_TEACHER_KEYS: set[str] = _STUDENT_KEYS | {
    "academic.grades.write",
    "academic.attendance.write",
    "academic.classes.write",
    "documents.documents.write",
    "knowledge.bases.write",
}

_REGISTRAR_KEYS: set[str] = _TEACHER_KEYS | {
    "academic.enroll.write",
    "tenant.users.read",
}

_DEAN_KEYS: set[str] = _REGISTRAR_KEYS | _category("academic.") | {
    "tenant.audit.read",
    "tenant.settings.read",
}


BUILT_IN_ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.admin: set(_ALL_KEYS),
    UserRole.manager: _MANAGER_KEYS,
    UserRole.employee: _EMPLOYEE_KEYS,
    UserRole.developer: _DEVELOPER_KEYS,
    UserRole.student: _STUDENT_KEYS,
    UserRole.teacher: _TEACHER_KEYS,
    UserRole.registrar: _REGISTRAR_KEYS,
    UserRole.dean: _DEAN_KEYS,
}


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def effective_permissions(user: User, db: Session) -> set[str]:
    """Compute the union of built-in role perms + every assigned custom
    role's permission_keys. Tenant isolation is automatic — the
    auto-filter scopes the CustomRole lookup to ``user.tenant_id``.
    """
    keys: set[str] = set(BUILT_IN_ROLE_PERMISSIONS.get(user.role, set()))
    rows = db.execute(
        select(CustomRole.permission_keys)
        .join(UserRoleAssignment, UserRoleAssignment.custom_role_id == CustomRole.id)
        .where(UserRoleAssignment.user_id == user.id)
    ).all()
    for (perm_keys,) in rows:
        if perm_keys:
            keys.update(perm_keys)
    return keys


def has_permission(user: User, permission_key: str, db: Session) -> bool:
    """True when the user's effective permissions include ``permission_key``."""
    return permission_key in effective_permissions(user, db)


def require_permission(permission_key: str) -> Callable:
    """FastAPI dep factory that raises 403 when the current user lacks
    ``permission_key``.

    Usage::

        @router.post("/invoices",
                     dependencies=[Depends(require_permission("finance.invoices.write"))])
        def create_invoice(...): ...
    """
    # Local import to avoid an import cycle (app.api.deps imports this
    # module transitively via require_roles_or_permissions).
    from app.api.deps import get_current_user

    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not has_permission(current_user, permission_key, db):
            raise PermissionDenied(
                f"Missing required permission: {permission_key}"
            )
        return current_user

    return _dep


def require_any_permission(*keys: str) -> Callable:
    """Like :func:`require_permission` but passes if any of ``keys`` is held."""
    from app.api.deps import get_current_user

    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        held = effective_permissions(current_user, db)
        if not any(k in held for k in keys):
            raise PermissionDenied(
                f"Requires one of: {', '.join(keys)}"
            )
        return current_user

    return _dep
