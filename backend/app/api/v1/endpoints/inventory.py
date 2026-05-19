"""Inventory & supply-chain endpoints — full 10-tool implementation."""
from __future__ import annotations

import base64
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.inventory import (
    Product, ProductCategory, PurchaseOrder, PurchaseOrderLine, ReturnRequest,
    Shipment, ShipmentEvent, StockAlert, StockMovement, Supplier, Warehouse,
    WarehouseZone,
)
from app.models.user import User, UserRole
from app.schemas.inventory import (
    BarcodeOut, BarcodeScanIn, InventoryAnalyticsOut, POIn, POLineOut, POOut,
    ProductCategoryIn, ProductCategoryOut, ProductIn, ProductOut, ReturnIn,
    ReturnOut, ShipmentEventIn, ShipmentEventOut, ShipmentIn, ShipmentOut,
    StockAlertIn, StockAlertOut, StockMovementIn, StockMovementOut,
    StockOnHandOut, SupplierIn, SupplierOut, WarehouseIn, WarehouseOut,
    WarehouseZoneIn, WarehouseZoneOut,
)

router = APIRouter()


def _crud(model, db, payload, item_id=None):
    if item_id:
        obj = db.get(model, item_id)
        if not obj:
            raise NotFoundError(f"{model.__name__} not found")
        for k, v in payload.model_dump().items():
            setattr(obj, k, v)
    else:
        obj = model(**payload.model_dump())
        db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def _on_hand(db: Session, product_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(StockMovement.product_id == product_id)
    )
    return int(total or 0)


# ============ 1. Suppliers ================================================
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(q: str | None = None, is_active: bool | None = None,
                   db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Supplier).order_by(Supplier.name)
    if q:
        stmt = stmt.where(or_(Supplier.name.ilike(f"%{q}%"),
                              Supplier.email.ilike(f"%{q}%"),
                              Supplier.contact_person.ilike(f"%{q}%")))
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active == is_active)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Supplier, db, payload)


@router.patch("/suppliers/{sid}", response_model=SupplierOut)
def update_supplier(sid: str, payload: SupplierIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Supplier, db, payload, item_id=sid)


@router.delete("/suppliers/{sid}", status_code=204)
def delete_supplier(sid: str, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Supplier, sid)
    if obj:
        db.delete(obj)
        db.commit()


# ============ 2. Warehouses ================================================
@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Warehouse).order_by(Warehouse.name)).all()


@router.post("/warehouses", response_model=WarehouseOut)
def create_warehouse(payload: WarehouseIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Warehouse, db, payload)


@router.patch("/warehouses/{wid}", response_model=WarehouseOut)
def update_warehouse(wid: str, payload: WarehouseIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Warehouse, db, payload, item_id=wid)


@router.delete("/warehouses/{wid}", status_code=204)
def delete_warehouse(wid: str, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Warehouse, wid)
    if obj:
        db.delete(obj)
        db.commit()


@router.get("/warehouses/{wid}/zones", response_model=list[WarehouseZoneOut])
def list_zones(wid: str, db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    return db.scalars(
        select(WarehouseZone).where(WarehouseZone.warehouse_id == wid).order_by(WarehouseZone.name)
    ).all()


@router.post("/warehouses/{wid}/zones", response_model=WarehouseZoneOut)
def create_zone(wid: str, payload: WarehouseZoneIn, db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    data = payload.model_dump()
    data["warehouse_id"] = wid
    obj = WarehouseZone(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/zones/{zid}", status_code=204)
def delete_zone(zid: str, db: Session = Depends(get_db),
                _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(WarehouseZone, zid)
    if obj:
        db.delete(obj)
        db.commit()


@router.get("/warehouses/{wid}/inventory")
def warehouse_inventory(wid: str, db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    """Stock in a specific warehouse, broken down by product and zone."""
    rows = db.execute(
        select(
            StockMovement.product_id, StockMovement.zone_id,
            func.coalesce(func.sum(StockMovement.quantity), 0)
        )
        .where(StockMovement.warehouse_id == wid)
        .group_by(StockMovement.product_id, StockMovement.zone_id)
    ).all()
    items = []
    for product_id, zone_id, qty in rows:
        p = db.get(Product, product_id) if product_id else None
        z = db.get(WarehouseZone, zone_id) if zone_id else None
        items.append({
            "product_id": product_id,
            "product_name": p.name if p else "Unknown",
            "sku": p.sku if p else "",
            "zone_id": zone_id,
            "zone_name": z.name if z else "Unassigned",
            "quantity": int(qty or 0),
        })
    return {"warehouse_id": wid, "items": items}


# ============ 3. Product Categories =======================================
@router.get("/categories", response_model=list[ProductCategoryOut])
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(ProductCategory).order_by(ProductCategory.name)).all()


@router.post("/categories", response_model=ProductCategoryOut)
def create_category(payload: ProductCategoryIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(ProductCategory, db, payload)


@router.delete("/categories/{cid}", status_code=204)
def delete_category(cid: str, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(ProductCategory, cid)
    if obj:
        db.delete(obj)
        db.commit()


# ============ 4. Products / Catalog =======================================
@router.get("/products", response_model=list[ProductOut])
def list_products(q: str | None = None, category_id: str | None = None,
                  supplier_id: str | None = None, is_active: bool | None = None,
                  db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(Product).order_by(Product.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like),
                              Product.barcode.ilike(like),
                              Product.description.ilike(like)))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if supplier_id:
        stmt = stmt.where(Product.supplier_id == supplier_id)
    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    return db.scalars(stmt.limit(2000)).all()


@router.post("/products", response_model=ProductOut)
def create_product(payload: ProductIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Product, db, payload)


@router.patch("/products/{pid}", response_model=ProductOut)
def update_product(pid: str, payload: ProductIn, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Product, db, payload, item_id=pid)


@router.delete("/products/{pid}", status_code=204)
def delete_product(pid: str, db: Session = Depends(get_db),
                   _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Product, pid)
    if obj:
        db.delete(obj)
        db.commit()


# ============ 5. Barcodes =================================================
def _generate_barcode_png(value: str, barcode_type: str = "code128") -> str:
    try:
        import barcode as bc
        from barcode.writer import ImageWriter
        cls = getattr(bc, barcode_type.upper(), None) or bc.Code128
        try:
            obj = cls(value, writer=ImageWriter())
        except Exception:
            obj = bc.Code128(value, writer=ImageWriter())
        buffer = io.BytesIO()
        obj.write(buffer, options={"write_text": True, "module_height": 8.0})
        return base64.b64encode(buffer.getvalue()).decode()
    except ImportError:
        # ASCII fallback: render bars as PNG via PIL if available
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (max(120, len(value) * 12), 60), "white")
            d = ImageDraw.Draw(img)
            x = 6
            for i, ch in enumerate(value):
                width = (ord(ch) % 3) + 1
                d.rectangle([x, 5, x + width, 40], fill="black")
                x += width + 2
            d.text((6, 44), value, fill="black")
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return ""


@router.get("/products/{pid}/barcode", response_model=BarcodeOut)
def product_barcode(pid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = db.get(Product, pid)
    if not p:
        raise NotFoundError("Product not found")
    value = p.barcode or p.sku
    png = _generate_barcode_png(value, p.barcode_type or "code128")
    return BarcodeOut(sku=p.sku, barcode_value=value, png_base64=png)


@router.post("/barcode/scan")
def barcode_scan(payload: BarcodeScanIn, db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    """Look up a product by scanned barcode or SKU."""
    value = payload.value.strip()
    p = db.scalar(select(Product).where(or_(Product.barcode == value, Product.sku == value)))
    if not p:
        return {"found": False, "value": value}
    on_hand = _on_hand(db, p.id)
    return {
        "found": True,
        "product": {
            "id": p.id, "sku": p.sku, "name": p.name,
            "barcode": p.barcode, "unit_price": float(p.unit_price),
            "unit_cost": float(p.unit_cost), "on_hand": on_hand,
            "low_stock_threshold": p.low_stock_threshold,
        }
    }


@router.post("/barcode/generate", response_model=BarcodeOut)
def barcode_generate(payload: BarcodeScanIn, barcode_type: str = "code128",
                     _: User = Depends(get_current_user)):
    value = payload.value.strip()
    png = _generate_barcode_png(value, barcode_type)
    return BarcodeOut(sku=value, barcode_value=value, png_base64=png)


# ============ 6. Stock movements & on-hand ================================
@router.get("/stock", response_model=list[StockOnHandOut])
def stock_on_hand(warehouse_id: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    out = []
    for p in products:
        if warehouse_id:
            qty = db.scalar(
                select(func.coalesce(func.sum(StockMovement.quantity), 0))
                .where(StockMovement.product_id == p.id, StockMovement.warehouse_id == warehouse_id)
            ) or 0
            qty = int(qty)
        else:
            qty = _on_hand(db, p.id)
        status = "ok"
        if qty <= 0:
            status = "out"
        elif qty <= p.low_stock_threshold:
            status = "low"
        out.append(StockOnHandOut(
            product_id=p.id, sku=p.sku, name=p.name,
            on_hand=qty, low_stock_threshold=p.low_stock_threshold, status=status,
            unit_cost=p.unit_cost,
            stock_value=Decimal(str(round(float(p.unit_cost) * qty, 2))),
        ))
    return out


@router.get("/stock/movements", response_model=list[StockMovementOut])
def list_movements(product_id: str | None = None, warehouse_id: str | None = None,
                   movement_type: str | None = None,
                   db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(StockMovement).order_by(StockMovement.created_at.desc())
    if product_id:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    return db.scalars(stmt.limit(1000)).all()


@router.post("/stock/movements", response_model=StockMovementOut)
def record_movement(payload: StockMovementIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = _crud(StockMovement, db, payload)
    # Auto-create alert if stock drops below threshold
    p = db.get(Product, obj.product_id)
    if p:
        on_hand = _on_hand(db, p.id)
        if on_hand <= p.low_stock_threshold:
            alert_type = "out_of_stock" if on_hand <= 0 else "low_stock"
            existing = db.scalar(
                select(StockAlert).where(
                    StockAlert.product_id == p.id,
                    StockAlert.is_resolved.is_(False),
                    StockAlert.alert_type == alert_type,
                )
            )
            if not existing:
                db.add(StockAlert(
                    product_id=p.id, alert_type=alert_type,
                    threshold=p.low_stock_threshold, current_qty=on_hand,
                    notes=f"Auto-generated: stock dropped to {on_hand}",
                ))
                db.commit()
        else:
            # Auto-resolve open alerts
            open_alerts = db.scalars(
                select(StockAlert).where(
                    StockAlert.product_id == p.id, StockAlert.is_resolved.is_(False),
                )
            ).all()
            for a in open_alerts:
                a.is_resolved = True
                a.current_qty = on_hand
            db.commit()
    return obj


# ============ 7. Stock alerts =============================================
@router.get("/alerts", response_model=list[StockAlertOut])
def list_alerts(is_resolved: bool | None = None, db: Session = Depends(get_db),
                _: User = Depends(get_current_user)):
    stmt = select(StockAlert).order_by(StockAlert.created_at.desc())
    if is_resolved is not None:
        stmt = stmt.where(StockAlert.is_resolved == is_resolved)
    return db.scalars(stmt.limit(500)).all()


@router.post("/alerts", response_model=StockAlertOut)
def create_alert(payload: StockAlertIn, db: Session = Depends(get_db),
                 _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(StockAlert, db, payload)


@router.post("/alerts/{aid}/resolve", response_model=StockAlertOut)
def resolve_alert(aid: str, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    obj = db.get(StockAlert, aid)
    if not obj:
        raise NotFoundError("Alert not found")
    obj.is_resolved = True
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/alerts/recompute")
def recompute_alerts(db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    created = 0
    resolved = 0
    for p in products:
        on_hand = _on_hand(db, p.id)
        open_alerts = db.scalars(
            select(StockAlert).where(StockAlert.product_id == p.id, StockAlert.is_resolved.is_(False))
        ).all()
        if on_hand <= p.low_stock_threshold:
            alert_type = "out_of_stock" if on_hand <= 0 else "low_stock"
            if not any(a.alert_type == alert_type for a in open_alerts):
                db.add(StockAlert(
                    product_id=p.id, alert_type=alert_type,
                    threshold=p.low_stock_threshold, current_qty=on_hand,
                ))
                created += 1
        else:
            for a in open_alerts:
                a.is_resolved = True
                resolved += 1
    db.commit()
    return {"created": created, "resolved": resolved}


@router.get("/stock/low")
def low_stock(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    on_hand_list = stock_on_hand(warehouse_id=None, db=db, _=None)  # type: ignore
    return [s.model_dump() if hasattr(s, "model_dump") else s for s in on_hand_list if s.status in {"low", "out"}]


# ============ 8. Purchase Orders ==========================================
@router.get("/purchase-orders", response_model=list[POOut])
def list_pos(status: str | None = None, supplier_id: str | None = None,
             db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc())
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/purchase-orders", response_model=POOut)
def create_po(payload: POIn, db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    from secrets import token_hex
    po_number = payload.po_number or f"PO-{date.today().year}-{token_hex(3).upper()}"
    total = sum((Decimal(l.quantity) * l.unit_cost for l in payload.lines), Decimal("0"))
    po = PurchaseOrder(
        po_number=po_number, supplier_id=payload.supplier_id,
        status=payload.status, order_date=payload.order_date,
        expected_date=payload.expected_date,
        notes=payload.notes, total=total,
    )
    db.add(po)
    db.flush()
    for line in payload.lines:
        db.add(PurchaseOrderLine(purchase_order_id=po.id, **line.model_dump()))
    db.commit()
    db.refresh(po)
    return po


@router.get("/purchase-orders/{pid}", response_model=POOut)
def get_po(pid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    po = db.get(PurchaseOrder, pid)
    if not po:
        raise NotFoundError("Purchase order not found")
    return po


@router.get("/purchase-orders/{pid}/lines", response_model=list[POLineOut])
def po_lines(pid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == pid)).all()


@router.post("/purchase-orders/{pid}/status", response_model=POOut)
def po_status(pid: str, payload: dict, db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    po = db.get(PurchaseOrder, pid)
    if not po:
        raise NotFoundError("PO not found")
    new_status = payload.get("status", po.status)
    old_status = po.status
    po.status = new_status
    # If transitioning to received, create stock-in movements
    if new_status == "received" and old_status != "received":
        lines = db.scalars(
            select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == pid)
        ).all()
        for line in lines:
            if line.product_id and line.quantity:
                db.add(StockMovement(
                    product_id=line.product_id,
                    movement_type="in", quantity=line.quantity,
                    reference=f"PO {po.po_number}",
                ))
                line.received_quantity = line.quantity
    db.commit()
    db.refresh(po)
    return po


@router.post("/purchase-orders/{pid}/receive-line/{lid}")
def receive_line(pid: str, lid: str, payload: dict, db: Session = Depends(get_db),
                 _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    line = db.get(PurchaseOrderLine, lid)
    if not line:
        raise NotFoundError("PO line not found")
    qty = int(payload.get("quantity", 0))
    if qty > 0 and line.product_id:
        line.received_quantity += qty
        db.add(StockMovement(
            product_id=line.product_id, movement_type="in",
            quantity=qty, reference=f"PO {pid} line",
        ))
    db.commit()
    return {"ok": True, "received": line.received_quantity}


@router.delete("/purchase-orders/{pid}", status_code=204)
def delete_po(pid: str, db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(PurchaseOrder, pid)
    if obj:
        db.delete(obj)
        db.commit()


# ============ 9. Shipments =================================================
@router.get("/shipments", response_model=list[ShipmentOut])
def list_shipments(status: str | None = None, direction: str | None = None,
                   db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Shipment).order_by(Shipment.expected_date.desc().nullslast())
    if status:
        stmt = stmt.where(Shipment.status == status)
    if direction:
        stmt = stmt.where(Shipment.direction == direction)
    return db.scalars(stmt.limit(500)).all()


@router.post("/shipments", response_model=ShipmentOut)
def create_shipment(payload: ShipmentIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = _crud(Shipment, db, payload)
    # Initial creation event
    db.add(ShipmentEvent(
        shipment_id=obj.id, timestamp=datetime.now(timezone.utc),
        status="created", location=payload.origin or "",
        description=f"Shipment {obj.tracking_number} created",
    ))
    db.commit()
    return obj


@router.patch("/shipments/{sid}", response_model=ShipmentOut)
def update_shipment(sid: str, payload: ShipmentIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(Shipment, sid)
    if not obj:
        raise NotFoundError("Shipment not found")
    old_status = obj.status
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    if old_status != obj.status:
        db.add(ShipmentEvent(
            shipment_id=obj.id, timestamp=datetime.now(timezone.utc),
            status=obj.status, location="",
            description=f"Status changed: {old_status} → {obj.status}",
        ))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/shipments/{sid}", status_code=204)
def delete_shipment(sid: str, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(Shipment, sid)
    if obj:
        db.delete(obj)
        db.commit()


@router.get("/shipments/{sid}/events", response_model=list[ShipmentEventOut])
def shipment_events(sid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(
        select(ShipmentEvent).where(ShipmentEvent.shipment_id == sid).order_by(ShipmentEvent.timestamp.desc())
    ).all()


@router.post("/shipments/{sid}/events", response_model=ShipmentEventOut)
def add_shipment_event(sid: str, payload: ShipmentEventIn, db: Session = Depends(get_db),
                       _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    data = payload.model_dump()
    data["shipment_id"] = sid
    obj = ShipmentEvent(**data)
    db.add(obj)
    # update parent status
    parent = db.get(Shipment, sid)
    if parent:
        parent.status = payload.status
        if payload.status == "delivered":
            parent.delivered_date = date.today()
    db.commit()
    db.refresh(obj)
    return obj


# ============ 10. Returns & Refunds =======================================
@router.get("/returns", response_model=list[ReturnOut])
def list_returns(status: str | None = None, refund_status: str | None = None,
                 db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    stmt = select(ReturnRequest).order_by(ReturnRequest.created_at.desc())
    if status:
        stmt = stmt.where(ReturnRequest.status == status)
    if refund_status:
        stmt = stmt.where(ReturnRequest.refund_status == refund_status)
    return db.scalars(stmt.limit(500)).all()


@router.post("/returns", response_model=ReturnOut)
def create_return(payload: ReturnIn, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    from secrets import token_hex
    data = payload.model_dump()
    if not data.get("rma_number"):
        data["rma_number"] = f"RMA-{date.today().year}-{token_hex(3).upper()}"
    obj = ReturnRequest(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/returns/{rid}", response_model=ReturnOut)
def update_return(rid: str, payload: ReturnIn, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    obj = db.get(ReturnRequest, rid)
    if not obj:
        raise NotFoundError("Return not found")
    old_status = obj.status
    for k, v in payload.model_dump().items():
        if k == "rma_number" and not v:
            continue
        setattr(obj, k, v)
    # If approved & received, restock
    if old_status != "received" and obj.status == "received" and obj.product_id:
        db.add(StockMovement(
            product_id=obj.product_id, movement_type="in",
            quantity=obj.quantity, reference=f"RMA {obj.rma_number}",
            notes=f"Restock from return: {obj.reason[:80]}",
        ))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/returns/{rid}", status_code=204)
def delete_return(rid: str, db: Session = Depends(get_db),
                  _: User = Depends(require_roles(UserRole.admin))):
    obj = db.get(ReturnRequest, rid)
    if obj:
        db.delete(obj)
        db.commit()


# ============ Analytics ==================================================
@router.get("/analytics", response_model=InventoryAnalyticsOut)
def inventory_analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    products = db.scalars(select(Product)).all()
    active_products = [p for p in products if p.is_active]
    total_products = len(products)
    low: list[dict] = []
    out_of_stock = 0
    total_value = 0.0
    top_products_data = []
    for p in active_products:
        qty = _on_hand(db, p.id)
        total_value += float(p.unit_cost) * qty
        top_products_data.append({"id": p.id, "sku": p.sku, "name": p.name,
                                 "on_hand": qty, "value": round(float(p.unit_cost) * qty, 2)})
        if qty <= 0:
            out_of_stock += 1
            low.append({"product_id": p.id, "sku": p.sku, "name": p.name,
                        "on_hand": qty, "threshold": p.low_stock_threshold, "status": "out"})
        elif qty <= p.low_stock_threshold:
            low.append({"product_id": p.id, "sku": p.sku, "name": p.name,
                        "on_hand": qty, "threshold": p.low_stock_threshold, "status": "low"})

    top_products_data.sort(key=lambda x: x["value"], reverse=True)
    open_pos = db.scalar(select(func.count(PurchaseOrder.id))
                        .where(PurchaseOrder.status.in_(("draft", "sent")))) or 0
    pending_ships = db.scalar(select(func.count(Shipment.id))
                             .where(Shipment.status.in_(("pending", "in_transit")))) or 0
    pending_returns = db.scalar(select(func.count(ReturnRequest.id))
                               .where(ReturnRequest.status == "requested")) or 0
    total_warehouses = db.scalar(select(func.count(Warehouse.id))) or 0
    total_suppliers = db.scalar(select(func.count(Supplier.id))) or 0

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    movements_recent = db.scalar(
        select(func.count(StockMovement.id)).where(StockMovement.created_at >= thirty_days_ago)
    ) or 0

    by_type_q = db.execute(
        select(StockMovement.movement_type, func.count(StockMovement.id))
        .group_by(StockMovement.movement_type)
    ).all()
    by_type = {t: c for t, c in by_type_q}

    # Inventory turnover: cost of goods sold (out movements) / avg inventory
    cogs_qty = db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(StockMovement.movement_type == "out")
    ) or 0
    turnover = round(abs(float(cogs_qty)) / max(total_value, 1) * 100, 2) if total_value else 0.0

    refund_total = db.scalar(
        select(func.coalesce(func.sum(ReturnRequest.refund_amount), 0))
    ) or 0

    return InventoryAnalyticsOut(
        total_products=total_products,
        active_products=len(active_products),
        low_stock_count=len(low) - out_of_stock,
        out_of_stock_count=out_of_stock,
        low_stock_items=low,
        total_stock_value=Decimal(str(round(total_value, 2))),
        open_purchase_orders=open_pos,
        pending_shipments=pending_ships,
        pending_returns=pending_returns,
        total_warehouses=total_warehouses,
        total_suppliers=total_suppliers,
        movements_last_30_days=movements_recent,
        top_products=top_products_data[:10],
        movements_by_type=by_type,
        inventory_turnover=turnover,
        refund_total=Decimal(str(refund_total)),
    )
