import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ArrowDown, ArrowUp, ArrowRightLeft, RotateCw, Plus } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';
import { Product, StockMovement, StockOnHand, Warehouse, STATUS_BADGE, STOCK_MOVEMENT_TYPES } from './types';

export function StockManagerTab() {
  const qc = useQueryClient();
  const [warehouseId, setWarehouseId] = useState<string>('');
  const [showMove, setShowMove] = useState(false);

  const warehouses = useQuery({
    queryKey: ['inventory', 'warehouses'],
    queryFn: async () => (await api.get<Warehouse[]>('/inventory/warehouses')).data,
  });
  const stock = useQuery({
    queryKey: ['inventory', 'stock', warehouseId],
    queryFn: async () => (await api.get<StockOnHand[]>('/inventory/stock', {
      params: warehouseId ? { warehouse_id: warehouseId } : {},
    })).data,
  });
  const products = useQuery({
    queryKey: ['inventory', 'products'],
    queryFn: async () => (await api.get<Product[]>('/inventory/products')).data,
  });
  const movements = useQuery({
    queryKey: ['inventory', 'movements'],
    queryFn: async () => (await api.get<StockMovement[]>('/inventory/stock/movements')).data,
  });

  const totalValue = (stock.data ?? []).reduce((s, x) => s + parseFloat(x.stock_value), 0);
  const totalUnits = (stock.data ?? []).reduce((s, x) => s + x.on_hand, 0);
  const lowCount = (stock.data ?? []).filter((s) => s.status === 'low').length;
  const outCount = (stock.data ?? []).filter((s) => s.status === 'out').length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Stock Manager</p>
          <p className="text-sm text-ink-muted">{stock.data?.length ?? 0} products tracked.</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Warehouse</label>
            <select className="ec-input" value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              <option value="">All warehouses</option>
              {warehouses.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowMove(true)}><Plus size={16} /> Record movement</button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <StatCard label="Total units on hand" value={totalUnits.toLocaleString()} />
        <StatCard label="Inventory value" value={formatCurrency(totalValue)} />
        <StatCard label="Low stock" value={lowCount} accent={lowCount > 0 ? 'amber' : undefined} />
        <StatCard label="Out of stock" value={outCount} accent={outCount > 0 ? 'rose' : undefined} />
      </div>

      {showMove && (
        <MovementForm
          products={products.data ?? []}
          warehouses={warehouses.data ?? []}
          onSaved={() => {
            setShowMove(false);
            qc.invalidateQueries({ queryKey: ['inventory', 'stock'] });
            qc.invalidateQueries({ queryKey: ['inventory', 'movements'] });
          }}
          onCancel={() => setShowMove(false)}
        />
      )}

      <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
        <div className="ec-card overflow-x-auto">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Stock levels</div>
          <table className="ec-table">
            <thead><tr><th>SKU</th><th>Name</th><th>On hand</th><th>Threshold</th><th>Status</th><th>Unit cost</th><th>Value</th></tr></thead>
            <tbody>
              {stock.data?.length ? stock.data.map((s) => (
                <tr key={s.product_id}>
                  <td className="font-mono text-xs">{s.sku}</td>
                  <td className="font-medium">{s.name}</td>
                  <td className="tabular-nums">{s.on_hand}</td>
                  <td className="tabular-nums">{s.low_stock_threshold}</td>
                  <td><span className={STATUS_BADGE[s.status] ?? 'ec-badge'}>{s.status}</span></td>
                  <td>{formatCurrency(s.unit_cost)}</td>
                  <td>{formatCurrency(s.stock_value)}</td>
                </tr>
              )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No products yet — add them in Catalog.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="ec-card overflow-y-auto">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Recent movements</div>
          <div className="max-h-[500px] divide-y divide-border/60">
            {movements.data?.length ? movements.data.slice(0, 20).map((m) => {
              const p = products.data?.find((x) => x.id === m.product_id);
              const Icon = m.movement_type === 'in' ? ArrowDown :
                          m.movement_type === 'out' ? ArrowUp :
                          m.movement_type === 'transfer' ? ArrowRightLeft : RotateCw;
              const color = m.movement_type === 'in' ? 'text-emerald-600' :
                           m.movement_type === 'out' ? 'text-rose-600' : 'text-brand-600';
              return (
                <div key={m.id} className="flex items-start gap-3 p-3">
                  <Icon size={16} className={`mt-0.5 ${color}`} />
                  <div className="flex-1 text-sm">
                    <p className="font-medium">{p?.name ?? '—'} <span className="text-xs text-ink-muted">({Math.abs(m.quantity)} {m.movement_type})</span></p>
                    {m.reference && <p className="text-xs text-ink-muted">{m.reference}</p>}
                    {m.notes && <p className="text-xs text-ink-muted">{m.notes}</p>}
                  </div>
                </div>
              );
            }) : <p className="p-4 text-center text-xs text-ink-muted">No movements yet.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: string | number; accent?: 'amber' | 'rose' }) {
  const ring = accent === 'rose' ? 'ring-2 ring-rose-200' : accent === 'amber' ? 'ring-2 ring-amber-200' : '';
  const color = accent === 'rose' ? 'text-rose-600' : accent === 'amber' ? 'text-amber-600' : '';
  return (
    <div className={`ec-card p-3 ${ring}`}>
      <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${color}`}>{value}</p>
    </div>
  );
}

function MovementForm({ products, warehouses, onSaved, onCancel }: {
  products: Product[]; warehouses: Warehouse[]; onSaved: () => void; onCancel: () => void;
}) {
  const [productId, setProductId] = useState(products[0]?.id ?? '');
  const [warehouseId, setWarehouseId] = useState<string>('');
  const [type, setType] = useState<string>('in');
  const [quantity, setQuantity] = useState<number>(1);
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');

  const save = useMutation({
    mutationFn: async () => {
      const signedQty = type === 'out' ? -Math.abs(quantity) : Math.abs(quantity);
      return (await api.post('/inventory/stock/movements', {
        product_id: productId,
        warehouse_id: warehouseId || null,
        zone_id: null,
        movement_type: type,
        quantity: signedQty,
        reference: reference || null,
        notes,
      })).data;
    },
    onSuccess: () => { toast.success('Movement recorded'); onSaved(); },
    onError: () => toast.error('Failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Record stock movement</h3>
        <button className="ec-btn-ghost" onClick={onCancel}>×</button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div>
          <label className="ec-label">Product</label>
          <select className="ec-input" value={productId} onChange={(e) => setProductId(e.target.value)}>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
          </select>
        </div>
        <div>
          <label className="ec-label">Warehouse</label>
          <select className="ec-input" value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
            <option value="">—</option>
            {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </div>
        <div>
          <label className="ec-label">Type</label>
          <select className="ec-input" value={type} onChange={(e) => setType(e.target.value)}>
            {STOCK_MOVEMENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="ec-label">Quantity</label>
          <input type="number" className="ec-input" value={quantity} min={1} onChange={(e) => setQuantity(Number(e.target.value))} />
        </div>
        <div className="md:col-span-2">
          <label className="ec-label">Reference</label>
          <input className="ec-input" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="PO number, invoice, etc." />
        </div>
        <div className="md:col-span-3">
          <label className="ec-label">Notes</label>
          <input className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!productId || save.isPending} onClick={() => save.mutate()}>Record</button>
      </div>
    </div>
  );
}
