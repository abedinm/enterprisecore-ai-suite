export type Supplier = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  contact_person: string | null;
  address: string | null;
  tax_id: string | null;
  payment_terms: string;
  rating: number;
  lead_time_days: number;
  is_active: boolean;
  notes: string;
};

export type Warehouse = {
  id: string;
  name: string;
  code: string;
  address: string | null;
  manager: string | null;
  phone: string | null;
  capacity: number;
  is_active: boolean;
};

export type WarehouseZone = {
  id: string;
  warehouse_id: string;
  name: string;
  aisle: string;
  rack: string;
  bin: string;
  capacity: number;
};

export type ProductCategory = {
  id: string;
  name: string;
  parent_id: string | null;
  description: string;
};

export type Product = {
  id: string;
  sku: string;
  name: string;
  description: string;
  category_id: string | null;
  unit_cost: string;
  unit_price: string;
  low_stock_threshold: number;
  reorder_quantity: number;
  barcode: string | null;
  barcode_type: string;
  unit_of_measure: string;
  weight_kg: string;
  image_url: string | null;
  supplier_id: string | null;
  is_active: boolean;
};

export type StockMovement = {
  id: string;
  product_id: string;
  warehouse_id: string | null;
  zone_id: string | null;
  movement_type: string;
  quantity: number;
  reference: string | null;
  notes: string;
};

export type StockOnHand = {
  product_id: string;
  sku: string;
  name: string;
  on_hand: number;
  low_stock_threshold: number;
  status: 'ok' | 'low' | 'out';
  unit_cost: string;
  stock_value: string;
};

export type PurchaseOrder = {
  id: string;
  po_number: string;
  supplier_id: string | null;
  status: string;
  order_date: string;
  expected_date: string | null;
  total: string;
  notes: string;
};

export type POLine = {
  id: string;
  product_id: string | null;
  description: string;
  quantity: number;
  unit_cost: string;
  received_quantity: number;
};

export type Shipment = {
  id: string;
  tracking_number: string;
  carrier: string | null;
  status: string;
  direction: string;
  purchase_order_id: string | null;
  ship_date: string | null;
  expected_date: string | null;
  delivered_date: string | null;
  origin: string | null;
  destination: string | null;
  notes: string;
};

export type ShipmentEvent = {
  id: string;
  shipment_id: string;
  timestamp: string;
  location: string | null;
  status: string;
  description: string;
};

export type ReturnRequest = {
  id: string;
  rma_number: string;
  product_id: string | null;
  customer_id: string | null;
  quantity: number;
  reason: string;
  status: string;
  refund_amount: string;
  refund_status: string;
  return_date: string | null;
};

export type StockAlert = {
  id: string;
  product_id: string;
  alert_type: string;
  threshold: number;
  current_qty: number;
  is_resolved: boolean;
  notes: string;
};

export const PO_STATUSES = ['draft', 'sent', 'partial', 'received', 'cancelled'] as const;
export const SHIPMENT_STATUSES = ['pending', 'in_transit', 'delivered', 'delayed', 'cancelled'] as const;
export const RETURN_STATUSES = ['requested', 'approved', 'received', 'refunded', 'rejected'] as const;
export const REFUND_STATUSES = ['pending', 'processed', 'refunded', 'denied'] as const;
export const STOCK_MOVEMENT_TYPES = ['in', 'out', 'adjustment', 'transfer'] as const;

export const STATUS_BADGE: Record<string, string> = {
  draft: 'ec-badge-blue', sent: 'ec-badge-amber', partial: 'ec-badge-amber',
  received: 'ec-badge-green', cancelled: 'ec-badge-rose',
  pending: 'ec-badge-amber', in_transit: 'ec-badge-blue', delivered: 'ec-badge-green',
  delayed: 'ec-badge-rose',
  requested: 'ec-badge-amber', approved: 'ec-badge-blue', refunded: 'ec-badge-green',
  rejected: 'ec-badge-rose',
  processed: 'ec-badge-blue', denied: 'ec-badge-rose',
  ok: 'ec-badge-green', low: 'ec-badge-amber', out: 'ec-badge-rose',
};
