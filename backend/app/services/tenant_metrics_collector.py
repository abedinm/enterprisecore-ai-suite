"""Periodic collector that exposes business-state gauges on /metrics.

The five Grafana dashboards (SaaS, Tenant Health, Construction, AI Spend,
Storage) read these gauges. They're collected on a 60-second cycle from the
housekeeping scheduler — fresh enough for ops dashboards, infrequent enough
not to add measurable load.

Cardinality control
-------------------
A per-tenant label on a metric with 10,000 tenants creates 10,000 time series
in Prometheus. The collector caps that with the **top-N pattern**: only the
``TOP_N_TENANTS`` (default 100) tenants with the highest recent activity get
their own label; everyone else is bucketed under the literal label value
``"other"`` and aggregated into one series. The aggregator never grows
beyond N + 1 series per metric, no matter how many tenants exist.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.tenant_context import bypass_tenant_filter
from app.db.session import SessionLocal

TOP_N_TENANTS = 100
# Rolling window for "request rate" — count requests served in the last
# minute divided by 60. ``http_requests_total`` is reset only by process
# restart, so we treat this as a coarse proxy for activity, not a precise
# rate. Production dashboards should compute the rate from ``increase()``
# over the metric directly; this gauge is a fallback for tenant sort order.
RATE_WINDOW = timedelta(minutes=1)


def _list_tenant_ids(db: Session) -> list[str]:
    from app.models.tenant import Tenant

    with bypass_tenant_filter():
        return list(db.scalars(select(Tenant.id)).all())


def _rank_top_tenants_by_usage(db: Session, tenant_ids: list[str]) -> list[str]:
    """Return ``tenant_ids`` ordered by a cheap "recent activity" proxy.

    We sum ``ai_usage_records.cost_usd`` for the current month — it's stable,
    monotonic, and tightly correlates with how active a tenant actually is.
    Tenants with no AI spend tie-break in their original (chronological) id
    order so the top-N is deterministic.
    """
    from app.models.ai import AiUsageRecord

    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    spend_by_tenant: dict[str, float] = {}
    with bypass_tenant_filter():
        rows = db.execute(
            select(
                AiUsageRecord.tenant_id,
                func.coalesce(func.sum(AiUsageRecord.cost_usd), 0),
            )
            .where(AiUsageRecord.occurred_at >= month_start)
            .group_by(AiUsageRecord.tenant_id)
        ).all()
    for tid, total in rows:
        spend_by_tenant[tid] = float(total or 0)
    return sorted(tenant_ids, key=lambda t: (-spend_by_tenant.get(t, 0.0), t))


def _label_for(tenant_id: str, top_ids: set[str]) -> str:
    return tenant_id if tenant_id in top_ids else "other"


def _collect_subscription_metrics(db: Session) -> None:
    from app.models.billing import TenantSubscription

    with bypass_tenant_filter():
        counts_by_plan = db.execute(
            select(TenantSubscription.plan, func.count())
            .where(TenantSubscription.status.in_(("active", "trialing")))
            .group_by(TenantSubscription.plan)
        ).all()
        total = db.execute(
            select(
                func.coalesce(func.sum(TenantSubscription.amount_per_period), 0),
                TenantSubscription.interval,
            )
            .where(TenantSubscription.status.in_(("active", "trialing")))
            .group_by(TenantSubscription.interval)
        ).all()

    # Wipe all known plan labels first so a plan that emptied out doesn't
    # keep a stale gauge value. Easiest is to call ``.clear()`` on the
    # underlying metric — prometheus_client supports it for both Counter
    # and Gauge with labels.
    try:
        metrics.subscription_count.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    for plan, count in counts_by_plan:
        metrics.subscription_count.labels(plan=plan or "unknown").set(int(count or 0))

    mrr = Decimal("0")
    arr = Decimal("0")
    for amount, interval in total:
        amount = Decimal(amount or 0)
        if interval == "year":
            arr += amount
            mrr += amount / Decimal(12)
        else:
            mrr += amount
            arr += amount * Decimal(12)
    metrics.subscription_mrr_usd.set(float(mrr))
    metrics.subscription_arr_usd.set(float(arr))


def _collect_tenant_metrics(db: Session) -> None:
    from app.models.ai import AiUsageRecord
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.tenant_usage import get_tenant_storage_mb

    tenant_ids = _list_tenant_ids(db)
    metrics.tenant_count.set(len(tenant_ids))

    top_ranked = _rank_top_tenants_by_usage(db, tenant_ids)[:TOP_N_TENANTS]
    top_ids = set(top_ranked)

    # User count per tenant.
    with bypass_tenant_filter():
        user_counts = dict(
            db.execute(
                select(User.tenant_id, func.count())
                .where(User.is_active.is_(True))
                .group_by(User.tenant_id)
            ).all()
        )
    try:
        metrics.tenant_user_count.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    aggregated_users: dict[str, int] = defaultdict(int)
    for tid in tenant_ids:
        label = _label_for(tid, top_ids)
        aggregated_users[label] += int(user_counts.get(tid) or 0)
    for label, n in aggregated_users.items():
        metrics.tenant_user_count.labels(tenant_id=label).set(n)

    # AI cost per tenant (this month).
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    with bypass_tenant_filter():
        cost_rows = db.execute(
            select(AiUsageRecord.tenant_id, func.coalesce(func.sum(AiUsageRecord.cost_usd), 0))
            .where(AiUsageRecord.occurred_at >= month_start)
            .group_by(AiUsageRecord.tenant_id)
        ).all()
    try:
        metrics.tenant_ai_cost_usd.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    aggregated_cost: dict[str, float] = defaultdict(float)
    for tid, cost in cost_rows:
        aggregated_cost[_label_for(tid, top_ids)] += float(cost or 0)
    for label, c in aggregated_cost.items():
        metrics.tenant_ai_cost_usd.labels(tenant_id=label).set(c)

    # Storage bytes per tenant — top-N only, others rolled into "other".
    try:
        metrics.tenant_storage_bytes.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    aggregated_storage: dict[str, float] = defaultdict(float)
    for tid in tenant_ids:
        try:
            mb = get_tenant_storage_mb(db, tid)
        except Exception:
            mb = 0.0
        aggregated_storage[_label_for(tid, top_ids)] += mb * 1024.0 * 1024.0
    for label, bytes_ in aggregated_storage.items():
        metrics.tenant_storage_bytes.labels(tenant_id=label).set(bytes_)

    # Tenant request rate — derived placeholder. The HTTP middleware doesn't
    # currently tag http_requests_total with a tenant_id label (intentional,
    # to keep that high-volume series low cardinality), so we expose 0.0
    # here and leave the dashboard to compute the rate from a separate
    # tenant-tagged source if/when that's wired up.
    try:
        metrics.tenant_request_rate.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    for tid in tenant_ids:
        metrics.tenant_request_rate.labels(
            tenant_id=_label_for(tid, top_ids)
        ).set(0.0)


def _collect_construction_metrics(db: Session) -> None:
    from app.models.construction.milestones import ConstructionMilestone
    from app.models.construction.projects import ConstructionProject
    from app.models.construction.risks import ConstructionRisk

    with bypass_tenant_filter():
        active = db.scalar(
            select(func.count(ConstructionProject.id)).where(
                ConstructionProject.status.in_(("planning", "active", "on_hold"))
            )
        ) or 0
        metrics.construction_active_projects.set(int(active))

        # Risks bucketed by severity (derived from score = probability*impact;
        # 1-5 low, 6-10 medium, 11-15 high, 16-25 critical).
        risks = db.execute(
            select(ConstructionRisk.score, func.count())
            .where(ConstructionRisk.status.in_(("open", "mitigated")))
            .group_by(ConstructionRisk.score)
        ).all()
        severity_buckets: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for score, count in risks:
            score = int(score or 0)
            if score >= 16:
                severity_buckets["critical"] += int(count)
            elif score >= 11:
                severity_buckets["high"] += int(count)
            elif score >= 6:
                severity_buckets["medium"] += int(count)
            else:
                severity_buckets["low"] += int(count)
        try:
            metrics.construction_risks_total.clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        for sev, n in severity_buckets.items():
            metrics.construction_risks_total.labels(severity=sev).set(n)

        today = datetime.now(timezone.utc).date()
        overdue = db.scalar(
            select(func.count(ConstructionMilestone.id)).where(
                ConstructionMilestone.status.in_(("upcoming", "missed")),
                ConstructionMilestone.planned_date < today,
                ConstructionMilestone.actual_date.is_(None),
            )
        ) or 0
        metrics.construction_overdue_milestones.set(int(overdue))


def collect_tenant_metrics(db: Session) -> None:
    """Single pass that refreshes every business-state gauge.

    Called by the housekeeping scheduler at a 60-second cadence. Designed
    to swallow per-section failures so an exception in one collector never
    leaves the others stale.
    """
    for name, fn in (
        ("subscription", _collect_subscription_metrics),
        ("tenant", _collect_tenant_metrics),
        ("construction", _collect_construction_metrics),
    ):
        try:
            fn(db)
        except Exception:
            logger.exception("tenant_metrics_collector: {} collector failed", name)


def collect_tenant_metrics_safely() -> None:
    """Top-level entry point for the scheduler — opens its own session."""
    try:
        with SessionLocal() as db:
            collect_tenant_metrics(db)
    except Exception:
        logger.exception("tenant_metrics_collector: outer pass failed")


__all__ = [
    "collect_tenant_metrics",
    "collect_tenant_metrics_safely",
    "TOP_N_TENANTS",
]
