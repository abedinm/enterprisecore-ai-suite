"""Project Management + Inventory expansion — full schema for 20 tools.

Brings the projects and inventory tables in sync with the rebuilt ORM models:

PROJECTS:
- ``projects``: + color, progress
- ``tasks``: + sprint_id, start_date, estimated_hours, actual_hours, story_points, position, tags
- ``sprints``: + status, capacity_points
- ``milestones``: + description, progress
- ``time_entries``: + notes, is_billable
- ``meetings``: + ends_at, location, agenda, attendees, status
- ``meeting_minutes``: + decisions, action_items
- NEW tables: ``resources``, ``resource_allocations``, ``task_dependencies``

INVENTORY:
- ``suppliers``: + contact_person, address, tax_id, payment_terms, rating, lead_time_days, is_active, notes
- ``warehouses``: + code, manager, phone, capacity, is_active
- ``products``: + category_id, reorder_quantity, barcode_type, unit_of_measure, weight_kg, image_url, supplier_id, is_active
- ``stock_movements``: + zone_id, notes
- ``purchase_orders``: + expected_date, notes
- ``purchase_order_lines``: + description, received_quantity
- ``shipments``: + direction, purchase_order_id, ship_date, delivered_date, origin, destination, notes
- ``return_requests``: + rma_number, customer_id, refund_amount, refund_status, return_date
- NEW tables: ``warehouse_zones``, ``product_categories``, ``shipment_events``, ``stock_alerts``

The migration is idempotent: it inspects the live database and only applies
the deltas that haven't been applied yet.

Revision ID: 0004_pm_inventory_expansion
Revises: 0003_ai_coding_module
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_pm_inventory_expansion"
down_revision: str | None = "0003_ai_coding_module"
branch_labels: str | None = None
depends_on: str | None = None


# ---- Idempotent helpers -------------------------------------------------
def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _add_col(table: str, column: sa.Column) -> None:
    if _has_table(table) and not _has_column(table, column.name):
        op.add_column(table, column)


# ---- Upgrade -------------------------------------------------------------
def upgrade() -> None:
    # Projects table additions
    _add_col("projects", sa.Column("color", sa.String(16), nullable=False, server_default="#4F46E5"))
    _add_col("projects", sa.Column("progress", sa.Integer, nullable=False, server_default="0"))

    # Tasks table additions
    _add_col("tasks", sa.Column("sprint_id", sa.String(32), nullable=True))
    _add_col("tasks", sa.Column("start_date", sa.Date, nullable=True))
    _add_col("tasks", sa.Column("estimated_hours", sa.Numeric(8, 2), nullable=False, server_default="0"))
    _add_col("tasks", sa.Column("actual_hours", sa.Numeric(8, 2), nullable=False, server_default="0"))
    _add_col("tasks", sa.Column("story_points", sa.Integer, nullable=False, server_default="0"))
    _add_col("tasks", sa.Column("position", sa.Integer, nullable=False, server_default="0"))
    _add_col("tasks", sa.Column("tags", sa.String(255), nullable=False, server_default=""))

    # Sprints additions
    _add_col("sprints", sa.Column("status", sa.String(40), nullable=False, server_default="planned"))
    _add_col("sprints", sa.Column("capacity_points", sa.Integer, nullable=False, server_default="0"))

    # Milestones additions
    _add_col("milestones", sa.Column("description", sa.Text, nullable=False, server_default=""))
    _add_col("milestones", sa.Column("progress", sa.Integer, nullable=False, server_default="0"))

    # TimeEntries additions
    _add_col("time_entries", sa.Column("notes", sa.Text, nullable=False, server_default=""))
    _add_col("time_entries", sa.Column("is_billable", sa.Boolean, nullable=False, server_default=sa.text("1")))

    # Meetings additions
    _add_col("meetings", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    _add_col("meetings", sa.Column("location", sa.String(255), nullable=True))
    _add_col("meetings", sa.Column("agenda", sa.Text, nullable=False, server_default=""))
    _add_col("meetings", sa.Column("attendees", sa.Text, nullable=False, server_default=""))
    _add_col("meetings", sa.Column("status", sa.String(40), nullable=False, server_default="scheduled"))

    # MeetingMinutes additions
    _add_col("meeting_minutes", sa.Column("decisions", sa.Text, nullable=False, server_default=""))
    _add_col("meeting_minutes", sa.Column("action_items", sa.Text, nullable=False, server_default=""))

    # NEW projects tables
    if not _has_table("resources"):
        op.create_table(
            "resources",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("name", sa.String(180), nullable=False, index=True),
            sa.Column("role", sa.String(80), nullable=False, server_default=""),
            sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False, server_default="0"),
            sa.Column("capacity_hours_per_week", sa.Numeric(6, 2), nullable=False, server_default="40"),
            sa.Column("skills", sa.Text, nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table("resource_allocations"):
        op.create_table(
            "resource_allocations",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("resource_id", sa.String(32), sa.ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=False),
            sa.Column("allocation_pct", sa.Numeric(5, 2), nullable=False, server_default="100"),
            sa.Column("notes", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table("task_dependencies"):
        op.create_table(
            "task_dependencies",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("task_id", sa.String(32), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("depends_on_task_id", sa.String(32), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("dep_type", sa.String(20), nullable=False, server_default="finish_to_start"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # Suppliers additions
    _add_col("suppliers", sa.Column("contact_person", sa.String(180), nullable=True))
    _add_col("suppliers", sa.Column("address", sa.Text, nullable=True))
    _add_col("suppliers", sa.Column("tax_id", sa.String(80), nullable=True))
    _add_col("suppliers", sa.Column("payment_terms", sa.String(80), nullable=False, server_default="Net 30"))
    _add_col("suppliers", sa.Column("rating", sa.Integer, nullable=False, server_default="0"))
    _add_col("suppliers", sa.Column("lead_time_days", sa.Integer, nullable=False, server_default="7"))
    _add_col("suppliers", sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")))
    _add_col("suppliers", sa.Column("notes", sa.Text, nullable=False, server_default=""))

    # Warehouses additions
    _add_col("warehouses", sa.Column("code", sa.String(40), nullable=False, server_default=""))
    _add_col("warehouses", sa.Column("manager", sa.String(160), nullable=True))
    _add_col("warehouses", sa.Column("phone", sa.String(80), nullable=True))
    _add_col("warehouses", sa.Column("capacity", sa.Integer, nullable=False, server_default="0"))
    _add_col("warehouses", sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")))

    # Products additions
    _add_col("products", sa.Column("category_id", sa.String(32), nullable=True))
    _add_col("products", sa.Column("reorder_quantity", sa.Integer, nullable=False, server_default="0"))
    _add_col("products", sa.Column("barcode_type", sa.String(20), nullable=False, server_default="code128"))
    _add_col("products", sa.Column("unit_of_measure", sa.String(20), nullable=False, server_default="ea"))
    _add_col("products", sa.Column("weight_kg", sa.Numeric(10, 3), nullable=False, server_default="0"))
    _add_col("products", sa.Column("image_url", sa.String(500), nullable=True))
    _add_col("products", sa.Column("supplier_id", sa.String(32), nullable=True))
    _add_col("products", sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")))

    # Stock movements additions
    _add_col("stock_movements", sa.Column("zone_id", sa.String(32), nullable=True))
    _add_col("stock_movements", sa.Column("notes", sa.Text, nullable=False, server_default=""))

    # Purchase orders additions
    _add_col("purchase_orders", sa.Column("expected_date", sa.Date, nullable=True))
    _add_col("purchase_orders", sa.Column("notes", sa.Text, nullable=False, server_default=""))

    # PO lines additions
    _add_col("purchase_order_lines", sa.Column("description", sa.String(255), nullable=False, server_default=""))
    _add_col("purchase_order_lines", sa.Column("received_quantity", sa.Integer, nullable=False, server_default="0"))

    # Shipments additions
    _add_col("shipments", sa.Column("direction", sa.String(20), nullable=False, server_default="inbound"))
    _add_col("shipments", sa.Column("purchase_order_id", sa.String(32), nullable=True))
    _add_col("shipments", sa.Column("ship_date", sa.Date, nullable=True))
    _add_col("shipments", sa.Column("delivered_date", sa.Date, nullable=True))
    _add_col("shipments", sa.Column("origin", sa.String(255), nullable=True))
    _add_col("shipments", sa.Column("destination", sa.String(255), nullable=True))
    _add_col("shipments", sa.Column("notes", sa.Text, nullable=False, server_default=""))

    # Returns additions
    _add_col("return_requests", sa.Column("rma_number", sa.String(60), nullable=False, server_default=""))
    _add_col("return_requests", sa.Column("customer_id", sa.String(64), nullable=True))
    _add_col("return_requests", sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    _add_col("return_requests", sa.Column("refund_status", sa.String(40), nullable=False, server_default="pending"))
    _add_col("return_requests", sa.Column("return_date", sa.Date, nullable=True))

    # NEW inventory tables
    if not _has_table("product_categories"):
        op.create_table(
            "product_categories",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, index=True),
            sa.Column("parent_id", sa.String(32), sa.ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table("warehouse_zones"):
        op.create_table(
            "warehouse_zones",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("warehouse_id", sa.String(32), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("aisle", sa.String(20), nullable=False, server_default=""),
            sa.Column("rack", sa.String(20), nullable=False, server_default=""),
            sa.Column("bin", sa.String(20), nullable=False, server_default=""),
            sa.Column("capacity", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table("shipment_events"):
        op.create_table(
            "shipment_events",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("shipment_id", sa.String(32), sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("status", sa.String(80), nullable=False),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _has_table("stock_alerts"):
        op.create_table(
            "stock_alerts",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("product_id", sa.String(32), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("alert_type", sa.String(40), nullable=False, server_default="low_stock"),
            sa.Column("threshold", sa.Integer, nullable=False, server_default="0"),
            sa.Column("current_qty", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_resolved", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("notes", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    # Drop new tables (existing tables keep their columns — SQLite doesn't drop them easily)
    for table in ("stock_alerts", "shipment_events", "warehouse_zones", "product_categories",
                  "task_dependencies", "resource_allocations", "resources"):
        if _has_table(table):
            op.drop_table(table)
