import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, ArrowRight, Star } from 'lucide-react';
import { api } from '../../lib/api';
import type { Contact } from './CustomersTab';

type Lead = { id: string; contact_id: string | null; source: string | null; status: string; score: number; notes: string };

const STATUSES = ['new', 'contacted', 'qualified', 'converted', 'lost'];
const STATUS_BADGE: Record<string, string> = {
  new: 'ec-badge-blue', contacted: 'ec-badge-amber', qualified: 'ec-badge-amber',
  converted: 'ec-badge-green', lost: 'ec-badge-rose',
};

export function LeadsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Lead | null>(null);
  const [statusFilter, setStatusFilter] = useState('');

  const leads = useQuery({
    queryKey: ['crm', 'leads', statusFilter],
    queryFn: async () => (await api.get<Lead[]>('/crm/leads', { params: statusFilter ? { status: statusFilter } : {} })).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/leads/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'leads'] }),
  });
  const convert = useMutation({
    mutationFn: async (id: string) => (await api.post(`/crm/leads/${id}/convert`)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['crm', 'leads'] }); qc.invalidateQueries({ queryKey: ['crm', 'deals'] }); },
  });

  const counts = (leads.data ?? []).reduce<Record<string, number>>((acc, l) => { acc[l.status] = (acc[l.status] ?? 0) + 1; return acc; }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Leads</p>
          <p className="text-sm text-ink-muted">{leads.data?.length ?? 0} leads</p>
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
            <Plus size={16} /> {show && !editing ? 'Close' : 'New lead'}
          </button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-5">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s}</p>
            <p className="text-xl font-semibold">{counts[s] ?? 0}</p>
          </div>
        ))}
      </div>

      {(show || editing) && contacts.data && (
        <Form contacts={contacts.data} editing={editing}
          onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'leads'] }); }}
          onCancel={() => { setShow(false); setEditing(null); }} />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Contact</th><th>Source</th><th>Score</th><th>Status</th><th>Notes</th><th></th></tr></thead>
          <tbody>
            {leads.data?.length ? leads.data.map((l) => {
              const c = contacts.data?.find((x) => x.id === l.contact_id);
              return (
                <tr key={l.id}>
                  <td className="font-medium">{c?.name ?? '—'}</td>
                  <td>{l.source ?? '—'}</td>
                  <td><span className="inline-flex items-center gap-1"><Star size={12} className="text-amber-500" /><strong>{l.score}</strong></span></td>
                  <td><span className={`ec-badge ${STATUS_BADGE[l.status] ?? 'ec-badge'}`}>{l.status}</span></td>
                  <td className="max-w-md truncate text-xs text-ink-muted" title={l.notes}>{l.notes || '—'}</td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    {l.status !== 'converted' && l.status !== 'lost' && (
                      <button className="ec-btn-ghost text-emerald-600" title="Convert to deal" onClick={() => convert.mutate(l.id)}><ArrowRight size={14} /></button>
                    )}
                    <button className="ec-btn-ghost" onClick={() => { setEditing(l); setShow(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete lead?')) remove.mutate(l.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No leads.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ contacts, editing, onSaved, onCancel }: { contacts: Contact[]; editing: Lead | null; onSaved: () => void; onCancel: () => void }) {
  const [contactId, setContactId] = useState(editing?.contact_id ?? contacts[0]?.id ?? '');
  const [source, setSource] = useState(editing?.source ?? 'website');
  const [status, setStatus] = useState(editing?.status ?? 'new');
  const [score, setScore] = useState(editing?.score ?? 50);
  const [notes, setNotes] = useState(editing?.notes ?? '');
  const save = useMutation({
    mutationFn: async () => {
      const body = { contact_id: contactId || null, source: source || null, status, score, notes };
      if (editing) return (await api.patch(`/crm/leads/${editing.id}`, body)).data;
      return (await api.post('/crm/leads', body)).data;
    },
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit lead' : 'New lead'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="md:col-span-2"><label className="ec-label">Contact</label>
          <select className="ec-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">—</option>
            {contacts.map((c) => <option key={c.id} value={c.id}>{c.name} {c.company ? `· ${c.company}` : ''}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Source</label><input className="ec-input" value={source ?? ''} onChange={(e) => setSource(e.target.value)} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Score</label><input type="number" min={0} max={100} className="ec-input" value={score} onChange={(e) => setScore(Number(e.target.value))} /></div>
        <div className="md:col-span-4"><label className="ec-label">Notes</label><textarea rows={3} className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}
