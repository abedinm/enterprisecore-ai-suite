import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Star, Trash2 } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import type { Employee } from './EmployeesTab';

type Review = { id: string; employee_id: string; reviewer_id: string | null; period: string; score: string; notes: string; created_at: string };

export function ReviewsTab() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState('');

  const employees = useQuery({
    queryKey: ['hr', 'employees'],
    queryFn: async () => (await api.get<Employee[]>('/hr/employees')).data,
  });
  const reviews = useQuery({
    queryKey: ['hr', 'reviews', filter],
    queryFn: async () => (await api.get<Review[]>('/hr/reviews', { params: filter ? { employee_id: filter } : {} })).data,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/hr/reviews/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['hr', 'reviews'] }),
  });

  const chart = (reviews.data ?? []).slice().reverse().map((r) => ({
    period: r.period, score: parseFloat(r.score),
  }));
  const avg = reviews.data?.length
    ? reviews.data.reduce((s, r) => s + parseFloat(r.score), 0) / reviews.data.length
    : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Performance reviews</p>
          <p className="text-sm text-ink-muted">{reviews.data?.length ?? 0} reviews · avg score <strong>{avg.toFixed(2)}</strong></p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Employee filter</label>
            <select className="ec-input md:!w-56" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">All employees</option>
              {employees.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowForm((v) => !v)}><Plus size={16} />New review</button>
        </div>
      </div>

      {showForm && employees.data && (
        <ReviewForm employees={employees.data}
          onSaved={() => { setShowForm(false); qc.invalidateQueries({ queryKey: ['hr', 'reviews'] }); }} />
      )}

      {chart.length > 0 && (
        <div className="ec-card p-5">
          <p className="mb-3 text-sm font-semibold">Score history</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                <XAxis dataKey="period" />
                <YAxis domain={[0, 5]} />
                <Tooltip />
                <Bar dataKey="score" fill="#4f46e5" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="ec-card overflow-hidden">
        <table className="ec-table">
          <thead><tr><th>Employee</th><th>Period</th><th>Score</th><th>Notes</th><th>Recorded</th><th></th></tr></thead>
          <tbody>
            {reviews.data?.length ? reviews.data.map((r) => {
              const emp = employees.data?.find((e) => e.id === r.employee_id);
              const score = parseFloat(r.score);
              return (
                <tr key={r.id}>
                  <td className="font-medium">{emp?.full_name ?? '—'}</td>
                  <td>{r.period}</td>
                  <td>
                    <span className="inline-flex items-center gap-1">
                      <Star size={14} className="text-amber-500" />
                      <strong>{score.toFixed(1)}</strong>
                      <span className="text-xs text-ink-muted">/ 5</span>
                    </span>
                  </td>
                  <td className="max-w-md truncate text-xs text-ink-muted" title={r.notes}>{r.notes || '—'}</td>
                  <td>{formatDate(r.created_at)}</td>
                  <td className="text-right">
                    <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete review?')) remove.mutate(r.id); }}><Trash2 size={14} /></button>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={6} className="py-8 text-center text-ink-muted">No reviews recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReviewForm({ employees, onSaved }: { employees: Employee[]; onSaved: () => void }) {
  const [empId, setEmpId] = useState(employees[0]?.id ?? '');
  const [period, setPeriod] = useState(`Q${Math.ceil((new Date().getMonth() + 1) / 3)} ${new Date().getFullYear()}`);
  const [score, setScore] = useState(4);
  const [notes, setNotes] = useState('');
  const save = useMutation({
    mutationFn: async () => (await api.post('/hr/reviews', {
      employee_id: empId, period, score, notes,
    })).data,
    onSuccess: onSaved,
  });
  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4 grid gap-3 md:grid-cols-5">
      <div className="md:col-span-2"><label className="ec-label">Employee</label>
        <select className="ec-input" value={empId} onChange={(e) => setEmpId(e.target.value)}>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </select>
      </div>
      <div><label className="ec-label">Period</label><input className="ec-input" value={period} onChange={(e) => setPeriod(e.target.value)} /></div>
      <div><label className="ec-label">Score (0-5)</label><input type="number" step="0.1" min={0} max={5} className="ec-input" value={score} onChange={(e) => setScore(Number(e.target.value))} /></div>
      <div className="flex items-end"><button className="ec-btn-primary w-full" disabled={!empId || save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save'}</button></div>
      <div className="md:col-span-5"><label className="ec-label">Notes</label><textarea rows={3} className="ec-input" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
    </div>
  );
}
