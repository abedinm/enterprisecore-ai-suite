import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Plus, Trash2, Edit3, Layers, X, Users } from 'lucide-react';
import { api } from '../../lib/api';
import type { Contact } from './CustomersTab';

type Segment = { id: string; name: string; rules: string };

const RULE_TEMPLATES = [
  { name: 'VIP tag', rules: { tag: 'vip' } },
  { name: 'Acme accounts', rules: { company_like: 'Acme' } },
  { name: 'Enterprise (open deals)', rules: { tag: 'enterprise', has_open_deals: true } },
  { name: 'Gmail contacts', rules: { email_domain: 'gmail.com' } },
];

export function SegmentsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Segment | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const segments = useQuery({
    queryKey: ['crm', 'segments'],
    queryFn: async () => (await api.get<Segment[]>('/crm/segments')).data,
  });
  useEffect(() => {
    if (segments.data?.length && !selected) setSelected(segments.data[0].id);
  }, [segments.data, selected]);

  const members = useQuery({
    enabled: !!selected,
    queryKey: ['crm', 'segments', selected, 'members'],
    queryFn: async () => (await api.get<Contact[]>(`/crm/segments/${selected}/members`)).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/segments/${id}`)).data,
    onSuccess: () => { setSelected(null); qc.invalidateQueries({ queryKey: ['crm', 'segments'] }); },
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Layers size={14} />Customer segments</p>
          <p className="text-sm text-ink-muted">{segments.data?.length ?? 0} segments · rules are JSON evaluated server-side</p>
        </div>
        <button className="ec-btn-primary" onClick={() => { setEditing(null); setShow((v) => !v); }}>
          <Plus size={16} /> {show && !editing ? 'Close' : 'New segment'}
        </button>
      </div>

      {(show || editing) && (
        <Form editing={editing}
          onSaved={(s) => { setShow(false); setEditing(null); setSelected(s.id); qc.invalidateQueries({ queryKey: ['crm', 'segments'] }); }}
          onCancel={() => { setShow(false); setEditing(null); }} />
      )}

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <div className="ec-card p-3">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Segments</p>
          {segments.data?.length ? (
            <ul className="space-y-1">
              {segments.data.map((s) => (
                <li key={s.id}>
                  <button onClick={() => setSelected(s.id)}
                          className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${selected === s.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}>
                    <span className="font-medium">{s.name}</span>
                    <Layers size={12} />
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="px-3 py-6 text-center text-sm text-ink-muted">No segments yet.</p>}
        </div>

        <div>
          {selected ? (() => {
            const seg = segments.data?.find((x) => x.id === selected);
            if (!seg) return null;
            let rules: Record<string, unknown> = {};
            try { rules = JSON.parse(seg.rules || '{}'); } catch { /* */ }
            return (
              <div className="space-y-3">
                <div className="ec-card p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-xl font-semibold">{seg.name}</h3>
                      <p className="text-xs text-ink-muted">{members.data?.length ?? 0} matching contact{(members.data?.length ?? 0) === 1 ? '' : 's'}</p>
                    </div>
                    <div className="flex gap-1">
                      <button className="ec-btn-ghost" onClick={() => { setEditing(seg); setShow(true); }}><Edit3 size={14} /></button>
                      <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete ' + seg.name + '?')) remove.mutate(seg.id); }}><Trash2 size={14} /></button>
                    </div>
                  </div>
                  <div className="mt-3 rounded-md bg-surface-muted p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Rules</p>
                    {Object.keys(rules).length ? (
                      <ul className="mt-1 space-y-1 text-sm">
                        {Object.entries(rules).map(([k, v]) => (
                          <li key={k}>
                            <code className="rounded bg-surface-elevated px-1.5 py-0.5 text-xs">{k}</code>{' '}
                            <strong>{String(v)}</strong>
                          </li>
                        ))}
                      </ul>
                    ) : <p className="text-xs text-ink-muted">No rules — segment matches no one.</p>}
                  </div>
                </div>

                <div className="ec-card overflow-hidden">
                  <div className="flex items-center gap-2 border-b border-border bg-surface-muted p-3 text-sm font-semibold">
                    <Users size={14} /> Members ({members.data?.length ?? 0})
                  </div>
                  <table className="ec-table">
                    <thead><tr><th>Name</th><th>Company</th><th>Email</th></tr></thead>
                    <tbody>
                      {members.data?.length ? members.data.map((m) => (
                        <tr key={m.id}>
                          <td className="font-medium">{m.name}</td>
                          <td>{m.company ?? '—'}</td>
                          <td>{m.email ?? '—'}</td>
                        </tr>
                      )) : <tr><td colSpan={3} className="py-6 text-center text-sm text-ink-muted">No matching contacts.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })() : <p className="text-sm text-ink-muted">Select a segment to view its members.</p>}
        </div>
      </div>
    </div>
  );
}

function Form({ editing, onSaved, onCancel }: { editing: Segment | null; onSaved: (s: Segment) => void; onCancel: () => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [rules, setRules] = useState(editing?.rules ?? '{"tag": "vip"}');
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      try { JSON.parse(rules); setError(null); }
      catch (e) { setError('Rules must be valid JSON'); throw e; }
      if (editing) return (await api.patch<Segment>(`/crm/segments/${editing.id}`, { name, rules })).data;
      return (await api.post<Segment>('/crm/segments', { name, rules })).data;
    },
    onSuccess: onSaved,
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit segment' : 'New segment'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="space-y-3">
        <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div>
          <label className="ec-label">Rules (JSON)</label>
          <textarea rows={6} className="ec-input font-mono text-xs" value={rules} onChange={(e) => setRules(e.target.value)} />
          {error && <p className="mt-1 text-xs text-rose-500">{error}</p>}
          <p className="mt-1 text-xs text-ink-muted">Supported keys: <code>tag</code>, <code>company_like</code>, <code>email_domain</code>, <code>has_open_deals</code></p>
        </div>
        <div>
          <label className="ec-label">Quick templates</label>
          <div className="flex flex-wrap gap-1">
            {RULE_TEMPLATES.map((t) => (
              <button key={t.name} type="button"
                className="rounded-md border border-border bg-surface-elevated px-2 py-1 text-xs hover:bg-surface-muted"
                onClick={() => setRules(JSON.stringify(t.rules, null, 2))}>
                {t.name}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}
