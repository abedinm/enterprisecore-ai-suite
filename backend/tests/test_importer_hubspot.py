"""HubSpot CSV importer tests."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.core.tenant_context import tenant_scope
from app.models.crm import Contact, Deal


HUBSPOT_CONTACTS_CSV = (
    "First Name,Last Name,Email,Phone Number,Company\n"
    "Ada,Lovelace,ada@hs.test,555-0101,Analytical Engine\n"
    "Grace,Hopper,grace@hs.test,555-0102,Navy\n"
    "Linus,Torvalds,linus@hs.test,555-0103,Linux Foundation\n"
)

HUBSPOT_DEALS_CSV = (
    "Deal Name,Amount,Deal Stage,Close Date\n"
    "Acme rebrand,12000,proposal,2026-08-15\n"
    "Globex retainer,48000,negotiation,2026-09-30\n"
)


def _upload(client, auth_headers, tmp_path, target, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "hs.csv"
    csv_path.write_text(body, encoding="utf-8")
    with csv_path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "hubspot", "target_entity": target},
            files={"file": ("hs.csv", fh, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_hubspot_detect_schema(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, "contact", HUBSPOT_CONTACTS_CSV)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/detect-schema", headers=auth_headers)
    assert r.status_code == 200
    cols = r.json()["columns"]
    assert "First Name" in cols and "Email" in cols


def test_hubspot_suggest_mapping_contacts(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, "contact", HUBSPOT_CONTACTS_CSV)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers)
    assert r.status_code == 200
    mapping = r.json()["mapping"]
    assert mapping["Email"] == "email"
    assert mapping["Phone Number"] == "phone"
    assert mapping["Company"] == "company"
    # First Name + Last Name should both be mapped (composed at commit time)
    assert "First Name" in mapping
    assert "Last Name" in mapping


def test_hubspot_commit_creates_three_contacts(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, "contact", HUBSPOT_CONTACTS_CSV)
    # Auto-suggest then commit
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 3
    db.expire_all()
    emails = {c.email for c in db.scalars(
        select(Contact).where(Contact.email.like("%@hs.test"))
    )}
    assert emails == {"ada@hs.test", "grace@hs.test", "linus@hs.test"}


def test_hubspot_dedup_by_email_skips_second_upload(client, auth_headers, tmp_path):
    j1 = _upload(client, auth_headers, tmp_path / "a", "contact", HUBSPOT_CONTACTS_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{j1['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{j1['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    client.post(f"/api/v1/importers/jobs/{j1['id']}/commit", headers=auth_headers)

    # Re-import same file with default dedup (HubSpot defaults to by_email)
    j2 = _upload(client, auth_headers, tmp_path / "b", "contact", HUBSPOT_CONTACTS_CSV)
    client.patch(f"/api/v1/importers/jobs/{j2['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{j2['id']}/commit", headers=auth_headers)
    body = r.json()
    assert body["row_count_skipped"] == 3
    assert body["row_count_imported"] == 0


def test_hubspot_rollback_removes_imported(client, auth_headers, tmp_path, db):
    csv = "First Name,Last Name,Email\nRollback,Test,rb@hs.test\n"
    j = _upload(client, auth_headers, tmp_path, "contact", csv)
    sm = client.post(f"/api/v1/importers/jobs/{j['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{j['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    client.post(f"/api/v1/importers/jobs/{j['id']}/commit", headers=auth_headers)
    db.expire_all()
    assert db.scalar(select(Contact).where(Contact.email == "rb@hs.test")) is not None

    r = client.post(f"/api/v1/importers/jobs/{j['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    assert db.scalar(select(Contact).where(Contact.email == "rb@hs.test")) is None


def test_hubspot_deals_import(client, auth_headers, tmp_path):
    j = _upload(client, auth_headers, tmp_path, "deal", HUBSPOT_DEALS_CSV)
    client.patch(f"/api/v1/importers/jobs/{j['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": {
                     "Deal Name": "title",
                     "Amount": "value",
                     "Deal Stage": "stage",
                     "Close Date": "expected_close_date",
                 }})
    r = client.post(f"/api/v1/importers/jobs/{j['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 2


def test_hubspot_cross_tenant_isolation(client, make_tenant, tmp_path, session_factory):
    """Tenant A's import does not leak into Tenant B."""
    tenant_a, _, token_a = make_tenant("hs-a")
    tenant_b, _, token_b = make_tenant("hs-b")

    csv = "First Name,Last Name,Email\nXrayUser,Tenant,xray@hs.test\n"
    csv_path = tmp_path / "hs.csv"
    csv_path.write_text(csv, encoding="utf-8")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    with csv_path.open("rb") as fh:
        j = client.post(
            "/api/v1/importers/jobs",
            headers=headers_a,
            data={"source": "hubspot", "target_entity": "contact"},
            files={"file": ("hs.csv", fh, "text/csv")},
        ).json()
    sm = client.post(f"/api/v1/importers/jobs/{j['id']}/suggest-mapping",
                     headers=headers_a).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{j['id']}/mapping", headers=headers_a,
                 json={"column_mapping": sm})
    client.post(f"/api/v1/importers/jobs/{j['id']}/commit", headers=headers_a)

    # Tenant B should see zero contacts with this email
    with session_factory() as s, tenant_scope(tenant_b.id):
        rows = s.scalars(select(Contact).where(Contact.email == "xray@hs.test")).all()
        assert rows == []
    with session_factory() as s, tenant_scope(tenant_a.id):
        rows = s.scalars(select(Contact).where(Contact.email == "xray@hs.test")).all()
        assert len(rows) == 1
