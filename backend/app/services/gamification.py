"""Gamification service — awards achievements and tracks streaks.

Call points
-----------

* :func:`award` is the only writer. It's idempotent on
  ``(tenant_id, user_id, achievement_key)`` so re-firing a hook never
  duplicates.
* :func:`record_streak_event` is called when an action that should
  contribute to a streak happens (login success, invoice send, etc.).
* :func:`seed_catalogue` runs once at app startup to populate the
  achievements table with the static list below. Safe to re-run.

The intention: business endpoints stay clean. They emit a domain event
(``invoice.sent``, ``deal.won``, ``user.login``) and the gamification
subscriber decides what — if anything — to unlock. This keeps
gamification fully decoupled; you can rip it out by un-subscribing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.gamification import Achievement, UserAchievement, UserStreak


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Spec:
    key: str
    label: str
    description: str
    icon: str = "Trophy"
    color: str = "6366f1"
    xp: int = 10
    tier: str = "common"          # common | rare | epic | legendary
    is_admin_only: bool = False
    is_secret: bool = False


SEED_ACHIEVEMENTS: list[_Spec] = [
    # --- Getting started ----------------------------------------------------
    _Spec("welcome",            "Welcome aboard",
          "Created your account and signed in for the first time.",
          icon="Sparkles", color="6366f1", xp=5, tier="common"),
    _Spec("first_login",        "Hello again",
          "Signed in. Easy XP — but the first of many.",
          icon="LogIn", color="6366f1", xp=5, tier="common"),
    _Spec("profile_completed",  "Looking sharp",
          "Filled out your profile — name, avatar, locale.",
          icon="User", color="22d3ee", xp=10, tier="common"),
    _Spec("mfa_enabled",        "Locked tight",
          "Turned on multi-factor authentication.",
          icon="ShieldCheck", color="10b981", xp=25, tier="rare"),

    # --- Finance ------------------------------------------------------------
    _Spec("first_customer",     "Open for business",
          "Added your first customer.",
          icon="Users", color="3b82f6", xp=10),
    _Spec("first_invoice",      "First invoice sent",
          "You sent an invoice. Real money is on the way.",
          icon="FileText", color="3b82f6", xp=15, tier="rare"),
    _Spec("ten_invoices",       "Invoice machine",
          "Sent ten invoices. The cadence is building.",
          icon="FileStack", color="3b82f6", xp=30, tier="rare"),
    _Spec("hundred_invoices",   "Invoice virtuoso",
          "Sent one hundred invoices. That's a real business.",
          icon="Award", color="f59e0b", xp=100, tier="epic"),
    _Spec("first_payment",      "Cha-ching",
          "Received your first payment.",
          icon="CircleDollarSign", color="10b981", xp=20, tier="rare"),

    # --- CRM ----------------------------------------------------------------
    _Spec("first_lead",         "First lead",
          "Added your first lead.",
          icon="UserPlus", color="6366f1", xp=10),
    _Spec("first_deal_won",     "Closed won",
          "Marked a deal as won. The first one feels great.",
          icon="Trophy", color="f59e0b", xp=25, tier="rare"),
    _Spec("ten_deals_won",      "Closer",
          "Closed ten deals.",
          icon="Crown", color="f59e0b", xp=60, tier="epic"),

    # --- HR -----------------------------------------------------------------
    _Spec("first_employee",     "Team of one",
          "Added your first employee record.",
          icon="Users", color="6366f1", xp=10),
    _Spec("first_payroll",      "Payroll run",
          "Completed your first payroll.",
          icon="ReceiptText", color="3b82f6", xp=30, tier="rare"),

    # --- Streaks ------------------------------------------------------------
    _Spec("login_streak_7",     "Daily rhythm",
          "Signed in seven days in a row.",
          icon="Flame", color="f97316", xp=20, tier="rare"),
    _Spec("login_streak_30",    "Unstoppable",
          "Signed in thirty days in a row.",
          icon="Flame", color="ef4444", xp=80, tier="epic"),
    _Spec("login_streak_100",   "Centurion",
          "Signed in one hundred days in a row. Take a break — but don't break the streak.",
          icon="Flame", color="d946ef", xp=300, tier="legendary"),

    # --- Power user --------------------------------------------------------
    _Spec("command_palette",    "Speed of thought",
          "Used the Cmd+K command palette.",
          icon="Command", color="6366f1", xp=10),
    _Spec("dark_mode",          "Lights out",
          "Switched to dark mode.",
          icon="Moon", color="6366f1", xp=5),
    _Spec("palette_picker",     "Style icon",
          "Tried a new colour palette.",
          icon="Palette", color="ec4899", xp=10),

    # --- Admin / Security --------------------------------------------------
    _Spec("sso_configured",     "Identity wired",
          "Connected an SSO identity provider.",
          icon="KeyRound", color="10b981", xp=40, tier="rare", is_admin_only=True),
    _Spec("api_key_minted",     "Built to integrate",
          "Generated your first API key.",
          icon="Plug", color="6366f1", xp=15, tier="rare", is_admin_only=True),
    _Spec("backup_taken",       "Belt and braces",
          "Ran your first backup.",
          icon="Database", color="10b981", xp=20, tier="rare", is_admin_only=True),

    # --- Secret eggs -------------------------------------------------------
    _Spec("konami",             "Up, up, down, down…",
          "You found the Konami code.",
          icon="Gamepad2", color="d946ef", xp=42, tier="legendary", is_secret=True),
    _Spec("seven_clicks",       "Persistent",
          "Clicked the logo seven times.",
          icon="MousePointerClick", color="d946ef", xp=15, tier="rare", is_secret=True),
    _Spec("midnight_user",      "Burning the midnight oil",
          "Signed in between midnight and 4 AM.",
          icon="Moon", color="6366f1", xp=20, tier="rare", is_secret=True),
]


def seed_catalogue(db: Session) -> int:
    """Idempotently upsert every achievement in :data:`SEED_ACHIEVEMENTS`.

    Returns the number of new rows inserted (existing rows aren't touched
    so admins can rename labels in-DB if they want).
    """
    existing = {row.key for row in db.scalars(select(Achievement)).all()}
    inserted = 0
    for spec in SEED_ACHIEVEMENTS:
        if spec.key in existing:
            continue
        db.add(Achievement(
            key=spec.key, label=spec.label, description=spec.description,
            icon=spec.icon, color=spec.color, xp=spec.xp, tier=spec.tier,
            is_admin_only=spec.is_admin_only, is_secret=spec.is_secret,
        ))
        inserted += 1
    if inserted:
        db.commit()
        logger.info("gamification: seeded {} new achievements", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Awarding
# ---------------------------------------------------------------------------

def award(db: Session, *, tenant_id: str, user_id: str, key: str) -> UserAchievement | None:
    """Award *key* to (tenant_id, user_id). Returns the new row or None if
    already awarded. Idempotent.

    Implementation note: the insert runs in a SAVEPOINT (``db.begin_nested()``)
    so the IntegrityError on duplicates rolls back ONLY the achievement insert,
    not whatever else the caller is doing in the same session. Without this,
    the rollback would wipe out e.g. a RefreshToken row added by the caller
    on the same login flow.
    """
    # Pre-check is cheap and avoids hitting the unique constraint at all in
    # the common "already awarded" case.
    existing = db.scalar(
        select(UserAchievement).where(
            UserAchievement.tenant_id == tenant_id,
            UserAchievement.user_id == user_id,
            UserAchievement.achievement_key == key,
        )
    )
    if existing is not None:
        return None

    row = UserAchievement(
        tenant_id=tenant_id,
        user_id=user_id,
        achievement_key=key,
        unlocked_at=datetime.now(timezone.utc),
    )
    sp = db.begin_nested()
    try:
        db.add(row)
        sp.commit()
    except IntegrityError:
        sp.rollback()
        return None
    # Surface as a notification so the SPA can render the celebration.
    try:
        from app.models.user import Notification
        spec = next((s for s in SEED_ACHIEVEMENTS if s.key == key), None)
        label = spec.label if spec else key
        sp_n = db.begin_nested()
        try:
            db.add(Notification(
                user_id=user_id,
                title="Achievement unlocked",
                body=label,
                level="success",
                link="/settings?tab=achievements",
            ))
            sp_n.commit()
        except Exception:  # pragma: no cover
            sp_n.rollback()
    except Exception as exc:  # pragma: no cover
        logger.warning("achievement notify failed: {}", exc)
    return row


def has_achievement(db: Session, *, tenant_id: str, user_id: str, key: str) -> bool:
    return db.scalar(
        select(UserAchievement.id).where(
            UserAchievement.tenant_id == tenant_id,
            UserAchievement.user_id == user_id,
            UserAchievement.achievement_key == key,
        )
    ) is not None


def total_xp(db: Session, *, tenant_id: str, user_id: str) -> int:
    """Sum of XP across all unlocks for this user. Cheap query, indexed."""
    rows = db.scalars(
        select(UserAchievement.achievement_key).where(
            UserAchievement.tenant_id == tenant_id,
            UserAchievement.user_id == user_id,
        )
    ).all()
    if not rows:
        return 0
    catalogue = {a.key: a.xp for a in db.scalars(select(Achievement)).all()}
    return sum(catalogue.get(k, 0) for k in rows)


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------
# Classic RPG-style curve: each level needs more XP than the previous.
#   level N requires 50 * N * (N + 1) / 2 XP cumulative.
# Levels 1–10:  L1=50, L2=150, L3=300, L4=500, L5=750, L6=1050…
# We cap at 50 (≈ 63k XP) so power users never hit a ceiling.

def level_for(xp: int) -> dict:
    """Compute (level, progress_to_next, xp_for_current_level)."""
    if xp <= 0:
        return {"level": 1, "xp": 0, "next_threshold": 50, "progress": 0.0}
    level = 1
    while level < 50 and xp >= _level_threshold(level + 1):
        level += 1
    cur_t = _level_threshold(level)
    next_t = _level_threshold(level + 1)
    progress = 0.0 if next_t == cur_t else (xp - cur_t) / (next_t - cur_t)
    return {
        "level": level,
        "xp": xp,
        "current_threshold": cur_t,
        "next_threshold": next_t,
        "progress": max(0.0, min(1.0, progress)),
    }


def _level_threshold(level: int) -> int:
    if level <= 1:
        return 0
    return 50 * level * (level - 1) // 2


# ---------------------------------------------------------------------------
# Streaks
# ---------------------------------------------------------------------------

def record_streak_event(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    kind: str,
    on_date: date | None = None,
) -> UserStreak:
    """Increment *kind*'s streak for the user. ``on_date`` defaults to today.

    Logic:
      * If the user already logged this kind for ``on_date`` → no-op.
      * If their last event was *yesterday* → current += 1.
      * If their last event was any earlier date → current resets to 1.
      * If a new record is set, ``best`` is bumped.

    Also auto-unlocks streak-milestone achievements (7/30/100 days).
    """
    day = on_date or date.today()
    streak = db.scalar(
        select(UserStreak).where(
            UserStreak.tenant_id == tenant_id,
            UserStreak.user_id == user_id,
            UserStreak.kind == kind,
        )
    )
    sp = db.begin_nested()
    try:
        if streak is None:
            streak = UserStreak(
                tenant_id=tenant_id, user_id=user_id, kind=kind,
                current=1, best=1, last_event_on=day,
            )
            db.add(streak)
        elif streak.last_event_on == day:
            sp.commit()
            return streak  # Same-day repeat, no change.
        elif streak.last_event_on == day - timedelta(days=1):
            streak.current = streak.current + 1
            streak.best = max(streak.best, streak.current)
            streak.last_event_on = day
        else:
            streak.current = 1
            streak.best = max(streak.best, 1)
            streak.last_event_on = day
        sp.commit()
    except Exception:  # pragma: no cover
        sp.rollback()
        return streak  # leave caller's outer tx intact
    # Don't db.commit() here — let the caller's outer tx handle the durable
    # commit. ``begin_nested`` releases the savepoint, the row is now visible
    # within the outer transaction.

    if kind == "login":
        for milestone, key in [(7, "login_streak_7"), (30, "login_streak_30"), (100, "login_streak_100")]:
            if streak.current >= milestone:
                award(db, tenant_id=tenant_id, user_id=user_id, key=key)
    return streak


def get_streak(db: Session, *, tenant_id: str, user_id: str, kind: str) -> UserStreak | None:
    return db.scalar(
        select(UserStreak).where(
            UserStreak.tenant_id == tenant_id,
            UserStreak.user_id == user_id,
            UserStreak.kind == kind,
        )
    )


def list_achievements_for(db: Session, *, tenant_id: str, user_id: str) -> list[dict]:
    """Return every achievement in the catalogue with an "unlocked" flag."""
    catalogue = db.scalars(select(Achievement)).all()
    earned = {
        r.achievement_key: r.unlocked_at
        for r in db.scalars(
            select(UserAchievement).where(
                UserAchievement.tenant_id == tenant_id,
                UserAchievement.user_id == user_id,
            )
        ).all()
    }
    out = []
    for a in catalogue:
        if a.is_secret and a.key not in earned:
            # Hide secret achievements until earned.
            continue
        out.append({
            "key": a.key,
            "label": a.label,
            "description": a.description,
            "icon": a.icon,
            "color": a.color,
            "xp": a.xp,
            "tier": a.tier,
            "unlocked": a.key in earned,
            "unlocked_at": earned[a.key].isoformat() if a.key in earned else None,
        })
    # Order: legendary > epic > rare > common; within tier, unlocked first.
    tier_order = {"legendary": 0, "epic": 1, "rare": 2, "common": 3}
    out.sort(key=lambda x: (tier_order.get(x["tier"], 9), not x["unlocked"], x["label"]))
    return out
