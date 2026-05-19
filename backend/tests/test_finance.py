"""Finance module — invoices, expenses, payroll, tax, currency, reports."""
from __future__ import annotations

from datetime import date


def test_customer_crud(client, auth_headers):
    r = client.post("/api/v1/finance/customers", headers=auth_headers,
                    json={"name": "Acme Corp", "email": "ap@acme.example", "currency": "USD"})
    assert r.status_code == 200, r.text
    cust = r.json()
    assert cust["name"] == "Acme Corp"

    listing = client.get("/api/v1/finance/customers", headers=auth_headers)
    assert listing.status_code == 200
    assert any(c["id"] == cust["id"] for c in listing.json())

    patch = client.patch(f"/api/v1/finance/customers/{cust['id']}", headers=auth_headers,
                         json={"name": "Acme LLC", "currency": "EUR"})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Acme LLC"


def test_invoice_create_and_pdf(client, auth_headers):
    cust = client.post("/api/v1/finance/customers", headers=auth_headers,
                       json={"name": "Test Cust", "currency": "USD"}).json()

    inv_body = {
        "customer_id": cust["id"],
        "issue_date": date.today().isoformat(),
        "due_date": date.today().isoformat(),
        "currency": "USD",
        "lines": [
            {"description": "Consulting", "quantity": 10, "unit_price": 150, "tax_rate": 0.08},
            {"description": "Software",   "quantity": 1,  "unit_price": 500, "tax_rate": 0.08},
        ],
    }
    r = client.post("/api/v1/finance/invoices", headers=auth_headers, json=inv_body)
    assert r.status_code == 200, r.text
    inv = r.json()
    # 10*150 + 1*500 = 2000 subtotal; 2000 * 8% = 160 tax; total 2160
    assert float(inv["subtotal"]) == 2000.0
    assert float(inv["tax_total"]) == 160.0
    assert float(inv["total"]) == 2160.0
    assert inv["invoice_number"].startswith("INV-")

    # PDF
    pdf = client.get(f"/api/v1/finance/invoices/{inv['id']}/pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 1000

    # Status change
    upd = client.post(f"/api/v1/finance/invoices/{inv['id']}/status", headers=auth_headers,
                      json={"status": "sent"})
    assert upd.status_code == 200
    assert upd.json()["status"] == "sent"


def test_payroll_estimate(client, auth_headers):
    r = client.post("/api/v1/finance/payroll/estimate", headers=auth_headers,
                    json={"gross_salary": 5000, "tax_rate": 0.22, "deductions": 200, "bonuses": 500})
    assert r.status_code == 200, r.text
    body = r.json()
    # 5000 + 500 = 5500 gross; tax 5500*0.22 = 1210; net 5500-1210-200 = 4090
    assert float(body["gross"]) == 5500.0
    assert float(body["tax"]) == 1210.0
    assert float(body["net"]) == 4090.0


def test_tax_progressive_brackets(client, auth_headers):
    # 100k income, 12k deductions → US default brackets
    r = client.post("/api/v1/finance/tax/estimate", headers=auth_headers,
                    json={"income": 100000, "deductions": 12000, "brackets": []})
    assert r.status_code == 200
    body = r.json()
    assert float(body["taxable_income"]) == 88000.0
    # Effective rate must be < 22% (top bracket touched only partly)
    assert 0.10 < float(body["effective_rate"]) < 0.20


def test_currency_rate_and_convert(client, auth_headers):
    today = date.today().isoformat()
    # USD→EUR @ 0.92
    r1 = client.post("/api/v1/finance/currency/rates", headers=auth_headers,
                     json={"base_currency": "USD", "quote_currency": "EUR",
                           "rate": 0.92, "effective_date": today})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/finance/currency/convert", headers=auth_headers,
                     json={"amount": 100, "from_currency": "USD", "to_currency": "EUR"})
    assert r2.status_code == 200
    body = r2.json()
    assert abs(float(body["converted"]) - 92.0) < 0.01


def test_reports_pnl_and_balance(client, auth_headers):
    start = "2025-01-01"
    end = date.today().isoformat()
    pnl = client.get("/api/v1/finance/reports/pnl",
                     headers=auth_headers, params={"start": start, "end": end})
    assert pnl.status_code == 200
    body = pnl.json()
    assert "revenue" in body and "net_income" in body and "by_category" in body

    bs = client.get("/api/v1/finance/reports/balance-sheet",
                    headers=auth_headers, params={"as_of": end})
    assert bs.status_code == 200
    assert "assets" in bs.json() and "totals" in bs.json()


def test_expense_crud(client, auth_headers):
    cat = client.post("/api/v1/finance/expense-categories",
                      headers=auth_headers, json={"name": "Office Supplies"})
    # Category may already exist from a previous test; either 200 or 409 OK
    assert cat.status_code in (200, 409)

    r = client.post("/api/v1/finance/expenses", headers=auth_headers,
                    json={"date": date.today().isoformat(), "amount": 42.50,
                          "currency": "USD", "description": "Pens & paper"})
    assert r.status_code == 200
    assert float(r.json()["amount"]) == 42.5
