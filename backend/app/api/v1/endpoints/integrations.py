"""Integration catalog + install/uninstall endpoints + OAuth callback +
Zapier inbound webhook.

The catalog endpoint is read-only and visible to any authenticated user
(so the UI can render the integrations marketplace). Install/uninstall
and config-update require admin or manager. The OAuth callback is public
(state-verified) because the third-party redirects the user's browser to
it directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.cache import cache_response
from app.core.exceptions import NotFoundError, ValidationFailed
from app.db.session import get_db
from app.models.integrations import TenantIntegration
from app.models.user import User, UserRole
from app.schemas.workflows import (
    IntegrationCatalogEntry, IntegrationConfigUpdate,
    IntegrationInstallResponse, TenantIntegrationOut,
)
from app.services.audit import record_audit
from app.services.integrations import (
    get_integration, list_integrations,
)
from app.services.integrations.docusign import DocuSignIntegration
from app.services.integrations.github import GitHubIntegration
from app.services.integrations.zapier import ZapierIntegration

router = APIRouter()


def _to_out(row: TenantIntegration) -> dict:
    return {
        "id": row.id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "key": row.key,
        "name": row.name,
        "is_enabled": row.is_enabled,
        "config": row.config or {},
        "installed_by_user_id": row.installed_by_user_id,
        "installed_at": row.installed_at,
        "last_used_at": row.last_used_at,
    }


@router.get("/catalog", response_model=list[IntegrationCatalogEntry])
@cache_response(ttl=3600, namespace="integrations:catalog")
def get_catalog(response: Response, _: User = Depends(get_current_user)):
    """Return every available connector + whether the deployment is
    configured to talk to it. ``configurable=False`` means the customer
    sees the listing but the install button is disabled until an admin
    sets the relevant env vars."""
    out = []
    for integ in list_integrations():
        out.append({
            "key": integ.key,
            "name": integ.name,
            "category": integ.category,
            "description": integ.description,
            "configurable": integ.__class__.is_configurable(),
            "default_event_types": list(integ.default_event_types),
        })
    return out


@router.get("/installed", response_model=list[TenantIntegrationOut])
def list_installed(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.scalars(
        select(TenantIntegration).order_by(TenantIntegration.created_at.desc())
    ).all()
    return [_to_out(r) for r in rows]


@router.post("/{key}/install", response_model=IntegrationInstallResponse)
def install_integration(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Start an install. For OAuth connectors (Slack, Google Workspace)
    we return the third-party authorization URL the UI should redirect
    to. For Zapier we provision the static API key and return it once."""
    try:
        connector = get_integration(key)
    except KeyError:
        raise NotFoundError(f"Unknown integration: {key}")
    from app.core.tenant_context import get_current_tenant_id

    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise ValidationFailed("No tenant context")

    if isinstance(connector, ZapierIntegration):
        _row, api_key = connector.install_static(
            tenant_id, db, installed_by_user_id=user.id
        )
        record_audit(
            db, actor=user, action="install", entity_type="integration",
            entity_id=key, detail={"key": key},
        )
        db.commit()
        return {"key": key, "install_url": None, "api_key": api_key, "requires_oauth": False}

    # OAuth connectors: build redirect URL using the request's base url.
    base = str(request.base_url).rstrip("/")
    redirect_url = f"{base}/api/v1/integrations/oauth/callback?key={key}"
    url = connector.install_url(tenant_id, redirect_url)
    return {"key": key, "install_url": url, "api_key": None, "requires_oauth": True}


@router.get("/oauth/callback")
def oauth_callback(
    request: Request,
    key: str = Query(...),
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """Public OAuth callback. The third-party redirects the user's browser
    here with ``?code=...&state=...``; we verify the state token (which
    embeds the tenant id) and exchange the code for tokens.

    Note: not protected by the usual auth middleware because the redirect
    happens in a fresh browser context. State verification + the OAuth
    code-exchange round-trip provide the security guarantees.
    """
    try:
        connector = get_integration(key)
    except KeyError:
        raise NotFoundError(f"Unknown integration: {key}")

    # State is "<key>:<tenant_id>"; we trust the tenant id from there.
    if ":" not in state:
        raise ValidationFailed("Malformed OAuth state")
    tenant_id = state.split(":", 1)[1]
    from app.core.tenant_context import tenant_scope

    with tenant_scope(tenant_id):
        row = connector.handle_oauth_callback(tenant_id, code, state, db)
    return {"ok": True, "integration_id": row.id, "key": row.key}


@router.post("/{key}/uninstall", status_code=status.HTTP_204_NO_CONTENT)
def uninstall_integration(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    try:
        connector = get_integration(key)
    except KeyError:
        raise NotFoundError(f"Unknown integration: {key}")
    from app.core.tenant_context import get_current_tenant_id

    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise ValidationFailed("No tenant context")
    connector.uninstall(tenant_id, db)
    record_audit(
        db, actor=user, action="uninstall", entity_type="integration",
        entity_id=key, detail={"key": key},
    )
    db.commit()
    return None


@router.patch("/{key}/config", response_model=TenantIntegrationOut)
def update_config(
    key: str,
    payload: IntegrationConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Update tenant-specific integration config (default Slack channel,
    Zapier outbound URL, event filter, etc). The config bag is merged
    rather than replaced so partial updates don't wipe other keys."""
    row = db.scalar(select(TenantIntegration).where(TenantIntegration.key == key))
    if row is None:
        raise NotFoundError(f"Integration not installed: {key}")
    merged = dict(row.config or {})
    merged.update(payload.config or {})
    row.config = merged
    if payload.is_enabled is not None:
        row.is_enabled = payload.is_enabled
    record_audit(
        db, actor=user, action="update_config", entity_type="integration",
        entity_id=row.id, detail={"keys": list((payload.config or {}).keys())},
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/{key}/test")
def test_integration(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    """Fire a synthetic event so the customer can confirm the wire is hot."""
    row = db.scalar(select(TenantIntegration).where(TenantIntegration.key == key))
    if row is None:
        raise NotFoundError(f"Integration not installed: {key}")
    try:
        connector = get_integration(key)
    except KeyError:
        raise NotFoundError(f"Unknown integration: {key}")
    return connector.fire_test(row)


# ---- Zapier inbound ------------------------------------------------------

@router.post("/zapier/inbound")
async def zapier_inbound(
    request: Request,
    key: str = Query(..., description="The tenant's Zapier API key"),
    db: Session = Depends(get_db),
):
    """Inbound API for Zaps to call. Authentication is the static API key
    issued at install time; we look it up across every Zapier integration
    row and pick the one whose decrypted token matches.

    Body shape::

        { "action": "create_crm_lead", "data": {...} }
    """
    connector = get_integration("zapier")
    assert isinstance(connector, ZapierIntegration)
    row = connector.find_by_api_key(db, key)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid Zapier API key")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    headers = dict(request.headers)
    from app.core.tenant_context import tenant_scope

    with tenant_scope(row.tenant_id):
        result = connector.handle_inbound(payload, headers, row)
    return result or {"ok": True}


# ---- DocuSign inbound ----------------------------------------------------

@router.post("/docusign/inbound")
async def docusign_inbound(
    request: Request,
    tenant_id: str = Query(..., description="The tenant id the envelope belongs to"),
    db: Session = Depends(get_db),
):
    """DocuSign Connect notification endpoint. DocuSign Connect doesn't
    carry a static API key — instead each Connect listener is configured
    per-account at install time and pings this URL with the tenant id in
    the query string. We re-verify by looking up the install row.

    Body is the simplified Connect JSON payload (``envelopeId`` + ``status``
    + custom fields). Signature verification (HMAC) is delegated to v2.
    """
    row = db.scalar(
        select(TenantIntegration).where(
            TenantIntegration.tenant_id == tenant_id,
            TenantIntegration.key == "docusign",
        )
    ) if False else None
    # Cross-tenant lookup must bypass the auto-filter since this endpoint
    # is unauthenticated.
    from app.core.tenant_context import bypass_tenant_filter, tenant_scope
    with bypass_tenant_filter():
        row = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.key == "docusign",
            )
        )
    if row is None:
        raise HTTPException(status_code=404, detail="DocuSign integration not installed")
    connector = get_integration("docusign")
    assert isinstance(connector, DocuSignIntegration)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    headers = dict(request.headers)
    with tenant_scope(row.tenant_id):
        result = connector.handle_inbound(payload, headers, row)
    return result or {"ok": True}


# ---- GitHub inbound ------------------------------------------------------

@router.post("/github/inbound")
async def github_inbound(
    request: Request,
    tenant_id: str = Query(..., description="The tenant id the repo belongs to"),
    db: Session = Depends(get_db),
):
    """GitHub webhook receiver. Each tenant configures GitHub to POST
    deliveries here with their tenant id in the query string. Webhook
    secret verification is delegated to v2 — for now we accept any
    delivery for a tenant that has the integration installed.
    """
    from app.core.tenant_context import bypass_tenant_filter, tenant_scope
    with bypass_tenant_filter():
        row = db.scalar(
            select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.key == "github",
            )
        )
    if row is None:
        raise HTTPException(status_code=404, detail="GitHub integration not installed")
    connector = get_integration("github")
    assert isinstance(connector, GitHubIntegration)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    headers = dict(request.headers)
    with tenant_scope(row.tenant_id):
        result = connector.handle_inbound(payload, headers, row)
    return result or {"ok": True}
