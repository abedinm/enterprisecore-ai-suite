import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, ShoppingCart, PackageCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import { POLine, PO_STATUSES, Product, PurchaseOrder, STATUS_BADGE, Supplier } from './types';

export function PurchaseOrdersTab() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [supplierFilter, setSupplierFilter] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const suppliers = useQuery({
    queryKey: ['inventory', 'suppliers'],
    queryFn: async () => (await api.get<Supplier[]>('/inventory/suppliers')).data,
  });
  const products = useQuery({
    queryKey: ['inventory', 'products'],
    queryFn: async () => (await api.get<Product[]>('/inventory/products')).data,
  });
  const pos = useQuery({
    queryKey: ['inventory', 'pos', statusFilter, supplierFilter],
    queryFn: async () => (await api.get<PurchaseOrder[]>('/inventory/purchase-orders', {
      params: { ...(statusFilter ? { status: statusFilter } : {}), ...(supplierFilter ? { supplier_id: supplierFilter } : {}) },
    })).data,
  });

  const setStatus = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      (await api.post(`/inventory/purchase-orders/${id}/status`, { status })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory', 'pos'] });
      qc.invalidateQueries({ queryKey: ['inventory', 'stock'] });
      toast.success('Status updated');
    },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/purchase-orders/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'pos'] }),
  });

  const totalsByStatus = (pos.data ?? []).reduce<Record<string, number>>((acc, p) => {
    acc[p.status] = (acc[p.status] ?? 0) + parseFloat(p.total);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Purchase Orders</p>
          <p className="text-sm text-ink-muted">{pos.data?.length ?? 0} POs.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Status</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {PO_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="ec-label">Supplier</label>
            <select className="ec-input" value={supplierFilter} onChange={(e) => setSupplierFilter(e.target.value)}>
              <option value="">All</option>
              {suppliers.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowForm(true)}><Plus size={16} /> New PO</button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-5">
        {PO_STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s}</p>
            <p className="text-sm font-semibold">{formatCurrency(totalsByStatus[s] ?? 0)}</p>
          </div>
        ))}
      </div>

      {showForm && (
        <POForm
          products={products.data ?? []}
          suppliers={suppliers.data ?? []}
          onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['inventory', 'pos'] }); }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <div className="grid gap-3 lg:grid-cols-[1fr_1fr]">
        <div className="ec-card overflow-x-auto">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Purchase orders</div>
          <table className="ec-table">
            <thead><tr><th>PO #</th><th>Supplier</th><th>Date</th><th>Expected</th><th>Total</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {pos.data?.length ? pos.data.map((p) => (
                <tr key={p.id} className={selected === p.id ? 'bg-surface-muted' : ''}>
                  <td className="font-mono cursor-pointer text-xs" onClick={() => setSelected(p.id)}>{p.po_number}</td>
                  <td>{suppliers.data?.find((s) => s.id === p.supplier_id)?.name ?? '—'}</td>
                  <td>{formatDate(p.order_date)}</td>
                  <td>{p.expected_date ? formatDate(p.expected_date) : '—'}</td>
                  <td>{formatCurrency(p.total)}</td>
                  <td>
                    <select
                      className={`ec-input !py-1 !w-32 ${STATUS_BADGE[p.status]}`}
                      value={p.status}
                      onChange={(e) => setStatus.mutate({ id: p.id, status: e.target.value })}
                    >
                      {PO_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete PO?')) remove.mutate(p.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No purchase orders yet.</td></tr>}
            </tbody>
          </table>
        </div>

        {selected ? (
          <POLines poId={selected} products={products.data ?? []} />
        ) : (
          <div className="ec-card p-6 text-center text-sm text-ink-muted">Click a PO number to view and receive lines.</div>
        )}
      </div>
    </div>
  );
}

function POForm({ products, suppliers, onSaved, onCancel }: {
  products: Product[]; suppliers: Supplier[];
  onSaved: () => void; onCancel: () => void;
}) {
  const [supplierId, setSupplierId] = useState(suppliers[0]?.id ?? '');
  const today = new Date().toISOString().slice(0, 10);
  const [orderDate, setOrderDate] = useState(today);
  const [expectedDate, setExpectedDate] = useState(new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10));
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<{ product_id: string | null; description: string; quantity: number; unit_cost: string }[]>([
    { product_id: '', description: '', quantity: 1, unit_cost: '0' },
  ]);

  const save = useMutation({
    mutationFn: async () => (await api.post('/inventory/purchase-orders', {
      supplier_id: supplierId || null,
      status: 'draft', order_date: orderDate, expected_date: expectedDate || null,
      notes,
      lines: lines.filter((l) => l.product_id || l.description).map((l) => ({
        product_id: l.product_id || null,
        description: l.description,
        quantity: l.quantity,
        unit_cost: l.unit_cost,
        received_quantity: 0,
      })),
    })).data,
    onSuccess: () => { toast.success('PO created'); onSaved(); },
    onError: () => toast.error('Failed'),
  });

  const total = lines.reduce((s, l) => s + l.quantity * Number(l.unit_cost), 0);

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">New purchase order</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Supplier</label>
          <select className="ec-input" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
            <option value="">—</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Order date</label><input type="date" className="ec-input" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} /></div>
        <div><label className="ec-label">Expected date</label><input type="date" className="ec-input" value={expectedDate} onChange={(e) => setExpectedDate(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Notes</label><textarea className="ec-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      </div>
      <p className="mt-4 mb-2 text-sm font-semibold">Line items</p>
      <div className="space-y-2">
        {lines.map((l, i) => (
          <div key={i} className="grid gap-2 md:grid-cols-[1fr_1fr_80px_120px_24px]">
            <select className="ec-input" value={l.product_id ?? ''} onChange={(e) => {
              const product = products.find((p) => p.id === e.target.value);
              setLines(lines.map((x, ix) => ix === i ? { ...x, product_id: e.target.value, description: product?.name ?? x.description, unit_cost: product?.unit_cost ?? x.unit_cost } : x));
            }}>
              <option value="">— Custom item —</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
            </select>
            <input className="ec-input" placeholder="Description" value={l.description} onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, description: e.target.value } : x))} />
            <input type="number" className="ec-input" min={1} value={l.quantity} onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, quantity: Number(e.target.value) } : x))} />
            <input type="number" className="ec-input" step="any" placeholder="Unit cost" value={l.unit_cost} onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, unit_cost: e.target.value } : x))} />
            <button className="ec-btn-ghost text-rose-600" onClick={() => setLines(lines.filter((_, ix) => ix !== i))}>×</button>
          </div>
        ))}
        <button className="ec-btn-secondary" onClick={() => setLines([...lines, { product_id: '', description: '', quantity: 1, unit_cost: '0' }])}>+ Add line</button>
      </div>
      <div className="mt-4 flex items-end justify-between gap-2">
        <p className="text-base">Total: <strong>{formatCurrency(total)}</strong></p>
        <div className="flex gap-2">
          <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="ec-btn-primary" disabled={save.isPending || !lines.length} onClick={() => save.mutate()}>Create PO</button>
        </div>
      </div>
    </div>
  );
}

function POLines({ poId, products }: { poId: string; products: Product[] }) {
  const qc = useQueryClient();
  const lines = useQuery({
    queryKey: ['inventory', 'po-lines', poId],
    queryFn: async () => (await api.get<POLine[]>(`/inventory/purchase-orders/${poId}/lines`)).data,
  });
  const [receiveQty, setReceiveQty] = useState<Record<string, number>>({});

  const receive = useMutation({
    mutationFn: async (lineId: string) => (await api.post(`/inventory/purchase-orders/${poId}/receive-line/${lineId}`, {
      quantity: receiveQty[lineId] ?? 0,
    })).data,
    onSuccess: (_d, lineId) => {
      setReceiveQty((s) => ({ ...s, [lineId]: 0 }));
      qc.invalidateQueries({ queryKey: ['inventory', 'po-lines', poId] });
      qc.invalidateQueries({ queryKey: ['inventory', 'stock'] });
      toast.success('Received');
    },
  });

  return (
    <div className="ec-card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">
        <ShoppingCart size={14} className="text-brand-600" /> Lines &amp; receiving
      </div>
      <div className="overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Product</th><th>Description</th><th>Ordered</th><th>Received</th><th>Cost</th><th>Receive</th></tr></thead>
          <tbody>
            {lines.data?.length ? lines.data.map((l) => {
              const remaining = l.quantity - l.received_quantity;
              return (
                <tr key={l.id}>
                  <td>{products.find((p) => p.id === l.product_id)?.name ?? '—'}</td>
                  <td>{l.description}</td>
                  <td>{l.quantity}</td>
                  <td>{l.received_quantity} {remaining > 0 && <span className="text-xs text-amber-600">({remaining} pending)</span>}</td>
                  <td>{formatCurrency(l.unit_cost)}</td>
                  <td>
                    {remaining > 0 ? (
                      <div className="flex gap-1">
                        <input type="number" className="ec-input !py-1 !w-16" max={remaining} value={receiveQty[l.id] ?? remaining} onChange={(e) => setReceiveQty((s) => ({ ...s, [l.id]: Number(e.target.value) }))} />
                        <button className="ec-btn-primary !py-1" onClick={() => receive.mutate(l.id)}><PackageCheck size={14} /></button>
                      </div>
                    ) : <span className="ec-badge-green">received</span>}
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-6 text-center text-xs text-ink-muted">No lines.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
