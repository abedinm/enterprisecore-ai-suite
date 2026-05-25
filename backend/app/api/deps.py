"""FastAPI dependency helpers."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDenied
from app.core.i18n import get_request_locale as _resolve_locale, translate
from app.core.plans import has_feature
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole

# auto_error=False: we fall through to the cookie if no Bearer header is present
# instead of raising 401 immediately.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_request_locale(request: Request) -> str:
    """Re-export of the i18n locale resolver as a FastAPI dependency.

    Endpoints that need to localize responses can declare::

        locale: str = Depends(get_request_locale)

    See :func:`app.core.i18n.get_request_locale` for the resolution order.
    """
    return _resolve_locale(request)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> User:
    """Accept auth token from either:
    - ``Authorization: Bearer <token>`` header (API / SDK / test clients), or
    - httpOnly cookie set by the login endpoint. Reads the modern
      ``__Host-access_token`` name first (used in production) and falls back to
      the legacy ``access_token`` for dev / older sessions.
    Bearer header takes priority so existing API tests continue working unchanged.
    """
    effective_token = token
    if not effective_token and request is not None:
        effective_token = (
            request.cookies.get("__Host-access_token")
            or request.cookies.get("access_token")
        )
    if not effective_token:
        raise AuthenticationError("Not authenticated")
    payload = decode_token(effective_token)
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise AuthenticationError("User account is inactive or does not exist")
    return user


def require_roles(*roles: UserRole, permission_keys: tuple[str, ...] | list[str] | None = None) -> Callable:
    """Allow access if the user's built-in role is in ``roles`` OR they hold
    any of ``permission_keys`` (granular RBAC, see :mod:`app.core.permissions`).

    The keyword arg is opt-in; existing call sites that just pass roles
    keep working unchanged. New endpoints can pass both to mean "admins
    by default plus anyone the tenant explicitly grants this permission".
    """
    keys = tuple(permission_keys or ())

    def _dep(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role in roles:
            return current_user
        if keys:
            # Defer the permission lookup until we actually need it so
            # the role short-circuit stays free.
            from sqlalchemy.orm import Session
            from app.core.permissions import has_permission
            from app.db.session import SessionLocal

            with SessionLocal() as db:  # type: Session
                for key in keys:
                    if has_permission(current_user, key, db):
                        return current_user
        raise PermissionDenied("You do not have permission to perform this action")

    return _dep


def require_plan_feature(feature: str) -> Callable:
    """Block requests when the current license plan does not include ``feature``.

    Used to gate SKU-restricted modules (e.g. ``academic`` only under +EDU).
    Combine with ``require_roles(...)`` when both a tier and a role are needed.
    """
    def _dep(request: Request = None) -> None:  # type: ignore[assignment]
        if not has_feature(feature):
            locale = _resolve_locale(request) if request is not None else "en"
            raise PermissionDenied(
                translate("errors.feature_unavailable", locale, feature=feature)
            )

    return _dep
