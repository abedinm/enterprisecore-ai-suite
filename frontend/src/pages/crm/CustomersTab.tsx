import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Check, Search } from 'lucide-react';
import { api } from '../../lib/api';

export type Contact = { id: string; name: string; company: string | null; email: string | null; phone: string | null; tags: string };

export function CustomersTab() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Contact | null>(null);

  const contacts = useQuery({
    queryKey: ['crm', 'contacts', q],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts', { params: q ? { q } : {} })).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/contacts/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'contacts'] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Customers</p>
          <p className="text-sm text-ink-muted">{contacts.data?.length ?? 0} contacts</p>
        </div>
        <div className="flex items-end gap-2">
          <div className="relative">
            <label className="ec-label">Search</label>
            <Search size={14} className="pointer-events-none absolute left-3 top-[34px] text-ink-subtle" />
            <input className="ec-input pl-9 md:!w-64" placeholder="name, company, email" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShow((v) => !v); }}>
            <Plus size={16} /> {show && !editing ? 'Close' : 'New customer'}
          </button>
        </div>
      </div>

      {(show || editing) && <Form editing={editing} onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'contacts'] }); }} onCancel={() => { setShow(false); setEditing(null); }} />}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Name</th><th>Company</th><th>Email</th><th>Phone</th><th>Tags</th><th></th></tr></thead>
          <tbody>
            {contacts.data?.length ? contacts.data.map((c) => {
              let tags: string[] = [];
              try { tags = JSON.parse(c.tags || '[]'); } catch { tags = []; }
              return (
                <tr key={c.id}>
                  <td className="font-medium">{c.name}</td>
                  <td>{c.company ?? '—'}</td>
                  <td>{c.email ?? '—'}</td>
                  <td>{c.phone ?? '—'}</td>
                  <td className="space-x-1">{tags.length ? tags.map((t) => <span key={t} className="ec-badge ec-badge-blue">{t}</span>) : '—'}</td>
                  <td className="text-right whitespace-nowrap">
                    <button className="ec-btn-ghost" onClick={() => { setEditing(c); setShow(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + c.name + '?')) remove.mutate(c.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No customers yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Form({ editing, onSaved, onCancel }: { editing: Contact | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [company, setCompany] = useState(editing?.company ?? '');
  const [email, setEmail] = useState(editing?.email ?? '');
  const [phone, setPhone] = useState(editing?.phone ?? '');
  const [tags, setTags] = useState<string>(editing ? (JSON.parse(editing.tags || '[]') as string[]).join(', ') : '');

  const save = useMutation({
    mutationFn: async () => {
      const tagsArr = tags.split(',').map((t) => t.trim()).filter(Boolean);
      const body = { name, company: company || null, email: email || null, phone: phone || null, tags: JSON.stringify(tagsArr) };
      if (editing) return (await api.patch(`/crm/contacts/${editing.id}`, body)).data;
      return (await api.post('/crm/contacts', body)).data;
    },
    onSuccess: onSaved,
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? `Edit ${editing.name}` : 'New customer'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Company</label><input className="ec-input" value={company ?? ''} onChange={(e) => setCompany(e.target.value)} /></div>
        <div><label className="ec-label">Email</label><input className="ec-input" value={email ?? ''} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="ec-label">Phone</label><input className="ec-input" value={phone ?? ''} onChange={(e) => setPhone(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Tags (comma-separated)</label><input className="ec-input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="vip, hot-lead, enterprise" /></div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : (editing ? <><Check size={14} /> Save</> : 'Create')}
        </button>
      </div>
    </div>
  );
}
