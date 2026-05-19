import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../../lib/api';

type Analytics = {
  total_projects: number;
  active_projects: number;
  completed_projects: number;
  tasks_by_status: Record<string, number>;
  tasks_by_priority: Record<string, number>;
  overdue_tasks: number;
  upcoming_milestones: number;
  total_time_minutes: number;
  total_tasks: number;
  completed_tasks: number;
  completion_rate: number;
  avg_task_duration_days: number;
  sprint_burn_rate: Record<string, number>;
  workload_by_assignee: { assignee_id: string; assignee?: string; open: number; done: number }[];
  project_progress: { id: string; name: string; progress: number }[];
  upcoming_deadlines: { id: string; title: string; due_date: string; project: string | null }[];
};

export function ProjectsAnalyticsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['projects', 'analytics'],
    queryFn: async () => (await api.get<Analytics>('/projects/analytics')).data,
  });

  if (isLoading || !data) return <p className="text-sm text-ink-muted">Loading analytics…</p>;

  const byStatus = Object.entries(data.tasks_by_status).map(([k, v]) => ({ name: k, count: v }));
  const byPriority = Object.entries(data.tasks_by_priority).map(([k, v]) => ({ name: k, count: v }));

  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-4">
        <Tile label="Active projects" value={data.active_projects} />
        <Tile label="Completed" value={data.completed_projects} tone="positive" />
        <Tile label="Overdue tasks" value={data.overdue_tasks} tone="rose" />
        <Tile label="Completion rate" value={`${Math.round((data.completion_rate ?? 0) * 100)}%`} tone="highlight" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Chart title="Tasks by status" data={byStatus} color="#4f46e5" />
        <Chart title="Tasks by priority" data={byPriority} color="#10b981" />
      </div>

      <div className="ec-card p-5">
        <p className="mb-3 text-sm font-semibold">Project progress</p>
        <div className="space-y-2">
          {data.project_progress.length ? data.project_progress.map((p) => (
            <div key={p.id}>
              <div className="flex justify-between text-sm"><span>{p.name}</span><strong>{p.progress}%</strong></div>
              <div className="mt-1 h-1.5 rounded bg-surface-muted">
                <div className="h-full rounded bg-brand-500" style={{ width: `${Math.min(100, p.progress)}%` }} />
              </div>
            </div>
          )) : <p className="text-sm text-ink-muted">No projects yet.</p>}
        </div>
      </div>

      <div className="ec-card p-5">
        <p className="mb-3 text-sm font-semibold">Upcoming deadlines</p>
        <ul className="space-y-2 text-sm">
          {data.upcoming_deadlines.length ? data.upcoming_deadlines.map((d) => (
            <li key={d.id} className="flex justify-between border-b border-border/60 pb-1">
              <span>{d.title} {d.project && <span className="text-ink-muted">· {d.project}</span>}</span>
              <strong>{d.due_date}</strong>
            </li>
          )) : <li className="text-ink-muted">No upcoming deadlines.</li>}
        </ul>
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string | number; tone?: 'positive' | 'rose' | 'highlight' }) {
  const cls = tone === 'positive' ? 'text-emerald-500'
    : tone === 'rose' ? 'text-rose-500'
    : tone === 'highlight' ? 'text-brand-600' : '';
  return (
    <div className="ec-card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${cls}`}>{value}</p>
    </div>
  );
}

function Chart({ title, data, color }: { title: string; data: { name: string; count: number }[]; color: string }) {
  return (
    <div className="ec-card p-5">
      <p className="mb-3 text-sm font-semibold">{title}</p>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" fill={color} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
