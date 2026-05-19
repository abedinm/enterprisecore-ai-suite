import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Download } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type CF = {
  period_start: string; period_end: string;
  entries: { period: string; inflow: string; outflow: string; net: string }[];
  totals: { inflow: string; outflow: string; net: string };
};

export function CashFlowTab() {
  const today = new Date();
  const [start, setStart] = useState(new Date(today.getFullYear(), 0, 1).toISOString().slice(0, 10));
  const [end, setEnd] = useState(today.toISOString().slice(0, 10));
  const [currency, setCurrency] = useState('USD');

  const { data, isLoading } = useQuery({
    queryKey: ['finance', 'cashflow', start, end],
    queryFn: async () => (await api.get<CF>('/finance/reports/cash-flow', { params: { start, end } })).data,
  });

  async function downloadPdf() {
    const r = await api.get('/finance/reports/cash-flow/pdf', {
      params: { start, end, currency }, responseType: 'blob',
    });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `cash-flow-${start}-${end}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const chart = (data?.entries ?? []).map((e) => ({
    period: e.period, inflow: parseFloat(e.inflow), outflow: parseFloat(e.outflow), net: parseFloat(e.net),
  }));
  let running = 0;
  const cumChart = chart.map((c) => { running += c.net; return { ...c, cumulative: running }; });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div><label className="ec-label">From</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="ec-label">To</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        <div><label className="ec-label">Currency</label><input className="ec-input w-20" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
        <button className="ec-btn-primary" onClick={downloadPdf} disabled={!data}><Download size={16} />PDF</button>
      </div>

      {isLoading || !data ? (
        <p className="text-sm text-ink-muted">Loading cash flow…</p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Kpi label="Total inflow" value={formatCurrency(data.totals.inflow, currency)} tone="positive" />
            <Kpi label="Total outflow" value={formatCurrency(data.totals.outflow, currency)} tone="negative" />
            <Kpi label="Net cash flow" value={formatCurrency(data.totals.net, currency)} tone="highlight" />
          </div>

          <div className="ec-card p-5">
            <p className="mb-3 text-sm font-semibold">Monthly inflow vs outflow</p>
            <div className="h-72">
              {cumChart.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={cumChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="period" />
                    <YAxis />
                    <Tooltip formatter={(v) => formatCurrency(v as number, currency)} />
                    <Legend />
                    <Bar dataKey="inflow" fill="#10b981" />
                    <Bar dataKey="outflow" fill="#ef4444" />
                  </BarChart>
                </ResponsiveContainer>
              ) : <Empty />}
            </div>
          </div>

          <div className="ec-card p-5">
            <p className="mb-3 text-sm font-semibold">Net flow & running cumulative</p>
            <div className="h-72">
              {cumChart.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={cumChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="period" />
                    <YAxis />
                    <Tooltip formatter={(v) => formatCurrency(v as number, currency)} />
                    <Legend />
                    <Bar dataKey="net" fill="#4f46e5" />
                    <Line type="monotone" dataKey="cumulative" stroke="#f59e0b" strokeWidth={2} />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : <Empty />}
            </div>
          </div>

          <div className="ec-card overflow-hidden">
            <table className="ec-table">
              <thead><tr><th>Period</th><th>Inflow</th><th>Outflow</th><th>Net</th></tr></thead>
              <tbody>
                {data.entries.length ? data.entries.map((e) => (
                  <tr key={e.period}>
                    <td className="font-medium">{e.period}</td>
                    <td className="text-emerald-500">{formatCurrency(e.inflow, currency)}</td>
                    <td className="text-rose-500">-{formatCurrency(e.outflow, currency)}</td>
                    <td className={parseFloat(e.net) >= 0 ? 'text-emerald-500' : 'text-rose-500'}>{formatCurrency(e.net, currency)}</td>
                  </tr>
                )) : <tr><td colSpan={4} className="py-8 text-center text-ink-muted">No cash flow data in this range.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: 'positive' | 'negative' | 'highlight' }) {
  const cls = tone === 'positive' ? 'text-emerald-500'
    : tone === 'negative' ? 'text-rose-500' : 'text-brand-600';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

function Empty() {
  return <div className="grid h-full place-items-center text-sm text-ink-muted">No cash flow data</div>;
}
