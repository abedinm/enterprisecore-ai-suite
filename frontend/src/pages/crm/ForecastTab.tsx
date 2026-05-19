import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type ForecastMonth = { period: string; expected_revenue: string; deal_count: number };
type Forecast = { months: ForecastMonth[]; method: string };

export function ForecastTab() {
  const [months, setMonths] = useState(6);
  const { data, isLoading } = useQuery({
    queryKey: ['crm', 'forecast', months],
    queryFn: async () => (await api.get<Forecast>('/crm/forecast', { params: { months_ahead: months } })).data,
  });

  const chart = (data?.months ?? []).map((m) => ({
    period: m.period, revenue: parseFloat(m.expected_revenue), deals: m.deal_count,
  }));
  const total = chart.reduce((s, c) => s + c.revenue, 0);
  const totalDeals = chart.reduce((s, c) => s + c.deals, 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-ink-muted"><TrendingUp size={14} />Sales forecast</p>
          <p className="text-sm text-ink-muted">Method: <code>{data?.method ?? '—'}</code> · deals weighted by probability</p>
        </div>
        <div>
          <label className="ec-label">Months ahead</label>
          <input type="number" min={1} max={24} className="ec-input w-24" value={months}
                 onChange={(e) => setMonths(Math.max(1, Math.min(24, Number(e.target.value))))} />
        </div>
      </div>

      {isLoading ? <p className="text-sm text-ink-muted">Loading…</p> : (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Tile label="Expected revenue" value={formatCurrency(total)} tone="positive" />
            <Tile label="Forecasted deals" value={totalDeals.toString()} />
            <Tile label="Avg deal value" value={formatCurrency(totalDeals > 0 ? total / totalDeals : 0)} />
          </div>

          <div className="ec-card p-5">
            <p className="mb-3 text-sm font-semibold">Expected revenue by month</p>
            <div className="h-72">
              {chart.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="period" />
                    <YAxis />
                    <Tooltip formatter={(v) => formatCurrency(v as number)} />
                    <Bar dataKey="revenue" fill="#4f46e5" />
                  </BarChart>
                </ResponsiveContainer>
              ) : <Empty />}
            </div>
          </div>

          <div className="ec-card p-5">
            <p className="mb-3 text-sm font-semibold">Deal count trend</p>
            <div className="h-56">
              {chart.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="period" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="deals" stroke="#10b981" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <Empty />}
            </div>
          </div>

          <div className="ec-card overflow-hidden">
            <table className="ec-table">
              <thead><tr><th>Period</th><th>Deal count</th><th>Expected revenue</th></tr></thead>
              <tbody>
                {data?.months.length ? data.months.map((m) => (
                  <tr key={m.period}>
                    <td className="font-medium">{m.period}</td>
                    <td>{m.deal_count}</td>
                    <td className="font-medium text-emerald-500">{formatCurrency(m.expected_revenue)}</td>
                  </tr>
                )) : <tr><td colSpan={3} className="py-8 text-center text-ink-muted">No deals with expected close dates yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'positive' }) {
  const cls = tone === 'positive' ? 'text-emerald-500' : '';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

function Empty() {
  return <div className="grid h-full place-items-center text-sm text-ink-muted">No forecast data</div>;
}
