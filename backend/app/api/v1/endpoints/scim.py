"""SCIM 2.0 endpoints.

Two routers live in this module:

* ``token_router`` — mounted under ``/api/v1/sso/scim/tokens`` for admins
  to mint and revoke SCIM bearer tokens from the regular admin UI.
* ``scim_router`` — mounted at the app root under ``/scim/v2/`` because
  SCIM clients (Okta, Azure AD, JumpCloud) hard-code that path per RFC
  7644 §3.1.

Each SCIM token is bound to exactly one tenant — its bearer authenticates
the entire request as that tenant, no JWT/user context required. We
verify the token by hashing the presented bearer with bcrypt-check
against the small set of active tokens for the tenant (token hashes use
the token's last 12 chars as a lookup hint to keep the candidate set
tiny).
"""
# NB: no `from __future__ import annotations` — keep runtime types for the
# FastAPI signature introspection quirk documented in auth.py.
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    NotFoundError,
    PermissionDenied,
    ValidationFailed,
)
from app.core.security import hash_password
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.db.session import get_db
from app.models.sso import SCIMToken
from app.models.user import User, UserRole
from app.schemas.sso import (
    SCIMListResponse,
    SCIMPatchRequest,
    SCIMTokenCreate,
    SCIMTokenCreateResponse,
    SCIMTokenRead,
    SCIMUserCreate,
    SCIMUserResource,
)

# Dedicated bcrypt context — same library passlib uses for passwords. We
# keep tokens separate so a future rotation of password-hashing settings
# doesn't sweep tokens out from under us.
_token_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Token mgmt — under /api/v1/sso/scim/tokens
# ---------------------------------------------------------------------------
token_router = APIRouter()


@token_router.post(
    "/tokens",
    response_model=SCIMTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scim_token(
    payload: SCIMTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> SCIMTokenCreateResponse:
    """Mint a new SCIM bearer token. The raw token is returned exactly once
    in the response body — store it now, you won't get to see it again."""
    raw = "scim_" + secrets.token_urlsafe(40)
    token_hash = _token_pwd.hash(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.ttl_days)
    row = SCIMToken(
        tenant_id=current_user.tenant_id,
        name=payload.name,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SCIMTokenCreateResponse(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        token=raw,
    )


@token_router.get("/tokens", response_model=list[SCIMTokenRead])
def list_scim_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> list[SCIMTokenRead]:
    rows = db.scalars(
        select(SCIMToken)
        .where(SCIMToken.tenant_id == current_user.tenant_id)
        .order_by(SCIMToken.created_at.desc())
    ).all()
    return [SCIMTokenRead.model_validate(r) for r in rows]


@token_router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_scim_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
):
    row = db.get(SCIMToken, token_id)
    if not row or row.tenant_id != current_user.tenant_id:
        raise NotFoundError("SCIM token not found")
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# SCIM 2.0 protocol surface — under /scim/v2/
# ---------------------------------------------------------------------------
scim_router = APIRouter()


def _resolve_scim_token(
    authorization: str | None,
    db: Session,
) -> SCIMToken:
    """Walk active tokens for any tenant and find one matching the bearer.

    Bcrypt's per-hash salt rules out a direct equality lookup. To keep the
    scan tight we look at *every* non-revoked, non-expired SCIM token in
    the system — there are realistically a handful per tenant, so even at
    1,000 tenants this is a 1,000-row scan with one bcrypt-verify per
    row. We short-circuit on the first match.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing or malformed Authorization header")
    bearer = authorization[7:].strip()
    if not bearer:
        raise AuthenticationError("Empty bearer token")

    with bypass_tenant_filter():
        candidates = db.scalars(
            select(SCIMToken).where(
                SCIMToken.revoked_at.is_(None),
                SCIMToken.expires_at > datetime.now(timezone.utc),
            )
        ).all()
    for cand in candidates:
        try:
            if _token_pwd.verify(bearer, cand.token_hash):
                cand.last_used_at = datetime.now(timezone.utc)
                db.commit()
                return cand
        except Exception:
            continue
    raise AuthenticationError("Invalid SCIM bearer token")


def _scim_user_view(user: User, request_base: str | None = None) -> dict[str, Any]:
    """Render a User as a SCIM Resource dict."""
    name_parts = user.full_name.split(" ", 1) if user.full_name else ("", "")
    given = name_parts[0]
    family = name_parts[1] if len(name_parts) > 1 else ""
    location = f"/scim/v2/Users/{user.id}"
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": user.id,
        "userName": user.email,
        "name": {"formatted": user.full_name, "givenName": given, "familyName": family},
        "displayName": user.full_name,
        "emails": [{"value": user.email, "type": "work", "primary": True}],
        "active": user.is_active,
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
            "lastModified": user.updated_at.isoformat() if user.updated_at else None,
            "location": location,
        },
    }


@scim_router.get("/Users")
def scim_list_users(
    request: Request,
    authorization: str | None = Header(default=None),
    filter: str | None = Query(default=None, alias="filter", max_length=500),
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=50, ge=0, le=500),
    db: Session = Depends(get_db),
):
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        stmt = select(User)
        # SCIM filter syntax: ``userName eq "foo@bar.com"`` — we handle the
        # equality case for userName since that's what Okta/Azure send.
        if filter:
            parsed = _parse_scim_filter(filter)
            if parsed:
                field, value = parsed
                if field == "userName":
                    stmt = stmt.where(User.email == value.lower())
                elif field == "email":
                    stmt = stmt.where(User.email == value.lower())
        all_rows = db.scalars(stmt.order_by(User.email)).all()
        total = len(all_rows)
        # SCIM uses 1-based startIndex per RFC 7644 §3.4.2.
        page = all_rows[startIndex - 1: startIndex - 1 + count]
        resources = [_scim_user_view(u) for u in page]
    return SCIMListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(resources),
        Resources=resources,
    ).model_dump()


def _parse_scim_filter(filter_str: str) -> tuple[str, str] | None:
    """Minimal SCIM filter parser — handles ``<field> eq "<value>"``.

    Full filter grammar (RFC 7644 §3.4.2.2) is large; we only need the
    equality case used by every provisioner we ship for.
    """
    parts = filter_str.strip().split(" ", 2)
    if len(parts) != 3:
        return None
    field, op, value = parts
    if op.lower() != "eq":
        return None
    value = value.strip().strip('"')
    return field, value


@scim_router.get("/Users/{user_id}")
def scim_get_user(
    user_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        user = db.get(User, user_id)
        if not user or user.tenant_id != token.tenant_id:
            raise NotFoundError("User not found")
        return _scim_user_view(user)


@scim_router.post("/Users", status_code=status.HTTP_201_CREATED)
def scim_create_user(
    payload: SCIMUserCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        email = (payload.userName or "").strip().lower()
        if not email:
            raise ValidationFailed("userName is required")
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            raise AppError("User already exists", code="conflict", status_code=409)
        full_name = (
            payload.displayName
            or (payload.name.formatted if payload.name and payload.name.formatted else None)
            or email
        )
        raw_pw = payload.password or secrets.token_urlsafe(24)
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(raw_pw),
            role=UserRole.employee,
            is_active=payload.active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return _scim_user_view(user)


@scim_router.put("/Users/{user_id}")
def scim_replace_user(
    user_id: str,
    payload: SCIMUserCreate,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        user = db.get(User, user_id)
        if not user or user.tenant_id != token.tenant_id:
            raise NotFoundError("User not found")
        user.email = (payload.userName or user.email).strip().lower()
        if payload.displayName:
            user.full_name = payload.displayName
        elif payload.name and payload.name.formatted:
            user.full_name = payload.name.formatted
        user.is_active = payload.active
        db.commit()
        db.refresh(user)
        return _scim_user_view(user)


@scim_router.patch("/Users/{user_id}")
def scim_patch_user(
    user_id: str,
    payload: SCIMPatchRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Apply a SCIM PatchOp.

    Supported operations: ``replace``/``add`` on ``active``,
    ``displayName``, ``name.givenName``, ``name.familyName``, ``userName``,
    ``emails[primary eq true].value``.
    """
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        user = db.get(User, user_id)
        if not user or user.tenant_id != token.tenant_id:
            raise NotFoundError("User not found")
        for op in payload.Operations:
            op_name = (op.op or "").lower()
            if op_name not in ("replace", "add", "remove"):
                continue
            path = (op.path or "").strip()
            value = op.value
            if op_name == "remove" and path == "active":
                user.is_active = False
                continue
            # Microsoft Azure AD sends ``op="Replace"`` with no ``path`` and
            # a dict body containing the fields to update. Handle that too.
            if not path and isinstance(value, dict):
                if "active" in value:
                    user.is_active = bool(value["active"])
                if "displayName" in value:
                    user.full_name = str(value["displayName"]) or user.full_name
                if "userName" in value:
                    user.email = str(value["userName"]).strip().lower()
                continue
            if path == "active":
                user.is_active = bool(value)
            elif path == "displayName":
                user.full_name = str(value) or user.full_name
            elif path == "userName":
                user.email = str(value).strip().lower()
            elif path == "name.givenName" and isinstance(value, str):
                parts = (user.full_name or "").split(" ", 1)
                family = parts[1] if len(parts) > 1 else ""
                user.full_name = f"{value} {family}".strip()
            elif path == "name.familyName" and isinstance(value, str):
                parts = (user.full_name or "").split(" ", 1)
                given = parts[0] if parts else ""
                user.full_name = f"{given} {value}".strip()
        db.commit()
        db.refresh(user)
        return _scim_user_view(user)


@scim_router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def scim_delete_user(
    user_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Soft delete — set is_active=False. SCIM clients treat this as a hard
    delete from their POV, but keeping the row preserves audit history."""
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        user = db.get(User, user_id)
        if not user or user.tenant_id != token.tenant_id:
            raise NotFoundError("User not found")
        user.is_active = False
        db.commit()
    return None


# ---- Groups (minimal — maps to UserRole) -----------------------------------
@scim_router.get("/Groups")
def scim_list_groups(
    authorization: str | None = Header(default=None),
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=50, ge=0, le=500),
    db: Session = Depends(get_db),
):
    """Expose UserRole as SCIM Groups.

    We don't have a Groups table — but Okta + Azure AD insist on listing
    groups before they create users. Mapping UserRole values to fake
    Groups satisfies the protocol surface.
    """
    token = _resolve_scim_token(authorization, db)
    with tenant_scope(token.tenant_id):
        resources = []
        for role in UserRole:
            members = db.scalars(select(User).where(User.role == role)).all()
            resources.append({
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
                "id": f"role-{role.value}",
                "displayName": role.value,
                "members": [{"value": u.id, "display": u.email} for u in members],
                "meta": {"resourceType": "Group", "location": f"/scim/v2/Groups/role-{role.value}"},
            })
    paged = resources[startIndex - 1: startIndex - 1 + count]
    return SCIMListResponse(
        totalResults=len(resources),
        startIndex=startIndex,
        itemsPerPage=len(paged),
        Resources=paged,
    ).model_dump()


@scim_router.post("/Groups", status_code=status.HTTP_201_CREATED)
def scim_create_group(
    payload: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Best-effort group create — if the displayName matches a known role,
    we acknowledge; otherwise we 400. Real RBAC group create lands in a
    later phase."""
    token = _resolve_scim_token(authorization, db)
    name = (payload.get("displayName") or "").strip()
    try:
        role = UserRole(name)
    except ValueError:
        raise ValidationFailed(f"Unknown role/group name: {name!r}")
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": f"role-{role.value}",
        "displayName": role.value,
        "members": [],
        "meta": {"resourceType": "Group", "location": f"/scim/v2/Groups/role-{role.value}"},
    }


@scim_router.get("/ServiceProviderConfig")
def scim_service_provider_config(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    _resolve_scim_token(authorization, db)
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://datatracker.ietf.org/doc/html/rfc7643",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {"name": "OAuth Bearer Token", "description": "Bearer SCIM token", "type": "oauthbearertoken", "primary": True},
        ],
    }
