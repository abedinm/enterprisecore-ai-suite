from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Supplier(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(180), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(80))
    contact_person: Mapped[str | None] = mapped_column(String(180))
    address: Mapped[str | None] = mapped_column(Text)
    tax_id: Mapped[str | None] = mapped_column(String(80))
    payment_terms: Mapped[str] = mapped_column(String(80), default="Net 30")
    rating: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Warehouse(IdMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(160), index=True)
    code: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str | None] = mapped_column(Text)
    manager: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(80))
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WarehouseZone(IdMixin, TimestampMixin, Base):
    warehouse_id: Mapped[str] = mapped_column(ForeignKey("warehouses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    aisle: Mapped[str] = mapped_column(String(20), default="")
    rack: Mapped[str] = mapped_column(String(20), default="")
    bin: Mapped[str] = mapped_column(String(20), default="")
    capacity: Mapped[int] = mapped_column(Integer, default=0)


class ProductCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "product_categories"

    name: Mapped[str] = mapped_column(String(120), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("product_categories.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(Text, default="")


class Product(IdMixin, TimestampMixin, Base):
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("product_categories.id", ondelete="SET NULL"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=0)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=0)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode_type: Mapped[str] = mapped_column(String(20), default="code128")
    unit_of_measure: Mapped[str] = mapped_column(String(20), default="ea")
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    image_url: Mapped[str | None] = mapped_column(String(500))
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StockMovement(IdMixin, TimestampMixin, Base):
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[str | None] = mapped_column(ForeignKey("warehouses.id", ondelete="SET NULL"))
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("warehouse_zones.id", ondelete="SET NULL"))
    movement_type: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default="")


class PurchaseOrder(IdMixin, TimestampMixin, Base):
    po_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40), default="draft")
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


class PurchaseOrderLine(IdMixin, TimestampMixin, Base):
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    received_quantity: Mapped[int] = mapped_column(Integer, default=0)


class Shipment(IdMixin, TimestampMixin, Base):
    tracking_number: Mapped[str] = mapped_column(String(120), index=True)
    carrier: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    direction: Mapped[str] = mapped_column(String(20), default="inbound")
    purchase_order_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_orders.id", ondelete="SET NULL"))
    ship_date: Mapped[date | None] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    delivered_date: Mapped[date | None] = mapped_column(Date)
    origin: Mapped[str | None] = mapped_column(String(255))
    destination: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default="")


class ShipmentEvent(IdMixin, TimestampMixin, Base):
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")


class ReturnRequest(IdMixin, TimestampMixin, Base):
    rma_number: Mapped[str] = mapped_column(String(60), index=True, default="")
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    customer_id: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="requested")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    refund_status: Mapped[str] = mapped_column(String(40), default="pending")
    return_date: Mapped[date | None] = mapped_column(Date)


class StockAlert(IdMixin, TimestampMixin, Base):
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(40), default="low_stock")
    threshold: Mapped[int] = mapped_column(Integer, default=0)
    current_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
