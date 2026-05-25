"""Construction risk register: CRUD, score computation, severity bucketing."""
from __future__ import annotations

import pytest

from tests._construction_helpers import make_project, set_verticals_plan


API = "/api/v1/construction"


def test_create_risk_stores_computed_score(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    r = client.post(
        f"{API}/projects/{p['id']}/risks",
        headers=auth_headers,
        json={
            "title": "Slip hazard near foundation",
            "category": "safety",
            "probability": 4,
            "impact": 3,
            "mitigation_plan": "Install signage + fall arrest",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["score"] == 12
    assert body["probability"] == 4
    assert body["impact"] == 3


def test_update_risk_recomputes_score(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    created = client.post(
        f"{API}/projects/{p['id']}/risks",
        headers=auth_headers,
        json={"title": "X", "probability": 2, "impact": 2},
    ).json()
    assert created["score"] == 4

    upd = client.patch(
        f"{API}/projects/{p['id']}/risks/{created['id']}",
        headers=auth_headers,
        json={"probability": 5, "impact": 5},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["score"] == 25


def test_risk_severity_buckets():
    from app.services.construction import risk_severity
    # Low: 1-4
    assert risk_severity(1) == "low"
    assert risk_severity(4) == "low"
    # Medium: 5-9
    assert risk_severity(5) == "medium"
    assert risk_severity(9) == "medium"
    # High: 10-15
    assert risk_severity(10) == "high"
    assert risk_severity(15) == "high"
    # Critical: 16-25
    assert risk_severity(16) == "critical"
    assert risk_severity(25) == "critical"


def test_compute_risk_score_validates_bounds():
    from app.core.exceptions import ValidationFailed
    from app.services.construction import compute_risk_score

    assert compute_risk_score(3, 4) == 12
    with pytest.raises(ValidationFailed):
        compute_risk_score(0, 3)
    with pytest.raises(ValidationFailed):
        compute_risk_score(3, 6)


def test_list_risks_orders_by_score_desc(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    # Insert three risks with distinct scores
    for prob, imp, title in [(1, 1, "low"), (5, 5, "max"), (3, 3, "mid")]:
        client.post(
            f"{API}/projects/{p['id']}/risks",
            headers=auth_headers,
            json={"title": title, "probability": prob, "impact": imp},
        )
    r = client.get(f"{API}/projects/{p['id']}/risks", headers=auth_headers)
    assert r.status_code == 200
    scores = [risk["score"] for risk in r.json()]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 25
    assert scores[-1] == 1


def test_invalid_probability_rejected_by_schema(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    r = client.post(
        f"{API}/projects/{p['id']}/risks",
        headers=auth_headers,
        json={"title": "Bad", "probability": 6, "impact": 1},
    )
    # Pydantic ge/le bounds reject this at the validation layer.
    assert r.status_code == 422
