"""Tiny shared helpers used by every academic sub-router.

Kept private to the academic package — these aren't general-purpose enough
to live in ``app/api/v1/endpoints/`` directly.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError, PermissionDenied
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
    """Like ``require_roles`` but raises a PermissionDenied with a friendlier
    message and accepts ``Depends(get_current_user)`` so the call site reads
    naturally.
    """

    def _dep(current: User = Depends(get_current_user)) -> User:
        if current.role not in roles:
            raise PermissionDenied(
                "Your role is not permitted to perform this action.",
            )
        return current

    return _dep


# Convenience role bundles — the same combos appear across multiple sub-routers.
STAFF_ROLES = (
    UserRole.admin, UserRole.manager, UserRole.teacher,
    UserRole.registrar, UserRole.dean,
)
TEACHER_OR_ADMIN = (UserRole.admin, UserRole.manager, UserRole.teacher)
REGISTRAR_OR_ADMIN = (UserRole.admin, UserRole.manager, UserRole.registrar, UserRole.dean)
