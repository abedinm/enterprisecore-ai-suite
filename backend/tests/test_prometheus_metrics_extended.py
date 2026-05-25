"""Extended Prometheus exposition + collector tests for the SaaS/business
metrics added under the dashboards.

Covers the new metric names (subscription/MRR/ARR, tenant counts, AI cost,
storage, construction), confirms the top-N cardinality cap, and exercises
the collector end-to-end against a small synthetic dataset.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.core import metrics
from app.core.tenant_context import bypass_tenant_filter, tenant_scope
from app.models.ai import AiUsageRecord
from app.models.billing import TenantSubscription
from app.models.construction.milestones import ConstructionMilestone
from app.models.construction.projects import ConstructionProject
from app.models.construction.risks import ConstructionRisk
from app.services import tenant_metrics_collector


def test_metric_definitions_exported():
    """Every metric the dashboards reference must exist as a module attribute."""
    expected = [
        "subscription_count",
        "subscription_mrr_usd",
        "subscription_arr_usd",
        "stripe_events_total",
        "tenant_count",
        "tenant_user_count",
        "tenant_request_rate",
        "tenant_ai_cost_usd",
        "tenant_storage_bytes",
        "construction_active_projects",
        "construction_risks_total",
        "construction_overdue_milestones",
    ]
    for name in expected:
        assert hasattr(metrics, name), f"metrics.{name} missing"


def test_metrics_exposition_contains_new_metric_names(client, session_factory, default_tenant):
    """After the collector runs, /metrics exposition should mention every
    new metric name at least once (HELP / TYPE comments count)."""
    with session_factory() as s, tenant_scope(default_tenant.id):
        tenant_metrics_collector.collect_tenant_metrics(s)

    body = client.get("/metrics").text
    for name in (
        "ec_subscription_count",
        "ec_subscription_mrr_usd",
        "ec_subscription_arr_usd",
        "ec_stripe_events_total",
        "ec_tenant_count",
        "ec_tenant_user_count",
        "ec_tenant_ai_cost_usd",
        "ec_tenant_storage_bytes",
        "ec_construction_active_projects",
        "ec_construction_risks_total",
        "ec_construction_overdue_milestones",
    ):
        assert name in body, f"{name!r} not in /metrics exposition"


def test_subscription_metrics_reflect_active_state(session_factory, default_tenant):
    with session_factory() as s, tenant_scope(default_tenant.id):
        # Two active subscriptions on different plans.
        s.add(TenantSubscription(
            tenant_id=default_tenant.id,
            plan="core",
            status="active",
            interval="month",
            amount_per_period=Decimal("100.00"),
        ))
        s.add(TenantSubscription(
            tenant_id=default_tenant.id,
            plan="edu",
            status="active",
            interval="year",
            amount_per_period=Decimal("1200.00"),
        ))
        s.commit()
        tenant_metrics_collector.collect_tenant_metrics(s)

    # MRR = 100 (month) + 1200/12 (year) = 200; ARR = 100*12 + 1200 = 2400.
    mrr_value = metrics.subscription_mrr_usd._value.get()  # type: ignore[attr-defined]
    arr_value = metrics.subscription_arr_usd._value.get()  # type: ignore[attr-defined]
    assert mrr_value >= 200.0 - 0.01
    assert arr_value >= 2400.0 - 0.01


def test_construction_metrics_reflect_state(session_factory, default_tenant):
    with session_factory() as s, tenant_scope(default_tenant.id):
        proj = ConstructionProject(
            tenant_id=default_tenant.id,
            name="Metrics Project",
            project_type="commercial",
            status="active",
        )
        s.add(proj)
        s.flush()
        # One critical risk (score 20) and one low (score 4).
        s.add(ConstructionRisk(
            tenant_id=default_tenant.id,
            construction_project_id=proj.id,
            title="High",
            probability=5, impact=4, score=20,
            status="open",
        ))
        s.add(ConstructionRisk(
            tenant_id=default_tenant.id,
            construction_project_id=proj.id,
            title="Low",
            probability=2, impact=2, score=4,
            status="open",
        ))
        # Overdue milestone.
        s.add(ConstructionMilestone(
            tenant_id=default_tenant.id,
            construction_project_id=proj.id,
            name="Overdue",
            planned_date=date.today() - timedelta(days=7),
            status="upcoming",
        ))
        s.commit()
        tenant_metrics_collector.collect_tenant_metrics(s)

    active_value = metrics.construction_active_projects._value.get()  # type: ignore[attr-defined]
    assert active_value >= 1
    overdue_value = metrics.construction_overdue_milestones._value.get()  # type: ignore[attr-defined]
    assert overdue_value >= 1


def test_top_n_tenant_limit_enforced(session_factory, default_tenant, monkeypatch):
    """When more than TOP_N tenants exist, the rest bucket under 'other'."""
    monkeypatch.setattr(tenant_metrics_collector, "TOP_N_TENANTS", 2)

    from app.models.tenant import Tenant
    with session_factory() as s, bypass_tenant_filter():
        # Create 5 tenants beyond default; spend assigned so two top tenants
        # are deterministic. The remaining 3 bucket into "other".
        for i, spend in enumerate([10, 8, 1, 1, 1]):
            t = Tenant(
                name=f"topN-{i}",
                slug=f"topn-{i}-{datetime.now().microsecond}-{i}",
                plan="evaluation",
                status="active",
                settings={},
                primary_contact_email=f"x{i}@x.test",
                timezone="UTC", currency="USD",
            )
            s.add(t)
            s.flush()
            s.add(AiUsageRecord(
                tenant_id=t.id,
                provider="anthropic",
                model="claude",
                feature="chat",
                tokens_in=0, tokens_out=0,
                cost_usd=Decimal(str(spend)),
                occurred_at=datetime.now(timezone.utc),
            ))
        s.commit()

    with session_factory() as s:
        tenant_metrics_collector.collect_tenant_metrics(s)

    # Inspect the gauge labels — expect at most TOP_N + 1 unique tenant_id
    # label values across tenant_ai_cost_usd.
    series = list(metrics.tenant_ai_cost_usd._metrics.items())  # type: ignore[attr-defined]
    label_values = {labels[0] for labels, _ in series}
    assert len(label_values) <= tenant_metrics_collector.TOP_N_TENANTS + 1
    # And 'other' must be present (we added more than TOP_N tenants).
    assert "other" in label_values


def test_collector_safely_swallows_exceptions(session_factory, monkeypatch):
    """A failing collector section must not crash the outer pass."""
    def boom(_db):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(tenant_metrics_collector, "_collect_subscription_metrics", boom)
    with session_factory() as s:
        # Should not raise.
        tenant_metrics_collector.collect_tenant_metrics(s)
