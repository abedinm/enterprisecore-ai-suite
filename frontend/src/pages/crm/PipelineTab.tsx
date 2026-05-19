import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Edit3, Trash2, X, Workflow, TrendingUp } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import type { Contact } from './CustomersTab';

type Deal = {
  id: string; contact_id: string | null; title: string; stage: string;
  value: string; probability: string; expected_close_date: string | null;
};
type PipelineDeal = {
  id: string; title: string; value: string; probability: string;
  expected_close_date: string | null; contact_id: string | null;
};
type Pipeline = { stages: { stage: string; deals: PipelineDeal[] }[] };

const STAGES = ['qualified', 'discovery', 'proposal', 'negotiation', 'won', 'lost'];
const STAGE_COLOR: Record<string, string> = {
  qualified: 'border-blue-500/40 bg-blue-500/5',
  discovery: 'border-cyan-500/40 bg-cyan-500/5',
  proposal: 'border-amber-500/40 bg-amber-500/5',
  negotiation: 'border-purple-500/40 bg-purple-500/5',
  won: 'border-emerald-500/40 bg-emerald-500/5',
  lost: 'border-rose-500/40 bg-rose-500/5',
};
const STAGE_TEXT: Record<string, string> = {
  qualified: 'text-blue-500', discovery: 'text-cyan-500', proposal: 'text-amber-500',
  negotiation: 'text-purple-500', won: 'text-emerald-500', lost: 'text-rose-500',
};

export function PipelineTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Deal | null>(null);

  const pipeline = useQuery({
    queryKey: ['crm', 'pipeline'],
    queryFn: async () => (await api.get<Pipeline>('/crm/deals/pipeline')).data,
  });
  const contacts = useQuery({
    queryKey: ['crm', 'contacts'],
    queryFn: async () => (await api.get<Contact[]>('/crm/contacts')).data,
  });

  const changeStage = useMutation({
    mutationFn: async ({ id, stage }: { id: string; stage: string }) =>
      (await api.post(`/crm/deals/${id}/stage`, { stage })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'pipeline'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/deals/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'pipeline'] }),
  });

  async function loadFullDeal(id: string) {
    const all = (await api.get<Deal[]>('/crm/deals')).data;
    return all.find((d) => d.id === id) ?? null;
  }

  const totalValue = pipeline.data?.stages
    .filter((s) => s.stage !== 'won' && s.stage !== 'lost')
    .reduce((sum, s) => sum + s.deals.reduce((x, d) => x + parseFloat(d.value), 0), 0) ?? 0;
  const weighted = pipeline.data?.stages
    .filter((s) => s.stage !== 'won' && s.stage !== 'lost')
    .reduce((sum, s) => sum + s.deals.reduce((x, d) => x + parseFloat(d.value) * parseFloat(d.probability) / 100, 0), 0) ?? 0;
  const wonValue = pipeline.data?.stages.find((s) => s.stage === 'won')?.deals.reduce((x, d) => x + parseFloat(d.value), 0) ?? 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Workflow size={14} /> Deal pipeline</p>
          <p className="text-sm text-ink-muted">Drag-free kanban · change stage via dropdown</p>
        </div>
        <button className="ec-btn-primary" onClick={() => { setEditing(null); setShow((v) => !v); }}>
          <Plus size={16} /> {show && !editing ? 'Close' : 'New deal'}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Open pipeline" value={formatCurrency(totalValue)} />
        <Tile label="Weighted forecast" value={formatCurrency(weighted)} tone="highlight" icon={<TrendingUp size={14} className="text-brand-600" />} />
        <Tile label="Won (closed)" value={formatCurrency(wonValue)} tone="positive" />
      </div>

      {(show || editing) && contacts.data && (
        <DealForm contacts={contacts.data} editing={editing}
          onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'pipeline'] }); }}
          onCancel={() => { setShow(false); setEditing(null); }} />
      )}

      <div className="grid gap-3 lg:grid-cols-6 md:grid-cols-3">
        {STAGES.map((stage) => {
          const col = pipeline.data?.stages.find((s) => s.stage === stage);
          const deals = col?.deals ?? [];
          const colTotal = deals.reduce((x, d) => x + parseFloat(d.value), 0);
          return (
            <div key={stage} className={`rounded-xl border ${STAGE_COLOR[stage]} p-3`}>
              <div className="mb-2 flex items-center justify-between">
                <p className={`text-xs font-semibold uppercase ${STAGE_TEXT[stage]}`}>{stage}</p>
                <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-[10px]">{deals.length}</span>
              </div>
              <p className="mb-2 text-xs text-ink-muted">{formatCurrency(colTotal)}</p>
              <div className="space-y-2">
                {deals.length ? deals.map((d) => {
                  const c = contacts.data?.find((x) => x.id === d.contact_id);
                  return (
                    <div key={d.id} className="rounded-md bg-surface-elevated p-2 text-xs shadow-sm">
                      <p className="font-medium">{d.title}</p>
                      <p className="text-ink-muted">{c?.name ?? '—'}</p>
                      <div className="mt-1 flex justify-between text-[11px]">
                        <span>{formatCurrency(d.value)}</span>
                        <span>{parseFloat(d.probability)}%</span>
                      </div>
                      {d.expected_close_date && <p className="text-[10px] text-ink-muted">close {formatDate(d.expected_close_date)}</p>}
                      <div className="mt-1 flex items-center gap-1">
                        <select className="ec-input !py-0.5 !text-[11px]" value={stage}
                          onChange={(e) => changeStage.mutate({ id: d.id, stage: e.target.value })}>
                          {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <button className="ec-btn-ghost !p-1" title="Edit"
                          onClick={async () => { const full = await loadFullDeal(d.id); if (full) { setEditing(full); setShow(true); } }}>
                          <Edit3 size={11} />
                        </button>
                        <button className="ec-btn-ghost text-rose-600 !p-1" title="Delete" onClick={() => { if (confirm('Delete deal ' + d.title + '?')) remove.mutate(d.id); }}>
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </div>
                  );
                }) : <p className="py-4 text-center text-[10px] text-ink-muted">No deals</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Tile({ label, value, tone, icon }: { label: string; value: string; tone?: 'positive' | 'highlight'; icon?: React.ReactNode }) {
  const cls = tone === 'positive' ? 'text-emerald-500' : tone === 'highlight' ? 'text-brand-600' : '';
  return (
    <div className="ec-card p-4">
      <p className="flex items-center gap-1 text-xs text-ink-muted">{icon}{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

function DealForm({ contacts, editing, onSaved, onCancel }: { contacts: Contact[]; editing: Deal | null; onSaved: () => void; onCancel: () => void }) {
  const [contactId, setContactId] = useState(editing?.contact_id ?? contacts[0]?.id ?? '');
  const [title, setTitle] = useState(editing?.title ?? '');
  const [stage, setStage] = useState(editing?.stage ?? 'qualified');
  const [value, setValue] = useState(editing ? parseFloat(editing.value) : 5000);
  const [probability, setProbability] = useState(editing ? parseFloat(editing.probability) : 30);
  const [closeDate, setCloseDate] = useState(editing?.expected_close_date ?? new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10));
  const save = useMutation({
    mutationFn: async () => {
      const body = { contact_id: contactId || null, title, stage, value, probability, expected_close_date: closeDate || null };
      if (editing) return (await api.patch(`/crm/deals/${editing.id}`, body)).data;
      return (await api.post('/crm/deals', body)).data;
    },
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit deal' : 'New deal'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div className="md:col-span-2"><label className="ec-label">Contact</label>
          <select className="ec-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">—</option>
            {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Stage</label>
          <select className="ec-input" value={stage} onChange={(e) => setStage(e.target.value)}>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Value</label><input type="number" step="any" className="ec-input" value={value} onChange={(e) => setValue(Number(e.target.value))} /></div>
        <div><label className="ec-label">Probability %</label><input type="number" min={0} max={100} className="ec-input" value={probability} onChange={(e) => setProbability(Number(e.target.value))} /></div>
        <div><label className="ec-label">Expected close</label><input type="date" className="ec-input" value={closeDate ?? ''} onChange={(e) => setCloseDate(e.target.value)} /></div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}
