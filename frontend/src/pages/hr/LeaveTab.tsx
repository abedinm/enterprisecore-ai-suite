import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Plus, Check, X, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Leave = { id: string; employee_id: string; start_date: string; end_date: string; leave_type: string; status: string; reason: string | null };
type Balance = { employee_id: string; by_type: Record<string, number>; total_taken: number };

const LEAVE_TYPES = ['annual', 'sick', 'personal', 'parental', 'unpaid', 'bereavement'];
const STATUSES = ['pending', 'approved', 'rejected', 'cancelled'];
const STATUS_BADGE: Record<string, string> = {
  pending: 'ec-badge-amber', approved: 'ec-badge-green',
  rejected: 'ec-badge-rose', cancelled: 'ec-badge',
};

export function LeaveTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [balanceEmpId, setBalanceEmpId] = useState('');

  const leaves = useQuery({
    queryKey: ['hr', 'leaves', statusFilter],
    queryFn: async () => (await api.get<Leave[]>('/hr/leaves', { params: statusFilter ? { status: statusFilter } : {} })).data,
  });
  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  useEffect(() => {
    if (employees.data?.length && !balanceEmpId) setBalanceEmpId(employees.data[0].id);
  }, [employees.data, balanceEmpId]);

  const balance = useQuery({
    enabled: !!balanceEmpId,
    queryKey: ['hr', 'leaves', balanceEmpId, 'balance'],
    queryFn: async () => (await api.get<Balance>(`/hr/leaves/balance/${balanceEmpId}`)).data,
  });

  const decide = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      (await api.post(`/hr/leaves/${id}/decision`, { status })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'leaves'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/leaves/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'leaves'] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Leave management</p>
          <p className="text-sm text-ink-muted">{leaves.data?.length ?? 0} requests</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Filter</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowForm((v) => !v)}>
            <Plus size={16} /> {showForm ? 'Close' : 'New leave request'}
          </button>
        </div>
      </div>

      {showForm && employees.data && (
        <LeaveForm employees={employees.data}
          onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['hr', 'leaves'] }); }} />
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="ec-card overflow-x-auto">
          <table className="ec-table">
            <thead><tr><th>Employee</th><th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Reason</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {leaves.data?.length ? leaves.data.map((l) => {
                const emp = employees.data?.find((e) => e.id === l.employee_id);
                const days = Math.round((new Date(l.end_date).getTime() - new Date(l.start_date).getTime()) / 86400000) + 1;
                return (
                  <tr key={l.id}>
                    <td className="font-medium">{emp?.full_name ?? '—'}</td>
                    <td className="capitalize">{l.leave_type}</td>
                    <td>{formatDate(l.start_date)}</td>
                    <td>{formatDate(l.end_date)}</td>
                    <td>{days}</td>
                    <td className="max-w-xs truncate text-xs text-ink-muted" title={l.reason ?? ''}>{l.reason ?? '—'}</td>
                    <td><span className={`ec-badge ${STATUS_BADGE[l.status]}`}>{l.status}</span></td>
                    <td className="space-x-1 whitespace-nowrap text-right">
                      {l.status === 'pending' && <>
                        <button className="ec-btn-ghost text-emerald-600" title="Approve" onClick={() => decide.mutate({ id: l.id, status: 'approved' })}><Check size={14} /></button>
                        <button className="ec-btn-ghost text-rose-600" title="Reject" onClick={() => decide.mutate({ id: l.id, status: 'rejected' })}><X size={14} /></button>
                      </>}
                      <button className="ec-btn-ghost text-rose-600" title="Delete" onClick={() => { if (confirm('Delete request?')) remove.mutate(l.id); }}><Trash2 size={14} /></button>
                    </td>
                  </tr>
                );
              }) : <tr><td colSpan={8} className="py-8 text-center text-ink-muted">No leave requests.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="ec-card p-4 space-y-3">
          <p className="text-sm font-semibold">Leave balance (YTD)</p>
          <select className="ec-input" value={balanceEmpId} onChange={(e) => setBalanceEmpId(e.target.value)}>
            <option value="">—</option>
            {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
          </select>
          {balance.data ? (
            <>
              <p className="text-2xl font-semibold">{balance.data.total_taken} <span className="text-sm font-normal text-ink-muted">days taken</span></p>
              <div className="space-y-2 text-sm">
                {Object.keys(balance.data.by_type).length ? Object.entries(balance.data.by_type).map(([t, d]) => (
                  <div key={t} className="flex justify-between rounded-md bg-surface-muted px-3 py-2">
                    <span className="capitalize">{t}</span><strong>{d} days</strong>
                  </div>
                )) : <p className="text-ink-muted">No approved leave this year.</p>}
              </div>
            </>
          ) : <p className="text-sm text-ink-muted">Select an employee.</p>}
        </div>
      </div>
    </div>
  );
}

function LeaveForm({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const week = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
  const [empId, setEmpId] = useState(employees[0]?.id ?? '');
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(week);
  const [type, setType] = useState('annual');
  const [reason, setReason] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/leaves', {
      employee_id: empId, start_date: start, end_date: end, leave_type: type, reason: reason || null,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-6">
      <div className="md:col-span-2"><label className="ec-label">Employee</label>
        <select className="ec-input" value={empId} onChange={(e) => setEmpId(e.target.value)}>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Type</label>
        <select className="ec-input" value={type} onChange={(e) => setType(e.target.value)}>
          {LEAVE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div><label className="ec-label">From</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
      <div><label className="ec-label">To</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
      <div className="flex items-end"><button className="ec-btn-primary w-full" disabled={!empId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Submit'}</button></div>
      <div className="md:col-span-6"><label className="ec-label">Reason</label><textarea rows={2} className="ec-input" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
    </div>
  );
}
