"""Inventory & supply-chain endpoints."""
from __future__ import annotations

import base64
import io
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.inventory import (
    Product, PurchaseOrder, PurchaseOrderLine, ReturnRequest, Shipment,
    StockMovement, Supplier, Warehouse,
)
from app.models.user import User, UserRole
from app.schemas.inventory import (
    BarcodeOut, InventoryAnalyticsOut, POIn, POLineOut, POOut, ProductIn,
    ProductOut, ReturnIn, ReturnOut, ShipmentIn, ShipmentOut, StockMovementIn,
    StockMovementOut, StockOnHandOut, SupplierIn, SupplierOut, WarehouseIn,
    WarehouseOut,
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


# ---- Suppliers ----------------------------------------------------------
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(q: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Supplier).order_by(Supplier.name)
    if q:
        stmt = stmt.where(Supplier.name.ilike(f"%{q}%"))
    return db.scalars(stmt.limit(500)).all()


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(payload: SupplierIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Supplier, db, payload)


# ---- Warehouses ---------------------------------------------------------
@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Warehouse).order_by(Warehouse.name)).all()


@router.post("/warehouses", response_model=WarehouseOut)
def create_warehouse(payload: WarehouseIn, db: Session = Depends(get_db),
                     _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Warehouse, db, payload)


# ---- Products / Catalog -------------------------------------------------
@router.get("/products", response_model=list[ProductOut])
def list_products(q: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(Product).order_by(Product.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like)))
    return db.scalars(stmt.limit(1000)).all()


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


@router.get("/products/{pid}/barcode", response_model=BarcodeOut)
def product_barcode(pid: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = db.get(Product, pid)
    if not p:
        raise NotFoundError("Product not found")
    try:
        import barcode  # python-barcode
        from barcode.writer import ImageWriter

        value = p.barcode or p.sku
        code = barcode.Code128(value, writer=ImageWriter())
        buffer = io.BytesIO()
        code.write(buffer, options={"write_text": True, "module_height": 8.0})
        return BarcodeOut(sku=p.sku, barcode_value=value,
                         png_base64=base64.b64encode(buffer.getvalue()).decode())
    except Exception as e:
        raise NotFoundError(f"Could not generate barcode: {e}")


# ---- Stock movements & on-hand -----------------------------------------
def _on_hand(db: Session, product_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(StockMovement.product_id == product_id)
    )
    return int(total or 0)


@router.get("/stock", response_model=list[StockOnHandOut])
def stock_on_hand(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    products = db.scalars(select(Product)).all()
    out = []
    for p in products:
        qty = _on_hand(db, p.id)
        status = "ok"
        if qty <= 0:
            status = "out"
        elif qty <= p.low_stock_threshold:
            status = "low"
        out.append(StockOnHandOut(
            product_id=p.id, sku=p.sku, name=p.name,
            on_hand=qty, low_stock_threshold=p.low_stock_threshold, status=status,
        ))
    return out


@router.get("/stock/movements", response_model=list[StockMovementOut])
def list_movements(product_id: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(StockMovement).order_by(StockMovement.created_at.desc())
    if product_id:
        stmt = stmt.where(StockMovement.product_id == product_id)
    return db.scalars(stmt.limit(500)).all()


@router.post("/stock/movements", response_model=StockMovementOut)
def record_movement(payload: StockMovementIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(StockMovement, db, payload)


@router.get("/stock/low")
def low_stock(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    on_hand_list = stock_on_hand(db=db, _=None)
    return [s for s in on_hand_list if s.status in {"low", "out"}]


# ---- Purchase Orders ----------------------------------------------------
@router.get("/purchase-orders", response_model=list[POOut])
def list_pos(status: str | None = None, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.order_date.desc())
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    return db.scalars(stmt.limit(500)).all()


@router.post("/purchase-orders", response_model=POOut)
def create_po(payload: POIn, db: Session = Depends(get_db),
              _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    from decimal import Decimal as D
    from secrets import token_hex
    po_number = payload.po_number or f"PO-{date.today().year}-{token_hex(3).upper()}"
    total = sum((D(l.quantity) * l.unit_cost for l in payload.lines), D("0"))
    po = PurchaseOrder(
        po_number=po_number, supplier_id=payload.supplier_id,
        status=payload.status, order_date=payload.order_date, total=total,
    )
    db.add(po)
    db.flush()
    for line in payload.lines:
        db.add(PurchaseOrderLine(purchase_order_id=po.id, **line.model_dump()))
    db.commit()
    db.refresh(po)
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
    po.status = payload.get("status", po.status)
    db.commit()
    db.refresh(po)
    return po


# ---- Shipments ----------------------------------------------------------
@router.get("/shipments", response_model=list[ShipmentOut])
def list_shipments(status: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(get_current_user)):
    stmt = select(Shipment).order_by(Shipment.expected_date.desc().nullslast())
    if status:
        stmt = stmt.where(Shipment.status == status)
    return db.scalars(stmt.limit(500)).all()


@router.post("/shipments", response_model=ShipmentOut)
def create_shipment(payload: ShipmentIn, db: Session = Depends(get_db),
                    _: User = Depends(require_roles(UserRole.admin, UserRole.manager))):
    return _crud(Shipment, db, payload)


# ---- Returns ------------------------------------------------------------
@router.get("/returns", response_model=list[ReturnOut])
def list_returns(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(ReturnRequest).order_by(ReturnRequest.created_at.desc())).all()


@router.post("/returns", response_model=ReturnOut)
def create_return(payload: ReturnIn, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return _crud(ReturnRequest, db, payload)


# ---- Analytics ----------------------------------------------------------
@router.get("/analytics", response_model=InventoryAnalyticsOut)
def inventory_analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    products = db.scalars(select(Product)).all()
    total_products = len(products)
    low = []
    total_value = 0
    for p in products:
        qty = _on_hand(db, p.id)
        total_value += float(p.unit_cost) * qty
        if qty <= p.low_stock_threshold:
            low.append({"product_id": p.id, "sku": p.sku, "name": p.name, "on_hand": qty,
                        "threshold": p.low_stock_threshold})
    open_pos = db.scalar(select(func.count(PurchaseOrder.id)).where(PurchaseOrder.status.in_(("draft", "sent")))) or 0
    pending_ships = db.scalar(select(func.count(Shipment.id)).where(Shipment.status == "pending")) or 0
    from decimal import Decimal as D
    return InventoryAnalyticsOut(
        total_products=total_products,
        low_stock_count=len(low),
        low_stock_items=low,
        total_stock_value=D(str(round(total_value, 2))),
        open_purchase_orders=open_pos,
        pending_shipments=pending_ships,
    )
