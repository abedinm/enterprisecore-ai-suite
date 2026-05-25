"""Granular RBAC endpoints — custom roles, assignments, effective perms."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.cache import cache_response, invalidate_for_tenant
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.permissions import (
    BUILT_IN_ROLE_PERMISSIONS, PERMISSION_CATALOG, effective_permissions,
)
from app.db.session import get_db
from app.models.rbac import CustomRole, UserRoleAssignment
from app.models.user import User, UserRole
from app.schemas.rbac import (
    BuiltInRoleOut, CustomRoleIn, CustomRoleOut, CustomRoleUpdate,
    EffectivePermissionsOut, PermissionOut, RoleAssignmentIn, RoleAssignmentOut,
)

router = APIRouter()


@router.get("/permissions", response_model=list[PermissionOut])
@cache_response(ttl=3600, namespace="rbac:permissions")
def list_permissions(
    response: Response,
    _: User = Depends(require_roles(UserRole.admin)),
):
    """List the global permission catalog. Admin only — the catalog is
    static, but exposing it broadly would let any user enumerate the
    surface area of the system.

    Cached 1 hour per tenant; the catalog is process-static, so the cache
    is really an aggressive opt-out from the auth+rate-limit pipeline. We
    still key on tenant so a future tenant-specific permission extension
    doesn't leak across boundaries.
    """
    return [
        PermissionOut(key=key, category=cat, description=desc)
        for key, cat, desc in PERMISSION_CATALOG
    ]


@router.get("/roles", response_model=dict)
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """List both built-in roles (with their canonical permission set) and
    the tenant's custom roles. Returned as a dict so the UI can render
    them in separate sections without an extra request."""
    built_ins = [
        BuiltInRoleOut(
            id=role.value,
            name=role.value,
            permission_keys=sorted(BUILT_IN_ROLE_PERMISSIONS.get(role, set())),
        )
        for role in UserRole
    ]
    custom = db.scalars(select(CustomRole).order_by(CustomRole.name)).all()
    return {
        "built_in": [b.model_dump() for b in built_ins],
        "custom": [CustomRoleOut.model_validate(r).model_dump(mode="json") for r in custom],
    }


def _validate_permission_keys(keys: list[str]) -> None:
    valid = {k for k, _, _ in PERMISSION_CATALOG}
    invalid = [k for k in keys if k not in valid]
    if invalid:
        raise ValidationFailed(f"Unknown permission keys: {', '.join(invalid)}")


@router.post("/roles", response_model=CustomRoleOut, status_code=201)
def create_custom_role(
    payload: CustomRoleIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    _validate_permission_keys(payload.permission_keys)
    role = CustomRole(
        name=payload.name,
        description=payload.description,
        permission_keys=payload.permission_keys,
        is_builtin=False,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    # Custom role added — wipe the per-tenant permissions cache so the next
    # /permissions or /roles call reflects the new role.
    invalidate_for_tenant("rbac:permissions")
    return role


@router.patch("/roles/{role_id}", response_model=CustomRoleOut)
def update_custom_role(
    role_id: str,
    payload: CustomRoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    role = db.get(CustomRole, role_id)
    if not role:
        raise NotFoundError("Custom role not found")
    if role.is_builtin:
        raise ValidationFailed("Built-in roles cannot be modified")
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.permission_keys is not None:
        _validate_permission_keys(payload.permission_keys)
        role.permission_keys = payload.permission_keys
    db.commit()
    db.refresh(role)
    invalidate_for_tenant("rbac:permissions")
    return role


@router.delete("/roles/{role_id}", status_code=204)
def delete_custom_role(
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    role = db.get(CustomRole, role_id)
    if not role:
        raise NotFoundError("Custom role not found")
    if role.is_builtin:
        raise ValidationFailed("Built-in roles cannot be deleted")
    db.delete(role)
    db.commit()
    invalidate_for_tenant("rbac:permissions")
    return None


@router.post("/users/{user_id}/roles", response_model=RoleAssignmentOut, status_code=201)
def assign_role_to_user(
    user_id: str,
    payload: RoleAssignmentIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    role = db.get(CustomRole, payload.custom_role_id)
    if not role:
        raise NotFoundError("Custom role not found")
    # Idempotent: don't double-assign.
    existing = db.scalar(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.custom_role_id == payload.custom_role_id,
        )
    )
    if existing:
        return existing
    assignment = UserRoleAssignment(
        user_id=user_id,
        custom_role_id=payload.custom_role_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/users/{user_id}/roles/{role_id}", status_code=204)
def revoke_role_from_user(
    user_id: str,
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    assignment = db.scalar(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.custom_role_id == role_id,
        )
    )
    if not assignment:
        raise NotFoundError("Role assignment not found")
    db.delete(assignment)
    db.commit()
    return None


@router.get(
    "/users/{user_id}/effective-permissions",
    response_model=EffectivePermissionsOut,
)
def user_effective_permissions(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    perms = effective_permissions(user, db)
    assignments = db.scalars(
        select(UserRoleAssignment.custom_role_id)
        .where(UserRoleAssignment.user_id == user_id)
    ).all()
    return EffectivePermissionsOut(
        user_id=user.id,
        built_in_role=user.role.value,
        custom_role_ids=list(assignments),
        permission_keys=sorted(perms),
    )
