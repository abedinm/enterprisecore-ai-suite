"""Asana CSV importer tests."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.projects import Project, Task


ASANA_CSV = (
    "Task ID,Created At,Completed At,Last Modified,Name,Section/Column,Assignee,Due Date,Tags,Notes\n"
    "1001,2026-05-01,,2026-05-10,Wireframe homepage,To do,Ada,2026-06-01,design,Initial sketches\n"
    "1002,2026-05-02,,2026-05-11,Build login form,In progress,Grace,2026-06-05,frontend,OAuth + magic link\n"
    "1003,2026-05-03,2026-05-12,2026-05-12,Ship marketing site,Done,Linus,2026-06-10,launch,All static assets ready\n"
)


def _upload(client, auth_headers, tmp_path, body, target="tasks"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "asana.csv"
    csv_path.write_text(body, encoding="utf-8")
    with csv_path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "asana", "target_entity": target},
            files={"file": ("asana.csv", fh, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_asana_detect_schema(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, ASANA_CSV)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/detect-schema", headers=auth_headers)
    assert r.status_code == 200
    cols = r.json()["columns"]
    assert "Task ID" in cols and "Name" in cols and "Section/Column" in cols


def test_asana_suggest_mapping_tasks(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, ASANA_CSV)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers)
    assert r.status_code == 200
    mapping = r.json()["mapping"]
    assert mapping["Name"] == "title"
    assert mapping["Section/Column"] == "status"
    assert mapping["Due Date"] == "due_date"
    assert mapping["Notes"] == "description"
    assert mapping["Task ID"] == "external_id"


def test_asana_validate_flags_missing_required(client, auth_headers, tmp_path):
    bad_csv = (
        "Task ID,Name,Section/Column,Due Date,Notes\n"
        "2001,,To do,2026-06-01,No title row\n"
    )
    job = _upload(client, auth_headers, tmp_path, bad_csv)
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm},
    )
    # Commit and check that the bad row was reported as failed.
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    body = r.json()
    assert body["row_count_failed"] == 1
    assert body["row_count_imported"] == 0


def test_asana_commit_creates_three_tasks(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, ASANA_CSV)
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm, "options": {"project_name": "Asana Pytest"}},
    )
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 3
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Asana Pytest"))
    assert proj is not None
    titles = {
        t.title for t in db.scalars(select(Task).where(Task.project_id == proj.id))
    }
    assert titles == {"Wireframe homepage", "Build login form", "Ship marketing site"}
    statuses = {
        t.status for t in db.scalars(select(Task).where(Task.project_id == proj.id))
    }
    assert "todo" in statuses and "in_progress" in statuses and "done" in statuses


def test_asana_rollback_removes_imported(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, ASANA_CSV)
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm, "options": {"project_name": "Asana Rollback"}},
    )
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Asana Rollback"))
    assert proj is not None
    proj_id = proj.id
    assert db.scalar(select(Task).where(Task.project_id == proj_id)) is not None

    r = client.post(f"/api/v1/importers/jobs/{job['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    remaining = list(db.scalars(select(Task).where(Task.project_id == proj_id)))
    assert remaining == []


def test_asana_dedup_by_task_id(client, auth_headers, tmp_path, db):
    job1 = _upload(client, auth_headers, tmp_path / "a", ASANA_CSV)
    sm = client.post(
        f"/api/v1/importers/jobs/{job1['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job1['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm, "options": {"project_name": "Asana Dedup"}},
    )
    client.post(f"/api/v1/importers/jobs/{job1['id']}/commit", headers=auth_headers)

    job2 = _upload(client, auth_headers, tmp_path / "b", ASANA_CSV)
    client.patch(
        f"/api/v1/importers/jobs/{job2['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm, "options": {"project_name": "Asana Dedup"}},
    )
    r = client.post(f"/api/v1/importers/jobs/{job2['id']}/commit", headers=auth_headers)
    body = r.json()
    assert body["row_count_skipped"] == 3
    assert body["row_count_imported"] == 0


def test_asana_cross_tenant_isolation(client, make_tenant, tmp_path, session_factory):
    tenant_a, _, token_a = make_tenant("asana-a")
    tenant_b, _, token_b = make_tenant("asana-b")

    csv_path = tmp_path / "asana.csv"
    csv_path.write_text(ASANA_CSV, encoding="utf-8")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    with csv_path.open("rb") as fh:
        job = client.post(
            "/api/v1/importers/jobs",
            headers=headers_a,
            data={"source": "asana", "target_entity": "tasks"},
            files={"file": ("asana.csv", fh, "text/csv")},
        ).json()
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=headers_a
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=headers_a,
        json={"column_mapping": sm, "options": {"project_name": "Asana Iso"}},
    )
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=headers_a)

    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = s.scalars(select(Project).where(Project.name == "Asana Iso")).all()
        assert rows == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = s.scalars(select(Project).where(Project.name == "Asana Iso")).all()
        assert len(rows) == 1
