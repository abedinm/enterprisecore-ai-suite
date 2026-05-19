import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import { Product, REFUND_STATUSES, RETURN_STATUSES, ReturnRequest, STATUS_BADGE } from './types';

export function ReturnsTab() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [refundFilter, setRefundFilter] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<ReturnRequest | null>(null);

  const products = useQuery({
    queryKey: ['inventory', 'products'],
    queryFn: async () => (await api.get<Product[]>('/inventory/products')).data,
  });
  const returns = useQuery({
    queryKey: ['inventory', 'returns', statusFilter, refundFilter],
    queryFn: async () => (await api.get<ReturnRequest[]>('/inventory/returns', {
      params: { ...(statusFilter ? { status: statusFilter } : {}), ...(refundFilter ? { refund_status: refundFilter } : {}) },
    })).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/returns/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'returns'] }),
  });

  const totals = {
    requested: (returns.data ?? []).filter((r) => r.status === 'requested').length,
    approved: (returns.data ?? []).filter((r) => r.status === 'approved').length,
    refunded: (returns.data ?? []).reduce((s, r) => r.refund_status === 'refunded' ? s + parseFloat(r.refund_amount) : s, 0),
    pending: (returns.data ?? []).reduce((s, r) => r.refund_status === 'pending' ? s + parseFloat(r.refund_amount) : s, 0),
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Returns &amp; Refunds</p>
          <p className="text-sm text-ink-muted">{returns.data?.length ?? 0} return requests.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Status</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {RETURN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="ec-label">Refund</label>
            <select className="ec-input" value={refundFilter} onChange={(e) => setRefundFilter(e.target.value)}>
              <option value="">All</option>
              {REFUND_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New return</button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <StatCard label="Requested" value={totals.requested} />
        <StatCard label="Approved" value={totals.approved} />
        <StatCard label="Pending refunds" value={formatCurrency(totals.pending)} />
        <StatCard label="Refunded total" value={formatCurrency(totals.refunded)} />
      </div>

      {(showForm || editing) && (
        <ReturnForm
          editing={editing}
          products={products.data ?? []}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['inventory', 'returns'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>RMA</th><th>Product</th><th>Qty</th><th>Reason</th><th>Status</th><th>Refund</th><th>Refund $</th><th>Date</th><th></th></tr></thead>
          <tbody>
            {returns.data?.length ? returns.data.map((r) => (
              <tr key={r.id}>
                <td className="font-mono text-xs">{r.rma_number}</td>
                <td>{products.data?.find((p) => p.id === r.product_id)?.name ?? '—'}</td>
                <td>{r.quantity}</td>
                <td className="max-w-xs truncate">{r.reason}</td>
                <td><span className={STATUS_BADGE[r.status] ?? 'ec-badge'}>{r.status}</span></td>
                <td><span className={STATUS_BADGE[r.refund_status] ?? 'ec-badge'}>{r.refund_status}</span></td>
                <td>{formatCurrency(r.refund_amount)}</td>
                <td>{r.return_date ? formatDate(r.return_date) : '—'}</td>
                <td className="text-right whitespace-nowrap">
                  <button className="ec-btn-ghost" onClick={() => setEditing(r)}><Edit3 size={14} /></button>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete return?')) remove.mutate(r.id); }}><Trash2 size={14} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={9} className="py-10 text-center text-ink-muted">No returns yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="ec-card p-3">
      <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function ReturnForm({ editing, products, onSaved, onCancel }: {
  editing: ReturnRequest | null; products: Product[];
  onSaved: () => void; onCancel: () => void;
}) {
  const [rma, setRma] = useState(editing?.rma_number ?? '');
  const [productId, setProductId] = useState(editing?.product_id ?? '');
  const [customerId, setCustomerId] = useState(editing?.customer_id ?? '');
  const [quantity, setQuantity] = useState(editing?.quantity ?? 1);
  const [reason, setReason] = useState(editing?.reason ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'requested');
  const [refundAmount, setRefundAmount] = useState(editing?.refund_amount ?? '0');
  const [refundStatus, setRefundStatus] = useState(editing?.refund_status ?? 'pending');
  const [returnDate, setReturnDate] = useState(editing?.return_date ?? '');

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        rma_number: rma,
        product_id: productId || null,
        customer_id: customerId || null,
        quantity, reason, status, refund_amount: refundAmount,
        refund_status: refundStatus,
        return_date: returnDate || null,
      };
      if (editing) return (await api.patch(`/inventory/returns/${editing.id}`, body)).data;
      return (await api.post('/inventory/returns', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? `Edit RMA ${editing.rma_number}` : 'New return'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">RMA number</label><input className="ec-input font-mono" value={rma} onChange={(e) => setRma(e.target.value)} placeholder="auto-generated" /></div>
        <div className="md:col-span-2"><label className="ec-label">Product</label>
          <select className="ec-input" value={productId ?? ''} onChange={(e) => setProductId(e.target.value)}>
            <option value="">—</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
          </select>
        </div>
        <div><label className="ec-label">Customer ID</label><input className="ec-input" value={customerId ?? ''} onChange={(e) => setCustomerId(e.target.value)} /></div>
        <div><label className="ec-label">Quantity</label><input type="number" min={1} className="ec-input" value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} /></div>
        <div><label className="ec-label">Return date</label><input type="date" className="ec-input" value={returnDate ?? ''} onChange={(e) => setReturnDate(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Reason</label><textarea className="ec-input" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {RETURN_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Refund amount</label><input type="number" step="any" className="ec-input" value={refundAmount} onChange={(e) => setRefundAmount(e.target.value)} /></div>
        <div><label className="ec-label">Refund status</label>
          <select className="ec-input" value={refundStatus} onChange={(e) => setRefundStatus(e.target.value)}>
            {REFUND_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Create'}</button>
      </div>
    </div>
  );
}
