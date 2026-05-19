"""Inventory module smoke tests."""
from __future__ import annotations


def test_product_and_stock_movement(client, auth_headers):
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "WIDGET-TEST", "name": "Test Widget",
        "unit_cost": 10, "unit_price": 29.99, "low_stock_threshold": 20,
    })
    assert p.status_code == 200, p.text
    pid = p.json()["id"]

    mv = client.post("/api/v1/inventory/stock/movements", headers=auth_headers, json={
        "product_id": pid, "movement_type": "in", "quantity": 50, "reference": "Initial",
    })
    assert mv.status_code == 200

    stock = client.get("/api/v1/inventory/stock", headers=auth_headers).json()
    row = next(s for s in stock if s["product_id"] == pid)
    assert row["on_hand"] == 50


def test_low_stock_alerts(client, auth_headers):
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "LOW-TEST", "name": "Almost out", "unit_cost": 5,
        "unit_price": 12, "low_stock_threshold": 100,
    }).json()
    client.post("/api/v1/inventory/stock/movements", headers=auth_headers, json={
        "product_id": p["id"], "movement_type": "in", "quantity": 5,
    })
    stock = client.get("/api/v1/inventory/stock", headers=auth_headers).json()
    row = next(s for s in stock if s["product_id"] == p["id"])
    assert row["status"] == "low"


def test_inventory_analytics(client, auth_headers):
    r = client.get("/api/v1/inventory/analytics", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "total_products" in body and body["total_products"] >= 1
    assert "total_stock_value" in body


def test_barcode_generation(client, auth_headers):
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "BAR-001", "name": "Barcode test", "barcode": "1234567890",
    }).json()
    r = client.get(f"/api/v1/inventory/products/{p['id']}/barcode", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sku"] == "BAR-001"
    assert body["barcode_value"] == "1234567890"
    assert len(body["png_base64"]) > 100  # has actual base64 data
