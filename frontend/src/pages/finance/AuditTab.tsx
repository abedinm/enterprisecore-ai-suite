import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { History, Filter } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';

type AuditEntry = {
  id: string; action: string; entity_type: string; entity_id: string | null;
  actor_id: string | null; detail: Record<string, unknown>; created_at: string;
};
type Summary = { total: number; by_entity: Record<string, number>; by_action: Record<string, number> };

const ENTITY_OPTIONS = [
  '', 'invoice', 'expense', 'expense_category', 'payroll_run', 'budget_plan',
  'tax_rate', 'vendor', 'vendor_payment', 'customer', 'recurring_payment', 'currency_rate',
];
const ACTION_OPTIONS = ['', 'create', 'update', 'delete', 'status_change'];

export function AuditTab() {
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [limit, setLimit] = useState(200);

  const entries = useQuery({
    queryKey: ['finance', 'audit', entityType, action, start, end, limit],
    queryFn: async () => (await api.get<AuditEntry[]>('/finance/audit-trail', {
      params: {
        ...(entityType ? { entity_type: entityType } : {}),
        ...(action ? { action } : {}),
        ...(start ? { start } : {}),
        ...(end ? { end } : {}),
        limit,
      },
    })).data,
  });

  const summary = useQuery({
    queryKey: ['finance', 'audit', 'summary'],
    queryFn: async () => (await api.get<Summary>('/finance/audit-trail/summary')).data,
  });

  function reset() {
    setEntityType(''); setAction(''); setStart(''); setEnd(''); setLimit(200);
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <History size={18} className="text-brand-600" />
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Financial audit trail</p>
          <p className="text-sm text-ink-muted">
            Every create / update / delete / status change in the Finance module is recorded with actor and timestamp.
          </p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Total events" value={summary.data?.total?.toString() ?? '—'} />
        <Tile label="Most active entity" value={topKey(summary.data?.by_entity) ?? '—'} />
        <Tile label="Most common action" value={topKey(summary.data?.by_action) ?? '—'} />
      </div>

      <div className="ec-card p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Filter size={14} />Filters</div>
        <div className="grid gap-3 md:grid-cols-6">
          <div>
            <label className="ec-label">Entity</label>
            <select className="ec-input" value={entityType} onChange={(e) => setEntityType(e.target.value)}>
              {ENTITY_OPTIONS.map((e) => <option key={e || 'any'} value={e}>{e || 'Any'}</option>)}
            </select>
          </div>
          <div>
            <label className="ec-label">Action</label>
            <select className="ec-input" value={action} onChange={(e) => setAction(e.target.value)}>
              {ACTION_OPTIONS.map((a) => <option key={a || 'any'} value={a}>{a || 'Any'}</option>)}
            </select>
          </div>
          <div><label className="ec-label">From</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <div><label className="ec-label">To</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
          <div><label className="ec-label">Limit</label><input type="number" className="ec-input" value={limit} min={10} max={1000} onChange={(e) => setLimit(Number(e.target.value))} /></div>
          <div className="flex items-end"><button className="ec-btn-secondary w-full" onClick={reset}>Reset</button></div>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Timestamp</th><th>Action</th><th>Entity</th><th>Entity ID</th><th>Actor</th><th>Detail</th></tr></thead>
          <tbody>
            {entries.isLoading ? (
              <tr><td colSpan={6} className="py-6 text-center text-ink-muted">Loading…</td></tr>
            ) : entries.data?.length ? entries.data.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap text-ink-muted">{formatDateTime(a.created_at)}</td>
                <td>
                  <span className={`ec-badge ${badgeColor(a.action)}`}>{a.action}</span>
                </td>
                <td>{a.entity_type}</td>
                <td className="font-mono text-xs text-ink-muted">{a.entity_id ? `${a.entity_id.slice(0, 8)}…` : '—'}</td>
                <td className="font-mono text-xs text-ink-muted">{a.actor_id ? `${a.actor_id.slice(0, 8)}…` : '—'}</td>
                <td className="max-w-md truncate text-xs text-ink-muted" title={JSON.stringify(a.detail)}>
                  {a.detail && Object.keys(a.detail).length ? JSON.stringify(a.detail) : '—'}
                </td>
              </tr>
            )) : <tr><td colSpan={6} className="py-10 text-center text-ink-muted">No audit events match the filters.</td></tr>}
          </tbody>
        </table>
      </div>

      {summary.data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="ec-card p-5">
            <p className="mb-2 text-sm font-semibold">Events by entity</p>
            <BreakdownList rows={summary.data.by_entity} />
          </div>
          <div className="ec-card p-5">
            <p className="mb-2 text-sm font-semibold">Events by action</p>
            <BreakdownList rows={summary.data.by_action} />
          </div>
        </div>
      )}
    </div>
  );
}

function badgeColor(action: string): string {
  if (action === 'create') return 'ec-badge-green';
  if (action === 'delete') return 'ec-badge-rose';
  if (action === 'update' || action === 'status_change') return 'ec-badge-amber';
  return 'ec-badge-blue';
}

function topKey(obj?: Record<string, number>): string | null {
  if (!obj) return null;
  const entries = Object.entries(obj).sort((a, b) => b[1] - a[1]);
  return entries[0] ? `${entries[0][0]} (${entries[0][1]})` : null;
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function BreakdownList({ rows }: { rows: Record<string, number> }) {
  const sorted = Object.entries(rows).sort((a, b) => b[1] - a[1]);
  const max = sorted[0]?.[1] ?? 1;
  if (!sorted.length) return <p className="text-sm text-ink-muted">No events yet.</p>;
  return (
    <ul className="space-y-2">
      {sorted.map(([k, v]) => (
        <li key={k}>
          <div className="flex justify-between text-sm"><span>{k}</span><strong>{v}</strong></div>
          <div className="mt-1 h-1.5 rounded bg-surface-muted">
            <div className="h-full rounded bg-brand-500" style={{ width: `${(v / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
