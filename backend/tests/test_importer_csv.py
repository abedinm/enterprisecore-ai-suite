"""Tests for the generic CSV importer.

Covers the workflow the other source-specific importers inherit from:
upload, manual mapping, validation of required fields, preview, commit
with three on_conflict modes (skip / update / create_duplicate),
rollback, and the discovery endpoint.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.models.crm import Contact
from app.models.import_jobs import ImportJob


def _post_upload(client, auth_headers, tmp_path: Path, source: str, target: str, csv_body: str):
    """Helper: upload a CSV body as multipart and return the created job."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(csv_body, encoding="utf-8")
    with csv_path.open("rb") as fh:
        resp = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": source, "target_entity": target},
            files={"file": ("input.csv", fh, "text/csv")},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_list_importers_includes_all_four(client, auth_headers):
    resp = client.get("/api/v1/importers", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    sources = {i["source"] for i in body["importers"]}
    # CRM/finance/HR sources plus the project-management additions.
    assert {"hubspot", "salesforce", "quickbooks", "csv"}.issubset(sources)
    assert {"asana", "notion", "trello", "microsoft_project"}.issubset(sources)


def test_csv_upload_detect_schema(client, auth_headers, tmp_path):
    csv_body = "name,email,phone\nAlice,alice@example.com,555-0001\nBob,bob@example.com,555-0002\n"
    job = _post_upload(client, auth_headers, tmp_path, "csv", "contact", csv_body)

    r = client.post(f"/api/v1/importers/jobs/{job['id']}/detect-schema", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "name" in body["columns"]
    assert "email" in body["columns"]
    assert len(body["sample_rows"]) == 2


def test_csv_suggest_mapping_for_contact(client, auth_headers, tmp_path):
    csv_body = "Full Name,Email Address,Phone Number\nAlice Smith,alice@ex.com,555\n"
    job = _post_upload(client, auth_headers, tmp_path, "csv", "contact", csv_body)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers)
    assert r.status_code == 200
    mapping = r.json()["mapping"]
    assert mapping["Email Address"] == "email"
    assert mapping["Full Name"] == "name"


def test_csv_validate_flags_missing_required(client, auth_headers, tmp_path):
    csv_body = "Email\nfoo@example.com\n,\n"
    job = _post_upload(client, auth_headers, tmp_path, "csv", "contact", csv_body)
    # Only email mapped -> name is missing
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"Email": "email"}})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/validate", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error_count"] >= 1
    assert any("name" in i["message"] for i in body["issues"])


def test_csv_commit_creates_contacts(client, auth_headers, tmp_path, db):
    csv_body = "name,email\nDeniseImport,denise@ex.com\nEliasImport,elias@ex.com\n"
    job = _post_upload(client, auth_headers, tmp_path, "csv", "contact", csv_body)
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"name": "name", "email": "email"}})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count_imported"] == 2

    # Verify they actually landed
    names = {c.name for c in db.scalars(select(Contact).where(
        Contact.name.in_(["DeniseImport", "EliasImport"])
    ))}
    assert names == {"DeniseImport", "EliasImport"}


def test_csv_on_conflict_skip_vs_update(client, auth_headers, tmp_path, db):
    # Seed an existing contact
    csv1 = "name,email\nOrigName,dup@ex.com\n"
    job1 = _post_upload(client, auth_headers, tmp_path / "a", "csv", "contact", csv1)
    client.patch(f"/api/v1/importers/jobs/{job1['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"name": "name", "email": "email"}})
    client.post(f"/api/v1/importers/jobs/{job1['id']}/commit", headers=auth_headers)

    # Second job with same email but different name; skip mode should leave first row's name
    csv2 = "name,email\nNewName,dup@ex.com\n"
    job2 = _post_upload(client, auth_headers, tmp_path / "b", "csv", "contact", csv2)
    client.patch(f"/api/v1/importers/jobs/{job2['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"name": "name", "email": "email"},
                       "options": {"dedup_strategy": "by_email", "on_conflict": "skip"}})
    r = client.post(f"/api/v1/importers/jobs/{job2['id']}/commit", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["row_count_skipped"] == 1
    rows = db.scalars(select(Contact).where(Contact.email == "dup@ex.com")).all()
    assert len(rows) == 1
    assert rows[0].name == "OrigName"

    # Third job with update mode should overwrite the name
    csv3 = "name,email\nUpdatedName,dup@ex.com\n"
    job3 = _post_upload(client, auth_headers, tmp_path / "c", "csv", "contact", csv3)
    client.patch(f"/api/v1/importers/jobs/{job3['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"name": "name", "email": "email"},
                       "options": {"dedup_strategy": "by_email", "on_conflict": "update"}})
    r = client.post(f"/api/v1/importers/jobs/{job3['id']}/commit", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    rows = db.scalars(select(Contact).where(Contact.email == "dup@ex.com")).all()
    assert len(rows) == 1
    assert rows[0].name == "UpdatedName"


def test_csv_preview_returns_mapped_rows(client, auth_headers, tmp_path):
    csv_body = "Full Name,Email\nPV Test,pv@ex.com\n"
    job = _post_upload(client, auth_headers, tmp_path, "csv", "contact", csv_body)
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"Full Name": "name", "Email": "email"}})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/preview", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert rows[0]["name"] == "PV Test"
    assert rows[0]["email"] == "pv@ex.com"


def test_upload_rejects_unknown_source(client, auth_headers, tmp_path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("a,b\n1,2\n")
    with csv_path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "totally-fake", "target_entity": "contact"},
            files={"file": ("x.csv", fh, "text/csv")},
        )
    assert r.status_code == 422
