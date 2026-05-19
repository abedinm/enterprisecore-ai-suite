import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Download, FileBadge } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Payslip = {
  payroll_run_id: string; employee_id: string | null; employee_name: string | null;
  period_start: string; period_end: string;
  gross: string; deductions: string; net: string; currency: string;
  lines: { label: string; amount: string; kind: string }[];
};

export function PayslipsTab() {
  const [empId, setEmpId] = useState('');
  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  useEffect(() => {
    if (employees.data?.length && !empId) setEmpId(employees.data[0].id);
  }, [employees.data, empId]);

  const payslips = useQuery({
    enabled: !!empId,
    queryKey: ['hr', 'payslips', empId],
    queryFn: async () => (await api.get<Payslip[]>(`/hr/payslips/${empId}`)).data,
  });

  async function downloadPdf(p: Payslip) {
    const r = await api.get(`/hr/payslips/${empId}/${p.payroll_run_id}/pdf`, { responseType: 'blob' });
    const url = URL.createObjectURL(r.data as Blob);
    const a = document.createElement('a');
    a.href = url; a.download = `payslip-${p.period_end}.pdf`; a.click();
    URL.revokeObjectURL(url);
  }

  const totalGross = (payslips.data ?? []).reduce((s, p) => s + parseFloat(p.gross), 0);
  const totalNet = (payslips.data ?? []).reduce((s, p) => s + parseFloat(p.net), 0);
  const emp = employees.data?.find((e) => e.id === empId);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="ec-label">Employee</label>
          <select className="ec-input md:!w-72" value={empId} onChange={(e) => setEmpId(e.target.value)}>
            <option value="">—</option>
            {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name} ({e.employee_code})</option>)}
          </select>
        </div>
        {emp && <p className="text-sm text-ink-muted">{emp.department ?? '—'} · {emp.title ?? '—'}</p>}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Payslips on record" value={(payslips.data?.length ?? 0).toString()} />
        <Tile label="Total gross" value={formatCurrency(totalGross)} />
        <Tile label="Total net" value={formatCurrency(totalNet)} tone="positive" />
      </div>

      <div className="space-y-3">
        {payslips.data?.length ? payslips.data.map((p) => (
          <div key={p.payroll_run_id} className="ec-card p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 font-semibold"><FileBadge size={16} className="text-brand-600" /> Period {formatDate(p.period_start)} → {formatDate(p.period_end)}</p>
                <p className="text-xs text-ink-muted">{p.lines.length} line items</p>
              </div>
              <button className="ec-btn-primary" onClick={() => downloadPdf(p)}><Download size={16} />PDF</button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <KpiBox label="Gross" value={formatCurrency(p.gross, p.currency)} />
              <KpiBox label="Deductions" value={`-${formatCurrency(p.deductions, p.currency)}`} tone="negative" />
              <KpiBox label="Net pay" value={formatCurrency(p.net, p.currency)} tone="positive" />
            </div>
            <table className="ec-table mt-3">
              <thead><tr><th>Label</th><th>Kind</th><th className="text-right">Amount</th></tr></thead>
              <tbody>
                {p.lines.map((l, i) => (
                  <tr key={i}>
                    <td>{l.label}</td>
                    <td><code className="rounded bg-surface-muted px-1 py-0.5 text-xs">{l.kind}</code></td>
                    <td className={`text-right ${l.kind === 'tax' || l.kind === 'deduction' ? 'text-rose-500' : ''}`}>{formatCurrency(l.amount, p.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )) : <div className="ec-card p-8 text-center text-sm text-ink-muted">No payslips for this employee yet. Create a payroll run with payslip lines on the Finance → Payroll tab.</div>}
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'positive' }) {
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${tone === 'positive' ? 'text-emerald-500' : ''}`}>{value}</p>
    </div>
  );
}

function KpiBox({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' }) {
  return (
    <div className="rounded-lg border border-border bg-surface-muted p-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${tone === 'positive' ? 'text-emerald-500' : tone === 'negative' ? 'text-rose-500' : ''}`}>{value}</p>
    </div>
  );
}
