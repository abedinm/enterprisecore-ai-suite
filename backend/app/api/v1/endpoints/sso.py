"""SSO endpoints — OIDC + SAML config CRUD + login/callback flows.

Layout:

* Config endpoints (``/config``) — admin-only, tenant-scoped, set or
  read the per-tenant SSO settings. Client secret is encrypted with
  Fernet on the way in and never returned on the way out.
* OIDC flow — ``/oidc/login`` redirects to the IdP, ``/oidc/callback``
  exchanges the code, verifies the ID token, and signs the user in.
* SAML flow — metadata, login, ACS, SLS. Lives in this same module to
  keep the SSO surface easy to reason about.
"""
# NOTE: `from __future__ import annotations` is intentionally NOT used —
# matches the pattern in auth.py for the same FastAPI signature-introspection
# reason.
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.api.v1.endpoints.auth import _issue_tokens, _set_auth_cookies
from app.core.config import settings as app_settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    NotFoundError,
    PermissionDenied,
    ValidationFailed,
)
from app.core.rate_limit import RateLimit
from app.core.security import decrypt_text, encrypt_text, hash_password
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import get_db
from app.models.sso import TenantSSOConfig
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.sso import SSOConfigIn, SSOConfigOut
from app.services import sso_oidc

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SSO_STATE_COOKIE = "sso_oidc_state"
SSO_NONCE_COOKIE = "sso_oidc_nonce"
SAML_RELAY_COOKIE = "sso_saml_relay"


def _config_to_out(cfg: TenantSSOConfig) -> SSOConfigOut:
    """Build the safe-to-return view of a TenantSSOConfig — strips secrets."""
    return SSOConfigOut(
        id=cfg.id,
        tenant_id=cfg.tenant_id,
        provider_type=cfg.provider_type,
        is_enabled=cfg.is_enabled,
        issuer_url=cfg.issuer_url,
        client_id=cfg.client_id,
        has_client_secret=bool(cfg.client_secret_encrypted),
        idp_metadata_url=cfg.idp_metadata_url,
        idp_entity_id=cfg.idp_entity_id,
        idp_sso_url=cfg.idp_sso_url,
        idp_x509_cert=cfg.idp_x509_cert,
        sp_entity_id=cfg.sp_entity_id,
        has_idp_metadata_xml=bool(cfg.idp_metadata_xml),
        email_attribute=cfg.email_attribute,
        name_attribute=cfg.name_attribute,
        groups_attribute=cfg.groups_attribute,
        auto_provision_users=cfg.auto_provision_users,
        default_role_for_new_users=cfg.default_role_for_new_users,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


def _public_base_url(request: Request) -> str:
    """Derive the externally-visible base URL from the request.

    Honours ``X-Forwarded-Proto`` + ``X-Forwarded-Host`` when present so a
    reverse proxy in front of us produces correct redirect_uris.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost"
    return f"{proto}://{host}"


def _lookup_tenant_by_slug(db: Session, slug: str) -> Tenant:
    """Cross-tenant Tenant lookup — these endpoints are pre-auth."""
    with bypass_tenant_filter():
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if not tenant:
        raise NotFoundError(f"Tenant '{slug}' not found")
    return tenant


def _lookup_active_sso_config(db: Session, tenant_id: str, provider_type: str) -> TenantSSOConfig:
    """Look up the SSO config for a tenant — bypasses the tenant filter
    because we're pre-auth here."""
    with bypass_tenant_filter():
        cfg = db.scalar(
            select(TenantSSOConfig).where(
                TenantSSOConfig.tenant_id == tenant_id,
                TenantSSOConfig.provider_type == provider_type,
            )
        )
    if not cfg:
        raise NotFoundError(f"No {provider_type.upper()} SSO config for this tenant")
    if not cfg.is_enabled:
        raise PermissionDenied(f"{provider_type.upper()} SSO is not enabled for this tenant")
    return cfg


def _apply_preset(payload: SSOConfigIn) -> SSOConfigIn:
    """If a preset is named, fill in defaults that the admin didn't override."""
    if not payload.preset or payload.preset == "custom":
        return payload
    preset = sso_oidc.PRESETS.get(payload.preset)
    if not preset:
        return payload
    if not payload.issuer_url and preset.get("issuer_url"):
        payload.issuer_url = preset["issuer_url"]
    return payload


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------
@router.post(
    "/config",
    response_model=SSOConfigOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(RateLimit("30/minute", id="sso-config"))],
)
def upsert_sso_config(
    payload: SSOConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> SSOConfigOut:
    """Create or replace the SSO config for the current tenant.

    Only one config row per tenant (DB-level unique constraint), so this is
    an upsert: if a row already exists we update it; otherwise we create.
    """
    payload = _apply_preset(payload)
    if payload.provider_type == "oidc":
        if not payload.issuer_url:
            raise ValidationFailed("issuer_url is required for OIDC")
        if not payload.client_id:
            raise ValidationFailed("client_id is required for OIDC")
    else:
        # SAML — need either a metadata URL, raw XML, or an SSO URL + cert.
        has_metadata = bool(payload.idp_metadata_url or payload.idp_metadata_xml)
        has_manual = bool(payload.idp_sso_url and payload.idp_x509_cert and payload.idp_entity_id)
        if not (has_metadata or has_manual):
            raise ValidationFailed(
                "Provide either idp_metadata_url / idp_metadata_xml, or "
                "(idp_sso_url + idp_entity_id + idp_x509_cert)."
            )

    cfg = db.scalar(select(TenantSSOConfig).where(TenantSSOConfig.tenant_id == current_user.tenant_id))
    if not cfg:
        cfg = TenantSSOConfig(
            tenant_id=current_user.tenant_id,
            provider_type=payload.provider_type,
            is_enabled=payload.is_enabled,
        )
        db.add(cfg)
    else:
        cfg.provider_type = payload.provider_type
        cfg.is_enabled = payload.is_enabled

    # OIDC
    cfg.issuer_url = payload.issuer_url
    cfg.client_id = payload.client_id
    if payload.client_secret:
        cfg.client_secret_encrypted = encrypt_text(payload.client_secret)
    # If client_secret is None we keep whatever's already stored — that lets
    # admins PATCH other fields without re-supplying the secret every time.

    # SAML
    cfg.idp_metadata_url = payload.idp_metadata_url
    cfg.idp_metadata_xml = payload.idp_metadata_xml
    cfg.idp_entity_id = payload.idp_entity_id
    cfg.idp_sso_url = payload.idp_sso_url
    cfg.idp_x509_cert = payload.idp_x509_cert
    cfg.sp_entity_id = payload.sp_entity_id

    cfg.email_attribute = payload.email_attribute
    cfg.name_attribute = payload.name_attribute
    cfg.groups_attribute = payload.groups_attribute
    cfg.auto_provision_users = payload.auto_provision_users
    cfg.default_role_for_new_users = payload.default_role_for_new_users

    db.commit()
    db.refresh(cfg)
    return _config_to_out(cfg)


@router.get("/config", response_model=SSOConfigOut)
def get_sso_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> SSOConfigOut:
    cfg = db.scalar(select(TenantSSOConfig).where(TenantSSOConfig.tenant_id == current_user.tenant_id))
    if not cfg:
        raise NotFoundError("No SSO config for this tenant")
    return _config_to_out(cfg)


@router.delete("/config", status_code=status.HTTP_204_NO_CONTENT)
def delete_sso_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    cfg = db.scalar(select(TenantSSOConfig).where(TenantSSOConfig.tenant_id == current_user.tenant_id))
    if cfg:
        db.delete(cfg)
        db.commit()
    return None


# ---------------------------------------------------------------------------
# OIDC flow
# ---------------------------------------------------------------------------
def _resolve_or_provision_user(
    db: Session,
    tenant: Tenant,
    cfg: TenantSSOConfig,
    email: str,
    claims: dict[str, Any],
) -> User:
    """Look up the user in the tenant or auto-provision when allowed."""
    email = email.strip().lower()
    with tenant_scope(tenant.id):
        user = db.scalar(select(User).where(User.email == email))
        if user:
            return user
        if not cfg.auto_provision_users:
            raise PermissionDenied(
                "SSO login rejected: user not found and auto-provisioning is disabled"
            )
        full_name = (
            claims.get(cfg.name_attribute)
            or claims.get("name")
            or claims.get("displayName")
            or email
        )
        try:
            role = UserRole(cfg.default_role_for_new_users)
        except ValueError:
            role = UserRole.employee
        user = User(
            email=email,
            full_name=full_name,
            # Random password — SSO users never log in by password.
            # We still store a hash so other code paths that read the
            # field don't have to special-case nullable.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.refresh(user)
        return user


@router.get("/oidc/login")
def oidc_login(
    request: Request,
    tenant_slug: str = Query(..., min_length=1, max_length=80),
    redirect_after: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
):
    """Begin the OIDC flow. Public endpoint — no auth.

    1. Look up the tenant's SSO config.
    2. Generate state + nonce, stash them in a signed cookie.
    3. Redirect to the IdP's /authorize endpoint.
    """
    tenant = _lookup_tenant_by_slug(db, tenant_slug)
    cfg = _lookup_active_sso_config(db, tenant.id, "oidc")
    nonce = secrets.token_urlsafe(24)
    state, cookie_value = sso_oidc.make_state_cookie(tenant.id, nonce, redirect_after)
    base_url = _public_base_url(request)
    redirect_uri = f"{base_url}/api/v1/sso/oidc/callback"
    auth_url = sso_oidc.build_authorize_url(
        cfg.issuer_url, cfg.client_id, redirect_uri, state, nonce,
    )
    resp = RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)
    secure = app_settings.app_env != "development"
    resp.set_cookie(
        SSO_STATE_COOKIE, cookie_value,
        max_age=600, path="/", httponly=True,
        secure=secure, samesite="lax",
    )
    return resp


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    response: Response,
    code: str = Query(..., max_length=4096),
    state: str = Query(..., max_length=200),
    db: Session = Depends(get_db),
):
    """Handle the IdP redirect back to us with ?code=... ?state=..."""
    cookie_value = request.cookies.get(SSO_STATE_COOKIE)
    if not cookie_value:
        raise AuthenticationError("Missing SSO state cookie — flow expired or never started")
    try:
        state_data = sso_oidc.verify_state_cookie(cookie_value, expected_state=state)
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc

    tenant_id = state_data["tenant_id"]
    nonce = state_data["nonce"]
    redirect_after = state_data.get("redirect_after") or "/"

    cfg = _lookup_active_sso_config(db, tenant_id, "oidc")
    if not cfg.client_secret_encrypted:
        raise AppError("OIDC config has no client_secret", code="sso_misconfigured", status_code=500)
    client_secret = decrypt_text(cfg.client_secret_encrypted)
    base_url = _public_base_url(request)
    redirect_uri = f"{base_url}/api/v1/sso/oidc/callback"

    token_resp = sso_oidc.exchange_code(
        cfg.issuer_url, cfg.client_id, client_secret, code, redirect_uri,
    )
    id_token = token_resp.get("id_token")
    if not id_token:
        raise AuthenticationError("IdP token response did not contain an id_token")
    try:
        claims = sso_oidc.verify_id_token(
            id_token, cfg.issuer_url, cfg.client_id, expected_nonce=nonce,
        )
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc

    email = claims.get(cfg.email_attribute) or claims.get("email")
    if not email:
        raise AuthenticationError("IdP did not provide an email in the ID token")

    with bypass_tenant_filter():
        tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant disappeared mid-flow")

    user = _resolve_or_provision_user(db, tenant, cfg, email, claims)
    with tenant_scope(tenant_id):
        user.last_login_at = datetime.now(timezone.utc)
        tokens = _issue_tokens(user, db)
        db.commit()
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    # Clear the state cookie so it can't be replayed.
    response.delete_cookie(SSO_STATE_COOKIE, path="/")

    # Browser flow — redirect to wherever the SPA wants. API flow can just
    # consume the JSON tokens. We return the tokens AND a Location header
    # via 200 + payload so tests can assert on either side.
    if redirect_after and redirect_after.startswith("/"):
        resp = RedirectResponse(redirect_after, status_code=status.HTTP_302_FOUND)
        # Re-attach the auth cookies + clear the state cookie on the redirect
        # response itself (set_cookies on `response` don't carry to a new one).
        _set_auth_cookies(resp, tokens.access_token, tokens.refresh_token)
        resp.delete_cookie(SSO_STATE_COOKIE, path="/")
        return resp
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer",
        "expires_in": tokens.expires_in,
        "user_email": user.email,
        "tenant_id": tenant.id,
    }


# ---------------------------------------------------------------------------
# SAML flow — implemented in a separate service module so the endpoints
# stay small. Import lazily because xmlsec can be slow to import.
# ---------------------------------------------------------------------------
@router.get("/saml/metadata")
def saml_metadata(
    request: Request,
    tenant_slug: str = Query(..., min_length=1, max_length=80),
    db: Session = Depends(get_db),
):
    from app.services import sso_saml

    tenant = _lookup_tenant_by_slug(db, tenant_slug)
    cfg = _lookup_active_sso_config(db, tenant.id, "saml")
    base_url = _public_base_url(request)
    xml = sso_saml.build_sp_metadata(tenant_slug, cfg, base_url)
    return Response(content=xml, media_type="application/xml")


@router.get("/saml/login")
def saml_login(
    request: Request,
    tenant_slug: str = Query(..., min_length=1, max_length=80),
    redirect_after: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
):
    from app.services import sso_saml

    tenant = _lookup_tenant_by_slug(db, tenant_slug)
    cfg = _lookup_active_sso_config(db, tenant.id, "saml")
    base_url = _public_base_url(request)
    relay_state = secrets.token_urlsafe(24)
    sso_url = sso_saml.build_authn_request_url(
        tenant_slug, cfg, base_url, relay_state, redirect_after or "/",
    )
    resp = RedirectResponse(sso_url, status_code=status.HTTP_302_FOUND)
    secure = app_settings.app_env != "development"
    # Store (tenant_id, redirect_after) keyed by the relay_state. Same
    # signed-cookie pattern as OIDC.
    payload = sso_saml.pack_relay_cookie(tenant.id, relay_state, redirect_after or "/")
    resp.set_cookie(
        SAML_RELAY_COOKIE, payload,
        max_age=600, path="/", httponly=True,
        secure=secure, samesite="lax",
    )
    return resp


@router.post("/saml/acs")
async def saml_acs(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Assertion Consumer Service — IdP POSTs the SAMLResponse here."""
    from app.services import sso_saml

    form = await request.form()
    saml_response = form.get("SAMLResponse")
    relay_state = form.get("RelayState")
    if not saml_response:
        raise AuthenticationError("Missing SAMLResponse in POST body")

    cookie_value = request.cookies.get(SAML_RELAY_COOKIE)
    if not cookie_value:
        raise AuthenticationError("Missing SAML relay cookie")
    try:
        relay_data = sso_saml.unpack_relay_cookie(cookie_value, relay_state or "")
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc

    tenant_id = relay_data["tenant_id"]
    redirect_after = relay_data.get("redirect_after") or "/"
    cfg = _lookup_active_sso_config(db, tenant_id, "saml")

    try:
        attrs = sso_saml.verify_response(saml_response, cfg, _public_base_url(request))
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc
    email = attrs.get(cfg.email_attribute) or attrs.get("email") or attrs.get("NameID")
    if not email:
        raise AuthenticationError("SAML assertion did not include an email")

    with bypass_tenant_filter():
        tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant not found")

    user = _resolve_or_provision_user(db, tenant, cfg, email, attrs)
    with tenant_scope(tenant.id):
        user.last_login_at = datetime.now(timezone.utc)
        tokens = _issue_tokens(user, db)
        db.commit()

    if redirect_after.startswith("/"):
        resp = RedirectResponse(redirect_after, status_code=status.HTTP_303_SEE_OTHER)
        _set_auth_cookies(resp, tokens.access_token, tokens.refresh_token)
        resp.delete_cookie(SAML_RELAY_COOKIE, path="/")
        return resp
    _set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    response.delete_cookie(SAML_RELAY_COOKIE, path="/")
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer",
        "user_email": user.email,
        "tenant_id": tenant.id,
    }


@router.get("/saml/sls")
def saml_sls(response: Response):
    """Single Logout Service — IdP-initiated logout drops our cookies."""
    response.delete_cookie("__Host-access_token", path="/")
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("__Host-refresh_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return {"status": "logged_out"}
