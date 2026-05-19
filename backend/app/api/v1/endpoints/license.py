"""License-status endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.license_key import verify_license
from app.models.user import User

router = APIRouter()


@router.get("/status")
def license_status(_: User = Depends(get_current_user)) -> dict:
    """Return the current license verification result. Always 200 — never
    rejects requests based on license state; the front-end uses this to show
    the appropriate banner/badge."""
    return verify_license().to_dict()
