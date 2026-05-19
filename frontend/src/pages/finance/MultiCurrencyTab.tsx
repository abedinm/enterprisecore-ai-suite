import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Banknote, ArrowRightLeft } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type Entry = {
  currency: string; invoiced: string; paid: string;
  outstanding: string; expenses: string; net: string;
};
type Summary = { as_of: string; currencies: Entry[] };
type Conversion = { converted: string; rate: string; from_currency: string; to_currency: string };

const PIE_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#84cc16', '#ec4899'];

export function MultiCurrencyTab() {
  const qc = useQueryClient();
  const summary = useQuery({
    queryKey: ['finance', 'multi-currency'],
    queryFn: async () => (await api.get<Summary>('/finance/currency/summary')).data,
  });

  const [base, setBase] = useState('USD');
  const [conversions, setConversions] = useState<Record<string, Conversion>>({});

  const convert = useMutation({
    mutationFn: async (payload: { from: string; to: string; amount: number }) =>
      (await api.post<Conversion>('/finance/currency/convert', {
        amount: payload.amount, from_currency: payload.from, to_currency: payload.to,
      })).data,
    onSuccess: (data) => setConversions((m) => ({ ...m, [data.from_currency]: data })),
  });

  function convertAll() {
    if (!summary.data) return;
    setConversions({});
    summary.data.currencies.forEach((c) => {
      if (c.currency === base) {
        setConversions((m) => ({ ...m, [c.currency]: { converted: c.net, rate: '1.0', from_currency: c.currency, to_currency: base } }));
        return;
      }
      const amt = parseFloat(c.net);
      if (!Number.isFinite(amt) || amt === 0) return;
      convert.mutate({ from: c.currency, to: base, amount: amt });
    });
    qc.invalidateQueries({ queryKey: ['finance', 'multi-currency'] });
  }

  if (summary.isLoading) return <p className="text-sm text-ink-muted">Loading currency exposure…</p>;
  if (!summary.data) return <p className="text-sm text-ink-muted">Failed to load.</p>;

  const totals = summary.data.currencies.reduce((acc, c) => ({
    invoiced: acc.invoiced + parseFloat(c.invoiced),
    paid: acc.paid + parseFloat(c.paid),
    outstanding: acc.outstanding + parseFloat(c.outstanding),
    expenses: acc.expenses + parseFloat(c.expenses),
  }), { invoiced: 0, paid: 0, outstanding: 0, expenses: 0 });

  const chartData = summary.data.currencies.map((c) => ({
    currency: c.currency,
    invoiced: parseFloat(c.invoiced),
    paid: parseFloat(c.paid),
    expenses: parseFloat(c.expenses),
  }));

  const pieData = summary.data.currencies
    .map((c) => ({ name: c.currency, value: parseFloat(c.invoiced) }))
    .filter((d) => d.value > 0);

  const totalInBase = Object.values(conversions).reduce((sum, c) => sum + parseFloat(c.converted), 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Multi-currency exposure</p>
          <p className="text-sm text-ink-muted">Balances broken down by ISO 4217 currency · snapshot {formatDate(summary.data.as_of)}</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Convert all to</label>
            <input className="ec-input w-24" maxLength={3} value={base}
                   onChange={(e) => setBase(e.target.value.toUpperCase())} />
          </div>
          <button className="ec-btn-primary" onClick={convertAll}><ArrowRightLeft size={16} />Recalculate</button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Tile label="Currencies in use" value={summary.data.currencies.length.toString()} />
        <Tile label="Total invoiced" value={formatCurrency(totals.invoiced)} />
        <Tile label="Total paid" value={formatCurrency(totals.paid)} tone="positive" />
        <Tile label="Total expenses" value={formatCurrency(totals.expenses)} tone="negative" />
      </div>

      {Object.keys(conversions).length > 0 && (
        <div className="ec-card p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Net position in {base}</p>
            <p className="text-xl font-semibold text-brand-600">{formatCurrency(totalInBase, base)}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Activity per currency</p>
          <div className="h-72">
            {chartData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                  <XAxis dataKey="currency" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="invoiced" fill="#4f46e5" />
                  <Bar dataKey="paid" fill="#10b981" />
                  <Bar dataKey="expenses" fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            ) : <Empty />}
          </div>
        </div>

        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Invoice mix by currency</p>
          <div className="h-72">
            {pieData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90} label>
                    {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : <Empty />}
          </div>
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead>
            <tr>
              <th>Currency</th><th>Invoiced</th><th>Paid</th><th>Outstanding</th>
              <th>Expenses</th><th>Net</th><th>In {base}</th>
            </tr>
          </thead>
          <tbody>
            {summary.data.currencies.length ? summary.data.currencies.map((c) => {
              const conv = conversions[c.currency];
              return (
                <tr key={c.currency}>
                  <td className="font-medium">
                    <span className="inline-flex items-center gap-2">
                      <Banknote size={14} className="text-ink-muted" />{c.currency}
                    </span>
                  </td>
                  <td>{formatCurrency(c.invoiced, c.currency)}</td>
                  <td className="text-emerald-500">{formatCurrency(c.paid, c.currency)}</td>
                  <td className="text-amber-500">{formatCurrency(c.outstanding, c.currency)}</td>
                  <td className="text-rose-500">{formatCurrency(c.expenses, c.currency)}</td>
                  <td className={parseFloat(c.net) >= 0 ? 'text-emerald-500' : 'text-rose-500'}>
                    {formatCurrency(c.net, c.currency)}
                  </td>
                  <td className="text-ink-muted">
                    {conv ? `${formatCurrency(conv.converted, base)} @ ${conv.rate}` :
                      (c.currency === base ? formatCurrency(c.net, base) : '—')}
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={7} className="py-8 text-center text-ink-muted">No multi-currency activity yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' }) {
  const cls = tone === 'positive' ? 'text-emerald-500' : tone === 'negative' ? 'text-rose-500' : '';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

function Empty() {
  return <div className="grid h-full place-items-center text-sm text-ink-muted">No data yet</div>;
}
