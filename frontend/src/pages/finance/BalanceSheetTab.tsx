import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type Balance = {
  as_of: string;
  assets: Record<string, string>;
  liabilities: Record<string, string>;
  equity: Record<string, string>;
  totals: Record<string, string>;
};

export function BalanceSheetTab() {
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [currency, setCurrency] = useState('USD');

  const { data, isLoading } = useQuery({
    queryKey: ['finance', 'balance', asOf],
    queryFn: async () => (await api.get<Balance>('/finance/reports/balance-sheet', { params: { as_of: asOf } })).data,
  });

  async function downloadPdf() {
    const r = await api.get('/finance/reports/balance-sheet/pdf', {
      params: { as_of: asOf, currency }, responseType: 'blob',
    });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `balance-sheet-${asOf}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div><label className="ec-label">As of</label><input type="date" className="ec-input" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></div>
        <div><label className="ec-label">Currency</label><input className="ec-input w-20" maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
        <button className="ec-btn-primary" onClick={downloadPdf} disabled={!data}><Download size={16} />PDF</button>
      </div>

      {isLoading || !data ? (
        <p className="text-sm text-ink-muted">Loading balance sheet…</p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Kpi label="Total assets" value={formatCurrency(data.totals.total_assets, currency)} tone="positive" />
            <Kpi label="Total liabilities" value={formatCurrency(data.totals.total_liabilities, currency)} tone="negative" />
            <Kpi label="Total equity" value={formatCurrency(data.totals.total_equity, currency)} tone="highlight" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Section title="Assets" entries={data.assets} total={data.totals.total_assets} currency={currency} accent="emerald" />
            <Section title="Liabilities" entries={data.liabilities} total={data.totals.total_liabilities} currency={currency} accent="rose" />
            <Section title="Equity" entries={data.equity} total={data.totals.total_equity} currency={currency} accent="brand" />
          </div>

          <div className="ec-card p-5">
            <p className="text-xs uppercase tracking-wider text-ink-muted">Accounting equation</p>
            <p className="mt-2 text-lg">
              <strong className="text-emerald-500">{formatCurrency(data.totals.total_assets, currency)}</strong>{' '}
              <span className="text-ink-muted">=</span>{' '}
              <strong className="text-rose-500">{formatCurrency(data.totals.total_liabilities, currency)}</strong>{' '}
              <span className="text-ink-muted">+</span>{' '}
              <strong className="text-brand-600">{formatCurrency(data.totals.total_equity, currency)}</strong>
            </p>
            <p className="mt-2 text-xs text-ink-muted">Snapshot of accounts as of {formatDate(data.as_of)}.</p>
          </div>
        </>
      )}
    </div>
  );
}

function Section({ title, entries, total, currency, accent }: {
  title: string; entries: Record<string, string>; total: string; currency: string;
  accent: 'emerald' | 'rose' | 'brand';
}) {
  const accentText = accent === 'emerald' ? 'text-emerald-500' : accent === 'rose' ? 'text-rose-500' : 'text-brand-600';
  return (
    <div className="ec-card p-5">
      <p className={`mb-3 text-lg font-semibold ${accentText}`}>{title}</p>
      <table className="ec-table">
        <tbody>
          {Object.entries(entries).map(([k, v]) => (
            <tr key={k}>
              <td className="capitalize">{k.replace(/_/g, ' ')}</td>
              <td className="text-right">{formatCurrency(v, currency)}</td>
            </tr>
          ))}
          <tr className="border-t border-border">
            <td className="pt-2 font-semibold">Total {title.toLowerCase()}</td>
            <td className={`pt-2 text-right font-bold ${accentText}`}>{formatCurrency(total, currency)}</td>
          </tr>
        </tbody>
      </table>
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
