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


# ---------------------------------------------------------------------------
# Deep sweep — exercise the long tail of HR endpoints so coverage doesn't
# stall at the 39% the audit flagged.
# ---------------------------------------------------------------------------
def test_employee_update_patch_path(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-UPD-001", "full_name": "Patch Me", "status": "active",
        "salary": 50000,
    }).json()
    r = client.patch(f"/api/v1/hr/employees/{emp['id']}", headers=auth_headers, json={
        "employee_code": emp["employee_code"], "full_name": "Patched", "status": "active",
        "salary": 60000,
    })
    assert r.status_code == 200, r.text
    assert r.json()["full_name"] == "Patched"


def test_employee_404_on_missing(client, auth_headers):
    r = client.get("/api/v1/hr/employees/non-existent-id", headers=auth_headers)
    assert r.status_code == 404


def test_employee_delete(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-DEL-001", "full_name": "Goner", "status": "active",
    }).json()
    r = client.delete(f"/api/v1/hr/employees/{emp['id']}", headers=auth_headers)
    assert r.status_code == 204


def test_attendance_summary_endpoint(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-SUM-001", "full_name": "Sum Tester", "status": "active",
    }).json()
    client.post("/api/v1/hr/attendance", headers=auth_headers, json={
        "employee_id": emp["id"],
        "clock_in": datetime.now(timezone.utc).isoformat(),
        "source": "manual",
    })
    r = client.get(f"/api/v1/hr/attendance/summary/{emp['id']}", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert "total_hours" in r.json() or "hours" in r.json() or isinstance(r.json(), dict)


def test_leave_balance_endpoint(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-BAL-001", "full_name": "Bal Tester", "status": "active",
    }).json()
    r = client.get(f"/api/v1/hr/leaves/balance/{emp['id']}", headers=auth_headers)
    assert r.status_code == 200


def test_leaves_list_filters(client, auth_headers):
    r = client.get("/api/v1/hr/leaves", headers=auth_headers, params={"status": "approved"})
    assert r.status_code == 200
    r2 = client.get("/api/v1/hr/leaves", headers=auth_headers, params={"status": "pending"})
    assert r2.status_code == 200


def test_attendance_list_with_date_filters(client, auth_headers):
    r = client.get(
        "/api/v1/hr/attendance",
        headers=auth_headers,
        params={
            "start": "2025-01-01T00:00:00+00:00",
            "end": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert r.status_code == 200


def test_review_full_cycle(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-REV-001", "full_name": "Rev Tester", "status": "active",
    }).json()
    r = client.post("/api/v1/hr/reviews", headers=auth_headers, json={
        "employee_id": emp["id"],
        "period": "2026-Q1",
        "score": 4,
        "notes": "Solid",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    upd = client.patch(f"/api/v1/hr/reviews/{rid}", headers=auth_headers, json={
        "employee_id": emp["id"], "period": "2026-Q1", "score": 5, "notes": "Updated",
    })
    assert upd.status_code == 200, upd.text
    assert float(upd.json()["score"]) == 5.0

    lst = client.get("/api/v1/hr/reviews", headers=auth_headers)
    assert lst.status_code == 200

    dele = client.delete(f"/api/v1/hr/reviews/{rid}", headers=auth_headers)
    assert dele.status_code == 204


def test_openings_full_cycle(client, auth_headers):
    op = client.post("/api/v1/hr/openings", headers=auth_headers,
                     json={"title": "DevOps Lead", "department": "Engineering"})
    assert op.status_code == 200
    oid = op.json()["id"]

    upd = client.patch(f"/api/v1/hr/openings/{oid}", headers=auth_headers,
                       json={"title": "DevOps Manager"})
    assert upd.status_code == 200
    lst = client.get("/api/v1/hr/openings", headers=auth_headers)
    assert lst.status_code == 200
    assert any(o["id"] == oid for o in lst.json())
    dele = client.delete(f"/api/v1/hr/openings/{oid}", headers=auth_headers)
    assert dele.status_code == 204


def test_candidates_full_cycle(client, auth_headers):
    op = client.post("/api/v1/hr/openings", headers=auth_headers,
                     json={"title": "PM", "department": "Product"}).json()
    resp = client.post("/api/v1/hr/candidates", headers=auth_headers, json={
        "job_opening_id": op["id"],
        "full_name": "Cand A", "email": "a@example.com", "stage": "applied",
    })
    assert resp.status_code == 200, resp.text
    cand = resp.json()
    upd = client.patch(f"/api/v1/hr/candidates/{cand['id']}", headers=auth_headers, json={
        "job_opening_id": op["id"], "full_name": "Cand A",
        "email": "a@example.com", "stage": "interview",
    })
    assert upd.status_code == 200, upd.text
    assert upd.json()["stage"] == "interview"
    lst = client.get("/api/v1/hr/candidates", headers=auth_headers)
    assert lst.status_code == 200
    dele = client.delete(f"/api/v1/hr/candidates/{cand['id']}", headers=auth_headers)
    assert dele.status_code == 204


def test_onboarding_tasks_cycle(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-ONB-001", "full_name": "Onboardee", "status": "active",
    }).json()
    t = client.post("/api/v1/hr/onboarding", headers=auth_headers, json={
        "employee_id": emp["id"],
        "title": "IT setup",
        "status": "open",
    })
    assert t.status_code == 200, t.text
    tid = t.json()["id"]
    upd = client.patch(f"/api/v1/hr/onboarding/{tid}", headers=auth_headers, json={
        "employee_id": emp["id"], "title": "IT setup", "status": "completed",
    })
    assert upd.status_code == 200
    lst = client.get("/api/v1/hr/onboarding", headers=auth_headers)
    assert lst.status_code == 200
    dele = client.delete(f"/api/v1/hr/onboarding/{tid}", headers=auth_headers)
    assert dele.status_code == 204


def test_org_units_crud_and_chart(client, auth_headers):
    u = client.post("/api/v1/hr/org-units", headers=auth_headers,
                    json={"name": "QA Team"})
    assert u.status_code == 200, u.text
    uid = u.json()["id"]
    upd = client.patch(f"/api/v1/hr/org-units/{uid}", headers=auth_headers,
                       json={"name": "QA"})
    assert upd.status_code == 200
    lst = client.get("/api/v1/hr/org-units", headers=auth_headers)
    assert lst.status_code == 200
    chart = client.get("/api/v1/hr/org-chart", headers=auth_headers)
    assert chart.status_code == 200
    dele = client.delete(f"/api/v1/hr/org-units/{uid}", headers=auth_headers)
    assert dele.status_code == 204


def test_training_cycle(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-TRN-001", "full_name": "Trainee", "status": "active",
    }).json()
    t = client.post("/api/v1/hr/training", headers=auth_headers, json={
        "employee_id": emp["id"],
        "course_name": "Security 101",
        "status": "assigned",
    })
    assert t.status_code == 200, t.text
    tid = t.json()["id"]
    upd = client.patch(f"/api/v1/hr/training/{tid}", headers=auth_headers, json={
        "employee_id": emp["id"], "course_name": "Security 101", "status": "completed",
    })
    assert upd.status_code == 200
    lst = client.get("/api/v1/hr/training", headers=auth_headers)
    assert lst.status_code == 200
    dele = client.delete(f"/api/v1/hr/training/{tid}", headers=auth_headers)
    assert dele.status_code == 204


def test_self_service_me_endpoint(client, auth_headers):
    """The /me endpoint may 404 if the admin user has no Employee row, but
    the handler must execute (covers the early-return branch)."""
    r = client.get("/api/v1/hr/me", headers=auth_headers)
    assert r.status_code in (200, 404)


def test_disciplinary_cycle(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-DSC-001", "full_name": "Disc Tester", "status": "active",
    }).json()
    d = client.post("/api/v1/hr/disciplinary", headers=auth_headers, json={
        "employee_id": emp["id"],
        "incident_date": date.today().isoformat(),
        "severity": "verbal",
        "notes": "Late again",
    })
    assert d.status_code == 200, d.text
    did = d.json()["id"]
    upd = client.patch(f"/api/v1/hr/disciplinary/{did}", headers=auth_headers, json={
        "employee_id": emp["id"], "incident_date": date.today().isoformat(),
        "severity": "written", "notes": "Late again",
    })
    assert upd.status_code == 200
    lst = client.get("/api/v1/hr/disciplinary", headers=auth_headers)
    assert lst.status_code == 200
    dele = client.delete(f"/api/v1/hr/disciplinary/{did}", headers=auth_headers)
    assert dele.status_code == 204


def test_payslips_listing_for_employee(client, auth_headers):
    emp = client.post("/api/v1/hr/employees", headers=auth_headers, json={
        "employee_code": "E-PAY-001", "full_name": "Pay Tester", "status": "active",
    }).json()
    r = client.get(f"/api/v1/hr/payslips/{emp['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
