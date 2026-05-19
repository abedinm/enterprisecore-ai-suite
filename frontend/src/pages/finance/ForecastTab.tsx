import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Download, TrendingUp } from 'lucide-react';
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Forecast = {
  method: string; months_ahead: number; confidence: string;
  history: { period: string; inflow: string; outflow: string; net: string }[];
  points: { period: string; revenue_forecast: string; expense_forecast: string; net_forecast: string }[];
};

export function ForecastTab() {
  const [months, setMonths] = useState(6);
  const [currency, setCurrency] = useState('USD');

  const { data, isLoading } = useQuery({
    queryKey: ['finance', 'forecast', months],
    queryFn: async () => (await api.get<Forecast>('/finance/reports/forecast', { params: { months_ahead: months } })).data,
  });

  async function downloadPdf() {
    const r = await api.get('/finance/reports/forecast/pdf', {
      params: { months_ahead: months, currency }, responseType: 'blob',
    });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `forecast-${months}m.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const historyData = (data?.history ?? []).map((h) => ({
    period: h.period,
    revenue: parseFloat(h.inflow),
    expense: parseFloat(h.outflow),
    net: parseFloat(h.net),
    forecast: false,
  }));
  const forecastData = (data?.points ?? []).map((p) => ({
    period: p.period,
    revenue: parseFloat(p.revenue_forecast),
    expense: parseFloat(p.expense_forecast),
    net: parseFloat(p.net_forecast),
    forecast: true,
  }));
  const combined = [...historyData, ...forecastData];
  const splitLabel = forecastData[0]?.period;

  const totalProjectedRevenue = forecastData.reduce((s, p) => s + p.revenue, 0);
  const totalProjectedExpense = forecastData.reduce((s, p) => s + p.expense, 0);
  const totalProjectedNet = totalProjectedRevenue - totalProjectedExpense;
  const confidencePct = data ? Math.round(parseFloat(data.confidence) * 100) : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="ec-label">Months ahead</label>
          <input type="number" min={1} max={24} className="ec-input w-24" value={months}
                 onChange={(e) => setMonths(Math.max(1, Math.min(24, Number(e.target.value))))} />
        </div>
        <div><label className="ec-label">Currency</label><input className="ec-input w-20" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
        <button className="ec-btn-primary" onClick={downloadPdf} disabled={!data}><Download size={16} />PDF</button>
        {data && (
          <p className="text-sm text-ink-muted">
            Method: <strong>{data.method.replace(/_/g, ' ')}</strong> · Confidence: <strong>{confidencePct}%</strong>
          </p>
        )}
      </div>

      {isLoading || !data ? (
        <p className="text-sm text-ink-muted">Loading forecast…</p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <Kpi label="Projected revenue" value={formatCurrency(totalProjectedRevenue, currency)} tone="positive" />
            <Kpi label="Projected expenses" value={formatCurrency(totalProjectedExpense, currency)} tone="negative" />
            <Kpi label="Projected net" value={formatCurrency(totalProjectedNet, currency)} tone="highlight" />
            <Kpi label="Confidence" value={`${confidencePct}%`} />
          </div>

          <div className="ec-card p-5">
            <p className="mb-3 flex items-center gap-2 text-sm font-semibold"><TrendingUp size={16} />History & projection</p>
            <div className="h-72">
              {combined.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={combined}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="period" />
                    <YAxis />
                    <Tooltip formatter={(v) => formatCurrency(v as number, currency)} />
                    <Legend />
                    {splitLabel && <ReferenceLine x={splitLabel} stroke="#94a3b8" strokeDasharray="3 3" label="forecast →" />}
                    <Line type="monotone" dataKey="revenue" stroke="#10b981" />
                    <Line type="monotone" dataKey="expense" stroke="#ef4444" />
                    <Line type="monotone" dataKey="net" stroke="#4f46e5" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              ) : <div className="grid h-full place-items-center text-sm text-ink-muted">Not enough history to forecast yet — record some invoices and expenses.</div>}
            </div>
          </div>

          <div className="ec-card overflow-hidden">
            <table className="ec-table">
              <thead><tr><th>Period</th><th>Revenue forecast</th><th>Expense forecast</th><th>Net forecast</th></tr></thead>
              <tbody>
                {data.points.length ? data.points.map((p) => (
                  <tr key={p.period}>
                    <td className="font-medium">{p.period}</td>
                    <td className="text-emerald-500">{formatCurrency(p.revenue_forecast, currency)}</td>
                    <td className="text-rose-500">{formatCurrency(p.expense_forecast, currency)}</td>
                    <td className={parseFloat(p.net_forecast) >= 0 ? 'text-emerald-500' : 'text-rose-500'}>{formatCurrency(p.net_forecast, currency)}</td>
                  </tr>
                )) : <tr><td colSpan={4} className="py-8 text-center text-ink-muted">No forecast data available.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' | 'highlight' }) {
  const cls = tone === 'positive' ? 'text-emerald-500'
    : tone === 'negative' ? 'text-rose-500'
    : tone === 'highlight' ? 'text-brand-600' : '';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}
