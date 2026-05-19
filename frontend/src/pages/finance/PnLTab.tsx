import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Download } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Pnl = {
  period_start: string; period_end: string;
  revenue: string; cogs: string; gross_profit: string;
  operating_expenses: string; net_income: string;
  by_category: Record<string, string>;
};

const PIE_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#84cc16', '#ec4899'];

export function PnLTab() {
  const today = new Date();
  const [start, setStart] = useState(new Date(today.getFullYear(), 0, 1).toISOString().slice(0, 10));
  const [end, setEnd] = useState(today.toISOString().slice(0, 10));
  const [currency, setCurrency] = useState('USD');

  const { data, isLoading } = useQuery({
    queryKey: ['finance', 'pnl', start, end],
    queryFn: async () => (await api.get<Pnl>('/finance/reports/pnl', { params: { start, end } })).data,
  });

  async function downloadPdf() {
    const r = await api.get('/finance/reports/pnl/pdf', {
      params: { start, end, currency }, responseType: 'blob',
    });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `pnl-${start}-${end}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const cats = Object.entries(data?.by_category ?? {})
    .map(([name, v]) => ({ name, value: parseFloat(v) }))
    .filter((c) => c.value > 0)
    .sort((a, b) => b.value - a.value);

  const stackedData = data ? [{
    name: 'Period',
    revenue: parseFloat(data.revenue),
    expenses: -parseFloat(data.operating_expenses),
    net: parseFloat(data.net_income),
  }] : [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div><label className="ec-label">Period start</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="ec-label">Period end</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        <div><label className="ec-label">Currency</label><input className="ec-input w-20" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
        <button className="ec-btn-primary" onClick={downloadPdf} disabled={!data}><Download size={16} />PDF</button>
      </div>

      {isLoading || !data ? (
        <p className="text-sm text-ink-muted">Loading…</p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <Kpi label="Revenue" value={formatCurrency(data.revenue, currency)} tone="positive" />
            <Kpi label="Gross profit" value={formatCurrency(data.gross_profit, currency)} />
            <Kpi label="Operating expenses" value={formatCurrency(data.operating_expenses, currency)} tone="negative" />
            <Kpi label="Net income" value={formatCurrency(data.net_income, currency)} tone="highlight" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="ec-card p-5">
              <p className="mb-3 text-sm font-semibold">Profit & loss snapshot</p>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stackedData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip formatter={(v) => formatCurrency(v as number, currency)} />
                    <Legend />
                    <Bar dataKey="revenue" fill="#10b981" />
                    <Bar dataKey="expenses" fill="#ef4444" />
                    <Bar dataKey="net" fill="#4f46e5" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="ec-card p-5">
              <p className="mb-3 text-sm font-semibold">Operating expenses by category</p>
              <div className="h-64">
                {cats.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={cats} dataKey="value" nameKey="name" outerRadius={80} label>
                        {cats.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Tooltip formatter={(v) => formatCurrency(v as number, currency)} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                ) : <Empty text="No expense categories" />}
              </div>
            </div>
          </div>

          <div className="ec-card p-5">
            <p className="mb-3 text-sm font-semibold">Statement</p>
            <table className="ec-table">
              <tbody>
                <tr><td>Revenue</td><td className="text-right">{formatCurrency(data.revenue, currency)}</td></tr>
                <tr><td>Cost of goods sold</td><td className="text-right">{formatCurrency(data.cogs, currency)}</td></tr>
                <tr className="font-semibold"><td>Gross profit</td><td className="text-right">{formatCurrency(data.gross_profit, currency)}</td></tr>
                <tr><td colSpan={2} className="pt-4 text-xs uppercase tracking-wider text-ink-muted">Operating expenses</td></tr>
                {cats.length ? cats.map((c) => (
                  <tr key={c.name}><td className="pl-6">{c.name}</td><td className="text-right">{formatCurrency(c.value, currency)}</td></tr>
                )) : <tr><td className="pl-6 text-ink-muted">None recorded</td><td></td></tr>}
                <tr className="font-semibold"><td>Total operating expenses</td><td className="text-right">{formatCurrency(data.operating_expenses, currency)}</td></tr>
                <tr className="border-t-2 border-border text-lg">
                  <td className="pt-3 font-bold">Net income</td>
                  <td className={`pt-3 text-right font-bold ${parseFloat(data.net_income) >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>{formatCurrency(data.net_income, currency)}</td>
                </tr>
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

function Empty({ text }: { text: string }) {
  return <div className="grid h-full place-items-center text-sm text-ink-muted">{text}</div>;
}
