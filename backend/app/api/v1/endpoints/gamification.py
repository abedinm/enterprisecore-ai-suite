"""Gamification API — achievements, streaks, XP, levels.

Endpoints
---------

* ``GET  /gamification/me``               — XP, level, streak summary
* ``GET  /gamification/achievements``     — full catalogue + unlocked flags
* ``POST /gamification/track/{event}``    — record a client-side event
                                             (e.g. command palette opened,
                                             dark mode switched, konami)

The ``/track/{event}`` endpoint is intentionally permissive — any
authenticated user can fire any event key the catalogue knows about.
Server-side awards (first invoice, deal won, etc.) stay protected by the
domain endpoints they hook into.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import gamification as gam

router = APIRouter()


# Map "client-trackable" event keys to the achievement key they unlock.
# Adding a new key here is the single place you need to touch to expose a
# new client-side achievement.
CLIENT_TRACKABLE: dict[str, str] = {
    "command_palette":  "command_palette",
    "dark_mode":        "dark_mode",
    "palette_picker":   "palette_picker",
    "konami":           "konami",
    "seven_clicks":     "seven_clicks",
    "profile_completed":"profile_completed",
}


@router.get("/me")
def my_progress(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    xp = gam.total_xp(db, tenant_id=current.tenant_id, user_id=current.id)
    level = gam.level_for(xp)
    login_streak = gam.get_streak(db, tenant_id=current.tenant_id, user_id=current.id, kind="login")
    return {
        "xp": xp,
        "level": level,
        "streak": {
            "current": login_streak.current if login_streak else 0,
            "best": login_streak.best if login_streak else 0,
            "kind": "login",
        },
    }


@router.get("/achievements")
def list_achievements(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return gam.list_achievements_for(db, tenant_id=current.tenant_id, user_id=current.id)


@router.post("/track/{event}")
def track_event(
    event: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    key = CLIENT_TRACKABLE.get(event)
    if not key:
        return {"unlocked": False, "reason": "unknown_event"}
    row = gam.award(db, tenant_id=current.tenant_id, user_id=current.id, key=key)
    return {
        "unlocked": row is not None,
        "key": key,
    }
