"""Periodic housekeeping jobs.

Currently:
  * ``cleanup_refresh_tokens`` — delete refresh tokens that are either
    expired or revoked-and-older-than-90-days. Keeps the table from
    bloating with one row per device per login forever.
  * ``cleanup_login_attempts`` — keep only the last 30 days of login-attempt
    audit so the table doesn't grow unbounded.
  * ``cleanup_ai_usage`` — same, 90 days for AI usage records.

Wire via ``start_scheduler`` at app startup; the FastAPI ``lifespan`` should
also call ``run_now_safely`` once so a fresh deployment isn't sitting on
stale data from a prior install.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
from sqlalchemy import delete, or_, select, func

from app.db.session import SessionLocal
from app.models.ai import AiUsageRecord
from app.models.security import LoginAttempt
from app.models.user import RefreshToken


# Retention windows
REFRESH_REVOKED_RETENTION = timedelta(days=90)
LOGIN_ATTEMPT_RETENTION = timedelta(days=30)
AI_USAGE_RETENTION = timedelta(days=90)


def cleanup_refresh_tokens() -> int:
    """Delete expired refresh tokens and old revoked ones. Returns the
    number of rows removed."""
    now = datetime.now(timezone.utc)
    revoked_cutoff = now - REFRESH_REVOKED_RETENTION
    with SessionLocal() as db:
        stmt = delete(RefreshToken).where(
            or_(
                RefreshToken.expires_at < now,
                (RefreshToken.revoked_at.is_not(None)) & (RefreshToken.revoked_at < revoked_cutoff),
            )
        )
        result = db.execute(stmt)
        db.commit()
        rows = result.rowcount or 0
    if rows:
        logger.info("housekeeping: removed {} stale refresh tokens", rows)
    return rows


def cleanup_login_attempts() -> int:
    cutoff = datetime.now(timezone.utc) - LOGIN_ATTEMPT_RETENTION
    with SessionLocal() as db:
        result = db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
        db.commit()
        rows = result.rowcount or 0
    if rows:
        logger.info("housekeeping: removed {} stale login-attempt rows", rows)
    return rows


def cleanup_ai_usage() -> int:
    cutoff = datetime.now(timezone.utc) - AI_USAGE_RETENTION
    with SessionLocal() as db:
        result = db.execute(delete(AiUsageRecord).where(AiUsageRecord.occurred_at < cutoff))
        db.commit()
        rows = result.rowcount or 0
    if rows:
        logger.info("housekeeping: removed {} stale ai_usage rows", rows)
    return rows


def run_all() -> dict[str, int]:
    """Run every cleanup job once. Returns per-job row counts."""
    return {
        "refresh_tokens": cleanup_refresh_tokens(),
        "login_attempts": cleanup_login_attempts(),
        "ai_usage": cleanup_ai_usage(),
    }


def run_now_safely() -> None:
    """Run all jobs once but swallow errors — startup must not fail
    because a cleanup query couldn't run."""
    try:
        run_all()
    except Exception as e:  # pragma: no cover
        logger.warning("housekeeping startup pass failed: {}", e)


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """Start APScheduler with the daily cleanup job. Idempotent — calling
    twice in the same process is a no-op."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    _scheduler.add_job(cleanup_refresh_tokens, "interval", hours=24,
                       id="cleanup_refresh_tokens", coalesce=True, max_instances=1)
    _scheduler.add_job(cleanup_login_attempts, "interval", hours=24,
                       id="cleanup_login_attempts", coalesce=True, max_instances=1)
    _scheduler.add_job(cleanup_ai_usage, "interval", hours=24,
                       id="cleanup_ai_usage", coalesce=True, max_instances=1)
    _scheduler.start()
    logger.info("housekeeping: scheduler started — 3 daily jobs")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
