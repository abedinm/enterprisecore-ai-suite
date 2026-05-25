import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Download, Plus, Trash2, Users, Edit3, X, Check } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import { TableSkipLink } from '../../components/TableSkipLink';

type Line = { id?: string; description: string; quantity: number; unit_price: number; tax_rate: number; line_total?: string };
type Invoice = {
  id: string; invoice_number: string; customer_id: string | null;
  issue_date: string; due_date: string; status: string;
  currency: string; subtotal: string; tax_total: string;
  discount_total: string; total: string; notes: string | null;
  lines: { id: string; description: string; quantity: string; unit_price: string; tax_rate: string; line_total: string }[];
};
type Customer = { id: string; name: string; email: string | null; phone: string | null; currency: string };

const STATUSES = ['draft', 'sent', 'paid', 'overdue', 'void'];
const STATUS_BADGE: Record<string, string> = {
  draft: 'ec-badge-blue', sent: 'ec-badge-amber',
  paid: 'ec-badge-green', overdue: 'ec-badge-rose', void: 'ec-badge',
};

export function InvoicesTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [showCustomers, setShowCustomers] = useState(false);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const invoices = useQuery({
    queryKey: ['finance', 'invoices', statusFilter],
    queryFn: async () => (await api.get<Invoice[]>('/finance/invoices', {
      params: statusFilter ? { status: statusFilter } : {},
    })).data,
  });
  const customers = useQuery({
    queryKey: ['finance', 'customers'],
    queryFn: async () => (await api.get<Customer[]>('/finance/customers')).data,
  });

  const updateStatus = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      (await api.post(`/finance/invoices/${id}/status`, { status })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'invoices'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/invoices/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'invoices'] }),
  });

  async function downloadPdf(invoice: Invoice) {
    const r = await api.get(`/finance/invoices/${invoice.id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${invoice.invoice_number}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const totalsByStatus = useMemo(() => {
    const acc: Record<string, number> = {};
    (invoices.data ?? []).forEach((i) => { acc[i.status] = (acc[i.status] ?? 0) + parseFloat(i.total); });
    return acc;
  }, [invoices.data]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Invoices</p>
          <p className="text-sm text-ink-muted">{invoices.data?.length ?? 0} invoices · PDF export ready</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Filter</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-secondary" onClick={() => setShowCustomers((v) => !v)}>
            <Users size={16} /> {showCustomers ? 'Hide customers' : 'Manage customers'}
          </button>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm((v) => !v); }}>
            <Plus size={16} /> {showForm && !editing ? 'Close' : 'New invoice'}
          </button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-5">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s}</p>
            <p className="text-sm font-semibold">{formatCurrency(totalsByStatus[s] ?? 0)}</p>
          </div>
        ))}
      </div>

      {showCustomers && <CustomersPanel customers={customers.data ?? []} onChange={() => qc.invalidateQueries({ queryKey: ['finance', 'customers'] })} />}

      {(showForm || editing) && customers.data && (
        <InvoiceForm
          customers={customers.data}
          editing={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['finance', 'invoices'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="relative ec-card overflow-x-auto">
        <TableSkipLink targetId="after-invoices-table" label="Skip invoices table" />
        <table className="ec-table" aria-label="Invoices">
          <thead>
            <tr><th scope="col">Number</th><th scope="col">Customer</th><th scope="col">Issued</th><th scope="col">Due</th><th scope="col">Total</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {invoices.data?.length ? invoices.data.map((inv) => (
              <tr key={inv.id}>
                <td className="font-medium">{inv.invoice_number}</td>
                <td>{customers.data?.find((c) => c.id === inv.customer_id)?.name ?? '—'}</td>
                <td>{formatDate(inv.issue_date)}</td>
                <td>{formatDate(inv.due_date)}</td>
                <td>{formatCurrency(inv.total, inv.currency)}</td>
                <td>
                  <select
                    className={`ec-input !py-1 !w-32 ${STATUS_BADGE[inv.status]}`}
                    value={inv.status}
                    onChange={(e) => updateStatus.mutate({ id: inv.id, status: e.target.value })}
                  >
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
                <td className="space-x-1 whitespace-nowrap text-right">
                  <button className="ec-btn-ghost" title="Edit" onClick={() => { setEditing(inv); setShowForm(true); }}><Edit3 size={16} /></button>
                  <button className="ec-btn-ghost" title="PDF" onClick={() => downloadPdf(inv)}><Download size={16} /></button>
                  <button className="ec-btn-ghost text-rose-600" title="Delete" onClick={() => { if (confirm('Delete invoice ' + inv.invoice_number + '?')) remove.mutate(inv.id); }}><Trash2 size={16} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={7} className="py-10 text-center text-ink-muted">No invoices yet — click "New invoice" to create one.</td></tr>}
          </tbody>
        </table>
        <div id="after-invoices-table" tabIndex={-1} />
      </div>
    </div>
  );
}

function InvoiceForm({ customers, editing, onSaved, onCancel }: { customers: Customer[]; editing: Invoice | null; onSaved: () => void; onCancel: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const due = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
  const [customerId, setCustomerId] = useState(editing?.customer_id ?? customers[0]?.id ?? '');
  const [issueDate, setIssueDate] = useState(editing?.issue_date ?? today);
  const [dueDate, setDueDate] = useState(editing?.due_date ?? due);
  const [currency, setCurrency] = useState(editing?.currency ?? 'USD');
  const [notes, setNotes] = useState(editing?.notes ?? '');
  const [lines, setLines] = useState<Line[]>(
    editing?.lines.map((l) => ({
      description: l.description, quantity: parseFloat(l.quantity),
      unit_price: parseFloat(l.unit_price), tax_rate: parseFloat(l.tax_rate),
    })) ?? [{ description: '', quantity: 1, unit_price: 0, tax_rate: 0 }],
  );
  const [discount, setDiscount] = useState(editing ? parseFloat(editing.discount_total) : 0);

  const subtotal = lines.reduce((sum, l) => sum + Number(l.quantity) * Number(l.unit_price), 0);
  const tax = lines.reduce((sum, l) => sum + Number(l.quantity) * Number(l.unit_price) * Number(l.tax_rate), 0);
  const total = subtotal + tax - Number(discount || 0);

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        customer_id: customerId, issue_date: issueDate, due_date: dueDate,
        currency, notes, discount_total: discount, lines,
      };
      if (editing) {
        return (await api.patch(`/finance/invoices/${editing.id}`, body)).data;
      }
      return (await api.post('/finance/invoices', body)).data;
    },
    onSuccess: async () => {
      // Celebrate on CREATE (not edit). The server-side first/10/100 milestone
      // achievements will also surface their own celebration via the
      // gamification refresh; this is the immediate visual reward.
      if (!editing) {
        try {
          const { popConfetti } = await import('../../lib/celebrate');
          popConfetti();
        } catch { /* never block on celebration */ }
        try {
          const { useGamification } = await import('../../store/gamification');
          useGamification.getState().refresh();
        } catch { /* noop */ }
      }
      onSaved();
    },
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? `Edit invoice ${editing.invoice_number}` : 'New invoice'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div>
          <label className="ec-label">Customer</label>
          <select className="ec-input" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
            <option value="">—</option>
            {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Issue date</label><input type="date" className="ec-input" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} /></div>
        <div><label className="ec-label">Due date</label><input type="date" className="ec-input" value={dueDate} onChange={(e) => setDueDate(e.target.value)} /></div>
        <div><label className="ec-label">Currency</label><input className="ec-input" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} /></div>
      </div>

      <div className="mt-4 space-y-2">
        <p className="text-sm font-medium text-ink-muted">Line items</p>
        {lines.map((line, i) => (
          <div key={i} className="grid gap-2 md:grid-cols-[1fr_80px_120px_80px_24px]">
            <input className="ec-input" placeholder="Description" value={line.description}
              onChange={(e) => setLines(lines.map((l, ix) => ix === i ? { ...l, description: e.target.value } : l))} />
            <input type="number" className="ec-input" value={line.quantity} min={0} step="any"
              onChange={(e) => setLines(lines.map((l, ix) => ix === i ? { ...l, quantity: Number(e.target.value) } : l))} />
            <input type="number" className="ec-input" placeholder="Unit price" value={line.unit_price} step="any"
              onChange={(e) => setLines(lines.map((l, ix) => ix === i ? { ...l, unit_price: Number(e.target.value) } : l))} />
            <input type="number" className="ec-input" placeholder="Tax (0-1)" value={line.tax_rate} step="0.01" min={0} max={1}
              onChange={(e) => setLines(lines.map((l, ix) => ix === i ? { ...l, tax_rate: Number(e.target.value) } : l))} />
            <button className="ec-btn-ghost text-rose-600" type="button"
              onClick={() => setLines(lines.filter((_, ix) => ix !== i))}>×</button>
          </div>
        ))}
        <button type="button" className="ec-btn-secondary" onClick={() => setLines([...lines, { description: '', quantity: 1, unit_price: 0, tax_rate: 0 }])}>+ Add line</button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div>
          <label className="ec-label">Discount</label>
          <input type="number" className="ec-input" value={discount} step="any" onChange={(e) => setDiscount(Number(e.target.value))} />
        </div>
        <div className="md:col-span-2">
          <label className="ec-label">Notes</label>
          <textarea className="ec-input" rows={2} value={notes ?? ''} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div className="text-sm text-ink-muted space-y-0.5">
          <p>Subtotal: <strong className="text-ink">{formatCurrency(subtotal, currency)}</strong></p>
          <p>Tax: <strong className="text-ink">{formatCurrency(tax, currency)}</strong></p>
          <p>Discount: <strong className="text-ink">-{formatCurrency(discount, currency)}</strong></p>
          <p className="text-base">Total: <strong className="text-ink">{formatCurrency(total, currency)}</strong></p>
        </div>
        <button className="ec-btn-primary" disabled={!customerId || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : editing ? 'Save changes' : 'Create invoice'}
        </button>
      </div>
    </div>
  );
}

function CustomersPanel({ customers, onChange }: { customers: Customer[]; onChange: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [editing, setEditing] = useState<string | null>(null);
  const [editVals, setEditVals] = useState<Partial<Customer>>({});

  const create = useMutation({
    mutationFn: async () => (await api.post('/finance/customers', {
      name, email: email || null, phone: phone || null, currency,
    })).data,
    onSuccess: () => { setName(''); setEmail(''); setPhone(''); setCurrency('USD'); onChange(); },
  });
  const update = useMutation({
    mutationFn: async ({ id, ...c }: Partial<Customer> & { id: string }) =>
      (await api.patch(`/finance/customers/${id}`, {
        name: c.name, email: c.email, phone: c.phone, currency: c.currency,
      })).data,
    onSuccess: () => { setEditing(null); onChange(); },
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/customers/${id}`)).data,
    onSuccess: onChange,
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <p className="text-sm font-semibold">Customers ({customers.length})</p>
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_140px_80px_80px]">
        <input className="ec-input" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="ec-input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="ec-input" placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <input className="ec-input" maxLength={3} placeholder="USD" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
        <button className="ec-btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate()}>Add</button>
      </div>
      <table className="ec-table">
        <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Currency</th><th></th></tr></thead>
        <tbody>
          {customers.length ? customers.map((c) => (
            <tr key={c.id}>
              {editing === c.id ? (
                <>
                  <td><input className="ec-input !py-1" defaultValue={c.name} onChange={(e) => setEditVals((s) => ({ ...s, name: e.target.value }))} /></td>
                  <td><input className="ec-input !py-1" defaultValue={c.email ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, email: e.target.value }))} /></td>
                  <td><input className="ec-input !py-1" defaultValue={c.phone ?? ''} onChange={(e) => setEditVals((s) => ({ ...s, phone: e.target.value }))} /></td>
                  <td><input className="ec-input !py-1 !w-20" maxLength={3} defaultValue={c.currency} onChange={(e) => setEditVals((s) => ({ ...s, currency: e.target.value.toUpperCase() }))} /></td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost text-emerald-600" onClick={() => update.mutate({ ...c, ...editVals, id: c.id })}><Check size={16} /></button>
                    <button className="ec-btn-ghost" onClick={() => setEditing(null)}><X size={16} /></button>
                  </td>
                </>
              ) : (
                <>
                  <td className="font-medium">{c.name}</td>
                  <td>{c.email ?? '—'}</td>
                  <td>{c.phone ?? '—'}</td>
                  <td>{c.currency}</td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost" onClick={() => { setEditing(c.id); setEditVals(c); }}><Edit3 size={16} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + c.name + '?')) remove.mutate(c.id); }}><Trash2 size={16} /></button>
                  </td>
                </>
              )}
            </tr>
          )) : <tr><td colSpan={5} className="py-6 text-center text-ink-muted">No customers yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
