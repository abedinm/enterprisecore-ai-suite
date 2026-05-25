"""SSE jobs channel — auth, content type, per-user isolation."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.sse import emit_job_event, _subscribers
from app.services.event_bus import publish_event, reset_subscribers


@pytest.fixture(autouse=True)
def _wipe():
    reset_subscribers()
    yield
    reset_subscribers()


def test_sse_jobs_requires_auth(client: TestClient):
    resp = client.get("/api/v1/sse/jobs")
    assert resp.status_code == 401


def test_sse_jobs_returns_event_stream(client: TestClient, auth_headers):
    # Use stream=True so we can read the first event without consuming
    # the whole infinite generator.
    with client.stream("GET", "/api/v1/sse/jobs", headers=auth_headers) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        first_chunk = b""
        for chunk in r.iter_bytes():
            first_chunk += chunk
            if b"hello" in first_chunk:
                break
        assert b"event: hello" in first_chunk


def test_emit_job_event_is_silent_for_unsubscribed_user():
    # No subscribers registered — must not raise.
    emit_job_event("nobody-here", "jobs.completed", {"x": 1})
    assert "nobody-here" not in _subscribers
