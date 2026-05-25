"""Construction project CRUD + role isolation."""
from __future__ import annotations

from tests._academic_helpers import make_user
from tests._construction_helpers import make_project, set_verticals_plan


API = "/api/v1/construction"


def test_create_then_list_then_get_project(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    created = make_project(client, auth_headers, name="Tower A")

    r = client.get(f"{API}/projects", headers=auth_headers)
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json()]
    assert "Tower A" in names

    r2 = client.get(f"{API}/projects/{created['id']}", headers=auth_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["name"] == "Tower A"
    assert body["project_type"] == "commercial"
    assert body["currency"] == "USD"


def test_update_project_status(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers, status="planning")
    r = client.patch(
        f"{API}/projects/{p['id']}",
        headers=auth_headers,
        json={"status": "active", "actual_end_date": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


def test_delete_project_204(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    p = make_project(client, auth_headers)
    r = client.delete(f"{API}/projects/{p['id']}", headers=auth_headers)
    assert r.status_code == 204
    r2 = client.get(f"{API}/projects/{p['id']}", headers=auth_headers)
    assert r2.status_code == 404


def test_employee_cannot_create_project(client, auth_headers, monkeypatch):
    """Employees can read but only Admin/Manager can write."""
    set_verticals_plan(monkeypatch)
    emp_headers = make_user(client, "emp_constr@local", "Employee")
    r = client.post(
        f"{API}/projects",
        headers=emp_headers,
        json={
            "name": "Should be blocked",
            "project_type": "residential",
            "contract_value": "100.00",
            "currency": "USD",
        },
    )
    assert r.status_code == 403


def test_employee_can_read_projects(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    make_project(client, auth_headers, name="Visible to Employees")
    emp_headers = make_user(client, "emp_constr2@local", "Employee")
    r = client.get(f"{API}/projects", headers=emp_headers)
    assert r.status_code == 200
    assert any(
        p["name"] == "Visible to Employees" for p in r.json()
    )


def test_get_missing_project_returns_404(client, auth_headers, monkeypatch):
    set_verticals_plan(monkeypatch)
    r = client.get(f"{API}/projects/does-not-exist", headers=auth_headers)
    assert r.status_code == 404
