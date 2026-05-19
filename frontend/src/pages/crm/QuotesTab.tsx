import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, Download, X, Receipt } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';
import type { Contact } from './CustomersTab';

type Quote = { id: string; quote_number: string; contact_id: string | null; status: string; total: string };

const STATUSES = ['draft', 'sent', 'accepted', 'rejected', 'expired'];
const STATUS_BADGE: Record<string, string> = {
  draft: 'ec-badge-blue', sent: 'ec-badge-amber',
  accepted: 'ec-badge-green', rejected: 'ec-badge-rose', expired: 'ec-badge',
};

export function QuotesTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Quote | null>(null);
  const [statusFilter, setStatusFilter] = useState('');

  const quotes = useQuery({
    queryKey: ['crm', 'quotations', statusFilter],
    queryFn: async () => (await api.get<Quote[]>('/crm/quotations', { params: statusFilter ? { status: statusFilter } : {} })).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/quotations/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'quotations'] }),
  });
  const updateStatus = useMutation({
    mutationFn: async ({ q, status }: { q: Quote; status: string }) =>
      (await api.patch(`/crm/quotations/${q.id}`, {
        quote_number: q.quote_number, contact_id: q.contact_id, status, total: parseFloat(q.total),
      })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'quotations'] }),
  });

  async function downloadPdf(q: Quote) {
    const r = await api.get(`/crm/quotations/${q.id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a'); a.href = url; a.download = `${q.quote_number}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const totalValue = (quotes.data ?? []).reduce((s, q) => s + parseFloat(q.total), 0);
  const totals = (quotes.data ?? []).reduce<Record<string, number>>((acc, q) => { acc[q.status] = (acc[q.status] ?? 0) + parseFloat(q.total); return acc; }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Receipt size={14} />Quotations</p>
          <p className="text-sm text-ink-muted">{quotes.data?.length ?? 0} quotes · total {formatCurrency(totalValue)}</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Filter</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShow((v) => !v); }}>
            <Plus size={16} /> {show && !editing ? 'Close' : 'New quote'}
          </button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-5">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s}</p>
            <p className="text-sm font-semibold">{formatCurrency(totals[s] ?? 0)}</p>
          </div>
        ))}
      </div>

      {(show || editing) && contacts.data && (
        <Form contacts={contacts.data} editing={editing}
          onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'quotations'] }); }}
          onCancel={() => { setShow(false); setEditing(null); }} />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Number</th><th>Contact</th><th>Total</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {quotes.data?.length ? quotes.data.map((q) => {
              const c = contacts.data?.find((x) => x.id === q.contact_id);
              return (
                <tr key={q.id}>
                  <td className="font-mono text-xs">{q.quote_number}</td>
                  <td>{c?.name ?? '—'}</td>
                  <td className="font-medium">{formatCurrency(q.total)}</td>
                  <td>
                    <select className={`ec-input !py-1 !w-32 ${STATUS_BADGE[q.status] ?? ''}`} value={q.status}
                            onChange={(e) => updateStatus.mutate({ q, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    <button className="ec-btn-ghost" title="PDF" onClick={() => downloadPdf(q)}><Download size={14} /></button>
                    <button className="ec-btn-ghost" onClick={() => { setEditing(q); setShow(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete quote?')) remove.mutate(q.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No quotes.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ contacts, editing, onSaved, onCancel }: { contacts: Contact[]; editing: Quote | null; onSaved: () => void; onCancel: () => void }) {
  const [contactId, setContactId] = useState(editing?.contact_id ?? contacts[0]?.id ?? '');
  const [number, setNumber] = useState(editing?.quote_number ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'draft');
  const [total, setTotal] = useState(editing ? parseFloat(editing.total) : 2500);
  const save = useMutation({
    mutationFn: async () => {
      const body = { quote_number: number || null, contact_id: contactId || null, status, total };
      if (editing) return (await api.patch(`/crm/quotations/${editing.id}`, body)).data;
      return (await api.post('/crm/quotations', body)).data;
    },
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit quote' : 'New quote'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div><label className="ec-label">Number (auto if blank)</label><input className="ec-input" value={number} onChange={(e) => setNumber(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Contact</label>
          <select className="ec-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">—</option>
            {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Total</label><input type="number" step="any" className="ec-input" value={total} onChange={(e) => setTotal(Number(e.target.value))} /></div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}
