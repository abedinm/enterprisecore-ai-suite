import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, FileSignature } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import type { Contact } from './CustomersTab';

type Contract = { id: string; contact_id: string | null; title: string; status: string; value: string; file_path: string | null; created_at?: string };

const STATUSES = ['draft', 'sent', 'signed', 'active', 'expired', 'cancelled'];
const STATUS_BADGE: Record<string, string> = {
  draft: 'ec-badge-blue', sent: 'ec-badge-amber', signed: 'ec-badge-green',
  active: 'ec-badge-green', expired: 'ec-badge', cancelled: 'ec-badge-rose',
};

export function ContractsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Contract | null>(null);
  const [statusFilter, setStatusFilter] = useState('');

  const contracts = useQuery({
    queryKey: ['crm', 'contracts', statusFilter],
    queryFn: async () => (await api.get<Contract[]>('/crm/contracts', { params: statusFilter ? { status: statusFilter } : {} })).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/contracts/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'contracts'] }),
  });
  const updateStatus = useMutation({
    mutationFn: async ({ c, status }: { c: Contract; status: string }) =>
      (await api.patch(`/crm/contracts/${c.id}`, {
        contact_id: c.contact_id, title: c.title, status, value: parseFloat(c.value), file_path: c.file_path,
      })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'contracts'] }),
  });

  const totals = (contracts.data ?? []).reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + parseFloat(c.value);
    return acc;
  }, {});
  const totalValue = (contracts.data ?? []).reduce((s, c) => s + parseFloat(c.value), 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><FileSignature size={14} />Contracts</p>
          <p className="text-sm text-ink-muted">{contracts.data?.length ?? 0} contracts · total value {formatCurrency(totalValue)}</p>
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
            <Plus size={16} /> {show && !editing ? 'Close' : 'New contract'}
          </button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-6">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s}</p>
            <p className="text-sm font-semibold">{formatCurrency(totals[s] ?? 0)}</p>
          </div>
        ))}
      </div>

      {(show || editing) && contacts.data && (
        <Form contacts={contacts.data} editing={editing}
          onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'contracts'] }); }}
          onCancel={() => { setShow(false); setEditing(null); }} />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Title</th><th>Contact</th><th>Value</th><th>Status</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {contracts.data?.length ? contracts.data.map((c) => {
              const contact = contacts.data?.find((x) => x.id === c.contact_id);
              return (
                <tr key={c.id}>
                  <td className="font-medium">{c.title}</td>
                  <td>{contact?.name ?? '—'}</td>
                  <td>{formatCurrency(c.value)}</td>
                  <td>
                    <select className={`ec-input !py-1 !w-32 ${STATUS_BADGE[c.status] ?? ''}`} value={c.status}
                            onChange={(e) => updateStatus.mutate({ c, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>{formatDate(c.created_at ?? null)}</td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    <button className="ec-btn-ghost" onClick={() => { setEditing(c); setShow(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete contract?')) remove.mutate(c.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No contracts.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ contacts, editing, onSaved, onCancel }: { contacts: Contact[]; editing: Contract | null; onSaved: () => void; onCancel: () => void }) {
  const [contactId, setContactId] = useState(editing?.contact_id ?? contacts[0]?.id ?? '');
  const [title, setTitle] = useState(editing?.title ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'draft');
  const [value, setValue] = useState(editing ? parseFloat(editing.value) : 10000);
  const [filePath, setFilePath] = useState(editing?.file_path ?? '');
  const save = useMutation({
    mutationFn: async () => {
      const body = { contact_id: contactId || null, title, status, value, file_path: filePath || null };
      if (editing) return (await api.patch(`/crm/contracts/${editing.id}`, body)).data;
      return (await api.post('/crm/contracts', body)).data;
    },
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit contract' : 'New contract'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="ec-label">Value</label><input type="number" step="any" className="ec-input" value={value} onChange={(e) => setValue(Number(e.target.value))} /></div>
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
        <div><label className="ec-label">File path</label><input className="ec-input" value={filePath ?? ''} onChange={(e) => setFilePath(e.target.value)} placeholder="optional" /></div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}
