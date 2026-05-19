import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import { AlertTriangle, CheckCircle2, Clock, Folders, TrendingUp } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';

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
  workload_by_assignee: { assignee_id: string; open_tasks: number }[];
  project_progress: { id: string; name: string; color: string; total_tasks: number; done_tasks: number; progress: number; status: string }[];
  upcoming_deadlines: { id: string; title: string; due_date: string; priority: string; days_left: number }[];
};

const STATUS_COLORS = ['#60a5fa', '#fbbf24', '#a78bfa', '#10b981', '#94a3b8'];
const PRIORITY_COLORS = ['#94a3b8', '#60a5fa', '#fbbf24', '#f43f5e'];

export function ProjectsAnalyticsTab() {
  const data = useQuery({
    queryKey: ['projects', 'analytics'],
    queryFn: async () => (await api.get<Analytics>('/projects/analytics')).data,
  });

  const a = data.data;
  if (!a) return <p className="py-10 text-center text-ink-muted">Loading analytics…</p>;

  const statusData = Object.entries(a.tasks_by_status).map(([name, value]) => ({ name, value }));
  const priorityData = Object.entries(a.tasks_by_priority).map(([name, value]) => ({ name, value }));
  const burnData = Object.entries(a.sprint_burn_rate).map(([name, value]) => ({ name, points: value }));

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <StatCard icon={Folders} label="Active projects" value={a.active_projects} sub={`${a.total_projects} total`} />
        <StatCard icon={CheckCircle2} label="Tasks done" value={`${a.completed_tasks}/${a.total_tasks}`} sub={`${a.completion_rate}% completion`} />
        <StatCard icon={AlertTriangle} label="Overdue" value={a.overdue_tasks} sub="open tasks past due" alert={a.overdue_tasks > 0} />
        <StatCard icon={Clock} label="Logged" value={`${Math.floor(a.total_time_minutes / 60)}h`} sub={`${a.total_time_minutes % 60}m total`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="ec-card p-4">
          <p className="mb-2 text-sm font-semibold">Tasks by status</p>
          <div className="h-56">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={statusData} dataKey="value" nameKey="name" outerRadius={80} label>
                  {statusData.map((_, i) => <Cell key={i} fill={STATUS_COLORS[i % STATUS_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="ec-card p-4">
          <p className="mb-2 text-sm font-semibold">Tasks by priority</p>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={priorityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                <Bar dataKey="value">
                  {priorityData.map((_, i) => <Cell key={i} fill={PRIORITY_COLORS[i % PRIORITY_COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="ec-card p-4">
        <p className="mb-3 text-sm font-semibold">Project progress</p>
        <div className="space-y-2">
          {a.project_progress.map((p) => (
            <div key={p.id} className="flex items-center gap-3">
              <div className="h-3 w-3 shrink-0 rounded-full" style={{ background: p.color }} />
              <div className="flex-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-xs text-ink-muted">{p.done_tasks}/{p.total_tasks} · {p.progress}%</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-surface-muted">
                  <div className="h-2 rounded-full transition-all" style={{ width: `${p.progress}%`, background: p.color }} />
                </div>
              </div>
            </div>
          ))}
          {a.project_progress.length === 0 && <p className="text-xs text-ink-muted">No projects yet.</p>}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {burnData.length > 0 && (
          <div className="ec-card p-4">
            <div className="mb-2 flex items-center gap-2">
              <TrendingUp size={16} className="text-brand-600" />
              <p className="text-sm font-semibold">Active sprint burn rate</p>
            </div>
            <div className="h-48">
              <ResponsiveContainer>
                <BarChart data={burnData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                  <Bar dataKey="points" fill="#4f46e5" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        <div className="ec-card p-4">
          <p className="mb-2 text-sm font-semibold">Upcoming deadlines (14 days)</p>
          <div className="space-y-1.5">
            {a.upcoming_deadlines.length ? a.upcoming_deadlines.map((d) => (
              <div key={d.id} className="flex items-center justify-between rounded-md bg-surface-muted px-3 py-2 text-sm">
                <span className="truncate">{d.title}</span>
                <span className="ml-2 whitespace-nowrap text-xs text-ink-muted">
                  {formatDate(d.due_date)} ({d.days_left}d)
                </span>
              </div>
            )) : <p className="text-xs text-ink-muted">Nothing due soon.</p>}
          </div>
        </div>
      </div>

      <div className="ec-card p-4">
        <p className="mb-2 text-sm font-semibold">Other metrics</p>
        <div className="grid gap-3 md:grid-cols-3 text-sm">
          <div>
            <p className="text-xs text-ink-muted">Avg task duration</p>
            <p className="text-lg font-semibold">{a.avg_task_duration_days} days</p>
          </div>
          <div>
            <p className="text-xs text-ink-muted">Upcoming milestones</p>
            <p className="text-lg font-semibold">{a.upcoming_milestones}</p>
          </div>
          <div>
            <p className="text-xs text-ink-muted">Completed projects</p>
            <p className="text-lg font-semibold">{a.completed_projects}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, alert }: {
  icon: typeof Folders; label: string; value: string | number; sub?: string; alert?: boolean;
}) {
  return (
    <div className={`ec-card p-3 ${alert ? 'ring-2 ring-rose-200 dark:ring-rose-900/40' : ''}`}>
      <div className="flex items-center gap-2">
        <Icon size={16} className={alert ? 'text-rose-600' : 'text-brand-600'} />
        <p className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</p>
      </div>
      <p className={`mt-1 text-2xl font-semibold ${alert ? 'text-rose-600' : ''}`}>{value}</p>
      {sub && <p className="text-xs text-ink-muted">{sub}</p>}
    </div>
  );
}
