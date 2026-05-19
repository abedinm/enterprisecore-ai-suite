"""HR module smoke tests."""
from __future__ import annotations

from datetime import date, datetime, timezone


def test_employee_crud(client, auth_headers):
    r = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-TEST-001",
        "full_name": "Test Person",
        "email": "test.person@local.host",
        "department": "Engineering",
        "title": "Software Engineer",
        "salary": 95000,
        "status": "active",
    })
    assert r.status_code == 200, r.text
    emp = r.json()
    assert emp["employee_code"] == "E-TEST-001"

    listing = client.get("/api/v1/hr/employees", headers=auth_headers, params={"q": "Test"})
    assert listing.status_code == 200
    assert any(e["id"] == emp["id"] for e in listing.json())


def test_leave_request_and_decision(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-LEAVE-001", "full_name": "Leave Tester", "status": "active",
    }).json()
    lr = client.post("/api/v1/hr/leaves", headers=auth_headers, json={
        "employee_id": emp["id"],
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
        "leave_type": "annual",
        "reason": "vacation",
    })
    assert lr.status_code == 200
    leave_id = lr.json()["id"]

    decide = client.post(f"/api/v1/hr/leaves/{leave_id}/decision",
                         headers=auth_headers, json={"status": "approved"})
    assert decide.status_code == 200
    assert decide.json()["status"] == "approved"


def test_attendance_clock_out(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-ATT-001", "full_name": "Attendance Tester", "status": "active",
    }).json()
    rec = client.post("/api/v1/hr/attendance", headers=auth_headers, json={
        "employee_id": emp["id"],
        "clock_in": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
    })
    assert rec.status_code == 200
    rec_id = rec.json()["id"]

    out = client.post(f"/api/v1/hr/attendance/{rec_id}/clock-out", headers=auth_headers)
    assert out.status_code == 200
    assert out.json()["clock_out"] is not None


def test_recruitment_pipeline(client, auth_headers):
    op = client.post("/api/v1/hr/openings", headers=auth_headers,
                     json={"title": "Senior Python", "department": "Engineering"})
    assert op.status_code == 200
    cand = client.post("/api/v1/hr/candidates", headers=auth_headers, json={
        "job_opening_id": op.json()["id"],
        "full_name": "Jane Doe", "email": "jane@example.com", "stage": "applied",
    })
    assert cand.status_code == 200
    assert cand.json()["stage"] == "applied"


def test_hr_analytics(client, auth_headers):
    r = client.get("/api/v1/hr/analytics", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "headcount" in body and body["headcount"] >= 1
    assert "by_department" in body
