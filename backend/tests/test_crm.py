"""CRM module smoke tests."""
from __future__ import annotations


def test_contact_lead_deal_flow(client, auth_headers):
    c = client.post("/api/v1/crm/contacts", headers=auth_headers,
                    json={"name": "Bob Smith", "company": "Acme",
                          "email": "bob@acme.example"})
    assert c.status_code == 200
    contact_id = c.json()["id"]

    lead = client.post("/api/v1/crm/leads", headers=auth_headers,
                       json={"contact_id": contact_id, "source": "website",
                             "status": "new", "score": 70})
    assert lead.status_code == 200

    deal = client.post("/api/v1/crm/deals", headers=auth_headers,
                       json={"contact_id": contact_id, "title": "Q3 platform",
                             "stage": "proposal", "value": 25000, "probability": 60})
    assert deal.status_code == 200
    d = deal.json()
    assert float(d["value"]) == 25000.0
    assert float(d["probability"]) == 60.0


def test_pipeline_stages(client, auth_headers):
    r = client.get("/api/v1/crm/deals/pipeline", headers=auth_headers)
    assert r.status_code == 200
    stages = r.json()["stages"]
    stage_names = [s["stage"] for s in stages]
    for expected in ("qualified", "proposal", "won", "lost"):
        assert expected in stage_names


def test_analytics_weighted_pipeline(client, auth_headers):
    r = client.get("/api/v1/crm/analytics", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # 25000 * 60% should be in weighted
    assert float(body["weighted_pipeline"]) >= 0
    assert "deals_by_stage" in body


def test_follow_up_complete(client, auth_headers):
    c = client.post("/api/v1/crm/contacts", headers=auth_headers,
                    json={"name": "FU Target"}).json()
    from datetime import datetime, timezone
    fu = client.post("/api/v1/crm/follow-ups", headers=auth_headers, json={
        "contact_id": c["id"],
        "due_at": datetime.now(timezone.utc).isoformat(),
        "notes": "Call back next week",
    })
    assert fu.status_code == 200
    fid = fu.json()["id"]
    done = client.post(f"/api/v1/crm/follow-ups/{fid}/complete", headers=auth_headers)
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
