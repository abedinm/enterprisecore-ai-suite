"""Periodic housekeeping jobs.

Currently:
  * ``cleanup_refresh_tokens`` — delete refresh tokens that are either
    expired or revoked-and-older-than-90-days. Keeps the table from
    bloating with one row per device per login forever.
  * ``cleanup_login_attempts`` — keep only the last 30 days of login-attempt
    audit so the table doesn't grow unbounded.
  * ``cleanup_ai_usage`` — same, 90 days for AI usage records.
  * ``knowledge_ingest_tick`` — drains the Knowledge Hub ingest queue every
    few seconds so uploaded documents move through parse → embed → ready
    without a separate worker process.

Wire via ``start_scheduler`` at app startup; the FastAPI ``lifespan`` should
also call ``run_now_safely`` once so a fresh deployment isn't sitting on
stale data from a prior install.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
from sqlalchemy import delete, or_, select, func

from app.core.config import settings
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


def expire_trials() -> int:
    """Flip tenants whose ``trial_ends_at`` has passed to ``trial_expired``.

    Returns the number of tenants transitioned. Bypasses the tenant filter
    because this job legitimately needs to see every tenant in the install.
    """
    from app.core.tenant_context import bypass_tenant_filter
    from app.models.tenant import Tenant
    from app.services.stripe_service import log_billing_event

    now = datetime.now(timezone.utc)
    transitioned = 0
    with SessionLocal() as db, bypass_tenant_filter():
        tenants = db.scalars(
            select(Tenant).where(
                Tenant.status.in_(("trial", "active")),
                Tenant.trial_ends_at.is_not(None),
                Tenant.trial_ends_at < now,
                Tenant.plan == "evaluation",
            )
        ).all()
        for t in tenants:
            t.status = "trial_expired"
            db.commit()
            try:
                log_billing_event(
                    db, t.id, "trial_expired",
                    metadata={"trial_ended_at": t.trial_ends_at.isoformat()},
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("trial_expired audit failed for {}: {}", t.id, exc)
            transitioned += 1
    if transitioned:
        logger.info("housekeeping: transitioned {} tenants to trial_expired", transitioned)
    return transitioned


def run_all() -> dict[str, int]:
    """Run every cleanup job once. Returns per-job row counts."""
    return {
        "refresh_tokens": cleanup_refresh_tokens(),
        "login_attempts": cleanup_login_attempts(),
        "ai_usage": cleanup_ai_usage(),
        "trials_expired": expire_trials(),
    }


def run_now_safely() -> None:
    """Run all jobs once but swallow errors — startup must not fail
    because a cleanup query couldn't run."""
    try:
        run_all()
    except Exception as e:  # pragma: no cover
        logger.warning("housekeeping startup pass failed: {}", e)


_scheduler: BackgroundScheduler | None = None


# ---------------------------------------------------------------------------
# Leader election — Postgres advisory lock
# ---------------------------------------------------------------------------
# Background scheduler jobs need to run EXACTLY ONCE across all replicas
# of the FastAPI process. In multi-replica SaaS deploys (Render, ECS, K8s)
# every replica boots its own APScheduler; without coordination each daily
# cleanup runs N times, doubling load and producing N audit-log entries.
#
# Strategy:
#   * On Postgres, take a session-level advisory lock keyed on a stable hash
#     of "ec-housekeeping-v1". Only one replica gets it; the rest skip job
#     registration entirely.
#   * On SQLite (single-process by definition) the lock is a no-op — there's
#     only one process so it always "wins".
#   * The lock is released when the SessionLocal closes (we hold a session
#     for the lifetime of the scheduler).
#
# Operators can force-disable leader election with LEADER_ELECTION=off (e.g.
# when running a single replica behind a load balancer and you want every
# replica to share housekeeping). Default is "on".
import os as _os
import hashlib as _hashlib
from sqlalchemy import text as _sa_text

_LEADER_LOCK_ID = int(_hashlib.blake2s(b"ec-housekeeping-v1", digest_size=8).hexdigest(), 16) & ((1 << 63) - 1)
_leader_session = None


def _acquire_leadership() -> bool:
    """Attempt to become the housekeeping leader.

    Returns True if THIS replica owns the lock and should register jobs.
    Returns False if another replica already owns it — the caller should
    skip job registration but still respond to HTTP traffic normally.
    """
    global _leader_session
    if _os.environ.get("LEADER_ELECTION", "on").lower() in ("off", "0", "false"):
        logger.info("housekeeping: leader election disabled, running unconditionally")
        return True
    if settings.db_backend != "postgres":
        # SQLite is single-process; nothing to coordinate.
        return True
    # Hold an open session for the lifetime of the scheduler — releasing
    # the session releases the lock.
    sess = SessionLocal()
    try:
        # pg_try_advisory_lock is non-blocking; if another replica holds
        # it we get False back immediately.
        row = sess.execute(_sa_text("SELECT pg_try_advisory_lock(:k)"), {"k": _LEADER_LOCK_ID}).scalar()
        if not row:
            sess.close()
            logger.info("housekeeping: another replica is the leader, skipping scheduler")
            return False
        _leader_session = sess
        logger.info("housekeeping: acquired leader lock — this replica runs scheduled jobs")
        return True
    except Exception as exc:
        logger.warning("housekeeping: leader election failed ({}); running unconditionally", exc)
        sess.close()
        return True


def _release_leadership() -> None:
    global _leader_session
    if _leader_session is None:
        return
    try:
        _leader_session.execute(_sa_text("SELECT pg_advisory_unlock(:k)"), {"k": _LEADER_LOCK_ID})
        _leader_session.close()
    except Exception:  # pragma: no cover
        pass
    _leader_session = None


def start_scheduler() -> None:
    """Start APScheduler with the daily cleanup job. Idempotent — calling
    twice in the same process is a no-op."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return
    if not _acquire_leadership():
        # Non-leader replicas don't register jobs. They still serve HTTP.
        return
    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    _scheduler.add_job(cleanup_refresh_tokens, "interval", hours=24,
                       id="cleanup_refresh_tokens", coalesce=True, max_instances=1)
    _scheduler.add_job(cleanup_login_attempts, "interval", hours=24,
                       id="cleanup_login_attempts", coalesce=True, max_instances=1)
    _scheduler.add_job(cleanup_ai_usage, "interval", hours=24,
                       id="cleanup_ai_usage", coalesce=True, max_instances=1)
    _scheduler.add_job(expire_trials, "interval", hours=24,
                       id="expire_trials", coalesce=True, max_instances=1)

    # Knowledge Hub ingest queue — short-interval poll so uploaded docs
    # don't sit idle.
    from app.services.ingest_worker import tick as ingest_tick

    poll_seconds = max(2, int(settings.knowledge_ingest_poll_seconds))
    _scheduler.add_job(ingest_tick, "interval", seconds=poll_seconds,
                       id="knowledge_ingest_tick", coalesce=True, max_instances=1)

    # Tenant + business-state Prometheus exporters — refresh every 60s so
    # the Grafana dashboards stay accurate without hammering the DB.
    from app.services.tenant_metrics_collector import collect_tenant_metrics_safely
    _scheduler.add_job(
        collect_tenant_metrics_safely, "interval", seconds=60,
        id="tenant_metrics_collector", coalesce=True, max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "housekeeping: scheduler started — daily jobs + knowledge ingest every {}s + tenant metrics every 60s",
        poll_seconds,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    _release_leadership()
