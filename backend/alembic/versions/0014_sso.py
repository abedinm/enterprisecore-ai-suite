"""SSO + SCIM + magic-link tables — Phase 7 identity layer.

Adds three tables for the enterprise identity story:

* ``tenant_sso_configs`` — one row per tenant; either OIDC creds or SAML
  metadata + cert. Secrets are encrypted at rest by the application
  layer before being written here.
* ``scim_tokens`` — long-lived bearer tokens for external SCIM
  provisioners (Okta, Azure AD, JumpCloud). Hashed at rest.
* ``magic_link_tokens`` — one-time URLs for passwordless login,
  password reset, and email verification. ``tenant_id`` is nullable to
  let password resets be issued before we know the user's tenant.

Idempotent: each table is created only when missing, so the migration
is safe to run against fresh ``Base.metadata.create_all`` databases AND
against partially-applied installs.

Revision ID: 0014_sso
Revises: 0013_multitenant
Create Date: 2026-05-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0014_sso"
down_revision: str | None = "0013_multitenant"
branch_labels: str | None = None
depends_on: str | None = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def upgrade() -> None:
    if not _has_table("tenant_sso_configs"):
        op.create_table(
            "tenant_sso_configs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
                index=True,
            ),
            sa.Column("provider_type", sa.String(length=16), nullable=False),
            sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("issuer_url", sa.String(length=500)),
            sa.Column("client_id", sa.String(length=255)),
            sa.Column("client_secret_encrypted", sa.Text),
            sa.Column("idp_metadata_url", sa.String(length=500)),
            sa.Column("idp_metadata_xml", sa.Text),
            sa.Column("idp_entity_id", sa.String(length=500)),
            sa.Column("idp_sso_url", sa.String(length=500)),
            sa.Column("idp_x509_cert", sa.Text),
            sa.Column("sp_entity_id", sa.String(length=500)),
            sa.Column("email_attribute", sa.String(length=120), nullable=False, server_default="email"),
            sa.Column("name_attribute", sa.String(length=120), nullable=False, server_default="name"),
            sa.Column("groups_attribute", sa.String(length=120)),
            sa.Column(
                "auto_provision_users", sa.Boolean, nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "default_role_for_new_users",
                sa.String(length=40),
                nullable=False,
                server_default="employee",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not _has_table("scim_tokens"):
        op.create_table(
            "scim_tokens",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("token_hash", sa.String(length=255), nullable=False, index=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True)),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(
            "ix_scim_tokens_tenant_active",
            "scim_tokens",
            ["tenant_id", "revoked_at"],
            unique=False,
        )

    if not _has_table("magic_link_tokens"):
        op.create_table(
            "magic_link_tokens",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=32),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            sa.Column("email", sa.String(length=255), nullable=False, index=True),
            sa.Column("purpose", sa.String(length=40), nullable=False, index=True),
            sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True, index=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column("ip_address", sa.String(length=64)),
            sa.Column("user_agent", sa.String(length=500)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        # Composite index that matches the most common lookup path:
        # "do we have a pending token for this email + purpose?".
        op.create_index(
            "ix_magic_link_email_purpose",
            "magic_link_tokens",
            ["email", "purpose"],
            unique=False,
        )


def downgrade() -> None:
    """Drop the SSO tables. Destructive — all SSO configs + tokens lost."""
    if _has_table("magic_link_tokens"):
        try:
            op.drop_index("ix_magic_link_email_purpose", table_name="magic_link_tokens")
        except Exception:
            pass
        op.drop_table("magic_link_tokens")
    if _has_table("scim_tokens"):
        try:
            op.drop_index("ix_scim_tokens_tenant_active", table_name="scim_tokens")
        except Exception:
            pass
        op.drop_table("scim_tokens")
    if _has_table("tenant_sso_configs"):
        op.drop_table("tenant_sso_configs")
