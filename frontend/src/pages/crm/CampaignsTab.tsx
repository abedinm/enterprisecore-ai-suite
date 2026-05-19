import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, Send, BarChart3, X } from 'lucide-react';
import { api } from '../../lib/api';

type Campaign = { id: string; name: string; status: string; sent_count: number; open_count: number; click_count: number };

const STATUSES = ['draft', 'scheduled', 'sending', 'sent', 'paused', 'cancelled'];
const STATUS_BADGE: Record<string, string> = {
  draft: 'ec-badge-blue', scheduled: 'ec-badge-amber', sending: 'ec-badge-amber',
  sent: 'ec-badge-green', paused: 'ec-badge', cancelled: 'ec-badge-rose',
};

export function CampaignsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [metricsFor, setMetricsFor] = useState<string | null>(null);

  const campaigns = useQuery({
    queryKey: ['crm', 'campaigns'],
    queryFn: async () => (await api.get<Campaign[]>('/crm/campaigns')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/crm/campaigns/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'campaigns'] }),
  });
  const updateStatus = useMutation({
    mutationFn: async ({ c, status }: { c: Campaign; status: string }) =>
      (await api.patch(`/crm/campaigns/${c.id}`, { name: c.name, status })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm', 'campaigns'] }),
  });

  const totals = (campaigns.data ?? []).reduce(
    (acc, c) => ({ sent: acc.sent + c.sent_count, opens: acc.opens + c.open_count, clicks: acc.clicks + c.click_count }),
    { sent: 0, opens: 0, clicks: 0 },
  );

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><Send size={14} />Email campaigns</p>
          <p className="text-sm text-ink-muted">{campaigns.data?.length ?? 0} campaigns</p>
        </div>
        <button className="ec-btn-primary" onClick={() => { setEditing(null); setShow((v) => !v); }}>
          <Plus size={16} /> {show && !editing ? 'Close' : 'New campaign'}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Total sent" value={totals.sent.toString()} />
        <Tile label="Total opens" value={totals.opens.toString()} tone="positive"
              subtitle={totals.sent ? `${((totals.opens / totals.sent) * 100).toFixed(1)}% open rate` : ''} />
        <Tile label="Total clicks" value={totals.clicks.toString()} tone="highlight"
              subtitle={totals.opens ? `${((totals.clicks / totals.opens) * 100).toFixed(1)}% CTR` : ''} />
      </div>

      {(show || editing) && <Form editing={editing} onSaved={() => { setShow(false); setEditing(null); qc.invalidateQueries({ queryKey: ['crm', 'campaigns'] }); }} onCancel={() => { setShow(false); setEditing(null); }} />}

      {metricsFor && <MetricsPanel campaignId={metricsFor} onClose={() => setMetricsFor(null)} onSaved={() => { setMetricsFor(null); qc.invalidateQueries({ queryKey: ['crm', 'campaigns'] }); }} />}

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Name</th><th>Status</th><th>Sent</th><th>Opens</th><th>Clicks</th><th>Open rate</th><th>CTR</th><th></th></tr></thead>
          <tbody>
            {campaigns.data?.length ? campaigns.data.map((c) => {
              const openRate = c.sent_count ? (c.open_count / c.sent_count) * 100 : 0;
              const ctr = c.open_count ? (c.click_count / c.open_count) * 100 : 0;
              return (
                <tr key={c.id}>
                  <td className="font-medium">{c.name}</td>
                  <td>
                    <select className={`ec-input !py-1 !w-32 ${STATUS_BADGE[c.status] ?? ''}`} value={c.status}
                            onChange={(e) => updateStatus.mutate({ c, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>{c.sent_count}</td>
                  <td>{c.open_count}</td>
                  <td>{c.click_count}</td>
                  <td>{openRate.toFixed(1)}%</td>
                  <td>{ctr.toFixed(1)}%</td>
                  <td className="space-x-1 whitespace-nowrap text-right">
                    <button className="ec-btn-ghost" title="Update metrics" onClick={() => setMetricsFor(c.id)}><BarChart3 size={14} /></button>
                    <button className="ec-btn-ghost" onClick={() => { setEditing(c); setShow(true); }}><Edit3 size={14} /></button>
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete campaign?')) remove.mutate(c.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={8} className="py-8 text-center text-ink-muted">No campaigns.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value, tone, subtitle }: { label: string; value: string; tone?: 'positive' | 'highlight'; subtitle?: string }) {
  const cls = tone === 'positive' ? 'text-emerald-500' : tone === 'highlight' ? 'text-brand-600' : '';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
      {subtitle && <p className="text-xs text-ink-muted">{subtitle}</p>}
    </div>
  );
}

function Form({ editing, onSaved, onCancel }: { editing: Campaign | null; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState(editing?.name ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'draft');
  const save = useMutation({
    mutationFn: async () => {
      const body = { name, status };
      if (editing) return (await api.patch(`/crm/campaigns/${editing.id}`, body)).data;
      return (await api.post('/crm/campaigns', body)).data;
    },
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit campaign' : 'New campaign'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Campaign name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : (editing ? 'Save' : 'Create')}</button>
      </div>
    </div>
  );
}

function MetricsPanel({ campaignId, onClose, onSaved }: { campaignId: string; onClose: () => void; onSaved: () => void }) {
  const [sent, setSent] = useState(0);
  const [opens, setOpens] = useState(0);
  const [clicks, setClicks] = useState(0);
  const save = useMutation({
    mutationFn: async () => (await api.post(`/crm/campaigns/${campaignId}/metrics`, null, { params: { sent, opens, clicks } })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">Add metrics</h3>
        <button className="ec-btn-ghost" onClick={onClose}><X size={16} /></button>
      </div>
      <p className="mb-3 text-xs text-ink-muted">These values are <em>added</em> to existing counts (deltas).</p>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Sent (Δ)</label><input type="number" className="ec-input" value={sent} onChange={(e) => setSent(Number(e.target.value))} /></div>
        <div><label className="ec-label">Opens (Δ)</label><input type="number" className="ec-input" value={opens} onChange={(e) => setOpens(Number(e.target.value))} /></div>
        <div><label className="ec-label">Clicks (Δ)</label><input type="number" className="ec-input" value={clicks} onChange={(e) => setClicks(Number(e.target.value))} /></div>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onClose}>Cancel</button>
        <button className="ec-btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Apply'}</button>
      </div>
    </div>
  );
}
