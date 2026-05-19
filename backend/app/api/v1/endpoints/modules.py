from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.init_db import MODULE_CATALOG
from app.models.user import User

router = APIRouter()


@router.get("")
def module_catalog(_: User = Depends(get_current_user)):
    return {"groups": MODULE_CATALOG}
