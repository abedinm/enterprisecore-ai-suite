"""Inventory module smoke tests — covers all 10 inventory tools."""
from __future__ import annotations

from datetime import date


# ============ 1. Stock manager + 5. Alerts ================================
def test_product_and_stock_movement(client, auth_headers):
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "WIDGET-TEST", "name": "Test Widget",
        "unit_cost": 10, "unit_price": 29.99, "low_stock_threshold": 20,
        "reorder_quantity": 100, "unit_of_measure": "ea",
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
    assert row["status"] == "ok"
    assert float(row["stock_value"]) == 500.0


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

    # Auto-alert should have been created
    alerts = client.get("/api/v1/inventory/alerts", headers=auth_headers,
                        params={"is_resolved": False}).json()
    assert any(a["product_id"] == p["id"] for a in alerts)


def test_alert_recompute(client, auth_headers):
    r = client.post("/api/v1/inventory/alerts/recompute", headers=auth_headers)
    assert r.status_code == 200
    assert "created" in r.json() and "resolved" in r.json()


# ============ 2. Purchase orders ==========================================
def test_purchase_order_with_lines(client, auth_headers):
    sup = client.post("/api/v1/inventory/suppliers", headers=auth_headers, json={
        "name": "TestSup", "payment_terms": "Net 30",
    }).json()
    prod = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "PO-LINE-001", "name": "PO Line Test", "unit_cost": 8,
    }).json()
    po = client.post("/api/v1/inventory/purchase-orders", headers=auth_headers, json={
        "supplier_id": sup["id"], "status": "draft",
        "order_date": "2026-05-20", "expected_date": "2026-05-27",
        "notes": "Quarterly stock",
        "lines": [
            {"product_id": prod["id"], "description": "PO Line Test",
             "quantity": 20, "unit_cost": 8, "received_quantity": 0},
        ],
    })
    assert po.status_code == 200, po.text
    pid = po.json()["id"]
    assert po.json()["po_number"].startswith("PO-")
    assert float(po.json()["total"]) == 160.0

    lines = client.get(f"/api/v1/inventory/purchase-orders/{pid}/lines",
                       headers=auth_headers).json()
    assert len(lines) == 1
    assert lines[0]["quantity"] == 20


def test_po_status_received_creates_stock_in(client, auth_headers):
    prod = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "PO-RECV-001", "name": "Receive me", "unit_cost": 3,
    }).json()
    # Get current stock baseline
    before = client.get("/api/v1/inventory/stock", headers=auth_headers).json()
    before_qty = next((s["on_hand"] for s in before if s["product_id"] == prod["id"]), 0)

    po = client.post("/api/v1/inventory/purchase-orders", headers=auth_headers, json={
        "supplier_id": None, "status": "draft",
        "order_date": "2026-05-20",
        "lines": [{"product_id": prod["id"], "quantity": 30, "unit_cost": 3,
                   "received_quantity": 0, "description": ""}],
    }).json()

    # Mark received
    r = client.post(f"/api/v1/inventory/purchase-orders/{po['id']}/status",
                    headers=auth_headers, json={"status": "received"})
    assert r.status_code == 200
    assert r.json()["status"] == "received"

    # Stock should have increased by 30
    after = client.get("/api/v1/inventory/stock", headers=auth_headers).json()
    after_qty = next(s["on_hand"] for s in after if s["product_id"] == prod["id"])
    assert after_qty == before_qty + 30


# ============ 3. Suppliers ================================================
def test_suppliers_crud(client, auth_headers):
    r = client.post("/api/v1/inventory/suppliers", headers=auth_headers, json={
        "name": "Acme Supply Co", "contact_person": "John Doe",
        "email": "john@acme.test", "phone": "555-0100",
        "address": "123 Main St", "tax_id": "TAX-123",
        "payment_terms": "Net 60", "rating": 4, "lead_time_days": 14,
        "is_active": True, "notes": "Reliable",
    })
    assert r.status_code == 200, r.text
    assert r.json()["rating"] == 4
    assert r.json()["lead_time_days"] == 14

    sid = r.json()["id"]
    upd = client.patch(f"/api/v1/inventory/suppliers/{sid}",
                       headers=auth_headers, json={**r.json(), "rating": 5})
    assert upd.status_code == 200
    assert upd.json()["rating"] == 5


# ============ 4. Warehouses + zones =======================================
def test_warehouses_and_zones(client, auth_headers):
    w = client.post("/api/v1/inventory/warehouses", headers=auth_headers, json={
        "name": "Main WH", "code": "WH-MAIN", "manager": "Bob",
        "phone": "555-0200", "capacity": 1000, "is_active": True,
    })
    assert w.status_code == 200, w.text
    wid = w.json()["id"]
    assert w.json()["code"] == "WH-MAIN"

    z = client.post(f"/api/v1/inventory/warehouses/{wid}/zones",
                    headers=auth_headers, json={
        "warehouse_id": wid, "name": "Zone A", "aisle": "1",
        "rack": "A", "bin": "01", "capacity": 200,
    })
    assert z.status_code == 200

    zones = client.get(f"/api/v1/inventory/warehouses/{wid}/zones",
                       headers=auth_headers).json()
    assert len(zones) >= 1
    assert zones[0]["name"] == "Zone A"


def test_warehouse_inventory(client, auth_headers):
    w = client.post("/api/v1/inventory/warehouses", headers=auth_headers, json={
        "name": "WH-002", "is_active": True,
    }).json()
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "WH-PROD-001", "name": "Warehouse product", "unit_cost": 1,
    }).json()
    client.post("/api/v1/inventory/stock/movements", headers=auth_headers, json={
        "product_id": p["id"], "warehouse_id": w["id"],
        "movement_type": "in", "quantity": 25,
    })
    inv = client.get(f"/api/v1/inventory/warehouses/{w['id']}/inventory",
                     headers=auth_headers).json()
    assert "items" in inv
    assert any(i["product_id"] == p["id"] and i["quantity"] == 25 for i in inv["items"])


# ============ 6. Barcode ==================================================
def test_barcode_generation(client, auth_headers):
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "BAR-001", "name": "Barcode test", "barcode": "1234567890",
    }).json()
    r = client.get(f"/api/v1/inventory/products/{p['id']}/barcode",
                   headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sku"] == "BAR-001"
    assert body["barcode_value"] == "1234567890"
    assert len(body["png_base64"]) > 100


def test_barcode_scan(client, auth_headers):
    p = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "SCAN-001", "name": "Scan me", "barcode": "SCAN-CODE-999",
        "unit_cost": 7, "unit_price": 15,
    }).json()
    client.post("/api/v1/inventory/stock/movements", headers=auth_headers, json={
        "product_id": p["id"], "movement_type": "in", "quantity": 15,
    })
    r = client.post("/api/v1/inventory/barcode/scan", headers=auth_headers,
                    json={"value": "SCAN-CODE-999"})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["product"]["sku"] == "SCAN-001"
    assert body["product"]["on_hand"] == 15

    # Negative case
    r2 = client.post("/api/v1/inventory/barcode/scan", headers=auth_headers,
                     json={"value": "DOES-NOT-EXIST-XYZ"})
    assert r2.status_code == 200
    assert r2.json()["found"] is False


# ============ 7. Shipments + events =======================================
def test_shipments_with_events(client, auth_headers):
    s = client.post("/api/v1/inventory/shipments", headers=auth_headers, json={
        "tracking_number": "1Z999AA1", "carrier": "UPS", "status": "pending",
        "direction": "inbound", "expected_date": "2026-06-01",
        "origin": "Berlin", "destination": "NYC",
    })
    assert s.status_code == 200, s.text
    sid = s.json()["id"]

    # Initial create-event is auto-logged
    events = client.get(f"/api/v1/inventory/shipments/{sid}/events",
                        headers=auth_headers).json()
    assert len(events) >= 1

    # Add another event
    ev = client.post(f"/api/v1/inventory/shipments/{sid}/events",
                     headers=auth_headers, json={
        "shipment_id": sid, "timestamp": "2026-05-22T08:00:00Z",
        "location": "Customs", "status": "customs",
        "description": "At Berlin customs",
    })
    assert ev.status_code == 200

    events = client.get(f"/api/v1/inventory/shipments/{sid}/events",
                        headers=auth_headers).json()
    assert len(events) >= 2


# ============ 8. Catalog (already covered) ================================
def test_categories_crud(client, auth_headers):
    c = client.post("/api/v1/inventory/categories", headers=auth_headers, json={
        "name": "Electronics", "description": "Powered devices",
    })
    assert c.status_code == 200
    cid = c.json()["id"]

    # Subcategory
    sub = client.post("/api/v1/inventory/categories", headers=auth_headers, json={
        "name": "Laptops", "parent_id": cid,
    })
    assert sub.status_code == 200
    assert sub.json()["parent_id"] == cid

    listed = client.get("/api/v1/inventory/categories", headers=auth_headers).json()
    assert any(x["id"] == cid for x in listed)


# ============ 9. Returns + refunds ========================================
def test_returns_and_restock_on_received(client, auth_headers):
    prod = client.post("/api/v1/inventory/products", headers=auth_headers, json={
        "sku": "RET-001", "name": "Returnable", "unit_cost": 4,
    }).json()
    # Put some stock so we have a baseline
    client.post("/api/v1/inventory/stock/movements", headers=auth_headers, json={
        "product_id": prod["id"], "movement_type": "in", "quantity": 100,
    })
    before = next(s for s in client.get("/api/v1/inventory/stock",
                                        headers=auth_headers).json()
                  if s["product_id"] == prod["id"])

    ret = client.post("/api/v1/inventory/returns", headers=auth_headers, json={
        "product_id": prod["id"], "quantity": 5,
        "reason": "Damaged in shipping", "status": "requested",
        "refund_amount": 20, "refund_status": "pending",
    })
    assert ret.status_code == 200, ret.text
    rid = ret.json()["id"]
    assert ret.json()["rma_number"].startswith("RMA-")

    # Mark received → triggers restock
    upd = client.patch(f"/api/v1/inventory/returns/{rid}", headers=auth_headers, json={
        **ret.json(), "status": "received",
    })
    assert upd.status_code == 200
    assert upd.json()["status"] == "received"

    after = next(s for s in client.get("/api/v1/inventory/stock",
                                       headers=auth_headers).json()
                 if s["product_id"] == prod["id"])
    assert after["on_hand"] == before["on_hand"] + 5


# ============ 10. Analytics ==============================================
def test_inventory_analytics(client, auth_headers):
    r = client.get("/api/v1/inventory/analytics", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    expected = {"total_products", "active_products", "low_stock_count",
                "out_of_stock_count", "low_stock_items", "total_stock_value",
                "open_purchase_orders", "pending_shipments", "pending_returns",
                "total_warehouses", "total_suppliers", "movements_last_30_days",
                "top_products", "movements_by_type", "inventory_turnover",
                "refund_total"}
    for key in expected:
        assert key in body, f"missing analytics key: {key}"
    assert body["total_products"] >= 1
