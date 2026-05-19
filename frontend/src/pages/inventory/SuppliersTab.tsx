import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Star, Search } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { Supplier } from './types';

export function SuppliersTab() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [activeOnly, setActiveOnly] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);

  const suppliers = useQuery({
    queryKey: ['inventory', 'suppliers', q, activeOnly],
    queryFn: async () => (await api.get<Supplier[]>('/inventory/suppliers', {
      params: { ...(q ? { q } : {}), ...(activeOnly ? { is_active: true } : {}) },
    })).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/inventory/suppliers/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['inventory', 'suppliers'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Supplier Tracker</p>
          <p className="text-sm text-ink-muted">{suppliers.data?.length ?? 0} suppliers · {(suppliers.data ?? []).filter((s) => s.is_active).length} active</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle" />
            <input className="ec-input pl-8" placeholder="Search name, email…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Active only</label>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> Add supplier</button>
        </div>
      </div>

      {(showForm || editing) && (
        <SupplierForm
          editing={editing}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['inventory', 'suppliers'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead>
            <tr><th>Name</th><th>Contact</th><th>Email</th><th>Phone</th><th>Terms</th><th>Lead</th><th>Rating</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {suppliers.data?.length ? suppliers.data.map((s) => (
              <tr key={s.id}>
                <td className="font-medium">{s.name}</td>
                <td>{s.contact_person ?? '—'}</td>
                <td>{s.email ?? '—'}</td>
                <td>{s.phone ?? '—'}</td>
                <td>{s.payment_terms}</td>
                <td>{s.lead_time_days}d</td>
                <td>
                  <div className="flex items-center gap-0.5">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <Star key={n} size={12} className={n <= s.rating ? 'fill-amber-400 text-amber-400' : 'text-ink-subtle'} />
                    ))}
                  </div>
                </td>
                <td>{s.is_active ? <span className="ec-badge-green">active</span> : <span className="ec-badge">inactive</span>}</td>
                <td className="text-right whitespace-nowrap">
                  <button className="ec-btn-ghost" onClick={() => { setEditing(s); setShowForm(true); }}><Edit3 size={14} /></button>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete supplier?')) remove.mutate(s.id); }}><Trash2 size={14} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={9} className="py-10 text-center text-ink-muted">No suppliers yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SupplierForm({ editing, onSaved, onCancel }: { editing: Supplier | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [contact, setContact] = useState(editing?.contact_person ?? '');
  const [email, setEmail] = useState(editing?.email ?? '');
  const [phone, setPhone] = useState(editing?.phone ?? '');
  const [address, setAddress] = useState(editing?.address ?? '');
  const [taxId, setTaxId] = useState(editing?.tax_id ?? '');
  const [terms, setTerms] = useState(editing?.payment_terms ?? 'Net 30');
  const [rating, setRating] = useState(editing?.rating ?? 0);
  const [leadTime, setLeadTime] = useState(editing?.lead_time_days ?? 7);
  const [active, setActive] = useState(editing?.is_active ?? true);
  const [notes, setNotes] = useState(editing?.notes ?? '');

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name, contact_person: contact || null, email: email || null,
        phone: phone || null, address: address || null, tax_id: taxId || null,
        payment_terms: terms, rating, lead_time_days: leadTime, is_active: active, notes,
      };
      if (editing) return (await api.patch(`/inventory/suppliers/${editing.id}`, body)).data;
      return (await api.post('/inventory/suppliers', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit supplier' : 'Add supplier'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Contact person</label><input className="ec-input" value={contact ?? ''} onChange={(e) => setContact(e.target.value)} /></div>
        <div><label className="ec-label">Email</label><input className="ec-input" value={email ?? ''} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="ec-label">Phone</label><input className="ec-input" value={phone ?? ''} onChange={(e) => setPhone(e.target.value)} /></div>
        <div><label className="ec-label">Tax ID</label><input className="ec-input" value={taxId ?? ''} onChange={(e) => setTaxId(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Address</label><textarea className="ec-input" rows={2} value={address ?? ''} onChange={(e) => setAddress(e.target.value)} /></div>
        <div><label className="ec-label">Payment terms</label><input className="ec-input" value={terms} onChange={(e) => setTerms(e.target.value)} placeholder="Net 30" /></div>
        <div><label className="ec-label">Lead time (days)</label><input type="number" className="ec-input" value={leadTime} onChange={(e) => setLeadTime(Number(e.target.value))} /></div>
        <div><label className="ec-label">Rating (0-5)</label><input type="number" min={0} max={5} className="ec-input" value={rating} onChange={(e) => setRating(Number(e.target.value))} /></div>
        <div className="md:col-span-3"><label className="ec-label">Notes</label><textarea className="ec-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Add'}</button>
      </div>
    </div>
  );
}
