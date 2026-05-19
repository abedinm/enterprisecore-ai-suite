import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell, Legend } from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Summary = {
  total_calls: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: string;
  by_feature: Record<string, { calls: number; tokens_in: number; tokens_out: number; cost_usd: string }>;
  by_provider: Record<string, { calls: number; tokens_in: number; tokens_out: number; cost_usd: string }>;
};

const COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7'];

export function UsageTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['ai', 'usage', 'summary'],
    queryFn: async () => (await api.get<Summary>('/ai/usage/summary', { params: { days: 30 } })).data,
  });

  if (isLoading || !data) return <p className="text-sm text-ink-muted">Loading usage…</p>;

  const byFeature = Object.entries(data.by_feature).map(([k, v]) => ({
    name: k, calls: v.calls, cost: parseFloat(v.cost_usd),
  })).sort((a, b) => b.cost - a.cost);
  const byProvider = Object.entries(data.by_provider).map(([k, v]) => ({ name: k, value: parseFloat(v.cost_usd) }));

  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-4">
        <Tile label="Total calls (30d)" value={data.total_calls.toLocaleString()} />
        <Tile label="Tokens in" value={data.total_tokens_in.toLocaleString()} />
        <Tile label="Tokens out" value={data.total_tokens_out.toLocaleString()} />
        <Tile label="Cost (USD)" value={formatCurrency(data.total_cost_usd)} highlight />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">Cost by feature</p>
          <div className="h-64">
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
          <div className="h-64">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={byProvider} dataKey="value" nameKey="name" outerRadius={80} label>
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
          <thead><tr><th>Feature</th><th>Calls</th><th>Tokens in</th><th>Tokens out</th><th>Cost</th></tr></thead>
          <tbody>
            {byFeature.length ? byFeature.map((f) => (
              <tr key={f.name}>
                <td className="font-medium">{f.name}</td>
                <td>{f.calls}</td>
                <td>{data.by_feature[f.name].tokens_in.toLocaleString()}</td>
                <td>{data.by_feature[f.name].tokens_out.toLocaleString()}</td>
                <td>{formatCurrency(f.cost)}</td>
              </tr>
            )) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No AI usage in the last 30 days.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${highlight ? 'text-brand-600' : ''}`}>{value}</p>
    </div>
  );
}
