"""Pydantic schemas for SSO + SCIM + magic-link endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ---------------------------------------------------------------------------
# Tenant SSO config (OIDC + SAML)
# ---------------------------------------------------------------------------
class SSOConfigIn(BaseModel):
    """Admin-supplied SSO config. Both OIDC and SAML share this shape; the
    relevant subset of fields is picked based on ``provider_type``."""

    provider_type: Literal["oidc", "saml"]
    is_enabled: bool = True

    # OIDC
    issuer_url: str | None = Field(default=None, max_length=500)
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = Field(default=None, max_length=500)
    # Sugar — set one of these to auto-fill issuer_url + scopes.
    preset: Literal["google", "microsoft", "okta", "custom"] | None = None

    # SAML
    idp_metadata_url: str | None = Field(default=None, max_length=500)
    idp_metadata_xml: str | None = None
    idp_entity_id: str | None = Field(default=None, max_length=500)
    idp_sso_url: str | None = Field(default=None, max_length=500)
    idp_x509_cert: str | None = None
    sp_entity_id: str | None = Field(default=None, max_length=500)

    # Attribute mapping
    email_attribute: str = "email"
    name_attribute: str = "name"
    groups_attribute: str | None = None

    auto_provision_users: bool = False
    default_role_for_new_users: str = "employee"


class SSOConfigOut(ORMModel):
    """Admin-facing SSO config view. The client secret is NEVER returned;
    only a boolean ``has_client_secret`` flag tells the UI whether one is
    stored."""

    id: str
    tenant_id: str
    provider_type: str
    is_enabled: bool

    issuer_url: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False

    idp_metadata_url: str | None = None
    idp_entity_id: str | None = None
    idp_sso_url: str | None = None
    idp_x509_cert: str | None = None
    sp_entity_id: str | None = None
    # Whether the admin has supplied metadata XML (don't echo back the
    # whole document — it can be huge and contains binary cert data).
    has_idp_metadata_xml: bool = False

    email_attribute: str
    name_attribute: str
    groups_attribute: str | None = None

    auto_provision_users: bool
    default_role_for_new_users: str

    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# SCIM tokens
# ---------------------------------------------------------------------------
class SCIMTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Default 1 year; admin can override.
    ttl_days: int = Field(default=365, ge=1, le=3650)


class SCIMTokenRead(ORMModel):
    id: str
    name: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class SCIMTokenCreateResponse(SCIMTokenRead):
    # Raw token — present exactly once, when the token is created.
    token: str


# ---------------------------------------------------------------------------
# Magic link
# ---------------------------------------------------------------------------
class MagicLinkRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    tenant_slug: str | None = Field(default=None, max_length=80)
    purpose: Literal["login", "password_reset", "email_verification"] = "login"


class MagicLinkConsume(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class MagicLinkConsumeResponse(BaseModel):
    """For login / verification this includes auth tokens. For password
    reset it includes a short-lived ``reset_token`` instead — the caller
    POSTs that to a (separate) password-reset confirm endpoint."""

    purpose: str
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = 0
    reset_token: str | None = None
    email: str | None = None


# ---------------------------------------------------------------------------
# SCIM 2.0 schema models
# ---------------------------------------------------------------------------
class SCIMName(BaseModel):
    formatted: str | None = None
    givenName: str | None = None
    familyName: str | None = None


class SCIMEmail(BaseModel):
    value: str
    type: str | None = "work"
    primary: bool = True


class SCIMUserResource(BaseModel):
    """SCIM 2.0 User representation.

    Shape adheres to RFC 7643 §4.1. The ``schemas`` and ``meta`` blocks are
    always populated so SCIM-compliant clients can parse the response without
    falling back to schema sniffing.
    """

    schemas: list[str] = Field(default_factory=lambda: ["urn:ietf:params:scim:schemas:core:2.0:User"])
    id: str | None = None
    userName: str
    name: SCIMName | None = None
    displayName: str | None = None
    emails: list[SCIMEmail] = Field(default_factory=list)
    active: bool = True
    meta: dict[str, Any] | None = None


class SCIMUserCreate(BaseModel):
    userName: str
    name: SCIMName | None = None
    displayName: str | None = None
    emails: list[SCIMEmail] = Field(default_factory=list)
    active: bool = True
    password: str | None = None


class SCIMListResponse(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
    )
    totalResults: int
    startIndex: int = 1
    itemsPerPage: int
    Resources: list[dict[str, Any]] = Field(default_factory=list)


class SCIMPatchOp(BaseModel):
    op: str  # "add" | "replace" | "remove"
    path: str | None = None
    value: Any | None = None


class SCIMPatchRequest(BaseModel):
    schemas: list[str] = Field(
        default_factory=lambda: ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]
    )
    Operations: list[SCIMPatchOp]


class SCIMGroupResource(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: ["urn:ietf:params:scim:schemas:core:2.0:Group"])
    id: str | None = None
    displayName: str
    members: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] | None = None
