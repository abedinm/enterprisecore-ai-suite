"""License-status + plan-features + remote-activation endpoints.

Combines the legacy offline-HMAC license check with the new remote
license-server flow (EC-XXXX-XXXX-XXXX-XXXX keys verified against
ec-license-server.fly.dev with a 7-day offline cache).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from app.api.deps import get_current_user, require_roles
from app.core import remote_license
from app.core.cache import cache_response
from app.core.config import settings
from app.core.license_key import verify_license
from app.core.plans import enabled_features, resolve_plan
from app.models.user import User, UserRole

router = APIRouter()


@router.get("/status")
def license_status(_: User = Depends(get_current_user)) -> dict:
    """Return both legacy (offline HMAC) and remote (license-server) state.

    Always 200 — the frontend uses this to show the appropriate banner/badge,
    not to reject the request.
    """
    return {
        "remote": remote_license.verify_remote().to_dict(),
        "legacy": verify_license().to_dict(),
        "configured_key_preview": _redact(settings.license_key),
        "license_api_url": settings.license_api_url,
    }


@router.get("/features")
@cache_response(ttl=300, namespace="license:features")
def license_features(response: Response, _: User = Depends(get_current_user)) -> dict:
    """Return the resolved plan + the set of features it unlocks.

    Used by the frontend on boot to decide which nav items / pages to render.
    Cached 5 min per tenant; ``invalidate_for_tenant("license:features")``
    fires from the billing webhook + activate/deactivate handlers below
    so a plan change shows up immediately.
    """
    return {
        "plan": resolve_plan().value,
        "features": sorted(enabled_features()),
    }


@router.post("/activate")
def activate(
    key: str = Body(..., embed=True, min_length=8),
    _user: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    """Persist a new key and verify it against the license server.

    Writes to the in-memory settings object; the Electron wrapper is
    responsible for persisting the key to user-data so subsequent launches
    pick it up from env.
    """
    settings.license_key = key.strip()                                  # type: ignore[misc]
    status = remote_license.verify_remote(key=key)
    if not status.valid:
        raise HTTPException(status_code=400, detail=status.to_dict())
    # Plan may have changed — wipe the cached feature set for this tenant
    # so the next /features call reflects the new plan immediately.
    from app.core.cache import invalidate_for_tenant
    invalidate_for_tenant("license:features")
    invalidate_for_tenant("modules:catalog")
    return status.to_dict()


@router.post("/deactivate")
def deactivate(_user: User = Depends(require_roles(UserRole.admin))) -> dict:
    """Free this machine's activation slot. Used during uninstall or
    when moving to a new computer."""
    return {"deactivated": remote_license.deactivate_remote()}


@router.post("/refresh")
def refresh(_: User = Depends(get_current_user)) -> dict:
    """Force a remote re-check, bypassing the cache window."""
    return remote_license.verify_remote().to_dict()


def _redact(key: str) -> str:
    key = (key or "").strip()
    if len(key) <= 8:
        return "****" if key else ""
    return f"{key[:4]}…{key[-4:]}"
