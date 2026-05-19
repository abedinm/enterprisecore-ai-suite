"""Projects module smoke tests."""
from __future__ import annotations

from datetime import date, datetime, timezone


def test_project_and_task_crud(client, auth_headers):
    p = client.post("/api/v1/projects/projects", headers=auth_headers, json={
        "name": "Test Project", "description": "Smoke", "status": "active", "budget": 5000,
    })
    assert p.status_code == 200, p.text
    pid = p.json()["id"]

    t = client.post("/api/v1/projects/tasks", headers=auth_headers, json={
        "project_id": pid, "title": "First task", "status": "todo", "priority": "high",
    })
    assert t.status_code == 200
    tid = t.json()["id"]

    upd = client.post(f"/api/v1/projects/tasks/{tid}/status",
                      headers=auth_headers, json={"status": "in_progress"})
    assert upd.status_code == 200
    assert upd.json()["status"] == "in_progress"


def test_kanban_has_columns(client, auth_headers):
    r = client.get("/api/v1/projects/tasks/kanban", headers=auth_headers)
    assert r.status_code == 200
    cols = r.json()["columns"]
    names = [c["status"] for c in cols]
    for s in ("todo", "in_progress", "in_review", "done"):
        assert s in names


def test_time_entry_compute_minutes(client, auth_headers):
    proj = client.post("/api/v1/projects/projects", headers=auth_headers,
                       json={"name": "Timer", "status": "active"}).json()
    task = client.post("/api/v1/projects/tasks", headers=auth_headers,
                       json={"project_id": proj["id"], "title": "Timed task"}).json()
    start = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 19, 11, 30, 0, tzinfo=timezone.utc)
    r = client.post("/api/v1/projects/time-entries", headers=auth_headers, json={
        "task_id": task["id"], "started_at": start.isoformat(), "ended_at": end.isoformat(),
    })
    assert r.status_code == 200
    assert r.json()["minutes"] == 90


def test_project_analytics(client, auth_headers):
    r = client.get("/api/v1/projects/analytics", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "total_projects" in body and body["total_projects"] >= 1
    assert "tasks_by_status" in body
