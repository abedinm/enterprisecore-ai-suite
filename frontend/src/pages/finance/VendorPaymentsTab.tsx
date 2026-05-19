import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, Truck, X, Check } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type Vendor = { id: string; name: string; email: string | null; phone: string | null; payment_terms: string | null };
type Payment = { id: string; vendor_id: string | null; payment_date: string; amount: string; status: string };

const STATUSES = ['scheduled', 'paid', 'overdue', 'cancelled'];
const STATUS_BADGE: Record<string, string> = {
  scheduled: 'ec-badge-blue', paid: 'ec-badge-green',
  overdue: 'ec-badge-rose', cancelled: 'ec-badge',
};

export function VendorPaymentsTab() {
  const qc = useQueryClient();
  const [showVendors, setShowVendors] = useState(false);
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const vendors = useQuery({
    queryKey: ['finance', 'vendors'],
    queryFn: async () => (await api.get<Vendor[]>('/finance/vendors')).data,
  });
  const payments = useQuery({
    queryKey: ['finance', 'vendor-payments', statusFilter],
    queryFn: async () => (await api.get<Payment[]>('/finance/vendor-payments', {
      params: statusFilter ? { status: statusFilter } : {},
    })).data,
  });

  const updateStatus = useMutation({
    mutationFn: async ({ id, status, vendor_id, payment_date, amount }: Payment) =>
      (await api.patch(`/finance/vendor-payments/${id}`, {
        vendor_id, payment_date, amount: parseFloat(amount), status,
      })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'vendor-payments'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/vendor-payments/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'vendor-payments'] }),
  });

  const totalScheduled = (payments.data ?? []).filter((p) => p.status === 'scheduled')
    .reduce((s, p) => s + parseFloat(p.amount), 0);
  const totalPaid = (payments.data ?? []).filter((p) => p.status === 'paid')
    .reduce((s, p) => s + parseFloat(p.amount), 0);
  const totalOverdue = (payments.data ?? []).filter((p) => p.status === 'overdue')
    .reduce((s, p) => s + parseFloat(p.amount), 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Vendor payments</p>
          <p className="text-sm text-ink-muted">{payments.data?.length ?? 0} payments · {vendors.data?.length ?? 0} vendors</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Filter</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-secondary" onClick={() => setShowVendors((v) => !v)}>
            <Truck size={16} /> {showVendors ? 'Hide vendors' : 'Manage vendors'}
          </button>
          <button className="ec-btn-primary" onClick={() => setShowPaymentForm((v) => !v)}>
            <Plus size={16} /> {showPaymentForm ? 'Close' : 'New payment'}
          </button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Scheduled" value={formatCurrency(totalScheduled)} tone="blue" />
        <Tile label="Paid" value={formatCurrency(totalPaid)} tone="green" />
        <Tile label="Overdue" value={formatCurrency(totalOverdue)} tone="rose" />
      </div>

      {showVendors && <VendorsPanel vendors={vendors.data ?? []} onChange={() => qc.invalidateQueries({ queryKey: ['finance', 'vendors'] })} />}

      {showPaymentForm && vendors.data && (
        <PaymentForm vendors={vendors.data}
          onSaved={() => { setShowPaymentForm(false); qc.invalidateQueries({ queryKey: ['finance', 'vendor-payments'] }); }} />
      )}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Date</th><th>Vendor</th><th>Amount</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {payments.data?.length ? payments.data.map((p) => (
              <tr key={p.id}>
                <td>{formatDate(p.payment_date)}</td>
                <td className="font-medium">{vendors.data?.find((v) => v.id === p.vendor_id)?.name ?? '—'}</td>
                <td>{formatCurrency(p.amount)}</td>
                <td>
                  <select className={`ec-input !py-1 !w-32 ${STATUS_BADGE[p.status] ?? ''}`}
                          value={p.status}
                          onChange={(e) => updateStatus.mutate({ ...p, status: e.target.value })}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
                <td className="text-right">
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete this payment?')) remove.mutate(p.id); }}>
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            )) : <tr><td colSpan={5} className="py-10 text-center text-ink-muted">No vendor payments recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone: 'blue' | 'green' | 'rose' }) {
  const cls = tone === 'green' ? 'text-emerald-500' : tone === 'rose' ? 'text-rose-500' : 'text-brand-600';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

function PaymentForm({ vendors, onSaved }: { vendors: Vendor[]; onSaved: () => void }) {
  const [vendorId, setVendorId] = useState(vendors[0]?.id ?? '');
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = useState(0);
  const [status, setStatus] = useState('scheduled');

  const save = useMutation({
    mutationFn: async () => (await api.post('/finance/vendor-payments', {
      vendor_id: vendorId || null, payment_date: paymentDate, amount, status,
    })).data,
    onSuccess: onSaved,
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-5">
      <div>
        <label className="ec-label">Vendor</label>
        <select className="ec-input" value={vendorId} onChange={(e) => setVendorId(e.target.value)}>
          <option value="">—</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Payment date</label><input type="date" className="ec-input" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} /></div>
      <div><label className="ec-label">Amount</label><input type="number" step="any" className="ec-input" value={amount} onChange={(e) => setAmount(Number(e.target.value))} /></div>
      <div>
        <label className="ec-label">Status</label>
        <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div className="flex items-end justify-end">
        <button className="ec-btn-primary" disabled={!amount || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

function VendorsPanel({ vendors, onChange }: { vendors: Vendor[]; onChange: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [terms, setTerms] = useState('Net 30');
  const [editing, setEditing] = useState<string | null>(null);
  const [editVals, setEditVals] = useState<Partial<Vendor>>({});

  const create = useMutation({
    mutationFn: async () => (await api.post('/finance/vendors', {
      name, email: email || null, phone: phone || null, payment_terms: terms || null,
    })).data,
    onSuccess: () => { setName(''); setEmail(''); setPhone(''); setTerms('Net 30'); onChange(); },
  });
  const update = useMutation({
    mutationFn: async ({ id, ...v }: Partial<Vendor> & { id: string }) =>
      (await api.patch(`/finance/vendors/${id}`, {
        name: v.name, email: v.email, phone: v.phone, payment_terms: v.payment_terms,
      })).data,
    onSuccess: () => { setEditing(null); onChange(); },
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/vendors/${id}`)).data,
    onSuccess: onChange,
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Vendors ({vendors.length})</p>
      </div>
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_140px_140px_80px]">
        <input className="ec-input" placeholder="Vendor name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="ec-input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="ec-input" placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <input className="ec-input" placeholder="Net 30" value={terms} onChange={(e) => setTerms(e.target.value)} />
        <button className="ec-btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate()}>Add</button>
      </div>
      <table className="ec-table">
        <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Terms</th><th></th></tr></thead>
        <tbody>
          {vendors.length ? vendors.map((v) => (
            <tr key={v.id}>
              {editing === v.id ? (
                <>
                  <td><input className="ec-input !py-1" defaultValue={v.name} onChange={(e) => setEditVals((s) => ({ ...s, name: e.target.value }))} /></td>
                  <td><input className="ec-input !py-1" defaultValue={v.email ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, email: e.target.value }))} /></td>
                  <td><input className="ec-input !py-1" defaultValue={v.phone ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, phone: e.target.value }))} /></td>
                  <td><input className="ec-input !py-1" defaultValue={v.payment_terms ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, payment_terms: e.target.value }))} /></td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost text-emerald-600" onClick={() => update.mutate({ id: v.id, name: v.name, email: v.email, phone: v.phone, payment_terms: v.payment_terms, ...editVals })}><Check size={16} /></button>
                    <button className="ec-btn-ghost" onClick={() => setEditing(null)}><X size={16} /></button>
                  </td>
                </>
              ) : (
                <>
                  <td className="font-medium">{v.name}</td>
                  <td>{v.email ?? '—'}</td>
                  <td>{v.phone ?? '—'}</td>
                  <td>{v.payment_terms ?? '—'}</td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost" onClick={() => { setEditing(v.id); setEditVals(v); }}><Edit3 size={16} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete vendor ' + v.name + '?')) remove.mutate(v.id); }}><Trash2 size={16} /></button>
                  </td>
                </>
              )}
            </tr>
          )) : <tr><td colSpan={5} className="py-6 text-center text-ink-muted">No vendors yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
