from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_current_user
from app.core.cache import cache_response
from app.core.plans import has_feature
from app.db.init_db import MODULE_CATALOG
from app.models.user import User

router = APIRouter()


@router.get("")
@cache_response(ttl=300, namespace="modules:catalog")
def module_catalog(response: Response, _: User = Depends(get_current_user)):
    """Return the module catalog, filtered by the current license plan.

    Each catalog group may carry an optional ``feature`` field that maps to a
    plan feature (see ``app/core/plans.py``). Groups whose feature is not
    enabled by the active license are excluded from the response so the
    frontend doesn't render nav for them. Groups with no ``feature`` field
    are always-on platform modules.
    """
    visible = [
        group for group in MODULE_CATALOG
        if "feature" not in group or has_feature(group["feature"])
    ]
    return {"groups": visible}
