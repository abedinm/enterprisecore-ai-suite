import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Check, Phone, AlertTriangle } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Contact } from './CustomersTab';

type FollowUp = { id: string; contact_id: string | null; due_at: string; status: string; notes: string };

export function FollowUpsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [openOnly, setOpenOnly] = useState(true);

  const followUps = useQuery({
    queryKey: ['crm', 'follow-ups', openOnly],
    queryFn: async () => (await api.get<FollowUp[]>('/crm/follow-ups', { params: { open_only: openOnly } })).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });

  const complete = useMutation({
    mutationFn: async (id: string) => (await api.post(`/crm/follow-ups/${id}/complete`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'follow-ups'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/follow-ups/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'follow-ups'] }),
  });

  const now = new Date();
  const overdueCount = (followUps.data ?? []).filter((f) => f.status === 'open' && new Date(f.due_at) < now).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Phone size={14} />Follow-ups</p>
          <p className="text-sm text-ink-muted">{followUps.data?.length ?? 0} {openOnly ? 'open' : 'total'}</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} />
            Open only
          </label>
          <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}>
            <Plus size={16} /> {show ? 'Close' : 'New follow-up'}
          </button>
        </div>
      </div>

      {overdueCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-500/5 px-4 py-2 text-sm">
          <AlertTriangle size={16} className="text-rose-500" />
          <span><strong>{overdueCount}</strong> follow-up{overdueCount === 1 ? '' : 's'} overdue.</span>
        </div>
      )}

      {show && contacts.data && <Form contacts={contacts.data} onSaved={() => { setShow(false); qc.invalidateQueries({ queryKey: ['crm', 'follow-ups'] }); }} />}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Due</th><th>Contact</th><th>Status</th><th>Notes</th><th></th></tr></thead>
          <tbody>
            {followUps.data?.length ? followUps.data.map((f) => {
              const c = contacts.data?.find((x) => x.id === f.contact_id);
              const overdue = f.status === 'open' && new Date(f.due_at) < now;
              return (
                <tr key={f.id} className={overdue ? 'bg-rose-500/5' : ''}>
                  <td className={overdue ? 'font-medium text-rose-500' : ''}>{formatDateTime(f.due_at)}{overdue && ' (overdue)'}</td>
                  <td className="font-medium">{c?.name ?? '—'}</td>
                  <td><span className={`ec-badge ${f.status === 'completed' ? 'ec-badge-green' : 'ec-badge-amber'}`}>{f.status}</span></td>
                  <td className="max-w-md truncate text-xs text-ink-muted" title={f.notes}>{f.notes || '—'}</td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    {f.status === 'open' && <button className="ec-btn-ghost text-emerald-600" onClick={() => complete.mutate(f.id)}><Check size={14} /></button>}
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete follow-up?')) remove.mutate(f.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No follow-ups.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ contacts, onSaved }: { contacts: Contact[]; onSaved: () => void }) {
  const [contactId, setContactId] = useState(contacts[0]?.id ?? '');
  const [dueAt, setDueAt] = useState(new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 16));
  const [notes, setNotes] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/crm/follow-ups', {
      contact_id: contactId || null, due_at: new Date(dueAt).toISOString(), status: 'open', notes,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-4">
      <div className="md:col-span-2"><label className="ec-label">Contact</label>
        <select className="ec-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
          <option value="">—</option>
          {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div className="md:col-span-2"><label className="ec-label">Due at</label><input type="datetime-local" className="ec-input" value={dueAt} onChange={(e) => setDueAt(e.target.value)} /></div>
      <div className="md:col-span-4"><label className="ec-label">Notes</label><textarea rows={2} className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="md:col-span-4 flex justify-end"><button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
    </div>
  );
}
