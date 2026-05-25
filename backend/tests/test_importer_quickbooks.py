"""QuickBooks CSV importer tests."""
from __future__ import annotations

from sqlalchemy import select

from app.models.finance import Customer, Invoice, Vendor


QB_CUSTOMERS_CSV = (
    "CustomerName,PrimaryEmail,PrimaryPhone,BillingAddressLine1\n"
    "Acme QB Migration LLC,billing@acme.qb,555-0301,123 Main St\n"
    "Globex QB Migration Inc,ar@globex.qb,555-0302,456 Oak Ave\n"
)

QB_VENDORS_CSV = (
    "VendorName,PrimaryEmail,PaymentTerms\n"
    "Office Supplies Co,sales@osc.qb,Net 30\n"
)

QB_INVOICES_CSV = (
    "DocNumber,TxnDate,DueDate,TotalAmount,Customer\n"
    "INV-1001,2026-03-01,2026-03-31,1500.00,Acme QB Migration LLC\n"
    "INV-1002,2026-03-05,2026-04-04,2750.50,Globex QB Migration Inc\n"
)


def _upload(client, auth_headers, tmp_path, target, body):
    tmp_path.mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "qb.csv"
    csv_path.write_text(body, encoding="utf-8")
    with csv_path.open("rb") as fh:
        r = client.post(
            "/api/v1/importers/jobs",
            headers=auth_headers,
            data={"source": "quickbooks", "target_entity": target},
            files={"file": ("qb.csv", fh, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_qb_customer_suggest_mapping(client, auth_headers, tmp_path):
    job = _upload(client, auth_headers, tmp_path, "customer", QB_CUSTOMERS_CSV)
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping", headers=auth_headers)
    m = r.json()["mapping"]
    assert m["CustomerName"] == "name"
    assert m["PrimaryEmail"] == "email"
    assert m["PrimaryPhone"] == "phone"
    assert m["BillingAddressLine1"] == "billing_address"


def test_qb_customer_commit(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, "customer", QB_CUSTOMERS_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["row_count_imported"] == 2
    db.expire_all()
    names = {c.name for c in db.scalars(
        select(Customer).where(Customer.name.in_(["Acme QB Migration LLC", "Globex QB Migration Inc"]))
    )}
    assert names == {"Acme QB Migration LLC", "Globex QB Migration Inc"}


def test_qb_vendor_commit(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, "vendor", QB_VENDORS_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["row_count_imported"] == 1
    db.expire_all()
    assert db.scalar(select(Vendor).where(Vendor.name == "Office Supplies Co")) is not None


def test_qb_invoice_commit_with_total(client, auth_headers, tmp_path, db):
    job = _upload(client, auth_headers, tmp_path, "invoice", QB_INVOICES_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count_imported"] == 2
    db.expire_all()
    inv = db.scalar(select(Invoice).where(Invoice.invoice_number == "INV-1001"))
    assert inv is not None
    assert float(inv.total) == 1500.0


def test_qb_invoice_dedup_by_number(client, auth_headers, tmp_path):
    job1 = _upload(client, auth_headers, tmp_path / "a", "invoice", QB_INVOICES_CSV)
    sm = client.post(f"/api/v1/importers/jobs/{job1['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job1['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    client.post(f"/api/v1/importers/jobs/{job1['id']}/commit", headers=auth_headers)

    job2 = _upload(client, auth_headers, tmp_path / "b", "invoice", QB_INVOICES_CSV)
    client.patch(f"/api/v1/importers/jobs/{job2['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    r = client.post(f"/api/v1/importers/jobs/{job2['id']}/commit", headers=auth_headers)
    assert r.status_code == 200
    # Default QB invoice dedup is by_invoice_number -> all skipped
    assert r.json()["row_count_skipped"] == 2


def test_qb_rollback_customer(client, auth_headers, tmp_path, db):
    csv_body = "CustomerName,PrimaryEmail\nRollbackCo,rb@qb.test\n"
    job = _upload(client, auth_headers, tmp_path, "customer", csv_body)
    sm = client.post(f"/api/v1/importers/jobs/{job['id']}/suggest-mapping",
                     headers=auth_headers).json()["mapping"]
    client.patch(f"/api/v1/importers/jobs/{job['id']}/mapping", headers=auth_headers,
                 json={"column_mapping": sm})
    client.post(f"/api/v1/importers/jobs/{job['id']}/commit", headers=auth_headers)
    db.expire_all()
    assert db.scalar(select(Customer).where(Customer.name == "RollbackCo")) is not None
    r = client.post(f"/api/v1/importers/jobs/{job['id']}/rollback", headers=auth_headers)
    assert r.status_code == 200
    db.expire_all()
    assert db.scalar(select(Customer).where(Customer.name == "RollbackCo")) is None
