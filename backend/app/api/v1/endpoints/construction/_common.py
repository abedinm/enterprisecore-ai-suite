"""Shared helpers for every construction sub-router.

Keeps the per-domain routers focused on shape rather than the same role
bundle and 404 helpers re-implemented per file. Closely mirrors the academic
``_common.py`` so the two packages read the same way to anyone scanning the
codebase.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError, PermissionDenied
from app.models.construction.projects import ConstructionProject
from app.models.user import User, UserRole


def _get_or_404(db, model_cls, obj_id: str, label: str):
    obj = db.get(model_cls, obj_id)
    if obj is None:
        raise NotFoundError(f"{label} not found")
    return obj


def _apply_update(obj, data: dict) -> None:
    for key, value in data.items():
        if value is not None:
            setattr(obj, key, value)


def require_any_role(*roles: UserRole) -> Callable:
    """Permit only the listed roles. Raises 403 with a clear message."""

    def _dep(current: User = Depends(get_current_user)) -> User:
        if current.role not in roles:
            raise PermissionDenied(
                "Your role is not permitted to perform this action.",
            )
        return current

    return _dep


# Bundle: Admin and Manager (Project Managers are mapped to UserRole.manager
# in EnterpriseCore — the suite doesn't have a dedicated PM role yet, and
# stretching the role enum here would ripple into auth tests). Reads stay
# open to any authenticated user.
PM_ROLES = (UserRole.admin, UserRole.manager)


def get_project_or_404(db: Session, project_id: str) -> ConstructionProject:
    """Centralised helper — every sub-router needs this exact lookup."""
    return _get_or_404(db, ConstructionProject, project_id, "Construction project")
