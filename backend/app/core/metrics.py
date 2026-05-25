"""Prometheus metrics — counters, histograms, and gauges for the suite.

All metrics use the ``ec_`` namespace so they stand out in mixed-tenant
dashboards. We use the ``prometheus_client`` default registry so the
``/metrics`` endpoint can call :func:`generate_latest` with no arguments.

CARDINALITY NOTES
=================
Cardinality is the single biggest operational risk with Prometheus. Label
values explode the storage cost — every distinct combination becomes a unique
time series. The patterns enforced here:

* ``path`` is the FastAPI route template (e.g. ``/api/v1/users/{user_id}``) —
  NEVER the raw URL — so a million distinct user IDs collapse to one series.
* ``user_id``, ``tenant_id``, ``email`` etc. are **never** used as labels.
* ``model`` is bounded by the small set of provider model names.
* Status is the integer HTTP status, not a free-text message.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# HTTP metrics
# ---------------------------------------------------------------------------
http_requests_total = Counter(
    "ec_http_requests_total",
    "HTTP requests served, partitioned by method, route template, and status.",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "ec_http_request_duration_seconds",
    "Request latency in seconds, partitioned by method and route template.",
    ["method", "path"],
    # Buckets chosen for typical API/web workloads — quick responses around
    # 10-100ms and the long tail up to 30s. Add more buckets only after
    # confirming dashboards need finer resolution; each bucket is a series.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

http_in_flight = Gauge(
    "ec_http_in_flight_requests",
    "Number of HTTP requests currently being processed.",
)

# ---------------------------------------------------------------------------
# Database metrics
# ---------------------------------------------------------------------------
db_query_duration_seconds = Histogram(
    "ec_db_query_duration_seconds",
    "Database query duration in seconds, partitioned by operation type.",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


@contextmanager
def time_db_query(operation: str) -> Iterator[None]:
    """Context manager to observe DB query latency. Use sparingly — the OTel
    SQLAlchemy instrumentation already records spans for every statement."""
    start = time.perf_counter()
    try:
        yield
    finally:
        db_query_duration_seconds.labels(operation=operation).observe(
            time.perf_counter() - start
        )


# ---------------------------------------------------------------------------
# AI / LLM metrics
# ---------------------------------------------------------------------------
ai_calls_total = Counter(
    "ec_ai_calls_total",
    "AI provider calls (success or failure), partitioned by provider/model/feature/success.",
    ["provider", "model", "feature", "success"],
)

ai_tokens_in_total = Counter(
    "ec_ai_tokens_in_total",
    "Cumulative input tokens consumed across all AI calls.",
    ["provider", "model"],
)

ai_tokens_out_total = Counter(
    "ec_ai_tokens_out_total",
    "Cumulative output tokens generated across all AI calls.",
    ["provider", "model"],
)

ai_cost_usd_total = Counter(
    "ec_ai_cost_usd_total",
    "Cumulative AI spend in USD across all calls.",
    ["provider", "model"],
)

ai_latency_seconds = Histogram(
    "ec_ai_latency_seconds",
    "End-to-end latency of an AI provider call in seconds.",
    ["provider", "model"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# ---------------------------------------------------------------------------
# Web chat metrics
# ---------------------------------------------------------------------------
webchat_messages_total = Counter(
    "ec_webchat_messages_total",
    "Web chat messages exchanged, partitioned by bot_id and role.",
    ["bot_id", "role"],
)

# ---------------------------------------------------------------------------
# Billing / subscription metrics — referenced by the SaaS Grafana dashboard.
# All are gauges (snapshot state) except the Stripe-events counter, which
# fires once per webhook delivery.
# ---------------------------------------------------------------------------
subscription_count = Gauge(
    "ec_subscription_count",
    "Active subscriptions, partitioned by plan.",
    ["plan"],
)
subscription_mrr_usd = Gauge(
    "ec_subscription_mrr_usd",
    "Current monthly recurring revenue across all active subscriptions, in USD.",
)
subscription_arr_usd = Gauge(
    "ec_subscription_arr_usd",
    "Annualized recurring revenue across all active subscriptions, in USD.",
)
stripe_events_total = Counter(
    "ec_stripe_events_total",
    "Stripe webhook events received (post-dedup).",
    ["event_type"],
)

# ---------------------------------------------------------------------------
# Tenant-scoped metrics — high-cardinality if labelled by raw tenant_id, so
# the collector applies the top-N pattern: only the top 100 tenants get their
# own ``tenant_id`` label; the rest are bucketed under ``tenant_id="other"``.
# ---------------------------------------------------------------------------
tenant_count = Gauge(
    "ec_tenant_count",
    "Number of tenants in the install.",
)
tenant_user_count = Gauge(
    "ec_tenant_user_count",
    "Active users per tenant (top-100 by usage; rest aggregated as 'other').",
    ["tenant_id"],
)
tenant_request_rate = Gauge(
    "ec_tenant_request_rate",
    "Recent HTTP request rate per tenant (rps, 1-minute window).",
    ["tenant_id"],
)
tenant_ai_cost_usd = Gauge(
    "ec_tenant_ai_cost_usd",
    "Cumulative AI spend per tenant in USD (current month).",
    ["tenant_id"],
)
tenant_storage_bytes = Gauge(
    "ec_tenant_storage_bytes",
    "Storage used per tenant in bytes.",
    ["tenant_id"],
)

# ---------------------------------------------------------------------------
# Construction module metrics — the construction dashboard graphs these.
# ---------------------------------------------------------------------------
construction_active_projects = Gauge(
    "ec_construction_active_projects",
    "Construction projects in an active (non-archived, non-completed) status.",
)
construction_risks_total = Gauge(
    "ec_construction_risks_total",
    "Open construction risks, partitioned by severity.",
    ["severity"],
)
construction_overdue_milestones = Gauge(
    "ec_construction_overdue_milestones",
    "Construction milestones whose due date is in the past and not yet completed.",
)

# ---------------------------------------------------------------------------
# Build / process info
# ---------------------------------------------------------------------------
build_info = Gauge(
    "ec_build_info",
    "Static build metadata (always 1). Labels carry version/commit/env.",
    ["version", "commit", "env"],
)


def record_ai_call(
    *,
    provider: str,
    model: str,
    feature: str,
    success: bool,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    latency_seconds: float | None = None,
) -> None:
    """Single entry point for AI service callers. Keeps the label set
    consistent and avoids the "forgot to increment ai_calls_total" foot-gun."""
    label_provider = provider or "unknown"
    label_model = model or "unknown"
    label_feature = feature or "general"
    label_success = "true" if success else "false"

    ai_calls_total.labels(
        provider=label_provider,
        model=label_model,
        feature=label_feature,
        success=label_success,
    ).inc()
    if tokens_in:
        ai_tokens_in_total.labels(provider=label_provider, model=label_model).inc(tokens_in)
    if tokens_out:
        ai_tokens_out_total.labels(provider=label_provider, model=label_model).inc(tokens_out)
    if cost_usd:
        ai_cost_usd_total.labels(provider=label_provider, model=label_model).inc(cost_usd)
    if latency_seconds is not None and latency_seconds >= 0:
        ai_latency_seconds.labels(provider=label_provider, model=label_model).observe(
            latency_seconds
        )


def set_build_info(version: str, commit: str, env: str) -> None:
    """Stamp the build_info gauge once at startup. Subsequent calls with the
    same labels are no-ops, so calling this is idempotent across reloads."""
    build_info.labels(version=version, commit=commit or "unknown", env=env or "unknown").set(1)


def render_latest() -> tuple[bytes, str]:
    """Render the registry as Prometheus exposition text. Returns (body, content_type)."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "ai_calls_total",
    "ai_cost_usd_total",
    "ai_latency_seconds",
    "ai_tokens_in_total",
    "ai_tokens_out_total",
    "build_info",
    "CollectorRegistry",
    "construction_active_projects",
    "construction_overdue_milestones",
    "construction_risks_total",
    "db_query_duration_seconds",
    "http_in_flight",
    "http_request_duration_seconds",
    "http_requests_total",
    "record_ai_call",
    "render_latest",
    "set_build_info",
    "stripe_events_total",
    "subscription_arr_usd",
    "subscription_count",
    "subscription_mrr_usd",
    "tenant_ai_cost_usd",
    "tenant_count",
    "tenant_request_rate",
    "tenant_storage_bytes",
    "tenant_user_count",
    "time_db_query",
    "webchat_messages_total",
]
