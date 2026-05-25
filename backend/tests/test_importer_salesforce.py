"""Salesforce CSV importer tests."""
from __future__ import annotations

from sqlalchemy import select

from app.models.crm import Contact, Deal


SF_CONTACTS_CSV = (
    "FirstName,LastName,Email,Phone,AccountName\n"
    "Jane,Doe,jane@sf.test,555-0201,Acme Corp\n"
    "John,Roe,john@sf.test,555-0202,Globex\n"
)

SF_OPP_CSV = (
    "Name,Amount,StageName,CloseDate,Probability\n"
    "Acme deal,15000,Discovery,2026-10-01,30\n"
    "Globex deal,80000,Negotiation,2026-11-15,75\n"
    "Initech deal,5500,Closed Won,2026-07-01,100\n"
)


def _upload(client, auth_headers, tmp_path, target, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "sf.csv"
    csv_path.write_text(body, encoding="utf-8")
    with csv_path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "salesforce", "target_entity": target},
            files={"file": ("sf.csv", fh, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_sf_suggest_mapping_contact(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, "contact", SF_CONTACTS_CSV)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers)
    m = r.json()["mapping"]
    assert m["Email"] == "email"
    assert m["Phone"] == "phone"
    assert m["AccountName"] == "company"


def test_sf_commit_contacts(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, "contact", SF_CONTACTS_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 2
    db.expire_all()
    emails = {c.email for c in db.scalars(
        select(Contact).where(Contact.email.in_(["jane@sf.test", "john@sf.test"]))
    )}
    assert emails == {"jane@sf.test", "john@sf.test"}


def test_sf_commit_opportunities(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, "deal", SF_OPP_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 3
    db.expire_all()
    titles = {d.title for d in db.scalars(
        select(Deal).where(Deal.title.in_(["Acme deal", "Globex deal", "Initech deal"]))
    )}
    assert titles == {"Acme deal", "Globex deal", "Initech deal"}


def test_sf_validation_flags_missing_required(client, auth_headers, tmp_path):
    csv_body = "FirstName,Phone\nNoMail,555-9999\n"
    job = _upload(client, auth_headers, tmp_path, "contact", csv_body)
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {"Phone": "phone"}})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/validate", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["error_count"] >= 1


def test_sf_rollback(client, auth_headers, tmp_path, db):
    csv_body = "FirstName,LastName,Email\nRoll,SF,sfroll@sf.test\n"
    job = _upload(client, auth_headers, tmp_path, "contact", csv_body)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    db.expire_all()
    assert db.scalar(select(Contact).where(Contact.email == "sfroll@sf.test")) is not None
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    assert db.scalar(select(Contact).where(Contact.email == "sfroll@sf.test")) is None
