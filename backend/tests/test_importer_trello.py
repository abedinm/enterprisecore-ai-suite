"""Trello JSON importer tests."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.projects import Project, Task


TRELLO_EXPORT = {
    "id": "boardA",
    "name": "Trello Pytest Board",
    "desc": "Internal demo board",
    "lists": [
        {"id": "L1", "name": "To Do", "closed": False},
        {"id": "L2", "name": "Doing", "closed": False},
        {"id": "L3", "name": "Done", "closed": False},
    ],
    "labels": [
        {"id": "lbl1", "name": "urgent"},
        {"id": "lbl2", "name": "design"},
    ],
    "members": [{"id": "m1", "username": "ada", "fullName": "Ada Lovelace"}],
    "cards": [
        {
            "id": "C1",
            "name": "Set up project repo",
            "idList": "L1",
            "due": "2026-06-01T17:00:00Z",
            "labels": [{"id": "lbl2", "name": "design"}],
            "idMembers": ["m1"],
            "desc": "Initialise monorepo",
            "checklists": [
                {
                    "name": "Init steps",
                    "checkItems": [
                        {"name": "git init", "state": "complete"},
                        {"name": "add CI", "state": "incomplete"},
                    ],
                }
            ],
        },
        {
            "id": "C2",
            "name": "Implement OAuth",
            "idList": "L2",
            "due": "2026-06-10T17:00:00Z",
            "labels": [{"id": "lbl1", "name": "urgent"}],
            "idMembers": [],
            "desc": "",
            "checklists": [],
        },
        {
            "id": "C3",
            "name": "Ship docs site",
            "idList": "L3",
            "due": None,
            "labels": [],
            "idMembers": [],
            "desc": "Docs are live",
            "checklists": [],
        },
    ],
}


def _upload(client, auth_headers, tmp_path, payload, target="board"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "trello.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "trello", "target_entity": target},
            files={"file": ("trello.json", fh, "application/json")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_trello_detect_schema(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, TRELLO_EXPORT)
    r = client.post(
        f"/api/v1/importers/jobs/{job['id']}/detect-schema", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert "name" in body["columns"]
    assert "idList" in body["columns"]


def test_trello_suggest_mapping(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, TRELLO_EXPORT)
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    assert sm["name"] == "title"
    assert sm["idList"] == "status"
    assert sm["due"] == "due_date"
    assert sm["labels"] == "tags"


def test_trello_validate_flags_missing_card_name(client, auth_headers, tmp_path):
    bad = dict(TRELLO_EXPORT)
    bad["cards"] = [{"id": "Cbad", "name": "", "idList": "L1"}]
    job = _upload(client, auth_headers, tmp_path, bad)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/validate", headers=auth_headers)
    assert r.status_code == 200
    issues = r.json()["issues"]
    assert any("missing 'name'" in i["message"] for i in issues)


def test_trello_commit_three_cards(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, TRELLO_EXPORT)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 3
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Trello Pytest Board"))
    assert proj is not None
    titles = {t.title for t in db.scalars(select(Task).where(Task.project_id == proj.id))}
    assert titles == {"Set up project repo", "Implement OAuth", "Ship docs site"}
    # Status mapping
    statuses = {
        t.title: t.status
        for t in db.scalars(select(Task).where(Task.project_id == proj.id))
    }
    assert statuses["Set up project repo"] == "todo"
    assert statuses["Implement OAuth"] == "in_progress"
    assert statuses["Ship docs site"] == "done"
    # Checklist appended to description
    repo_task = db.scalar(
        select(Task).where(Task.title == "Set up project repo").where(Task.project_id == proj.id)
    )
    assert "[x] git init" in repo_task.description
    assert "[ ] add CI" in repo_task.description


def test_trello_dedup_by_card_id(client, auth_headers, tmp_path, db):
    job1 = _upload(client, auth_headers, tmp_path / "a", TRELLO_EXPORT)
    client.post(f"/api/v1/importers/jobs/{job1['id']}/commit", headers=auth_headers)

    job2 = _upload(client, auth_headers, tmp_path / "b", TRELLO_EXPORT)
    r = client.post(f"/api/v1/importers/jobs/{job2['id']}/commit", headers=auth_headers)
    body = r.json()
    assert body["row_count_skipped"] == 3
    assert body["row_count_imported"] == 0


def test_trello_rollback(client, auth_headers, tmp_path, db):
    payload = dict(TRELLO_EXPORT)
    payload["name"] = "Trello Rollback Board"
    job = _upload(client, auth_headers, tmp_path, payload)
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Trello Rollback Board"))
    assert proj is not None
    proj_id = proj.id

    r = client.post(f"/api/v1/importers/jobs/{job['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    rows = list(db.scalars(select(Task).where(Task.project_id == proj_id)))
    assert rows == []


def test_trello_cross_tenant_isolation(client, make_tenant, tmp_path, session_factory):
    tenant_a, _, token_a = make_tenant("trello-a")
    tenant_b, _, token_b = make_tenant("trello-b")

    payload = dict(TRELLO_EXPORT)
    payload["name"] = "Trello Iso Board"
    p = tmp_path / "trello.json"
    p.write_text(json.dumps(payload), encoding="utf-8")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    with p.open("rb") as fh:
        job = client.post(
            "/api/v1/importers/jobs",
            headers=headers_a,
            data={"source": "trello", "target_entity": "board"},
            files={"file": ("trello.json", fh, "application/json")},
        ).json()
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=headers_a)

    with session_factory() as s, tenant_scope(tenant_b.id):
        assert s.scalars(select(Project).where(Project.name == "Trello Iso Board")).all() == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        assert len(s.scalars(select(Project).where(Project.name == "Trello Iso Board")).all()) == 1
