import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Plus, Trash2, BarChart3 } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type BudgetItem = { id?: string; category: string; planned_amount: number; actual_amount: number };
type Budget = { id: string; name: string; fiscal_year: number; currency: string; items: BudgetItem[] };
type AnalyticsRow = { id: string; category: string; planned: string; actual: string; variance: string; utilization: string };
type Analytics = {
  plan_id: string; name: string; fiscal_year: number; currency: string;
  rows: AnalyticsRow[];
  totals: { planned: string; actual: string; variance: string };
};

const SUGGESTED_CATS = ['Travel', 'Software', 'Utilities', 'Office', 'Marketing', 'Payroll', 'Rent', 'Insurance'];

export function BudgetsTab() {
  const qc = useQueryClient();
  const [show, setShow] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const budgets = useQuery({
    queryKey: ['finance', 'budgets'],
    queryFn: async () => (await api.get<Budget[]>('/finance/budgets')).data,
  });

  useEffect(() => {
    if (budgets.data?.length && !selectedId) setSelectedId(budgets.data[0].id);
  }, [budgets.data, selectedId]);

  const analytics = useQuery({
    enabled: !!selectedId,
    queryKey: ['finance', 'budgets', selectedId, 'analytics'],
    queryFn: async () => (await api.get<Analytics>(`/finance/budgets/${selectedId}/analytics`)).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/budgets/${id}`)).data,
    onSuccess: () => { setSelectedId(null); qc.invalidateQueries({ queryKey: ['finance', 'budgets'] }); },
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-muted">{budgets.data?.length ?? 0} budget plans · variance tracked against expense categories</p>
        <button className="ec-btn-primary" onClick={() => setShow((v) => !v)}>
          <Plus size={16} /> {show ? 'Close form' : 'New budget plan'}
        </button>
      </div>

      {show && <BudgetForm onSaved={(plan) => { setShow(false); setSelectedId(plan.id); qc.invalidateQueries({ queryKey: ['finance', 'budgets'] }); }} />}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="ec-card p-3">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Plans</p>
          {budgets.data?.length ? (
            <ul className="space-y-1">
              {budgets.data.map((b) => (
                <li key={b.id}>
                  <button
                    onClick={() => setSelectedId(b.id)}
                    className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm ${selectedId === b.id ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'}`}
                  >
                    <span className="font-medium">{b.name}</span>
                    <span className={`text-xs ${selectedId === b.id ? 'text-white/80' : 'text-ink-muted'}`}>{b.fiscal_year}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="px-3 py-6 text-center text-sm text-ink-muted">No budgets yet.</p>}
        </div>

        <div>
          {analytics.data ? (
            <AnalyticsPanel data={analytics.data} onDelete={() => { if (confirm('Delete budget plan?')) remove.mutate(analytics.data!.plan_id); }} />
          ) : (
            <p className="text-sm text-ink-muted">Select a plan on the left to view analytics.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function AnalyticsPanel({ data, onDelete }: { data: Analytics; onDelete: () => void }) {
  const chartData = data.rows.map((r) => ({
    category: r.category, planned: parseFloat(r.planned), actual: parseFloat(r.actual),
  }));
  const planned = parseFloat(data.totals.planned);
  const actual = parseFloat(data.totals.actual);
  const utilPct = planned > 0 ? (actual / planned) * 100 : 0;
  return (
    <div className="space-y-4">
      <div className="ec-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-muted">FY {data.fiscal_year} · {data.currency}</p>
            <h3 className="text-xl font-semibold">{data.name}</h3>
          </div>
          <button className="ec-btn-ghost text-rose-600" onClick={onDelete}><Trash2 size={16} /></button>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <KpiBox label="Planned" value={formatCurrency(data.totals.planned, data.currency)} />
          <KpiBox label="Actual" value={formatCurrency(data.totals.actual, data.currency)} />
          <KpiBox label="Variance" value={formatCurrency(data.totals.variance, data.currency)}
                  positive={parseFloat(data.totals.variance) >= 0} />
        </div>
        <div className="mt-4">
          <div className="flex justify-between text-xs text-ink-muted">
            <span>Utilization</span><span>{utilPct.toFixed(1)}%</span>
          </div>
          <div className="mt-1 h-2 rounded bg-surface-muted">
            <div className={`h-full rounded ${utilPct > 100 ? 'bg-rose-500' : 'bg-emerald-500'}`}
                 style={{ width: `${Math.min(150, utilPct)}%` }} />
          </div>
        </div>
      </div>

      <div className="ec-card p-5">
        <p className="mb-3 flex items-center gap-2 text-sm font-semibold"><BarChart3 size={16} />Planned vs actual by category</p>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
              <XAxis dataKey="category" />
              <YAxis />
              <Tooltip formatter={(v) => formatCurrency(v as number, data.currency)} />
              <Legend />
              <Bar dataKey="planned" fill="#94a3b8" />
              <Bar dataKey="actual" fill="#4f46e5" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Category</th><th>Planned</th><th>Actual</th><th>Variance</th><th>Utilization</th></tr></thead>
          <tbody>
            {data.rows.length ? data.rows.map((r) => {
              const util = parseFloat(r.utilization) * 100;
              return (
                <tr key={r.id}>
                  <td className="font-medium">{r.category}</td>
                  <td>{formatCurrency(r.planned, data.currency)}</td>
                  <td>{formatCurrency(r.actual, data.currency)}</td>
                  <td className={parseFloat(r.variance) < 0 ? 'text-rose-500' : 'text-emerald-500'}>
                    {formatCurrency(r.variance, data.currency)}
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 overflow-hidden rounded bg-surface-muted">
                        <div className={`h-full ${util > 100 ? 'bg-rose-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(100, util)}%` }} />
                      </div>
                      <span className="text-xs text-ink-muted">{util.toFixed(0)}%</span>
                    </div>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-6 text-center text-ink-muted">No line items.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function KpiBox({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-surface-muted p-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${positive === false ? 'text-rose-500' : positive ? 'text-emerald-500' : ''}`}>{value}</p>
    </div>
  );
}

function BudgetForm({ onSaved }: { onSaved: (plan: Budget) => void }) {
  const [name, setName] = useState('Operating budget');
  const [fy, setFy] = useState(new Date().getFullYear());
  const [currency, setCurrency] = useState('USD');
  const [items, setItems] = useState<BudgetItem[]>(
    SUGGESTED_CATS.slice(0, 4).map((c) => ({ category: c, planned_amount: 0, actual_amount: 0 })),
  );
  const save = useMutation({
    mutationFn: async () => (await api.post<Budget>('/finance/budgets', {
      name, fiscal_year: fy, currency, items,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <h3 className="mb-3 text-lg font-semibold">New budget plan</h3>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Fiscal year</label><input type="number" className="ec-input" value={fy} onChange={(e) => setFy(Number(e.target.value))} /></div>
        <div><label className="ec-label">Currency</label><input className="ec-input" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
      </div>
      <div className="mt-4 space-y-2">
        <p className="text-sm font-medium text-ink-muted">Line items</p>
        {items.map((it, i) => (
          <div key={i} className="grid gap-2 md:grid-cols-[1fr_140px_140px_32px]">
            <input className="ec-input" placeholder="Category" value={it.category}
              list={`cat-suggest-${i}`}
              onChange={(e) => setItems(items.map((x, ix) => ix === i ? { ...x, category: e.target.value } : x))} />
            <datalist id={`cat-suggest-${i}`}>
              {SUGGESTED_CATS.map((c) => <option key={c} value={c} />)}
            </datalist>
            <input type="number" className="ec-input" placeholder="Planned" value={it.planned_amount}
              onChange={(e) => setItems(items.map((x, ix) => ix === i ? { ...x, planned_amount: Number(e.target.value) } : x))} />
            <input type="number" className="ec-input" placeholder="Actual (opt)" value={it.actual_amount}
              onChange={(e) => setItems(items.map((x, ix) => ix === i ? { ...x, actual_amount: Number(e.target.value) } : x))} />
            <button className="ec-btn-ghost text-rose-600" type="button" onClick={() => setItems(items.filter((_, ix) => ix !== i))}><Trash2 size={14} /></button>
          </div>
        ))}
        <button type="button" className="ec-btn-secondary" onClick={() => setItems([...items, { category: '', planned_amount: 0, actual_amount: 0 }])}>+ Add line</button>
      </div>
      <div className="mt-4 flex justify-end">
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save budget'}</button>
      </div>
    </div>
  );
}
