"""Tenant model — root of the multi-tenancy data graph.

Every other table in the database carries a ``tenant_id`` FK that points here.
Dropping a tenant cascades through every owning table so a customer's data is
removed wholesale rather than orphaned. The Default Tenant created by
migration 0013_multitenant is what every pre-existing row was backfilled to,
so single-tenant installs (the prior shape) keep working unchanged.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Tenant(IdMixin, TimestampMixin, Base):
    """One paying customer (or evaluating prospect) of the suite.

    A Tenant is the unit of data isolation: every business record (a Customer,
    an Invoice, an Employee, a Class, a Construction Project, etc.) belongs to
    exactly one Tenant via ``tenant_id``. The auto-filter in
    ``app/core/tenant_orm.py`` rewrites every SELECT to scope by the current
    tenant context, making cross-tenant data leakage impossible at the ORM
    layer.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # URL-safe identifier for subdomain / path routing (e.g. ``acme`` →
    # ``acme.enterprisecore.app``). Unique across the whole install.
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    # Per-tenant plan — overrides the global license plan when set. See
    # ``app/core/plans.py::resolve_plan`` for the lookup logic.
    plan: Mapped[str] = mapped_column(String(20), default="evaluation", nullable=False)
    # active | trial | suspended | cancelled
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Free-form JSON bag for tenant-specific config (feature toggles, branding
    # overrides). Kept as a single JSON column so adding a setting never
    # requires a migration.
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    primary_contact_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    timezone: Mapped[str] = mapped_column(String(60), default="UTC", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)


class TenantInvite(IdMixin, TimestampMixin, Base):
    """Pending invitation to join a tenant.

    Created by ``POST /tenants/me/users/invite``, consumed by
    ``POST /tenants/accept-invite``. ``token`` is a high-entropy random string
    that doubles as the URL parameter the invitee clicks. ``status`` flips
    from ``pending`` to ``accepted`` (or ``revoked`` if the inviter changes
    their mind).
    """

    __tablename__ = "tenant_invites"

    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), default="Employee", nullable=False)
    token: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    # pending | accepted | revoked
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    invited_by_id: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
