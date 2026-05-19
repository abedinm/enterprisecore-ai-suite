import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Award } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDateTime } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Training = { id: string; employee_id: string; course_name: string; status: string; completed_at: string | null };

const STATUSES = ['assigned', 'in_progress', 'completed', 'cancelled'];
const BADGE: Record<string, string> = {
  assigned: 'ec-badge-blue', in_progress: 'ec-badge-amber',
  completed: 'ec-badge-green', cancelled: 'ec-badge-rose',
};

export function TrainingTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');

  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  const trainings = useQuery({
    queryKey: ['hr', 'training', statusFilter],
    queryFn: async () => (await api.get<Training[]>('/hr/training', { params: statusFilter ? { status: statusFilter } : {} })).data,
  });

  const update = useMutation({
    mutationFn: async (t: Training) => (await api.patch(`/hr/training/${t.id}`, {
      employee_id: t.employee_id, course_name: t.course_name, status: t.status, completed_at: t.completed_at,
    })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'training'] }),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/training/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'training'] }),
  });

  const counts = (trainings.data ?? []).reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1; return acc;
  }, {});
  const completion = trainings.data?.length ? (counts['completed'] ?? 0) / trainings.data.length : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Training</p>
          <p className="text-sm text-ink-muted">{trainings.data?.length ?? 0} records · completion <strong>{(completion * 100).toFixed(0)}%</strong></p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Filter</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowForm((v) => !v)}><Plus size={16} />{showForm ? 'Close' : 'Assign training'}</button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s.replace('_', ' ')}</p>
            <p className="text-xl font-semibold">{counts[s] ?? 0}</p>
          </div>
        ))}
      </div>

      {showForm && employees.data && <TrainingForm employees={employees.data}
        onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['hr', 'training'] }); }} />}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Employee</th><th>Course</th><th>Status</th><th>Completed at</th><th></th></tr></thead>
          <tbody>
            {trainings.data?.length ? trainings.data.map((t) => {
              const emp = employees.data?.find((e) => e.id === t.employee_id);
              return (
                <tr key={t.id}>
                  <td className="font-medium">{emp?.full_name ?? '—'}</td>
                  <td className="flex items-center gap-2">
                    <Award size={14} className="text-brand-600" />{t.course_name}
                  </td>
                  <td>
                    <select className={`ec-input !py-1 !w-32 ${BADGE[t.status] ?? ''}`} value={t.status}
                            onChange={(e) => update.mutate({ ...t, status: e.target.value })}>
                      {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td>{t.completed_at ? formatDateTime(t.completed_at) : '—'}</td>
                  <td className="text-right">
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete record?')) remove.mutate(t.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={5} className="py-8 text-center text-ink-muted">No training records.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TrainingForm({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [empId, setEmpId] = useState(employees[0]?.id ?? '');
  const [course, setCourse] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/training', {
      employee_id: empId, course_name: course, status: 'assigned', completed_at: null,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-4">
      <div className="md:col-span-2"><label className="ec-label">Employee</label>
        <select className="ec-input" value={empId} onChange={(e) => setEmpId(e.target.value)}>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select>
      </div>
      <div className="md:col-span-2"><label className="ec-label">Course name</label><input className="ec-input" value={course} onChange={(e) => setCourse(e.target.value)} /></div>
      <div className="md:col-span-4 flex justify-end"><button className="ec-btn-primary" disabled={!empId || !course || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Assign'}</button></div>
    </div>
  );
}
