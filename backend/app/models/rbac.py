"""Phase 9 — granular RBAC.

The existing :class:`~app.models.user.UserRole` enum gives every tenant the
same eight built-in roles (admin, manager, employee, developer, student,
teacher, registrar, dean). That covers most installs, but enterprise
customers routinely want to define their own roles — e.g. "Finance Auditor"
that can read every finance entity but can't mutate anything, or "Project
Owner" that can sign construction contracts without being a full admin.

This module adds a richer permission layer on top:

* :class:`Permission` — global catalog of permission keys (not tenant
  scoped). Seeded by the 0017_rbac_security migration.
* :class:`CustomRole` — tenant-defined role that holds a list of
  permission keys.
* :class:`UserRoleAssignment` — junction granting a user a custom role.
  A user keeps their built-in ``role`` AND can have any number of custom
  roles layered on top.

Resolution happens in :mod:`app.core.permissions`.
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Permission(IdMixin, Base):
    """A globally-defined permission key.

    Not tenant-scoped: the catalog is shared by every tenant. Permissions
    are immutable from the API surface — they're seeded by migration and
    only updated when a new module ships.
    """

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CustomRole(IdMixin, TenantMixin, TimestampMixin, Base):
    """Tenant-defined role layered on top of the eight built-in UserRoles.

    Customers can create any number of these. The set of granted
    permissions is stored as a JSON list of permission keys; we accept
    the denormalised storage in exchange for not needing a third
    junction table. Cross-tenant isolation is automatic via TenantMixin.
    """

    __tablename__ = "custom_roles"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Built-ins are visible in listings but cannot be edited / deleted via
    # the API. We don't ship any seeded built-ins today (the UserRole
    # enum covers that), but the flag is here so future seedings can use
    # the same table.
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Permission keys this role grants. Stored as JSON list-of-strings.
    permission_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_custom_roles_tenant_name"),
    )


class UserRoleAssignment(IdMixin, TenantMixin, TimestampMixin, Base):
    """Junction: a user holds a custom role.

    A user can have multiple custom roles; the effective permission set is
    the union of (built-in role permissions) ∪ (every custom role's
    permissions). Resolved in :func:`app.core.permissions.has_permission`.
    """

    __tablename__ = "user_role_assignments"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    custom_role_id: Mapped[str] = mapped_column(
        ForeignKey("custom_roles.id", ondelete="CASCADE"), index=True, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "custom_role_id", name="uq_user_role_assignment"),
    )
