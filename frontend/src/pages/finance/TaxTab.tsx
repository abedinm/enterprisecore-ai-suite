import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency } from '../../lib/utils';

type Bracket = { from: string; to: string; rate: string; taxable: string; tax: string };
type Result = {
  taxable_income: string; estimated_tax: string; effective_rate: string;
  breakdown: Bracket[];
};
type TaxRate = { id: string; jurisdiction: string; name: string; rate: string };

const PRESETS: Record<string, [number, number][]> = {
  'US 2024 (Single, default)': [
    [11000, 0.10], [44725, 0.12], [95375, 0.22], [182100, 0.24],
    [231250, 0.32], [578125, 0.35], [0, 0.37],
  ],
  'UK 2024-25': [
    [12570, 0], [50270, 0.20], [125140, 0.40], [0, 0.45],
  ],
  'Australia 2024': [
    [18200, 0], [45000, 0.19], [135000, 0.30], [190000, 0.37], [0, 0.45],
  ],
  'Flat 20%': [[0, 0.20]],
  'Flat 30%': [[0, 0.30]],
};

export function TaxTab() {
  const qc = useQueryClient();
  const [income, setIncome] = useState(80000);
  const [deductions, setDeductions] = useState(12000);
  const [preset, setPreset] = useState('US 2024 (Single, default)');
  const [result, setResult] = useState<Result | null>(null);

  const estimate = useMutation({
    mutationFn: async () => {
      const brackets = preset === 'US 2024 (Single, default)' ? [] : PRESETS[preset];
      return (await api.post<Result>('/finance/tax/estimate', { income, deductions, brackets })).data;
    },
    onSuccess: (d) => setResult(d),
  });

  const rates = useQuery({
    queryKey: ['finance', 'tax-rates'],
    queryFn: async () => (await api.get<TaxRate[]>('/finance/tax-rates')).data,
  });
  const [jurisdiction, setJurisdiction] = useState('');
  const [rateName, setRateName] = useState('');
  const [rateValue, setRateValue] = useState(0.20);
  const addRate = useMutation({
    mutationFn: async () => (await api.post('/finance/tax-rates', {
      jurisdiction, name: rateName, rate: rateValue,
    })).data,
    onSuccess: () => { setJurisdiction(''); setRateName(''); qc.invalidateQueries({ queryKey: ['finance', 'tax-rates'] }); },
  });
  const removeRate = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/tax-rates/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'tax-rates'] }),
  });

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5 space-y-3">
          <p className="text-sm font-semibold">Income tax estimator</p>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="ec-label">Annual income</label><input type="number" className="ec-input" value={income} onChange={(e) => setIncome(Number(e.target.value))} /></div>
            <div><label className="ec-label">Deductions</label><input type="number" className="ec-input" value={deductions} onChange={(e) => setDeductions(Number(e.target.value))} /></div>
          </div>
          <div>
            <label className="ec-label">Bracket preset</label>
            <select className="ec-input" value={preset} onChange={(e) => setPreset(e.target.value)}>
              {Object.keys(PRESETS).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary w-full" onClick={() => estimate.mutate()} disabled={estimate.isPending}>
            {estimate.isPending ? 'Calculating…' : 'Estimate tax'}
          </button>
        </div>

        <div className="ec-card p-5 space-y-2">
          <p className="text-sm font-semibold">Result</p>
          {result ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <KpiSmall label="Taxable income" value={formatCurrency(result.taxable_income)} />
                <KpiSmall label="Estimated tax" value={formatCurrency(result.estimated_tax)} tone="negative" />
                <KpiSmall label="Effective rate" value={`${(parseFloat(result.effective_rate) * 100).toFixed(2)}%`} />
              </div>
              <p className="mt-3 text-xs uppercase tracking-wider text-ink-muted">Bracket breakdown</p>
              <table className="ec-table">
                <thead><tr><th>From</th><th>To</th><th>Rate</th><th>Taxable</th><th>Tax</th></tr></thead>
                <tbody>
                  {result.breakdown.length ? result.breakdown.map((b, i) => (
                    <tr key={i}>
                      <td>{formatCurrency(b.from)}</td>
                      <td>{parseFloat(b.to) === parseFloat(b.from) ? '∞' : formatCurrency(b.to)}</td>
                      <td>{(parseFloat(b.rate) * 100).toFixed(2)}%</td>
                      <td>{formatCurrency(b.taxable)}</td>
                      <td className="text-rose-500">{formatCurrency(b.tax)}</td>
                    </tr>
                  )) : <tr><td colSpan={5} className="text-ink-muted">No taxable amount.</td></tr>}
                </tbody>
              </table>
            </>
          ) : <p className="text-sm text-ink-muted">Enter values and press <strong>Estimate tax</strong>.</p>}
        </div>
      </div>

      <div className="ec-card p-5">
        <p className="mb-3 text-sm font-semibold">Saved tax rates (for invoices &amp; reports)</p>
        <div className="mb-3 grid gap-2 md:grid-cols-[1fr_1fr_120px_80px]">
          <input className="ec-input" placeholder="Jurisdiction (e.g. CA, UK)" value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} />
          <input className="ec-input" placeholder="Name (e.g. Standard VAT)" value={rateName} onChange={(e) => setRateName(e.target.value)} />
          <input type="number" step="0.001" className="ec-input" placeholder="Rate" value={rateValue} onChange={(e) => setRateValue(Number(e.target.value))} />
          <button className="ec-btn-primary" disabled={!jurisdiction || !rateName || addRate.isPending} onClick={() => addRate.mutate()}>
            <Plus size={14} /> Add
          </button>
        </div>
        <table className="ec-table">
          <thead><tr><th>Jurisdiction</th><th>Name</th><th>Rate</th><th></th></tr></thead>
          <tbody>
            {rates.data?.length ? rates.data.map((r) => (
              <tr key={r.id}>
                <td className="font-medium">{r.jurisdiction}</td>
                <td>{r.name}</td>
                <td>{(parseFloat(r.rate) * 100).toFixed(2)}%</td>
                <td className="text-right">
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete tax rate?')) removeRate.mutate(r.id); }}><Trash2 size={16} /></button>
                </td>
              </tr>
            )) : <tr><td colSpan={4} className="py-6 text-center text-ink-muted">No saved tax rates.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function KpiSmall({ label, value, tone }: { label: string; value: string; tone?: 'negative' }) {
  return (
    <div className="rounded-lg bg-surface-muted p-2">
      <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className={`text-base font-semibold ${tone === 'negative' ? 'text-rose-500' : ''}`}>{value}</p>
    </div>
  );
}
