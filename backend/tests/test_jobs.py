"""Tests for the background-job system.

Covers both the sync fallback (no REDIS_URL set — what dev/test/small
installs actually run) and the Redis-mode path with a mocked RQ Queue.

The auth + tenant fixtures are shared with the rest of the suite via
conftest.py — the default test tenant is auto-scoped for every test.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.jobs import Job, JobAttempt
from app.services import jobs as jobs_svc


@pytest.fixture(autouse=True)
def _ensure_sync_mode_unless_overridden(monkeypatch):
    """Most tests want the sync path. Tests that exercise Redis mode set
    their own queue override + this fixture's auto-clear runs after."""

    monkeypatch.delenv("REDIS_URL", raising=False)
    jobs_svc.set_queue_override(None)
    jobs_svc.set_redis_connection(None)
    yield
    jobs_svc.set_queue_override(None)
    jobs_svc.set_redis_connection(None)


def _ping(*args, **kwargs):
    """Top-level harmless function used as the queue target.

    It has to be module-level so its dotted path resolves on the worker.
    """

    return {"called_with": list(args), "kwargs": dict(kwargs)}


def _boom(*args, **kwargs):
    """Always-fails target used by the failure test."""

    raise ValueError("intentional test failure")


# ---------------------------------------------------------------------------
# Sync-mode behaviour
# ---------------------------------------------------------------------------

def test_enqueue_sync_mode_runs_immediately(db):
    """No REDIS_URL → callable runs inline, job row reaches completed."""

    handle = jobs_svc.enqueue_or_run(_ping, 1, 2, foo="bar")
    assert handle.mode == "sync"
    assert handle.status == "completed"
    assert handle.result == {"called_with": [1, 2], "kwargs": {"foo": "bar"}}

    row = db.get(Job, handle.job_id)
    assert row is not None
    assert row.status == "completed"
    assert row.attempts == 1
    assert row.completed_at is not None
    assert row.function_name.endswith("_ping")
    # Result excerpt is the str() of the dict, capped at 500 chars.
    assert row.result_excerpt is not None
    assert "called_with" in row.result_excerpt


def test_sync_mode_failure_records_error(db):
    """A raising target → status=failed + last_error populated."""

    handle = jobs_svc.enqueue_or_run(_boom)
    assert handle.mode == "sync"
    assert handle.status == "failed"
    assert handle.error and "intentional" in handle.error

    row = db.get(Job, handle.job_id)
    assert row.status == "failed"
    assert row.last_error and "intentional" in row.last_error
    # An attempt row was written too.
    attempts = list(db.scalars(select(JobAttempt).where(JobAttempt.job_id == row.id)).all())
    assert len(attempts) == 1
    assert attempts[0].status == "failed"
    assert attempts[0].error_message and "intentional" in attempts[0].error_message


def test_job_status_transitions(db):
    """Sync mode goes queued→running→completed (compressed in one call)."""

    handle = jobs_svc.enqueue_or_run(_ping)
    row = db.get(Job, handle.job_id)
    assert row.status == "completed"
    # In sync mode the started_at + completed_at are both set.
    assert row.started_at is not None
    assert row.completed_at is not None


# ---------------------------------------------------------------------------
# Redis-mode behaviour (mocked)
# ---------------------------------------------------------------------------

def test_enqueue_redis_mode_queues_without_executing(db, monkeypatch):
    """Mock the RQ queue: enqueue should hand off, not run inline."""

    fake_queue = MagicMock()
    fake_rq_job = MagicMock()
    fake_rq_job.id = "rq-abc-123"
    fake_queue.enqueue.return_value = fake_rq_job
    jobs_svc.set_queue_override(fake_queue)
    # Sentinel: if the function ran, it'd touch this list.
    side_effects: list = []

    def _target():
        side_effects.append("ran")

    handle = jobs_svc.enqueue_or_run(_target)
    assert handle.mode == "redis"
    assert handle.status == "queued"
    assert side_effects == [], "target must NOT run inline in Redis mode"

    row = db.get(Job, handle.job_id)
    assert row.status == "queued"
    assert row.rq_job_id == "rq-abc-123"
    fake_queue.enqueue.assert_called_once()


def test_cancel_queued_job(db, monkeypatch):
    """A queued (Redis-mode) job can be cancelled — status→cancelled."""

    fake_queue = MagicMock()
    fake_rq_job = MagicMock()
    fake_rq_job.id = "rq-zzz"
    fake_queue.enqueue.return_value = fake_rq_job
    jobs_svc.set_queue_override(fake_queue)

    handle = jobs_svc.enqueue_or_run(_ping, "noop")
    assert handle.status == "queued"

    ok = jobs_svc.cancel_job(handle.job_id)
    assert ok

    db.expire_all()
    row = db.get(Job, handle.job_id)
    assert row.status == "cancelled"
    assert row.completed_at is not None


def test_cancel_completed_job_is_rejected(db):
    handle = jobs_svc.enqueue_or_run(_ping)
    assert handle.status == "completed"
    assert jobs_svc.cancel_job(handle.job_id) is False


def test_retry_failed_job_creates_new_attempt(db):
    """Retrying a failed sync-mode job runs it again + bumps attempts."""

    h1 = jobs_svc.enqueue_or_run(_boom)
    assert h1.status == "failed"

    h2 = jobs_svc.retry_job(h1.job_id)
    assert h2 is not None
    # Retry of a _boom call also fails — but a NEW Job row was created.
    assert h2.job_id != h1.job_id
    assert h2.status == "failed"

    # The original row still has 1 attempt; the new row has its own.
    r1 = db.get(Job, h1.job_id)
    r2 = db.get(Job, h2.job_id)
    assert r1.attempts == 1
    assert r2.attempts == 1
    assert r2.function_name == r1.function_name


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

def test_cross_tenant_jobs_not_visible(make_tenant, session_factory):
    """Tenant A enqueues a job; tenant B cannot see it via list_jobs."""

    tenant_a, _user_a, _tok_a = make_tenant("jobs-a")
    tenant_b, _user_b, _tok_b = make_tenant("jobs-b")

    with tenant_scope(tenant_a.id):
        h = jobs_svc.enqueue_or_run(_ping, "a-only")

    # Look from tenant B's scope.
    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = jobs_svc.list_jobs(s)
        assert all(r.id != h.job_id for r in rows), (
            "tenant B should not see tenant A's job"
        )

    # And from tenant A's scope it IS visible.
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = jobs_svc.list_jobs(s)
        assert any(r.id == h.job_id for r in rows)


# ---------------------------------------------------------------------------
# Endpoint surface
# ---------------------------------------------------------------------------

def test_list_jobs_endpoint(client, auth_headers, db):
    jobs_svc.enqueue_or_run(_ping, "listed")
    r = client.get("/api/v1/jobs", headers=auth_headers)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert isinstance(payload, list)
    assert any(j["function_name"].endswith("_ping") for j in payload)


def test_get_job_detail_with_attempts(client, auth_headers):
    h = jobs_svc.enqueue_or_run(_ping, "detail")
    r = client.get(f"/api/v1/jobs/{h.job_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == h.job_id
    assert body["status"] == "completed"
    assert isinstance(body["attempts_history"], list)
    assert len(body["attempts_history"]) == 1


def test_job_stats_endpoint(client, auth_headers):
    jobs_svc.enqueue_or_run(_ping, "stats-1")
    r = client.get("/api/v1/jobs/stats", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("queued", "running", "completed_today", "failed_today", "total"):
        assert key in body
    assert body["completed_today"] >= 1


def test_retry_endpoint(client, auth_headers):
    h = jobs_svc.enqueue_or_run(_boom)
    r = client.post(f"/api/v1/jobs/{h.job_id}/retry", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] and body["job_id"] != h.job_id


def test_cancel_endpoint_on_completed_rejected(client, auth_headers):
    h = jobs_svc.enqueue_or_run(_ping)
    r = client.post(f"/api/v1/jobs/{h.job_id}/cancel", headers=auth_headers)
    assert r.status_code == 400
