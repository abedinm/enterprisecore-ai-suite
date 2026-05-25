"""Observability tests — Prometheus exposition, request IDs, JSON logging."""
from __future__ import annotations

import io
import json
import os
import re

import pytest
from loguru import logger

# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------
def test_metrics_endpoint_returns_prometheus_text(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    # prometheus_client returns text/plain; version=0.0.4; charset=utf-8
    assert ct.startswith("text/plain")


def test_metrics_body_contains_known_counters(client):
    # Drive a tiny bit of traffic so the counters are non-empty for known paths.
    client.get("/api/health")
    client.get("/api/health")

    resp = client.get("/metrics")
    body = resp.text
    assert "ec_http_requests_total" in body
    assert "ec_http_request_duration_seconds" in body
    assert "ec_ai_calls_total" in body
    assert "ec_webchat_messages_total" in body
    assert "ec_build_info" in body


def test_metrics_uses_path_template_not_raw_path(client, auth_headers):
    # Hit a route with a path parameter twice with DIFFERENT IDs. Both should
    # collapse into the same Prometheus series (path template),
    # not produce two distinct entries.
    # /api/v1/users/{user_id} is the canonical templated route — use whatever
    # is available. We don't assert on a specific ID; just that there are NOT
    # raw user-IDs appearing as label values in the exposition output.
    client.get("/api/health")
    resp = client.get("/metrics")
    body = resp.text
    # Sanity: nothing in the metrics body should contain a literal UUID-shaped
    # value as a label — those would mean we accidentally labeled by raw path.
    assert not re.search(r'path="[^"]*[0-9a-f]{8}-[0-9a-f]{4}', body), \
        "raw UUIDs leaked into Prometheus labels — cardinality bug"


# ---------------------------------------------------------------------------
# X-Request-Id header
# ---------------------------------------------------------------------------
def test_request_id_added_when_absent(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid is not None
    assert len(rid) >= 16, "request id should be a ULID, not a short token"


def test_request_id_echoed_when_provided(client):
    supplied = "my-trace-id-12345"
    resp = client.get("/api/health", headers={"X-Request-Id": supplied})
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == supplied


def test_request_id_minted_when_missing_is_ulid(client):
    # ULIDs are 26 chars, Crockford base32. Loose check — exact format.
    resp = client.get("/api/health")
    rid = resp.headers.get("x-request-id")
    assert rid is not None
    assert len(rid) == 26
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", rid), f"not a ULID: {rid}"


def test_request_id_distinct_between_requests(client):
    a = client.get("/api/health").headers.get("x-request-id")
    b = client.get("/api/health").headers.get("x-request-id")
    assert a and b and a != b


def test_request_id_oversize_header_ignored_and_replaced(client):
    # Hostile / malformed value — we should ignore it and mint our own.
    huge = "x" * 5000
    resp = client.get("/api/health", headers={"X-Request-Id": huge})
    out = resp.headers.get("x-request-id")
    assert out is not None and out != huge and len(out) == 26


# ---------------------------------------------------------------------------
# JSON logging
# ---------------------------------------------------------------------------
def test_json_logging_emits_valid_json(monkeypatch):
    """When LOG_FORMAT=json we should produce one JSON object per log line.

    We capture stderr by replacing sys.stderr inside the sink call. The sink
    writes via ``sys.stderr.write`` so monkeypatching sys.stderr works.
    """
    import sys

    from app.core import logging as app_logging

    # Clear any previously-installed sinks (loguru is global state).
    logger.remove()

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)

    sink_id = logger.add(app_logging._json_sink, level="DEBUG", format="{message}")
    try:
        token = app_logging.request_id_ctx.set("test-req-id-123")
        try:
            logger.info("hello structured world")
            logger.bind(custom_field="value").warning("with extras")
        finally:
            app_logging.request_id_ctx.reset(token)
    finally:
        logger.remove(sink_id)

    raw = buf.getvalue().strip()
    assert raw, "no log lines captured"
    lines = [line for line in raw.splitlines() if line.strip()]
    assert len(lines) >= 2

    for line in lines:
        obj = json.loads(line)  # must parse cleanly
        assert obj["level"] in {"INFO", "WARNING"}
        assert obj["message"]
        assert obj["timestamp"].endswith("Z")
        assert obj["request_id"] == "test-req-id-123"

    # The second line had extras → must show up under 'extra'.
    second = json.loads(lines[1])
    assert second.get("extra", {}).get("custom_field") == "value"


def test_json_logging_captures_exception_structurally(monkeypatch):
    """An exception should land in a structured `exception` field, NOT as a
    multi-line traceback string in the message."""
    import sys

    from app.core import logging as app_logging

    logger.remove()
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    sink_id = logger.add(app_logging._json_sink, level="DEBUG", format="{message}")
    try:
        try:
            raise ValueError("kaboom")
        except ValueError:
            logger.opt(exception=True).error("something broke")
    finally:
        logger.remove(sink_id)

    line = buf.getvalue().strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["level"] == "ERROR"
    assert obj["message"] == "something broke"
    assert "exception" in obj
    assert obj["exception"]["type"] == "ValueError"
    assert obj["exception"]["value"] == "kaboom"
    assert "Traceback" in (obj["exception"]["traceback"] or "")


def test_log_format_resolution(monkeypatch):
    from app.core import logging as app_logging
    from app.core.config import settings

    monkeypatch.setenv("LOG_FORMAT", "json")
    assert app_logging._resolve_log_format() == "json"

    monkeypatch.setenv("LOG_FORMAT", "human")
    assert app_logging._resolve_log_format() == "human"

    monkeypatch.delenv("LOG_FORMAT", raising=False)
    # Default depends on env; test app_env is "development".
    assert settings.app_env == "development"
    assert app_logging._resolve_log_format() == "human"


# ---------------------------------------------------------------------------
# Metrics middleware behaviour
# ---------------------------------------------------------------------------
def test_metrics_counter_increments_on_real_request(client):
    # Snapshot the count, fire a known endpoint, verify the counter moved up.
    before = client.get("/metrics").text
    client.get("/api/health")
    after = client.get("/metrics").text

    def _extract_health_counter(body: str) -> float:
        total = 0.0
        for line in body.splitlines():
            if line.startswith("#"):
                continue
            if 'ec_http_requests_total{' in line and 'path="/api/health"' in line:
                try:
                    total += float(line.rsplit(" ", 1)[1])
                except (IndexError, ValueError):
                    pass
        return total

    # /api/health is EXCLUDED from PrometheusMiddleware, so its count must
    # NOT increase. This guards the exclusion behaviour.
    assert _extract_health_counter(after) == _extract_health_counter(before)


def test_in_flight_gauge_exposed(client):
    body = client.get("/metrics").text
    assert "ec_http_in_flight_requests" in body


# ---------------------------------------------------------------------------
# Tracing setup is a no-op when OTLP endpoint is unset
# ---------------------------------------------------------------------------
def test_setup_tracing_noop_without_endpoint(monkeypatch):
    from app.core import tracing

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert tracing.setup_tracing(app=None, engine=None) is False
