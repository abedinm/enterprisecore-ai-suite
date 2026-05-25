"""SSO + SCIM + magic-link models.

Three tables that turn the suite into something an IT department can actually
roll out:

* ``TenantSSOConfig`` — one row per tenant; holds the OIDC or SAML credentials
  that ``/sso/oidc/login`` and ``/sso/saml/login`` use to redirect operators
  off to their corporate IdP.
* ``SCIMToken`` — bearer tokens issued from the admin UI for use by
  automated provisioners (Okta, Azure AD, JumpCloud). Hashed at rest; raw
  value shown to the admin exactly once.
* ``MagicLinkToken`` — one-time URLs for passwordless login, password reset,
  and email verification. ``tenant_id`` is nullable because password-reset
  links are issued before we know what tenant the email lives in.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class TenantSSOConfig(IdMixin, TenantMixin, TimestampMixin, Base):
    """Per-tenant SSO configuration. One row per tenant (unique constraint).

    Holds either an OIDC config (issuer_url + client_id + client_secret) or a
    SAML config (idp_metadata + idp_x509_cert), distinguished by
    ``provider_type``. Secrets are Fernet-encrypted at rest via
    ``app.core.security.encrypt_text`` — never the bare value.
    """

    __tablename__ = "tenant_sso_configs"

    provider_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "oidc" | "saml"
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- OIDC ----------------------------------------------------------
    # ``issuer_url`` is the IdP's base URL — Authlib appends /.well-known/
    # openid-configuration to discover endpoints + JWKS automatically.
    issuer_url: Mapped[str | None] = mapped_column(String(500))
    client_id: Mapped[str | None] = mapped_column(String(255))
    # Fernet-encrypted ciphertext; decrypt with ``decrypt_text``.
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text)

    # --- SAML ----------------------------------------------------------
    # Either the IdP metadata URL (fetched on demand) or the raw XML
    # (pasted by the admin once at config time).
    idp_metadata_url: Mapped[str | None] = mapped_column(String(500))
    idp_metadata_xml: Mapped[str | None] = mapped_column(Text)
    idp_entity_id: Mapped[str | None] = mapped_column(String(500))
    idp_sso_url: Mapped[str | None] = mapped_column(String(500))
    # PEM-encoded X.509 cert used to verify the IdP's signature on the
    # SAMLResponse.
    idp_x509_cert: Mapped[str | None] = mapped_column(Text)
    # Service Provider entity id — usually derived from the tenant slug
    # (e.g. ``https://app.enterprisecore.ai/sso/saml/<slug>``) but can be
    # overridden if the IdP needs a custom value.
    sp_entity_id: Mapped[str | None] = mapped_column(String(500))

    # --- Common attribute mapping --------------------------------------
    email_attribute: Mapped[str] = mapped_column(String(120), default="email", nullable=False)
    name_attribute: Mapped[str] = mapped_column(String(120), default="name", nullable=False)
    # When set, parsed as a list and used to populate UserRole. Optional —
    # blank means we don't touch role on SSO login.
    groups_attribute: Mapped[str | None] = mapped_column(String(120))

    # If True, an unknown email signing in via SSO auto-creates a User in
    # this tenant. If False, the login is rejected with a 403 telling the
    # admin to invite the user first.
    auto_provision_users: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_role_for_new_users: Mapped[str] = mapped_column(String(40), default="employee", nullable=False)


class SCIMToken(IdMixin, TenantMixin, TimestampMixin, Base):
    """Long-lived bearer token used by external SCIM provisioners.

    Each token authenticates as exactly one tenant; that scoping is the
    whole reason SCIM lives outside the regular user/JWT system. The raw
    token is shown to the admin once at creation time and hashed (bcrypt)
    before storage — even a full DB dump can't reveal usable tokens.
    """

    __tablename__ = "scim_tokens"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # bcrypt hash of the raw token. Bcrypt's per-hash salt means we can't
    # do a direct equality lookup; the auth path scans active tokens for
    # this tenant and verifies one at a time. Token rotation policy keeps
    # the active-token count tiny per tenant so the scan is cheap.
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MagicLinkToken(Base, IdMixin, TimestampMixin):
    """One-time URL token for passwordless flows.

    ``tenant_id`` is NULLABLE because a password-reset link is issued
    before we know which tenant the email belongs to (we don't want to
    leak that information by enumeration). When the user redeems the
    link, the consume endpoint locates the user and pins the right
    tenant_id in the response.

    Storing only the sha256 hash of the raw token means a DB compromise
    can't be used to forge active links — the attacker would have to
    pre-image the hash for every outstanding token.
    """

    __tablename__ = "magic_link_tokens"

    # Nullable so password-reset (cross-tenant lookup) works.
    tenant_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # "login" | "password_reset" | "email_verification" | "invite"
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # sha256 hex of the raw token. Raw is in the email URL.
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
