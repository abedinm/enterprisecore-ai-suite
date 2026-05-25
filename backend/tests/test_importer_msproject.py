"""Microsoft Project XML importer tests."""
from __future__ import annotations

from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.projects import Project, Resource, Task, TaskDependency


MSP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Office Move Q3</Name>
  <Tasks>
    <Task>
      <UID>1</UID>
      <Name>Pack desks</Name>
      <OutlineLevel>1</OutlineLevel>
      <Start>2026-06-01T08:00:00</Start>
      <Finish>2026-06-03T17:00:00</Finish>
      <PercentComplete>50</PercentComplete>
      <Notes>Bubble wrap monitors</Notes>
    </Task>
    <Task>
      <UID>2</UID>
      <Name>Transport boxes</Name>
      <OutlineLevel>1</OutlineLevel>
      <Start>2026-06-04T08:00:00</Start>
      <Finish>2026-06-05T17:00:00</Finish>
      <PercentComplete>0</PercentComplete>
      <PredecessorLink>
        <PredecessorUID>1</PredecessorUID>
        <Type>1</Type>
      </PredecessorLink>
    </Task>
    <Task>
      <UID>3</UID>
      <Name>Reconnect workstations</Name>
      <OutlineLevel>2</OutlineLevel>
      <Start>2026-06-06T08:00:00</Start>
      <Finish>2026-06-08T17:00:00</Finish>
      <PercentComplete>0</PercentComplete>
      <PredecessorLink>
        <PredecessorUID>2</PredecessorUID>
        <Type>1</Type>
      </PredecessorLink>
    </Task>
  </Tasks>
  <Resources>
    <Resource><UID>1</UID><Name>Alice Mover</Name></Resource>
    <Resource><UID>2</UID><Name>Bob IT</Name></Resource>
  </Resources>
</Project>
"""


def _upload(client, auth_headers, tmp_path, body, target="project"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "project.xml"
    path.write_text(body, encoding="utf-8")
    with path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "microsoft_project", "target_entity": target},
            files={"file": ("project.xml", fh, "application/xml")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_msp_detect_schema(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, MSP_XML)
    r = client.post(
        f"/api/v1/importers/jobs/{job['id']}/detect-schema", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    cols = body["columns"]
    assert "UID" in cols and "Name" in cols and "Start" in cols
    # Also surfaces project_name + task_count for the UI
    sample = body["sample_rows"]
    assert any(row["Name"] == "Pack desks" for row in sample)


def test_msp_suggest_mapping_tasks(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, MSP_XML, target="tasks")
    sm = client.post(
        f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers
    ).json()["mapping"]
    assert sm["UID"] == "external_id"
    assert sm["Name"] == "title"
    assert sm["Start"] == "start_date"
    assert sm["Finish"] == "due_date"


def test_msp_validate_flags_missing_name(client, auth_headers, tmp_path):
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Bad</Name>
  <Tasks>
    <Task><UID>1</UID><OutlineLevel>1</OutlineLevel></Task>
  </Tasks>
</Project>"""
    job = _upload(client, auth_headers, tmp_path, bad_xml)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/validate", headers=auth_headers)
    issues = r.json()["issues"]
    assert any("missing <Name>" in i["message"] for i in issues)


def test_msp_commit_creates_three_tasks_plus_deps(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, MSP_XML)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count_imported"] == 3
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "Office Move Q3"))
    assert proj is not None
    tasks = list(db.scalars(select(Task).where(Task.project_id == proj.id)))
    assert {t.title for t in tasks} == {
        "Pack desks", "Transport boxes", "Reconnect workstations"
    }
    # Dependencies created (Transport depends on Pack, Reconnect depends on Transport)
    deps = list(db.scalars(select(TaskDependency)))
    assert len(deps) >= 2
    # Resources imported
    resources = list(db.scalars(select(Resource).where(Resource.name.like("%Mover%"))))
    assert len(resources) == 1


def test_msp_dedup_by_uid(client, auth_headers, tmp_path, db):
    job1 = _upload(client, auth_headers, tmp_path / "a", MSP_XML)
    client.post(f"/api/v1/importers/jobs/{job1['id']}/commit", headers=auth_headers)

    job2 = _upload(client, auth_headers, tmp_path / "b", MSP_XML)
    r = client.post(f"/api/v1/importers/jobs/{job2['id']}/commit", headers=auth_headers)
    body = r.json()
    assert body["row_count_skipped"] == 3
    assert body["row_count_imported"] == 0


def test_msp_rollback(client, auth_headers, tmp_path, db):
    custom = MSP_XML.replace("Office Move Q3", "MSP Rollback Project")
    job = _upload(client, auth_headers, tmp_path, custom)
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    db.expire_all()
    proj = db.scalar(select(Project).where(Project.name == "MSP Rollback Project"))
    assert proj is not None
    proj_id = proj.id
    task_ids_before = [t.id for t in db.scalars(select(Task).where(Task.project_id == proj_id))]
    assert task_ids_before

    r = client.post(f"/api/v1/importers/jobs/{job['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    after = list(db.scalars(select(Task).where(Task.project_id == proj_id)))
    assert after == []
    # Dependencies should also be gone (cascade from task deletion)
    remaining_deps = [
        d for d in db.scalars(select(TaskDependency))
        if d.task_id in task_ids_before
    ]
    assert remaining_deps == []


def test_msp_cross_tenant_isolation(client, make_tenant, tmp_path, session_factory):
    tenant_a, _, token_a = make_tenant("msp-a")
    tenant_b, _, token_b = make_tenant("msp-b")

    body = MSP_XML.replace("Office Move Q3", "MSP Iso Project")
    p = tmp_path / "project.xml"
    p.write_text(body, encoding="utf-8")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    with p.open("rb") as fh:
        job = client.post(
            "/api/v1/importers/jobs",
            headers=headers_a,
            data={"source": "microsoft_project", "target_entity": "project"},
            files={"file": ("project.xml", fh, "application/xml")},
        ).json()
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=headers_a)

    with session_factory() as s, tenant_scope(tenant_b.id):
        assert s.scalars(select(Project).where(Project.name == "MSP Iso Project")).all() == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        assert len(s.scalars(select(Project).where(Project.name == "MSP Iso Project")).all()) == 1
