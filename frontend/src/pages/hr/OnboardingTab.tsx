import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Check, Circle } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Task = { id: string; employee_id: string | null; title: string; status: string; due_date: string | null };

const STATUSES = ['open', 'in_progress', 'completed', 'blocked'];

export function OnboardingTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [empFilter, setEmpFilter] = useState('');

  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  const tasks = useQuery({
    queryKey: ['hr', 'onboarding', empFilter],
    queryFn: async () => (await api.get<Task[]>('/hr/onboarding', { params: empFilter ? { employee_id: empFilter } : {} })).data,
  });

  const update = useMutation({
    mutationFn: async (t: Task) => (await api.patch(`/hr/onboarding/${t.id}`, {
      employee_id: t.employee_id, title: t.title, status: t.status, due_date: t.due_date,
    })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'onboarding'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/onboarding/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'onboarding'] }),
  });

  const byStatus = (tasks.data ?? []).reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1; return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Onboarding tasks</p>
          <p className="text-sm text-ink-muted">{tasks.data?.length ?? 0} tasks</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Employee filter</label>
            <select className="ec-input md:!w-56" value={empFilter} onChange={(e) => setEmpFilter(e.target.value)}>
              <option value="">All</option>
              {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowForm((v) => !v)}><Plus size={16} /> {showForm ? 'Close' : 'New task'}</button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s.replace('_', ' ')}</p>
            <p className="text-xl font-semibold">{byStatus[s] ?? 0}</p>
          </div>
        ))}
      </div>

      {showForm && employees.data && (
        <TaskForm employees={employees.data}
          onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['hr', 'onboarding'] }); }} />
      )}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th></th><th>Task</th><th>Assigned to</th><th>Due</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {tasks.data?.length ? tasks.data.map((t) => {
              const emp = employees.data?.find((e) => e.id === t.employee_id);
              const done = t.status === 'completed';
              return (
                <tr key={t.id} className={done ? 'opacity-60' : ''}>
                  <td>
                    <button className="ec-btn-ghost" onClick={() => update.mutate({ ...t, status: done ? 'open' : 'completed' })}>
                      {done ? <Check size={16} className="text-emerald-500" /> : <Circle size={16} />}
                    </button>
                  </td>
                  <td className={`font-medium ${done ? 'line-through' : ''}`}>{t.title}</td>
                  <td>{emp?.full_name ?? '—'}</td>
                  <td>{formatDate(t.due_date)}</td>
                  <td>
                    <select className="ec-input !py-1 !w-32" value={t.status}
                            onChange={(e) => update.mutate({ ...t, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="text-right">
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete task?')) remove.mutate(t.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No onboarding tasks.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TaskForm({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [title, setTitle] = useState('');
  const [empId, setEmpId] = useState(employees[0]?.id ?? '');
  const [due, setDue] = useState(new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10));
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/onboarding', {
      title, employee_id: empId || null, status: 'open', due_date: due,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-5">
      <div className="md:col-span-2"><label className="ec-label">Task title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <div className="md:col-span-2"><label className="ec-label">Assign to</label>
        <select className="ec-input" value={empId} onChange={(e) => setEmpId(e.target.value)}>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Due date</label><input type="date" className="ec-input" value={due} onChange={(e) => setDue(e.target.value)} /></div>
      <div className="md:col-span-5 flex justify-end"><button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
    </div>
  );
}
