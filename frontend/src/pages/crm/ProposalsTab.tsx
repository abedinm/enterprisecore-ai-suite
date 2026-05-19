import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, Download, X, FileText } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';
import type { Contact } from './CustomersTab';

type Proposal = { id: string; contact_id: string | null; title: string; status: string; amount: string; body: string };

const STATUSES = ['draft', 'sent', 'accepted', 'rejected', 'expired'];
const STATUS_BADGE: Record<string, string> = {
  draft: 'ec-badge-blue', sent: 'ec-badge-amber',
  accepted: 'ec-badge-green', rejected: 'ec-badge-rose', expired: 'ec-badge',
};

export function ProposalsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Proposal | null>(null);
  const [statusFilter, setStatusFilter] = useState('');

  const proposals = useQuery({
    queryKey: ['crm', 'proposals', statusFilter],
    queryFn: async () => (await api.get<Proposal[]>('/crm/proposals', { params: statusFilter ? { status: statusFilter } : {} })).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/proposals/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'proposals'] }),
  });
  const updateStatus = useMutation({
    mutationFn: async ({ p, status }: { p: Proposal; status: string }) =>
      (await api.patch(`/crm/proposals/${p.id}`, {
        contact_id: p.contact_id, title: p.title, status, amount: parseFloat(p.amount), body: p.body,
      })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'proposals'] }),
  });

  async function downloadPdf(p: Proposal) {
    const r = await api.get(`/crm/proposals/${p.id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a'); a.href = url; a.download = `proposal-${p.id.slice(0, 8)}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const totalValue = (proposals.data ?? []).reduce((s, p) => s + parseFloat(p.amount), 0);
  const totals = (proposals.data ?? []).reduce<Record<string, number>>((acc, p) => { acc[p.status] = (acc[p.status] ?? 0) + parseFloat(p.amount); return acc; }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><FileText size={14} />Proposals</p>
          <p className="text-sm text-ink-muted">{proposals.data?.length ?? 0} proposals · total {formatCurrency(totalValue)}</p>
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
            <Plus size={16} /> {show && !editing ? 'Close' : 'New proposal'}
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
          onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'proposals'] }); }}
          onCancel={() => { setShow(false); setEditing(null); }} />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Title</th><th>Contact</th><th>Amount</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {proposals.data?.length ? proposals.data.map((p) => {
              const c = contacts.data?.find((x) => x.id === p.contact_id);
              return (
                <tr key={p.id}>
                  <td className="font-medium">{p.title}</td>
                  <td>{c?.name ?? '—'}</td>
                  <td>{formatCurrency(p.amount)}</td>
                  <td>
                    <select className={`ec-input !py-1 !w-32 ${STATUS_BADGE[p.status] ?? ''}`} value={p.status}
                            onChange={(e) => updateStatus.mutate({ p, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    <button className="ec-btn-ghost" title="PDF" onClick={() => downloadPdf(p)}><Download size={14} /></button>
                    <button className="ec-btn-ghost" onClick={() => { setEditing(p); setShow(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete proposal?')) remove.mutate(p.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No proposals.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ contacts, editing, onSaved, onCancel }: { contacts: Contact[]; editing: Proposal | null; onSaved: () => void; onCancel: () => void }) {
  const [contactId, setContactId] = useState(editing?.contact_id ?? contacts[0]?.id ?? '');
  const [title, setTitle] = useState(editing?.title ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'draft');
  const [amount, setAmount] = useState(editing ? parseFloat(editing.amount) : 5000);
  const [body, setBody] = useState(editing?.body ?? '');
  const save = useMutation({
    mutationFn: async () => {
      const data = { contact_id: contactId || null, title, status, amount, body };
      if (editing) return (await api.patch(`/crm/proposals/${editing.id}`, data)).data;
      return (await api.post('/crm/proposals', data)).data;
    },
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit proposal' : 'New proposal'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="ec-label">Amount</label><input type="number" step="any" className="ec-input" value={amount} onChange={(e) => setAmount(Number(e.target.value))} /></div>
        <div><label className="ec-label">Contact</label>
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
      </div>
      <div className="mt-3"><label className="ec-label">Body / sections</label><textarea rows={6} className="ec-input" value={body} onChange={(e) => setBody(e.target.value)} placeholder="Use double newlines to separate sections in the PDF." /></div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}
