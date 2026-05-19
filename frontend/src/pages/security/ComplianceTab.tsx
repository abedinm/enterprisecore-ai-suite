import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, ShieldCheck } from 'lucide-react';
import { api } from '../../lib/api';

type Check = { id: string; framework: string; item: string; status: string; evidence: string };
type Report = { framework: string; total: number; met: number; partial: number; missed: number; pending: number; score: number };
const STATUSES = ['open', 'pending', 'met', 'partial', 'missed', 'n/a'];

export function ComplianceTab() {
  const qc = useQueryClient();
  const [framework, setFramework] = useState('SOC2');
  const checks = useQuery({
    queryKey: ['security', 'compliance', framework],
    queryFn: async () => (await api.get<Check[]>('/security/compliance', { params: { framework } })).data,
  });
  const report = useQuery({
    queryKey: ['security', 'compliance-report', framework],
    queryFn: async () => (await api.get<Report>(`/security/compliance/report/${framework}`)).data,
  });

  const updateStatus = useMutation({
    mutationFn: async ({ id, status, evidence }: { id: string; status: string; evidence?: string }) =>
      (await api.post(`/security/compliance/${id}/status`, { status, evidence })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['security', 'compliance', framework] });
      qc.invalidateQueries({ queryKey: ['security', 'compliance-report', framework] });
    },
  });

  const [newItem, setNewItem] = useState('');
  const add = useMutation({
    mutationFn: async () => (await api.post('/security/compliance', { framework, item: newItem, status: 'open' })).data,
    onSuccess: () => { setNewItem(''); qc.invalidateQueries({ queryKey: ['security', 'compliance', framework] }); },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="ec-label">Framework</label>
          <select className="ec-input" value={framework} onChange={(e) => setFramework(e.target.value)}>
            <option>SOC2</option>
            <option>HIPAA</option>
            <option>ISO27001</option>
            <option>GDPR</option>
            <option>PCI-DSS</option>
          </select>
        </div>
        {report.data && (
          <div className="ec-card p-3 flex items-center gap-4 text-sm">
            <ShieldCheck className="text-brand-600" size={18} />
            <div className="flex items-center gap-2">
              <strong className="text-2xl">{report.data.score}%</strong>
              <span className="text-xs text-ink-muted">{report.data.met} met / {report.data.partial} partial / {report.data.missed} missed / {report.data.pending} pending / {report.data.total} total</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <input className="ec-input flex-1" placeholder="New control item…" value={newItem} onChange={(e) => setNewItem(e.target.value)} />
        <button className="ec-btn-primary" disabled={!newItem || add.isPending} onClick={() => add.mutate()}><Plus size={14} />Add</button>
      </div>

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead><tr><th>Item</th><th>Status</th><th>Evidence</th></tr></thead>
          <tbody>
            {checks.data?.length ? checks.data.map((c) => (
              <tr key={c.id}>
                <td>{c.item}</td>
                <td>
                  <select className="ec-input !py-1 !w-32" value={c.status}
                          onChange={(e) => updateStatus.mutate({ id: c.id, status: e.target.value })}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
                <td className="text-xs text-ink-muted">{c.evidence || '—'}</td>
              </tr>
            )) : <tr><td colSpan={3} className="py-8 text-center text-ink-muted">No controls tracked for {framework} yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
