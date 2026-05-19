"""Projects module smoke tests — covers all 10 PM tools."""
from __future__ import annotations

from datetime import date, datetime, timezone


# ============ 1. Kanban + 4. Scheduler + tasks ============================
def test_project_and_task_crud(client, auth_headers):
    p = client.post("/api/v1/projects/projects", headers=auth_headers, json={
        "name": "Test Project", "description": "Smoke", "status": "active", "budget": 5000,
    })
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    assert p.json()["color"] == "#4F46E5"  # default

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
    for s in ("backlog", "todo", "in_progress", "in_review", "done"):
        assert s in names


def test_scheduler_returns_buckets(client, auth_headers):
    r = client.get("/api/v1/projects/scheduler/upcoming?days=14", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body and "milestones" in body and "overdue" in body
    assert body["horizon_days"] == 14


# ============ 2. Gantt =====================================================
def test_gantt_endpoint(client, auth_headers):
    p = client.post("/api/v1/projects/projects", headers=auth_headers, json={
        "name": "Gantt Project", "status": "active",
        "start_date": "2026-01-01", "end_date": "2026-06-30",
    }).json()
    t = client.post("/api/v1/projects/tasks", headers=auth_headers, json={
        "project_id": p["id"], "title": "Phase 1", "start_date": "2026-02-01",
        "due_date": "2026-03-01",
    }).json()
    r = client.get(f"/api/v1/projects/projects/{p['id']}/gantt", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["id"] == p["id"]
    assert any(x["id"] == t["id"] for x in body["tasks"])
    assert "dependencies" in body


# ============ 3. Time tracker ==============================================
def test_time_entry_compute_minutes(client, auth_headers):
    proj = client.post("/api/v1/projects/projects", headers=auth_headers,
                       json={"name": "Timer", "status": "active"}).json()
    task = client.post("/api/v1/projects/tasks", headers=auth_headers,
                       json={"project_id": proj["id"], "title": "Timed task"}).json()
    start = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 19, 11, 30, 0, tzinfo=timezone.utc)
    r = client.post("/api/v1/projects/time-entries", headers=auth_headers, json={
        "task_id": task["id"], "started_at": start.isoformat(), "ended_at": end.isoformat(),
        "notes": "Worked", "is_billable": True,
    })
    assert r.status_code == 200
    assert r.json()["minutes"] == 90
    assert r.json()["is_billable"] is True


def test_time_entry_updates_task_actual_hours(client, auth_headers):
    proj = client.post("/api/v1/projects/projects", headers=auth_headers,
                       json={"name": "ActualHours", "status": "active"}).json()
    task = client.post("/api/v1/projects/tasks", headers=auth_headers,
                       json={"project_id": proj["id"], "title": "Effort task"}).json()
    start = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    client.post("/api/v1/projects/time-entries", headers=auth_headers, json={
        "task_id": task["id"], "started_at": start.isoformat(), "ended_at": end.isoformat(),
    })
    fresh = client.get(f"/api/v1/projects/tasks", headers=auth_headers,
                       params={"project_id": proj["id"]}).json()
    updated = next(t for t in fresh if t["id"] == task["id"])
    assert float(updated["actual_hours"]) >= 2.0


# ============ 5. Resource allocator =======================================
def test_resources_and_allocations(client, auth_headers):
    r = client.post("/api/v1/projects/resources", headers=auth_headers, json={
        "name": "Alice", "role": "Dev", "hourly_rate": 95, "capacity_hours_per_week": 40,
        "skills": "python,react", "is_active": True,
    })
    assert r.status_code == 200
    rid = r.json()["id"]
    assert r.json()["name"] == "Alice"

    p = client.post("/api/v1/projects/projects", headers=auth_headers,
                    json={"name": "Allocated", "status": "active"}).json()

    a = client.post("/api/v1/projects/allocations", headers=auth_headers, json={
        "resource_id": rid, "project_id": p["id"],
        "start_date": "2026-05-01", "end_date": "2026-08-01",
        "allocation_pct": 75, "notes": "Q2 push",
    })
    assert a.status_code == 200
    assert float(a.json()["allocation_pct"]) == 75


# ============ 6. Milestones ===============================================
def test_milestones_crud(client, auth_headers):
    p = client.post("/api/v1/projects/projects", headers=auth_headers,
                    json={"name": "Milestones", "status": "active"}).json()
    m = client.post("/api/v1/projects/milestones", headers=auth_headers, json={
        "project_id": p["id"], "title": "Beta launch",
        "description": "All P0 features", "due_date": "2026-06-15",
        "status": "open", "progress": 35,
    })
    assert m.status_code == 200, m.text
    assert m.json()["progress"] == 35

    listed = client.get("/api/v1/projects/milestones", headers=auth_headers,
                       params={"project_id": p["id"]}).json()
    assert any(x["id"] == m.json()["id"] for x in listed)


# ============ 7. Workload =================================================
def test_workload_endpoint(client, auth_headers):
    r = client.get("/api/v1/projects/workload", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


# ============ 8. Sprint planner + burndown ================================
def test_sprint_and_burndown(client, auth_headers):
    p = client.post("/api/v1/projects/projects", headers=auth_headers,
                    json={"name": "Sprintful", "status": "active"}).json()
    s = client.post("/api/v1/projects/sprints", headers=auth_headers, json={
        "project_id": p["id"], "name": "Sprint 1",
        "start_date": "2026-05-01", "end_date": "2026-05-14",
        "goal": "Ship MVP", "status": "active", "capacity_points": 30,
    })
    assert s.status_code == 200
    sid = s.json()["id"]

    bd = client.get(f"/api/v1/projects/sprints/{sid}/burndown", headers=auth_headers)
    assert bd.status_code == 200
    burn = bd.json()
    assert burn["sprint_id"] == sid
    assert "ideal" in burn and "actual" in burn
    assert isinstance(burn["ideal"], list)


# ============ 9. Meetings + minutes =======================================
def test_meetings_and_minutes(client, auth_headers):
    p = client.post("/api/v1/projects/projects", headers=auth_headers,
                    json={"name": "Meetings Test", "status": "active"}).json()
    m = client.post("/api/v1/projects/meetings", headers=auth_headers, json={
        "project_id": p["id"], "title": "Standup",
        "starts_at": "2026-05-20T10:00:00Z",
        "ends_at": "2026-05-20T10:30:00Z",
        "location": "Zoom", "agenda": "1. Updates 2. Blockers",
        "attendees": "Alice,Bob,Charlie", "status": "scheduled",
    })
    assert m.status_code == 200, m.text
    mid = m.json()["id"]
    assert m.json()["attendees"] == "Alice,Bob,Charlie"

    minute = client.post(f"/api/v1/projects/meetings/{mid}/minutes",
                         headers=auth_headers, json={
        "body": "Reviewed sprint", "decisions": "Cut feature X",
        "action_items": "Alice — fix bug Y by Friday",
    })
    assert minute.status_code == 200, minute.text
    assert minute.json()["decisions"] == "Cut feature X"

    listed = client.get(f"/api/v1/projects/meetings/{mid}/minutes",
                        headers=auth_headers).json()
    assert len(listed) >= 1


# ============ 10. Analytics ===============================================
def test_project_analytics(client, auth_headers):
    r = client.get("/api/v1/projects/analytics", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Validate all 14 metrics are present
    expected = {"total_projects", "active_projects", "completed_projects",
                "tasks_by_status", "tasks_by_priority", "overdue_tasks",
                "upcoming_milestones", "total_time_minutes", "total_tasks",
                "completed_tasks", "completion_rate", "avg_task_duration_days",
                "sprint_burn_rate", "workload_by_assignee", "project_progress",
                "upcoming_deadlines"}
    for key in expected:
        assert key in body, f"missing analytics key: {key}"
    assert body["total_projects"] >= 1
