import { useQuery } from '@tanstack/react-query';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { AlertCircle, TrendingUp, Zap } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Summary = {
  total_calls: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: string;
  by_feature: Record<string, { calls: number; tokens_in: number; tokens_out: number; cost_usd: string }>;
  by_provider: Record<string, { calls: number; tokens_in: number; tokens_out: number; cost_usd: string }>;
};

type DailyPoint = { date: string; cost_usd: string; calls: number };

type MySpend = {
  user_id: string;
  daily_spend_usd: string;
  daily_limit_usd: string;
  limit_pct: string;
  calls_24h: number;
  tokens_24h: number;
  cost_30d: string;
  calls_30d: number;
  tokens_30d: number;
  by_provider_30d: Record<string, { calls: number; tokens_in: number; tokens_out: number; cost_usd: string }>;
  timeline: DailyPoint[];
};

const COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7'];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Tile({ label, value, sub, highlight }: {
  label: string; value: string; sub?: string; highlight?: boolean;
}) {
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${highlight ? 'text-brand-600' : ''}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-ink-muted">{sub}</p>}
    </div>
  );
}

function LimitBar({ pct, limitUsd, spendUsd }: { pct: number; limitUsd: number; spendUsd: number }) {
  const capped = Math.min(pct, 1);
  const danger = capped >= 0.9;
  const warn = capped >= 0.7;
  const color = danger ? 'bg-red-500' : warn ? 'bg-amber-400' : 'bg-brand-600';
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-ink-muted">
        <span className="flex items-center gap-1">
          {danger && <AlertCircle size={12} className="text-red-500" />}
          Daily limit: {formatCurrency(spendUsd)} / {limitUsd > 0 ? formatCurrency(limitUsd) : 'No limit'}
        </span>
        <span className={danger ? 'text-red-500 font-semibold' : ''}>
          {limitUsd > 0 ? `${(capped * 100).toFixed(1)} %` : '—'}
        </span>
      </div>
      {limitUsd > 0 && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
          <div
            className={`h-full rounded-full transition-all duration-500 ${color}`}
            style={{ width: `${capped * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// My Spend Section
// ---------------------------------------------------------------------------

function MySpendSection() {
  const { data, isLoading } = useQuery<MySpend>({
    queryKey: ['ai', 'usage', 'my-summary'],
    queryFn: async () => (await api.get<MySpend>('/ai/usage/my-summary')).data,
    refetchInterval: 60_000,
  });

  if (isLoading || !data) {
    return (
      <div className="ec-card p-5">
        <p className="text-sm text-ink-muted">Loading your spend data…</p>
      </div>
    );
  }

  const dailySpend = parseFloat(data.daily_spend_usd);
  const dailyLimit = parseFloat(data.daily_limit_usd);
  const limitPct = parseFloat(data.limit_pct);

  const timelineData = data.timeline.map((p) => ({
    date: p.date.slice(5),  // "MM-DD"
    cost: parseFloat(p.cost_usd),
    calls: p.calls,
  }));

  const byProvider = Object.entries(data.by_provider_30d).map(([k, v]) => ({
    name: k, value: parseFloat(v.cost_usd),
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Zap size={16} className="text-brand-600" />
        <p className="text-sm font-semibold">My AI Spend</p>
      </div>

      {/* KPI row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Today (24 h)" value={formatCurrency(dailySpend)} highlight />
        <Tile label="Calls (24 h)" value={data.calls_24h.toLocaleString()} />
        <Tile label="Cost (30 d)" value={formatCurrency(parseFloat(data.cost_30d))} />
        <Tile label="Calls (30 d)" value={data.calls_30d.toLocaleString()} />
      </div>

      {/* Daily limit progress bar */}
      <div className="ec-card p-4">
        <LimitBar pct={limitPct} limitUsd={dailyLimit} spendUsd={dailySpend} />
      </div>

      {/* Timeline + per-provider donut */}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2 ec-card p-5">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
            <TrendingUp size={14} /> Daily spend (30 d)
          </p>
          {timelineData.length > 0 ? (
            <div className="h-48">
              <ResponsiveContainer>
                <BarChart data={timelineData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toFixed(3)}`} />
                  <Tooltip formatter={(v) => formatCurrency(v as number)} labelFormatter={(l) => `Date: ${l}`} />
                  <Bar dataKey="cost" fill="#4f46e5" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-ink-muted">No AI calls in the last 30 days.</p>
          )}
        </div>

        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">By provider (30 d)</p>
          {byProvider.length > 0 ? (
            <div className="h-48">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={byProvider} dataKey="value" nameKey="name" outerRadius={60} label>
                    {byProvider.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(v as number)} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-ink-muted">No data yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// All-users admin overview
// ---------------------------------------------------------------------------

function AllUsersSection() {
  const { data, isLoading } = useQuery<Summary>({
    queryKey: ['ai', 'usage', 'summary'],
    queryFn: async () => (await api.get<Summary>('/ai/usage/summary', { params: { days: 30 } })).data,
  });

  if (isLoading || !data) return <p className="text-sm text-ink-muted">Loading platform usage…</p>;

  const byFeature = Object.entries(data.by_feature).map(([k, v]) => ({
    name: k, calls: v.calls, cost: parseFloat(v.cost_usd),
  })).sort((a, b) => b.cost - a.cost);
  const byProvider = Object.entries(data.by_provider).map(([k, v]) => ({ name: k, value: parseFloat(v.cost_usd) }));

  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold text-ink-muted">Platform-wide (all users, last 30 d)</p>
      <div className="grid gap-3 md:grid-cols-4">
        <Tile label="Total calls" value={data.total_calls.toLocaleString()} />
        <Tile label="Tokens in" value={data.total_tokens_in.toLocaleString()} />
        <Tile label="Tokens out" value={data.total_tokens_out.toLocaleString()} />
        <Tile label="Total cost" value={formatCurrency(data.total_cost_usd)} highlight />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">Cost by feature</p>
          <div className="h-60">
            <ResponsiveContainer>
              <BarChart data={byFeature.slice(0, 10)}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                <XAxis dataKey="name" interval={0} angle={-25} textAnchor="end" height={70} tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip formatter={(v) => formatCurrency(v as number)} />
                <Bar dataKey="cost" fill="#4f46e5" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">Cost by provider</p>
          <div className="h-60">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={byProvider} dataKey="value" nameKey="name" outerRadius={75} label>
                  {byProvider.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => formatCurrency(v as number)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead>
            <tr>
              <th>Feature</th><th>Calls</th><th>Tokens in</th><th>Tokens out</th><th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {byFeature.length ? byFeature.map((f) => (
              <tr key={f.name}>
                <td className="font-medium">{f.name}</td>
                <td>{f.calls}</td>
                <td>{data.by_feature[f.name].tokens_in.toLocaleString()}</td>
                <td>{data.by_feature[f.name].tokens_out.toLocaleString()}</td>
                <td>{formatCurrency(f.cost)}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={5} className="py-8 text-center text-ink-muted">
                  No AI usage in the last 30 days.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main tab
// ---------------------------------------------------------------------------

export function UsageTab() {
  return (
    <div className="space-y-8">
      <MySpendSection />
      <hr className="border-border" />
      <AllUsersSection />
    </div>
  );
}
