import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, TrendingDown } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import { Project, Sprint, Task } from './types';

const STATUSES = ['planned', 'active', 'completed', 'cancelled'] as const;
const STATUS_BADGE: Record<string, string> = {
  planned: 'ec-badge-blue', active: 'ec-badge-amber',
  completed: 'ec-badge-green', cancelled: 'ec-badge-rose',
};

type Burndown = {
  sprint_id: string; name: string;
  start_date: string; end_date: string;
  total_points: number; completed_points: number; remaining_points: number;
  ideal: { date: string; points: number }[];
  actual: { date: string; points: number }[];
  task_count: number; completed_tasks: number;
};

export function SprintsTab() {
  const qc = useQueryClient();
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Sprint | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });
  const sprints = useQuery({
    queryKey: ['projects', 'sprints', projectFilter],
    queryFn: async () => (await api.get<Sprint[]>('/projects/sprints', {
      params: projectFilter ? { project_id: projectFilter } : {},
    })).data,
  });
  const tasks = useQuery({
    queryKey: ['projects', 'tasks', 'forSprint', selected],
    queryFn: async () => selected ? (await api.get<Task[]>('/projects/tasks', { params: { sprint_id: selected } })).data : [],
    enabled: !!selected,
  });
  const burndown = useQuery({
    queryKey: ['projects', 'burndown', selected],
    queryFn: async () => selected ? (await api.get<Burndown>(`/projects/sprints/${selected}/burndown`)).data : null,
    enabled: !!selected,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/sprints/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects', 'sprints'] }),
  });

  const sprint = sprints.data?.find((s) => s.id === selected);

  const chartData = burndown.data?.ideal.map((d, i) => ({
    date: d.date.slice(5),
    ideal: d.points,
    actual: burndown.data?.actual[i]?.points,
  })) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Sprint Planner</p>
          <p className="text-sm text-ink-muted">Plan, run, and review sprints with burndown tracking.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Project</label>
            <select className="ec-input" value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}>
              <option value="">All</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New sprint</button>
        </div>
      </div>

      {(showForm || editing) && (
        <SprintForm
          editing={editing}
          projects={projects.data ?? []}
          defaultProjectId={projectFilter}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['projects', 'sprints'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="grid gap-3 md:grid-cols-[320px_1fr]">
        <div className="ec-card overflow-hidden">
          <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">All sprints</div>
          <div className="max-h-[500px] overflow-y-auto divide-y divide-border/60">
            {sprints.data?.length ? sprints.data.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelected(s.id)}
                className={`w-full p-3 text-left transition hover:bg-surface-muted ${selected === s.id ? 'bg-surface-muted' : ''}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{s.name}</p>
                  <span className={STATUS_BADGE[s.status] ?? 'ec-badge'}>{s.status}</span>
                </div>
                <p className="mt-0.5 text-xs text-ink-muted">{formatDate(s.start_date)} → {formatDate(s.end_date)}</p>
              </button>
            )) : <p className="p-6 text-center text-sm text-ink-muted">No sprints yet.</p>}
          </div>
        </div>

        {selected && sprint && burndown.data ? (
          <div className="space-y-3">
            <div className="ec-card p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold">{sprint.name}</h3>
                  <p className="text-xs text-ink-muted">{formatDate(sprint.start_date)} → {formatDate(sprint.end_date)} · Capacity: {sprint.capacity_points}pt</p>
                  {sprint.goal && <p className="mt-2 text-sm">{sprint.goal}</p>}
                </div>
                <div className="flex gap-1">
                  <button className="ec-btn-ghost" onClick={() => setEditing(sprint)}><Edit3 size={14} /></button>
                  <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete sprint?')) remove.mutate(sprint.id); }}><Trash2 size={14} /></button>
                </div>
              </div>
              <div className="mt-4 grid gap-2 md:grid-cols-4">
                <StatCard label="Tasks" value={String(burndown.data.task_count)} />
                <StatCard label="Completed" value={String(burndown.data.completed_tasks)} />
                <StatCard label="Total points" value={String(burndown.data.total_points)} />
                <StatCard label="Remaining" value={String(burndown.data.remaining_points)} />
              </div>
            </div>

            <div className="ec-card p-4">
              <div className="mb-3 flex items-center gap-2">
                <TrendingDown size={16} className="text-brand-600" />
                <p className="text-sm font-semibold">Burndown chart</p>
              </div>
              <div className="h-60">
                <ResponsiveContainer>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                    <Legend />
                    <Line type="monotone" dataKey="ideal" stroke="#9ca3af" strokeDasharray="4 4" name="Ideal" />
                    <Line type="monotone" dataKey="actual" stroke="#4f46e5" strokeWidth={2} name="Actual" connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="ec-card overflow-x-auto">
              <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Sprint tasks ({tasks.data?.length ?? 0})</div>
              <table className="ec-table">
                <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Story Pts</th><th>Due</th></tr></thead>
                <tbody>
                  {tasks.data?.length ? tasks.data.map((t) => (
                    <tr key={t.id}>
                      <td className="font-medium">{t.title}</td>
                      <td>{t.status}</td>
                      <td>{t.priority}</td>
                      <td>{t.story_points}</td>
                      <td>{t.due_date ? formatDate(t.due_date) : '—'}</td>
                    </tr>
                  )) : <tr><td colSpan={5} className="py-6 text-center text-ink-muted">Assign tasks to this sprint via the Kanban or task form.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="ec-card p-10 text-center text-sm text-ink-muted">
            Pick a sprint to see burndown and contained tasks.
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-muted p-3">
      <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}

function SprintForm({ editing, projects, defaultProjectId, onSaved, onCancel }: {
  editing: Sprint | null; projects: Project[]; defaultProjectId: string;
  onSaved: () => void; onCancel: () => void;
}) {
  const [name, setName] = useState(editing?.name ?? '');
  const [projectId, setProjectId] = useState(editing?.project_id ?? defaultProjectId);
  const [startDate, setStartDate] = useState(editing?.start_date ?? new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(editing?.end_date ?? new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10));
  const [goal, setGoal] = useState(editing?.goal ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'planned');
  const [capacity, setCapacity] = useState(editing?.capacity_points ?? 20);

  const save = useMutation({
    mutationFn: async () => {
      const body = { project_id: projectId, name, start_date: startDate, end_date: endDate, goal, status, capacity_points: capacity };
      if (editing) return (await api.patch(`/projects/sprints/${editing.id}`, body)).data;
      return (await api.post('/projects/sprints', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit sprint' : 'New sprint'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Sprint name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Sprint 23" /></div>
        <div><label className="ec-label">Project</label>
          <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Start</label><input type="date" className="ec-input" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></div>
        <div><label className="ec-label">End</label><input type="date" className="ec-input" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></div>
        <div><label className="ec-label">Capacity (points)</label><input type="number" className="ec-input" value={capacity} onChange={(e) => setCapacity(Number(e.target.value))} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="md:col-span-3"><label className="ec-label">Goal</label><textarea className="ec-input" rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || !projectId || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Create'}</button>
      </div>
    </div>
  );
}
