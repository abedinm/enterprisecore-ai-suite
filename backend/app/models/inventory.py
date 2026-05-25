from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import UniqueConstraint

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class Supplier(IdMixin, TenantMixin, TimestampMixin, Base):
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


class Warehouse(IdMixin, TenantMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(160), index=True)
    code: Mapped[str] = mapped_column(String(40), default="")
    address: Mapped[str | None] = mapped_column(Text)
    manager: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(80))
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WarehouseZone(IdMixin, TenantMixin, TimestampMixin, Base):
    warehouse_id: Mapped[str] = mapped_column(ForeignKey("warehouses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    aisle: Mapped[str] = mapped_column(String(20), default="")
    rack: Mapped[str] = mapped_column(String(20), default="")
    bin: Mapped[str] = mapped_column(String(20), default="")
    capacity: Mapped[int] = mapped_column(Integer, default=0)


class ProductCategory(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "product_categories"

    name: Mapped[str] = mapped_column(String(120), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("product_categories.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(Text, default="")


class Product(IdMixin, TenantMixin, TimestampMixin, Base):
    sku: Mapped[str] = mapped_column(String(80), index=True)
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
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),)


class StockMovement(IdMixin, TenantMixin, TimestampMixin, Base):
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    warehouse_id: Mapped[str | None] = mapped_column(ForeignKey("warehouses.id", ondelete="SET NULL"))
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("warehouse_zones.id", ondelete="SET NULL"))
    movement_type: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default="")


class PurchaseOrder(IdMixin, TenantMixin, TimestampMixin, Base):
    po_number: Mapped[str] = mapped_column(String(60), index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40), default="draft")
    order_date: Mapped[date] = mapped_column(Date)
    expected_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("tenant_id", "po_number", name="uq_purchase_orders_tenant_number"),)


class PurchaseOrderLine(IdMixin, TenantMixin, TimestampMixin, Base):
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    received_quantity: Mapped[int] = mapped_column(Integer, default=0)


class Shipment(IdMixin, TenantMixin, TimestampMixin, Base):
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


class ShipmentEvent(IdMixin, TenantMixin, TimestampMixin, Base):
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")


class ReturnRequest(IdMixin, TenantMixin, TimestampMixin, Base):
    rma_number: Mapped[str] = mapped_column(String(60), index=True, default="")
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    customer_id: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="requested")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    refund_status: Mapped[str] = mapped_column(String(40), default="pending")
    return_date: Mapped[date | None] = mapped_column(Date)


class StockAlert(IdMixin, TenantMixin, TimestampMixin, Base):
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(40), default="low_stock")
    threshold: Mapped[int] = mapped_column(Integer, default=0)
    current_qty: Mapped[int] = mapped_column(Integer, default=0)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
