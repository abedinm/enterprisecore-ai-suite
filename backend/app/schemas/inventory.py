"""Inventory & supply-chain pydantic schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: str | None = None
    phone: str | None = None
    contact_person: str | None = None
    address: str | None = None
    tax_id: str | None = None
    payment_terms: str = "Net 30"
    rating: int = 0
    lead_time_days: int = 7
    is_active: bool = True
    notes: str = ""


class SupplierOut(ORMModel):
    id: str
    name: str
    email: str | None
    phone: str | None
    contact_person: str | None
    address: str | None
    tax_id: str | None
    payment_terms: str
    rating: int
    lead_time_days: int
    is_active: bool
    notes: str


class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = ""
    address: str | None = None
    manager: str | None = None
    phone: str | None = None
    capacity: int = 0
    is_active: bool = True


class WarehouseOut(ORMModel):
    id: str
    name: str
    code: str
    address: str | None
    manager: str | None
    phone: str | None
    capacity: int
    is_active: bool


class WarehouseZoneIn(BaseModel):
    warehouse_id: str
    name: str
    aisle: str = ""
    rack: str = ""
    bin: str = ""
    capacity: int = 0


class WarehouseZoneOut(ORMModel):
    id: str
    warehouse_id: str
    name: str
    aisle: str
    rack: str
    bin: str
    capacity: int


class ProductCategoryIn(BaseModel):
    name: str
    parent_id: str | None = None
    description: str = ""


class ProductCategoryOut(ORMModel):
    id: str
    name: str
    parent_id: str | None
    description: str


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str
    description: str = ""
    category_id: str | None = None
    unit_cost: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    low_stock_threshold: int = 0
    reorder_quantity: int = 0
    barcode: str | None = None
    barcode_type: str = "code128"
    unit_of_measure: str = "ea"
    weight_kg: Decimal = Decimal("0")
    image_url: str | None = None
    supplier_id: str | None = None
    is_active: bool = True


class ProductOut(ORMModel):
    id: str
    sku: str
    name: str
    description: str
    category_id: str | None
    unit_cost: Decimal
    unit_price: Decimal
    low_stock_threshold: int
    reorder_quantity: int
    barcode: str | None
    barcode_type: str
    unit_of_measure: str
    weight_kg: Decimal
    image_url: str | None
    supplier_id: str | None
    is_active: bool


class StockMovementIn(BaseModel):
    product_id: str
    warehouse_id: str | None = None
    zone_id: str | None = None
    movement_type: str  # in|out|adjustment|transfer
    quantity: int
    reference: str | None = None
    notes: str = ""


class StockMovementOut(ORMModel):
    id: str
    product_id: str
    warehouse_id: str | None
    zone_id: str | None
    movement_type: str
    quantity: int
    reference: str | None
    notes: str


class POLineIn(BaseModel):
    product_id: str | None = None
    description: str = ""
    quantity: int = 1
    unit_cost: Decimal = Decimal("0")
    received_quantity: int = 0


class POIn(BaseModel):
    po_number: str | None = None
    supplier_id: str | None = None
    status: str = "draft"
    order_date: date
    expected_date: date | None = None
    notes: str = ""
    lines: list[POLineIn] = []


class POLineOut(ORMModel):
    id: str
    product_id: str | None
    description: str
    quantity: int
    unit_cost: Decimal
    received_quantity: int


class POOut(ORMModel):
    id: str
    po_number: str
    supplier_id: str | None
    status: str
    order_date: date
    expected_date: date | None
    total: Decimal
    notes: str


class ShipmentIn(BaseModel):
    tracking_number: str
    carrier: str | None = None
    status: str = "pending"
    direction: str = "inbound"
    purchase_order_id: str | None = None
    ship_date: date | None = None
    expected_date: date | None = None
    delivered_date: date | None = None
    origin: str | None = None
    destination: str | None = None
    notes: str = ""


class ShipmentOut(ORMModel):
    id: str
    tracking_number: str
    carrier: str | None
    status: str
    direction: str
    purchase_order_id: str | None
    ship_date: date | None
    expected_date: date | None
    delivered_date: date | None
    origin: str | None
    destination: str | None
    notes: str


class ShipmentEventIn(BaseModel):
    shipment_id: str
    timestamp: datetime
    location: str | None = None
    status: str
    description: str = ""


class ShipmentEventOut(ORMModel):
    id: str
    shipment_id: str
    timestamp: datetime
    location: str | None
    status: str
    description: str


class ReturnIn(BaseModel):
    rma_number: str = ""
    product_id: str | None = None
    customer_id: str | None = None
    quantity: int = 1
    reason: str = ""
    status: str = "requested"
    refund_amount: Decimal = Decimal("0")
    refund_status: str = "pending"
    return_date: date | None = None


class ReturnOut(ORMModel):
    id: str
    rma_number: str
    product_id: str | None
    customer_id: str | None
    quantity: int
    reason: str
    status: str
    refund_amount: Decimal
    refund_status: str
    return_date: date | None


class StockAlertIn(BaseModel):
    product_id: str
    alert_type: str = "low_stock"
    threshold: int = 0
    current_qty: int = 0
    notes: str = ""


class StockAlertOut(ORMModel):
    id: str
    product_id: str
    alert_type: str
    threshold: int
    current_qty: int
    is_resolved: bool
    notes: str


class InventoryAnalyticsOut(BaseModel):
    total_products: int
    active_products: int
    low_stock_count: int
    out_of_stock_count: int
    low_stock_items: list[dict]
    total_stock_value: Decimal
    open_purchase_orders: int
    pending_shipments: int
    pending_returns: int
    total_warehouses: int
    total_suppliers: int
    movements_last_30_days: int
    top_products: list[dict]
    movements_by_type: dict[str, int]
    inventory_turnover: float
    refund_total: Decimal


class BarcodeOut(BaseModel):
    sku: str
    barcode_value: str
    png_base64: str


class StockOnHandOut(BaseModel):
    product_id: str
    sku: str
    name: str
    on_hand: int
    low_stock_threshold: int
    status: str  # ok | low | out
    unit_cost: Decimal
    stock_value: Decimal


class BarcodeScanIn(BaseModel):
    value: str
