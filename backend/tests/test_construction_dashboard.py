"""Dashboard rollup: counts/totals come back correct under realistic seed data."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from tests._construction_helpers import make_project, set_verticals_plan


API = "/api/v1/construction"


def test_dashboard_rollup_aggregates_correctly(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers, name="Dashboard Test Project")

    # Seed a spread of risks across severity buckets.
    # score 4 (low), score 8 (medium), score 12 (high), score 20 (critical)
    for prob, imp, title in [(2, 2, "low"), (2, 4, "med"), (3, 4, "high"), (4, 5, "crit")]:
        client.post(
            f"{API}/projects/{p['id']}/risks",
            headers=auth_headers,
            json={"title": title, "probability": prob, "impact": imp},
        )

    # Two milestones — one inside the 30-day window, one outside.
    today = date.today()
    client.post(
        f"{API}/projects/{p['id']}/milestones",
        headers=auth_headers,
        json={
            "name": "Foundation pour",
            "planned_date": (today + timedelta(days=10)).isoformat(),
            "status": "upcoming",
        },
    )
    client.post(
        f"{API}/projects/{p['id']}/milestones",
        headers=auth_headers,
        json={
            "name": "Topping out",
            "planned_date": (today + timedelta(days=120)).isoformat(),
            "status": "upcoming",
        },
    )

    # Two open variations + one rejected — only the two open should count.
    for cost, status_ in [("50000.00", "pending"), ("25000.00", "approved"),
                          ("99999.00", "rejected")]:
        client.post(
            f"{API}/projects/{p['id']}/variations",
            headers=auth_headers,
            json={
                "title": f"VAR {status_}",
                "cost_impact": cost,
                "status": status_,
            },
        )

    # EOT requests: one submitted (10 days), one approved (5 days), one rejected.
    client.post(
        f"{API}/projects/{p['id']}/eot-requests",
        headers=auth_headers,
        json={"requested_days": 10, "reason": "rain", "status": "submitted"},
    )
    client.post(
        f"{API}/projects/{p['id']}/eot-requests",
        headers=auth_headers,
        json={"requested_days": 5, "reason": "supply", "status": "approved"},
    )

    # Insurance: one expiring inside 90d, one outside.
    client.post(
        f"{API}/projects/{p['id']}/insurances",
        headers=auth_headers,
        json={
            "insurance_type": "CAR",
            "provider": "InsureCo",
            "policy_number": "POL-001",
            "expiry_date": (today + timedelta(days=30)).isoformat(),
        },
    )
    client.post(
        f"{API}/projects/{p['id']}/insurances",
        headers=auth_headers,
        json={
            "insurance_type": "PL",
            "provider": "InsureCo",
            "policy_number": "POL-002",
            "expiry_date": (today + timedelta(days=200)).isoformat(),
        },
    )

    # Two schedule tasks with progress 50% and 100% -> average 75%.
    client.post(
        f"{API}/projects/{p['id']}/schedule/tasks",
        headers=auth_headers,
        json={"name": "Foundations", "progress_percent": 50, "duration_days": 10},
    )
    client.post(
        f"{API}/projects/{p['id']}/schedule/tasks",
        headers=auth_headers,
        json={"name": "Frame", "progress_percent": 100, "duration_days": 14},
    )

    # A progress report
    client.post(
        f"{API}/projects/{p['id']}/progress-reports",
        headers=auth_headers,
        json={
            "report_date": today.isoformat(),
            "overall_progress_percent": 60,
            "narrative": "Solid week",
            "workforce_count": 30,
        },
    )

    # A site instruction so recent_site_instructions has at least one.
    client.post(
        f"{API}/projects/{p['id']}/site-instructions",
        headers=auth_headers,
        json={"title": "Tighten bolts on column C4"},
    )

    # Now fetch the dashboard.
    r = client.get(
        f"{API}/projects/{p['id']}/dashboard", headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["project"]["name"] == "Dashboard Test Project"

    rb = body["risk_buckets"]
    assert rb["low"] == 1 and rb["medium"] == 1
    assert rb["high"] == 1 and rb["critical"] == 1
    assert rb["total"] == 4

    # Schedule progress: average of 50 and 100 -> 75
    assert body["schedule_progress_percent"] == 75

    upcoming_names = [m["name"] for m in body["upcoming_milestones"]]
    assert "Foundation pour" in upcoming_names
    assert "Topping out" not in upcoming_names

    open_vars = body["open_variations"]
    assert len(open_vars) == 2
    assert Decimal(body["open_variations_cost_impact_total"]) == Decimal("75000.00")

    assert body["pending_eot_days"] == 10

    expiring = body["expiring_insurances"]
    expiring_numbers = [i["policy_number"] for i in expiring]
    assert "POL-001" in expiring_numbers
    assert "POL-002" not in expiring_numbers

    assert len(body["recent_site_instructions"]) >= 1
    assert body["latest_progress_report"] is not None
    assert body["latest_progress_report"]["overall_progress_percent"] == 60


def test_dashboard_empty_project_returns_zeros(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers, name="Empty Project")
    r = client.get(
        f"{API}/projects/{p['id']}/dashboard", headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["risk_buckets"]["total"] == 0
    assert body["schedule_progress_percent"] == 0
    assert body["upcoming_milestones"] == []
    assert body["open_variations"] == []
    assert Decimal(body["open_variations_cost_impact_total"]) == Decimal("0")
    assert body["pending_eot_days"] == 0
    assert body["expiring_insurances"] == []
    assert body["latest_progress_report"] is None


def test_dashboard_404_when_project_missing(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    r = client.get(
        f"{API}/projects/nope/dashboard", headers=auth_headers,
    )
    assert r.status_code == 404


def test_check_insurance_expiries_helper(db, monkeypatch):
    """Service-level helper returns only policies inside the window."""
    set_verticals_plan(monkeypatch)
    from app.models.construction.insurances import ConstructionInsurance
    from app.models.construction.projects import ConstructionProject
    from app.services.construction import check_insurance_expiries

    proj = ConstructionProject(
        name="Insurance Helper Project", project_type="industrial",
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    today = date(2026, 5, 22)
    rows = [
        ConstructionInsurance(
            construction_project_id=proj.id,
            insurance_type="CAR", provider="X",
            policy_number="A", expiry_date=today + timedelta(days=10),
        ),
        ConstructionInsurance(
            construction_project_id=proj.id,
            insurance_type="PI", provider="Y",
            policy_number="B", expiry_date=today + timedelta(days=200),
        ),
        ConstructionInsurance(
            construction_project_id=proj.id,
            insurance_type="PL", provider="Z",
            policy_number="C", expiry_date=today - timedelta(days=5),
        ),
    ]
    db.add_all(rows)
    db.commit()
    out = check_insurance_expiries(
        db, construction_project_id=proj.id,
        days_ahead=90, today=today,
    )
    nums = [r.policy_number for r in out]
    assert nums == ["A"]
