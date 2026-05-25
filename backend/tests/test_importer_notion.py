"""Notion CSV importer tests."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.documents import Document
from app.models.projects import Project, Task


NOTION_TASKS_CSV = (
    "Name,Status,Assignee,Due,Tags,Description\n"
    "Design system kickoff,To do,Ada,2026-06-15,design,Define tokens and components\n"
    "Migrate auth flow,In progress,Grace,2026-06-20,backend,Move to magic links\n"
    "Launch beta,Done,Linus,2026-06-30,launch,Beta cohort ready\n"
)

# Notion users frequently rename columns or add emoji.
NOTION_TASKS_VARIANT_CSV = (
    "Task,State,Owner,Deadline 📅,Labels,Notes\n"
    "Refactor billing,Doing,Ada,2026-07-01,backend,Stripe webhook hardening\n"
)

NOTION_NOTES_CSV = (
    "Name,Tags,Body\n"
    "Weekly retro 2026-05-22,team,What went well: shipping. Risk: scope creep.\n"
    "Customer-call notes Acme,sales,They want SSO + audit log.\n"
)


def _upload(client, auth_headers, tmp_path, body, target):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "notion.csv"
    path.write_text(body, encoding="utf-8")
    with path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "notion", "target_entity": target},
            files={"file": ("notion.csv", fh, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_notion_detect_schema(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, NOTION_TASKS_CSV, "tasks")
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/detect-schema", headers=auth_headers)
    assert r.status_code == 200
    assert "Name" in r.json()["columns"]


def test_notion_suggest_mapping_handles_variants(client, auth_headers, tmp_path):
    """Notion's column names vary database-to-database — suggester must cope."""
    job = _upload(client, auth_headers, tmp_path, NOTION_TASKS_VARIANT_CSV, "tasks")
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    assert sm["Task"] == "title"
    assert sm["State"] == "status"
    assert sm["Deadline 📅"] == "due_date"
    assert sm["Notes"] == "description"


def test_notion_validate_missing_title(client, auth_headers, tmp_path):
    bad_csv = "Name,Status,Description\n,To do,Empty title\n"
    job = _upload(client, auth_headers, tmp_path, bad_csv, "tasks")
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm},
    )
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    body = r.json()
    assert body["row_count_failed"] == 1
    assert body["row_count_imported"] == 0


def test_notion_commit_three_tasks(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, NOTION_TASKS_CSV, "tasks")
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm, "options": {"project_name": "Notion Pytest"}},
    )
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.json()["row_count_imported"] == 3
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Notion Pytest"))
    assert proj is not None
    titles = {t.title for t in db.scalars(select(Task).where(Task.project_id == proj.id))}
    assert "Design system kickoff" in titles


def test_notion_notes_import(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, NOTION_NOTES_CSV, "notes")
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm},
    )
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.json()["row_count_imported"] == 2
    db.expire_all()
    doc = db.scalar(select(Document).where(Document.title == "Weekly retro 2026-05-22"))
    assert doc is not None
    assert "shipping" in doc.content


def test_notion_rollback_removes(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, NOTION_TASKS_CSV, "tasks")
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=auth_headers,
        json={"column_mapping": sm, "options": {"project_name": "Notion Rollback"}},
    )
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Notion Rollback"))
    assert proj is not None
    proj_id = proj.id

    r = client.post(f"/api/v1/importers/jobs/{job['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    rows = list(db.scalars(select(Task).where(Task.project_id == proj_id)))
    assert rows == []


def test_notion_cross_tenant_isolation(client, make_tenant, tmp_path, session_factory):
    tenant_a, _, token_a = make_tenant("notion-a")
    tenant_b, _, token_b = make_tenant("notion-b")

    p = tmp_path / "notion.csv"
    p.write_text(NOTION_TASKS_CSV, encoding="utf-8")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    with p.open("rb") as fh:
        job = client.post(
            "/api/v1/importers/jobs",
            headers=headers_a,
            data={"source": "notion", "target_entity": "tasks"},
            files={"file": ("notion.csv", fh, "text/csv")},
        ).json()
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=headers_a
    ).json()["mapping"]
    client.patch(
        f"/api/v1/importers/jobs/{job['id']}/mapping",
        headers=headers_a,
        json={"column_mapping": sm, "options": {"project_name": "Notion Iso"}},
    )
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=headers_a)

    with session_factory() as s, tenant_scope(tenant_b.id):
        assert s.scalars(select(Project).where(Project.name == "Notion Iso")).all() == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        assert len(s.scalars(select(Project).where(Project.name == "Notion Iso")).all()) == 1
