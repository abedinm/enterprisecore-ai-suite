import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { LogIn, LogOut, Download, CalendarPlus, UserCircle2 } from 'lucide-react';
import { api } from '../../lib/api';
import { formatCurrency, formatDate, formatDateTime } from '../../lib/utils';

type Self = {
  employee: {
    id: string; employee_code: string; full_name: string;
    email: string | null; department: string | null; title: string | null;
    hire_date: string | null; salary: string; status: string;
  } | null;
  recent_attendance: { id: string; clock_in: string; clock_out: string | null; source: string }[];
  upcoming_leaves: { id: string; start_date: string; end_date: string; leave_type: string; status: string }[];
  open_onboarding: { id: string; title: string; status: string; due_date: string | null }[];
  training: { id: string; course_name: string; status: string; completed_at: string | null }[];
  payslips: { payroll_run_id: string; period_start: string; period_end: string; gross: string; net: string; currency: string }[];
};

const LEAVE_TYPES = ['annual', 'sick', 'personal', 'parental', 'unpaid', 'bereavement'];

export function SelfServiceTab() {
  const qc = useQueryClient();
  const self = useQuery({
    queryKey: ['hr', 'self'],
    queryFn: async () => (await api.get<Self>('/hr/me')).data,
  });

  const clockIn = useMutation({
    mutationFn: async () => (await api.post('/hr/me/clock-in')).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'self'] }),
  });
  const clockOut = useMutation({
    mutationFn: async () => (await api.post('/hr/me/clock-out')).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'self'] }),
  });

  if (self.isLoading) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (!self.data?.employee) {
    return (
      <div className="ec-card p-8 text-center">
        <UserCircle2 size={48} className="mx-auto text-ink-muted" />
        <p className="mt-3 text-sm">Your user account isn't linked to an employee record yet.</p>
        <p className="mt-1 text-xs text-ink-muted">Ask an admin to add you under <code>HR → Employees</code> with your email <strong>{(self.data as any)?.email ?? 'your login email'}</strong>.</p>
      </div>
    );
  }

  const emp = self.data.employee;
  const openShift = self.data.recent_attendance.find((a) => !a.clock_out);

  return (
    <div className="space-y-5">
      <div className="ec-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="grid h-14 w-14 place-items-center rounded-full bg-brand-600 text-white text-xl font-semibold">
              {emp.full_name.split(' ').map((p) => p[0]).slice(0, 2).join('')}
            </div>
            <div>
              <p className="text-xl font-semibold">{emp.full_name}</p>
              <p className="text-sm text-ink-muted">{emp.title ?? '—'} · {emp.department ?? '—'}</p>
              <p className="text-xs text-ink-muted">Code <code>{emp.employee_code}</code> · Status <strong>{emp.status}</strong></p>
            </div>
          </div>
          <div className="text-right text-sm">
            <p className="text-xs text-ink-muted">Annual salary</p>
            <p className="text-lg font-semibold">{formatCurrency(emp.salary)}</p>
            <p className="mt-1 text-xs text-ink-muted">Hired {formatDate(emp.hire_date)}</p>
          </div>
        </div>
      </div>

      <div className="ec-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Today</p>
            {openShift ? (
              <p className="text-sm text-emerald-500">Clocked in at {formatDateTime(openShift.clock_in)}</p>
            ) : <p className="text-sm text-ink-muted">Not currently clocked in.</p>}
          </div>
          <div className="flex gap-2">
            <button className="ec-btn-primary" disabled={!!openShift || clockIn.isPending} onClick={() => clockIn.mutate()}><LogIn size={16} />Clock in</button>
            <button className="ec-btn-secondary" disabled={!openShift || clockOut.isPending} onClick={() => clockOut.mutate()}><LogOut size={16} />Clock out</button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <LeaveRequestCard onSubmitted={() => qc.invalidateQueries({ queryKey: ['hr', 'self'] })} />

        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">Upcoming leave</p>
          {self.data.upcoming_leaves.length ? (
            <ul className="space-y-2 text-sm">
              {self.data.upcoming_leaves.map((l) => (
                <li key={l.id} className="flex justify-between rounded-md bg-surface-muted px-3 py-2">
                  <span><strong className="capitalize">{l.leave_type}</strong> · {formatDate(l.start_date)} → {formatDate(l.end_date)}</span>
                  <span className={`ec-badge ec-badge-${l.status === 'approved' ? 'green' : l.status === 'pending' ? 'amber' : 'rose'}`}>{l.status}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-muted">No upcoming leave.</p>}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">Open onboarding tasks</p>
          {self.data.open_onboarding.length ? (
            <ul className="space-y-2 text-sm">
              {self.data.open_onboarding.map((t) => (
                <li key={t.id} className="flex justify-between rounded-md bg-surface-muted px-3 py-2">
                  <span>{t.title}</span>
                  <span className="text-xs text-ink-muted">due {formatDate(t.due_date)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-muted">All onboarding tasks complete.</p>}
        </div>

        <div className="ec-card p-5">
          <p className="mb-2 text-sm font-semibold">Training</p>
          {self.data.training.length ? (
            <ul className="space-y-2 text-sm">
              {self.data.training.map((t) => (
                <li key={t.id} className="flex justify-between rounded-md bg-surface-muted px-3 py-2">
                  <span>{t.course_name}</span>
                  <span className="text-xs capitalize text-ink-muted">{t.status}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-muted">No training assignments.</p>}
        </div>
      </div>

      <div className="ec-card p-5">
        <p className="mb-2 text-sm font-semibold">Payslips</p>
        {self.data.payslips.length ? (
          <ul className="space-y-2 text-sm">
            {self.data.payslips.map((p) => (
              <li key={p.payroll_run_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-surface-muted px-3 py-2">
                <span>{formatDate(p.period_start)} → {formatDate(p.period_end)}</span>
                <div className="flex items-center gap-3">
                  <span><strong className="text-emerald-500">{formatCurrency(p.net, p.currency)}</strong> <span className="text-xs text-ink-muted">net</span></span>
                  <button className="ec-btn-ghost" onClick={async () => {
                    const r = await api.get(`/hr/payslips/${emp.id}/${p.payroll_run_id}/pdf`, { responseType: 'blob' });
                    const url = URL.createObjectURL(r.data as Blob);
                    const a = document.createElement('a'); a.href = url; a.download = `payslip-${p.period_end}.pdf`; a.click();
                    URL.revokeObjectURL(url);
                  }}><Download size={14} /></button>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-muted">No payslips yet.</p>}
      </div>

      <div className="ec-card overflow-hidden">
        <div className="border-b border-border bg-surface-muted p-3 text-sm font-semibold">Recent attendance</div>
        <table className="ec-table">
          <thead><tr><th>Clock in</th><th>Clock out</th><th>Source</th></tr></thead>
          <tbody>
            {self.data.recent_attendance.length ? self.data.recent_attendance.map((a) => (
              <tr key={a.id}>
                <td>{formatDateTime(a.clock_in)}</td>
                <td>{a.clock_out ? formatDateTime(a.clock_out) : <span className="text-emerald-500">still in</span>}</td>
                <td className="text-xs text-ink-muted">{a.source}</td>
              </tr>
            )) : <tr><td colSpan={3} className="py-6 text-center text-ink-muted">No records yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LeaveRequestCard({ onSubmitted }: { onSubmitted: () => void }) {
  const [start, setStart] = useState(new Date().toISOString().slice(0, 10));
  const [end, setEnd] = useState(new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10));
  const [type, setType] = useState('annual');
  const [reason, setReason] = useState('');
  const submit = useMutation({
    mutationFn: async () => (await api.post('/hr/me/leave-request', {
      employee_id: '', // server replaces from current user
      start_date: start, end_date: end, leave_type: type, reason: reason || null,
    })).data,
    onSuccess: () => { setReason(''); onSubmitted(); },
  });
  return (
    <div className="ec-card p-5">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold"><CalendarPlus size={16} />Request leave</p>
      <div className="grid gap-3 md:grid-cols-3">
        <div><label className="ec-label">Type</label>
          <select className="ec-input" value={type} onChange={(e) => setType(e.target.value)}>
            {LEAVE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div><label className="ec-label">From</label><input type="date" className="ec-input" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="ec-label">To</label><input type="date" className="ec-input" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Reason</label><textarea rows={2} className="ec-input" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
      </div>
      <div className="mt-3 flex justify-end">
        <button className="ec-btn-primary" disabled={submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? 'Submitting…' : 'Submit request'}</button>
      </div>
    </div>
  );
}
