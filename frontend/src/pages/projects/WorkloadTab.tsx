import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, CartesianGrid } from 'recharts';
import { api } from '../../lib/api';
import { Project } from './types';

type WorkloadItem = {
  user_id: string | null;
  name: string;
  total_tasks: number;
  in_progress: number;
  todo: number;
  done: number;
  overdue: number;
  estimated_hours: number;
  actual_hours: number;
  high_priority: number;
};

export function WorkloadTab() {
  const [projectId, setProjectId] = useState<string>('');

  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });

  const data = useQuery({
    queryKey: ['projects', 'workload', projectId],
    queryFn: async () => (await api.get<{ items: WorkloadItem[] }>('/projects/workload', {
      params: projectId ? { project_id: projectId } : {},
    })).data,
  });

  const items = data.data?.items ?? [];
  const chartData = items.map((i) => ({
    name: i.name,
    todo: i.todo, in_progress: i.in_progress, done: i.done, overdue: i.overdue,
  }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Team Workload</p>
          <p className="text-sm text-ink-muted">Current task distribution by assignee.</p>
        </div>
        <div>
          <label className="ec-label">Project filter</label>
          <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">All projects</option>
            {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      <div className="ec-card p-4">
        <p className="mb-3 text-sm font-semibold">Tasks per assignee</p>
        {chartData.length > 0 ? (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'rgb(var(--color-surface-elevated))', border: '1px solid rgb(var(--color-border))' }} />
                <Legend />
                <Bar dataKey="todo" stackId="a" fill="#60a5fa" name="To Do" />
                <Bar dataKey="in_progress" stackId="a" fill="#fbbf24" name="In Progress" />
                <Bar dataKey="done" stackId="a" fill="#10b981" name="Done" />
                <Bar dataKey="overdue" stackId="b" fill="#f43f5e" name="Overdue" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="py-8 text-center text-ink-muted">No workload data yet.</p>
        )}
      </div>

      <div className="ec-card overflow-x-auto">
        <table className="ec-table">
          <thead>
            <tr><th>Assignee</th><th>Total</th><th>To Do</th><th>In Progress</th><th>Done</th><th>Overdue</th><th>Estimated</th><th>Actual</th><th>Load</th></tr>
          </thead>
          <tbody>
            {items.length ? items.map((i) => {
              const load = Math.min(100, Math.round((i.in_progress + i.todo) * 12.5));
              const loadColor = load > 80 ? 'bg-rose-600' : load > 50 ? 'bg-amber-500' : 'bg-emerald-500';
              return (
                <tr key={(i.user_id ?? '_unassigned')}>
                  <td className="font-medium">{i.name}</td>
                  <td>{i.total_tasks}</td>
                  <td>{i.todo}</td>
                  <td>{i.in_progress}</td>
                  <td>{i.done}</td>
                  <td className={i.overdue > 0 ? 'text-rose-600 font-semibold' : ''}>{i.overdue}</td>
                  <td>{i.estimated_hours.toFixed(1)}h</td>
                  <td>{i.actual_hours.toFixed(1)}h</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded-full bg-surface-muted">
                        <div className={`h-2 rounded-full ${loadColor}`} style={{ width: `${load}%` }} />
                      </div>
                      <span className="text-xs">{load}%</span>
                    </div>
                  </td>
                </tr>
              );
            }) : <tr><td colSpan={9} className="py-10 text-center text-ink-muted">No workload to show.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
