"""Inventory & supply-chain pydantic schemas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: str | None = None
    phone: str | None = None


class SupplierOut(ORMModel):
    id: str
    name: str
    email: str | None
    phone: str | None


class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    address: str | None = None


class WarehouseOut(ORMModel):
    id: str
    name: str
    address: str | None


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str
    description: str = ""
    unit_cost: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    low_stock_threshold: int = 0
    barcode: str | None = None


class ProductOut(ORMModel):
    id: str
    sku: str
    name: str
    description: str
    unit_cost: Decimal
    unit_price: Decimal
    low_stock_threshold: int
    barcode: str | None


class StockMovementIn(BaseModel):
    product_id: str
    warehouse_id: str | None = None
    movement_type: str  # in|out|adjustment|transfer
    quantity: int
    reference: str | None = None


class StockMovementOut(ORMModel):
    id: str
    product_id: str
    warehouse_id: str | None
    movement_type: str
    quantity: int
    reference: str | None


class POLineIn(BaseModel):
    product_id: str | None = None
    quantity: int = 1
    unit_cost: Decimal = Decimal("0")


class POIn(BaseModel):
    po_number: str | None = None
    supplier_id: str | None = None
    status: str = "draft"
    order_date: date
    lines: list[POLineIn] = []


class POLineOut(ORMModel):
    id: str
    product_id: str | None
    quantity: int
    unit_cost: Decimal


class POOut(ORMModel):
    id: str
    po_number: str
    supplier_id: str | None
    status: str
    order_date: date
    total: Decimal


class ShipmentIn(BaseModel):
    tracking_number: str
    carrier: str | None = None
    status: str = "pending"
    expected_date: date | None = None


class ShipmentOut(ORMModel):
    id: str
    tracking_number: str
    carrier: str | None
    status: str
    expected_date: date | None


class ReturnIn(BaseModel):
    product_id: str | None = None
    quantity: int = 1
    reason: str = ""


class ReturnOut(ORMModel):
    id: str
    product_id: str | None
    quantity: int
    reason: str
    status: str


class InventoryAnalyticsOut(BaseModel):
    total_products: int
    low_stock_count: int
    low_stock_items: list[dict]
    total_stock_value: Decimal
    open_purchase_orders: int
    pending_shipments: int


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
