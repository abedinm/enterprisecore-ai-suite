import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Calculator, Wallet } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';

type Estimate = { gross: string; tax: string; deductions: string; bonuses: string; net: string; frequency: string };
type Run = {
  id: string; period_start: string; period_end: string; status: string;
  gross_total: string; deduction_total: string; net_total: string;
};
type Line = { employee_id: string | null; label: string; amount: number; kind: string };
type Frequency = 'weekly' | 'biweekly' | 'monthly' | 'annual';

const KINDS = [
  { value: 'earning', label: 'Earning' },
  { value: 'bonus', label: 'Bonus' },
  { value: 'tax', label: 'Tax' },
  { value: 'deduction', label: 'Deduction' },
];

export function PayrollTab() {
  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <Calculator0 />
        <RunForm />
      </div>
      <RunList />
    </div>
  );
}

function Calculator0() {
  const [gross, setGross] = useState(5000);
  const [taxRate, setTaxRate] = useState(0.22);
  const [deductions, setDeductions] = useState(150);
  const [bonuses, setBonuses] = useState(0);
  const [frequency, setFrequency] = useState<Frequency>('monthly');
  const [result, setResult] = useState<Estimate | null>(null);

  const calc = useMutation({
    mutationFn: async () => (await api.post<Estimate>('/finance/payroll/estimate', {
      gross_salary: gross, tax_rate: taxRate, deductions, bonuses, pay_frequency: frequency,
    })).data,
    onSuccess: (d) => setResult(d),
  });

  const annual = result ? Math.round(parseFloat(result.net) * ({ weekly: 52, biweekly: 26, monthly: 12, annual: 1 }[frequency])) : 0;

  return (
    <div className="ec-card p-5 space-y-3">
      <p className="flex items-center gap-2 text-sm font-semibold"><Calculator size={16} />Payroll calculator</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="ec-label">Pay frequency</label>
          <select className="ec-input" value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
            <option value="weekly">Weekly</option>
            <option value="biweekly">Bi-weekly</option>
            <option value="monthly">Monthly</option>
            <option value="annual">Annual</option>
          </select>
        </div>
        <div><label className="ec-label">Gross salary</label><input type="number" className="ec-input" value={gross} onChange={(e) => setGross(Number(e.target.value))} /></div>
        <div><label className="ec-label">Combined tax rate</label><input type="number" step="0.01" min={0} max={1} className="ec-input" value={taxRate} onChange={(e) => setTaxRate(Number(e.target.value))} /></div>
        <div><label className="ec-label">Deductions</label><input type="number" className="ec-input" value={deductions} onChange={(e) => setDeductions(Number(e.target.value))} /></div>
        <div><label className="ec-label">Bonuses</label><input type="number" className="ec-input" value={bonuses} onChange={(e) => setBonuses(Number(e.target.value))} /></div>
      </div>
      <button className="ec-btn-primary w-full" onClick={() => calc.mutate()} disabled={calc.isPending}>
        {calc.isPending ? 'Calculating…' : 'Calculate net pay'}
      </button>
      {result && (
        <div className="mt-2 space-y-1 rounded-lg border border-border bg-surface-muted p-3 text-sm">
          <p className="flex justify-between"><span>Gross (incl. bonuses)</span><strong>{formatCurrency(result.gross)}</strong></p>
          <p className="flex justify-between"><span>Tax withheld</span><strong className="text-rose-500">-{formatCurrency(result.tax)}</strong></p>
          <p className="flex justify-between"><span>Other deductions</span><strong className="text-rose-500">-{formatCurrency(result.deductions)}</strong></p>
          <hr className="my-2 border-border" />
          <p className="flex justify-between text-lg"><span>Net pay</span><strong className="text-emerald-500">{formatCurrency(result.net)}</strong></p>
          <p className="text-xs text-ink-muted">≈ <strong>{formatCurrency(annual)}</strong> per year</p>
        </div>
      )}
    </div>
  );
}

function RunForm() {
  const qc = useQueryClient();
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const [end, setEnd] = useState(new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10));
  const [lines, setLines] = useState<Line[]>([
    { employee_id: 'EMP-001', label: 'Base salary', amount: 5000, kind: 'earning' },
    { employee_id: 'EMP-001', label: 'Income tax', amount: 800, kind: 'tax' },
  ]);

  const save = useMutation({
    mutationFn: async () => (await api.post('/finance/payroll', {
      period_start: start, period_end: end, lines,
    })).data,
    onSuccess: () => {
      setLines([{ employee_id: 'EMP-001', label: 'Base salary', amount: 5000, kind: 'earning' }]);
      qc.invalidateQueries({ queryKey: ['finance', 'payroll'] });
    },
  });

  const gross = lines.filter((l) => l.kind === 'earning' || l.kind === 'bonus').reduce((s, l) => s + Number(l.amount), 0);
  const ded = lines.filter((l) => l.kind === 'tax' || l.kind === 'deduction').reduce((s, l) => s + Number(l.amount), 0);

  return (
    <div className="ec-card p-5 space-y-3">
      <p className="flex items-center gap-2 text-sm font-semibold"><Wallet size={16} />New payroll run</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className="ec-label">Period start</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="ec-label">Period end</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
      </div>
      <div className="space-y-2">
        {lines.map((l, i) => (
          <div key={i} className="grid gap-2 md:grid-cols-[100px_1fr_100px_110px_24px]">
            <input className="ec-input !py-1" placeholder="Emp ID" value={l.employee_id ?? ''}
              onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, employee_id: e.target.value } : x))} />
            <input className="ec-input !py-1" placeholder="Label" value={l.label}
              onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, label: e.target.value } : x))} />
            <input type="number" className="ec-input !py-1" placeholder="Amount" value={l.amount}
              onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, amount: Number(e.target.value) } : x))} />
            <select className="ec-input !py-1" value={l.kind}
              onChange={(e) => setLines(lines.map((x, ix) => ix === i ? { ...x, kind: e.target.value } : x))}>
              {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
            <button className="ec-btn-ghost text-rose-600" type="button" onClick={() => setLines(lines.filter((_, ix) => ix !== i))}>×</button>
          </div>
        ))}
        <button type="button" className="ec-btn-secondary" onClick={() => setLines([...lines, { employee_id: '', label: '', amount: 0, kind: 'earning' }])}>
          <Plus size={14} /> Add line
        </button>
      </div>
      <div className="rounded-lg border border-border bg-surface-muted p-3 text-sm">
        <p className="flex justify-between"><span>Gross</span><strong>{formatCurrency(gross)}</strong></p>
        <p className="flex justify-between"><span>Deductions / tax</span><strong className="text-rose-500">-{formatCurrency(ded)}</strong></p>
        <p className="flex justify-between text-base"><span>Net</span><strong className="text-emerald-500">{formatCurrency(gross - ded)}</strong></p>
      </div>
      <button className="ec-btn-primary w-full" disabled={!lines.length || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? 'Saving…' : 'Save payroll run'}
      </button>
    </div>
  );
}

function RunList() {
  const qc = useQueryClient();
  const runs = useQuery({
    queryKey: ['finance', 'payroll'],
    queryFn: async () => (await api.get<Run[]>('/finance/payroll')).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/finance/payroll/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'payroll'] }),
  });

  return (
    <div className="ec-card overflow-hidden">
      <div className="border-b border-border bg-surface-muted p-3">
        <p className="text-sm font-semibold">Saved payroll runs</p>
      </div>
      <table className="ec-table">
        <thead><tr><th>Period</th><th>Status</th><th>Gross</th><th>Deductions</th><th>Net</th><th></th></tr></thead>
        <tbody>
          {runs.data?.length ? runs.data.map((r) => (
            <tr key={r.id}>
              <td>{formatDate(r.period_start)} → {formatDate(r.period_end)}</td>
              <td><span className="ec-badge ec-badge-blue">{r.status}</span></td>
              <td>{formatCurrency(r.gross_total)}</td>
              <td className="text-rose-500">-{formatCurrency(r.deduction_total)}</td>
              <td className="font-medium text-emerald-500">{formatCurrency(r.net_total)}</td>
              <td className="text-right">
                <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete payroll run?')) remove.mutate(r.id); }}><Trash2 size={16} /></button>
              </td>
            </tr>
          )) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No payroll runs saved yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
