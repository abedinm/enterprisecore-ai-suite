"""Phase 9 — RBAC + enterprise security hardening tables.

Creates six tables:

* ``permissions`` — global catalog of permission keys (NOT tenant-scoped).
* ``custom_roles`` — tenant-defined RBAC role.
* ``user_role_assignments`` — junction (user × custom_role).
* ``tenant_encryption_keys`` — per-tenant DEK rows (envelope + BYOK).
* ``tenant_security_policies`` — per-tenant IP allowlist + policy bag.
* ``audit_stream_destinations`` — SIEM / webhook outbound destinations.

Plus a seed step that fills the ``permissions`` table with the
``PERMISSION_CATALOG`` defined in :mod:`app.core.permissions`.

Idempotent: every ``create_table`` is gated by a ``_has_table`` probe so
this migration can be replayed against a DB built via
``Base.metadata.create_all`` (the path tests take) without
duplicate-table errors.

Revision ID: 0017_rbac_security
Revises: 0015_billing  (siblings 0014_sso / 0016_webhooks_gdpr may
                        rebase their own ``down_revision`` to chain
                        whichever lands last)
Create Date: 2026-05-23
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0017_rbac_security"
down_revision: str | None = "0016_webhooks_gdpr"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. permissions — global catalog.
    # ------------------------------------------------------------------
    if not _has_table("permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("key", sa.String(length=120), nullable=False, unique=True, index=True),
            sa.Column("category", sa.String(length=40), nullable=False, index=True),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
        )

    # ------------------------------------------------------------------
    # 2. custom_roles — tenant-defined role.
    # ------------------------------------------------------------------
    if not _has_table("custom_roles"):
        op.create_table(
            "custom_roles",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("is_builtin", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("permission_keys", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "name", name="uq_custom_roles_tenant_name"),
        )

    # ------------------------------------------------------------------
    # 3. user_role_assignments — junction.
    # ------------------------------------------------------------------
    if not _has_table("user_role_assignments"):
        op.create_table(
            "user_role_assignments",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("user_id", sa.String(length=32),
                      sa.ForeignKey("users.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("custom_role_id", sa.String(length=32),
                      sa.ForeignKey("custom_roles.id", ondelete="CASCADE"),
                      nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "custom_role_id", name="uq_user_role_assignment"),
        )

    # ------------------------------------------------------------------
    # 4. tenant_encryption_keys — per-tenant DEKs.
    # ------------------------------------------------------------------
    if not _has_table("tenant_encryption_keys"):
        op.create_table(
            "tenant_encryption_keys",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("key_version", sa.Integer, nullable=False, server_default="1", index=True),
            sa.Column("wrapped_dek", sa.LargeBinary, nullable=False),
            sa.Column("kms_provider", sa.String(length=20), nullable=False, server_default="server"),
            sa.Column("kms_key_ref", sa.String(length=500)),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("rotated_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "key_version", name="uq_tenant_dek_version"),
        )

    # ------------------------------------------------------------------
    # 5. tenant_security_policies — per-tenant policy bag.
    # ------------------------------------------------------------------
    if not _has_table("tenant_security_policies"):
        op.create_table(
            "tenant_security_policies",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("ip_allowlist_cidrs", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
            sa.Column("ip_allowlist_enforced", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", name="uq_tenant_security_policy"),
        )

    # ------------------------------------------------------------------
    # 6. audit_stream_destinations — SIEM / webhook outbound.
    # ------------------------------------------------------------------
    if not _has_table("audit_stream_destinations"):
        op.create_table(
            "audit_stream_destinations",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id", sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("destination_type", sa.String(length=40), nullable=False),
            sa.Column("url", sa.Text, nullable=False),
            sa.Column("credentials_encrypted", sa.Text),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("last_success_at", sa.DateTime(timezone=True)),
            sa.Column("last_error_at", sa.DateTime(timezone=True)),
            sa.Column("last_error_message", sa.Text),
            sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    # ------------------------------------------------------------------
    # 7. Seed the permission catalog.
    # ------------------------------------------------------------------
    _seed_permissions()


def _seed_permissions() -> None:
    """Insert every PERMISSION_CATALOG row that isn't already present."""
    from app.core.permissions import PERMISSION_CATALOG
    from app.db.base import _ulid  # type: ignore

    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.text("SELECT key FROM permissions"))}
    to_insert = [
        {"id": _ulid(), "key": key, "category": cat, "description": desc}
        for key, cat, desc in PERMISSION_CATALOG
        if key not in existing
    ]
    if not to_insert:
        return
    perms_t = sa.table(
        "permissions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(perms_t, to_insert)


def downgrade() -> None:
    for name in (
        "audit_stream_destinations",
        "tenant_security_policies",
        "tenant_encryption_keys",
        "user_role_assignments",
        "custom_roles",
        "permissions",
    ):
        if _has_table(name):
            op.drop_table(name)
