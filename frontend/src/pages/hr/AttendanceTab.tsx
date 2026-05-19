import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Clock, LogIn, LogOut, Trash2 } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Attendance = { id: string; employee_id: string; clock_in: string; clock_out: string | null; source: string };
type Summary = { employee_id: string; days_present: number; hours_total: string; last_clock_in: string | null };

export function AttendanceTab() {
  const qc = useQueryClient();
  const [employeeId, setEmployeeId] = useState('');

  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  useEffect(() => {
    if (employees.data?.length && !employeeId) setEmployeeId(employees.data[0].id);
  }, [employees.data, employeeId]);

  const records = useQuery({
    enabled: !!employeeId,
    queryKey: ['hr', 'attendance', employeeId],
    queryFn: async () => (await api.get<Attendance[]>('/hr/attendance', { params: { employee_id: employeeId } })).data,
  });
  const summary = useQuery({
    enabled: !!employeeId,
    queryKey: ['hr', 'attendance', employeeId, 'summary'],
    queryFn: async () => (await api.get<Summary>(`/hr/attendance/summary/${employeeId}`)).data,
  });

  const clockIn = useMutation({
    mutationFn: async () => (await api.post('/hr/attendance', {
      employee_id: employeeId, clock_in: new Date().toISOString(), source: 'manual',
    })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hr', 'attendance'] });
    },
  });
  const clockOut = useMutation({
    mutationFn: async (id: string) => (await api.post(`/hr/attendance/${id}/clock-out`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'attendance'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/attendance/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'attendance'] }),
  });

  const openRecord = records.data?.find((r) => !r.clock_out);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="grow">
          <label className="ec-label">Employee</label>
          <select className="ec-input md:!w-80" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)}>
            <option value="">—</option>
            {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name} ({e.employee_code})</option>)}
          </select>
        </div>
        <button className="ec-btn-primary" disabled={!employeeId || clockIn.isPending || !!openRecord} onClick={() => clockIn.mutate()}>
          <LogIn size={16} /> Clock in
        </button>
        <button className="ec-btn-secondary" disabled={!openRecord || clockOut.isPending} onClick={() => openRecord && clockOut.mutate(openRecord.id)}>
          <LogOut size={16} /> Clock out
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Tile label="Days present" value={summary.data?.days_present?.toString() ?? '0'} />
        <Tile label="Hours total" value={summary.data?.hours_total ?? '0'} />
        <Tile label="Last clock in" value={summary.data?.last_clock_in ? formatDateTime(summary.data.last_clock_in) : '—'} />
      </div>

      {openRecord && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/5 px-4 py-2 text-sm">
          <Clock size={16} className="text-emerald-500" />
          <span>Currently clocked in since <strong>{formatDateTime(openRecord.clock_in)}</strong></span>
        </div>
      )}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Clock in</th><th>Clock out</th><th>Source</th><th>Duration</th><th></th></tr></thead>
          <tbody>
            {records.data?.length ? records.data.map((r) => {
              const duration = r.clock_out ? (new Date(r.clock_out).getTime() - new Date(r.clock_in).getTime()) / 3600000 : null;
              return (
                <tr key={r.id}>
                  <td>{formatDateTime(r.clock_in)}</td>
                  <td>{r.clock_out ? formatDateTime(r.clock_out) : <span className="text-emerald-500">open</span>}</td>
                  <td><code className="text-xs text-ink-muted">{r.source}</code></td>
                  <td>{duration !== null ? `${duration.toFixed(2)}h` : '—'}</td>
                  <td className="text-right whitespace-nowrap">
                    {!r.clock_out && <button className="ec-btn-ghost" onClick={() => clockOut.mutate(r.id)}><LogOut size={14} /></button>}
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete record?')) remove.mutate(r.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No attendance records.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}
