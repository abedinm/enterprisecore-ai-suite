import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Calendar, AlertCircle, Flag } from 'lucide-react';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import { PRIORITY_COLORS } from './types';

type SchedulerData = {
  today: string;
  horizon_days: number;
  tasks: { id: string; title: string; due_date: string; priority: string; status: string; project_id: string | null; assignee_id: string | null }[];
  milestones: { id: string; title: string; due_date: string; status: string; project_id: string; progress: number }[];
  overdue: { id: string; title: string; due_date: string; days_overdue: number; priority: string; project_id: string | null; assignee_id: string | null }[];
};

export function SchedulerTab() {
  const [horizon, setHorizon] = useState(30);

  const data = useQuery({
    queryKey: ['projects', 'scheduler', horizon],
    queryFn: async () => (await api.get<SchedulerData>('/projects/scheduler/upcoming', { params: { days: horizon } })).data,
  });

  const byDate = useMemo(() => {
    const map: Record<string, { tasks: any[]; milestones: any[] }> = {};
    (data.data?.tasks ?? []).forEach((t) => {
      const key = t.due_date;
      if (!map[key]) map[key] = { tasks: [], milestones: [] };
      map[key].tasks.push(t);
    });
    (data.data?.milestones ?? []).forEach((m) => {
      const key = m.due_date;
      if (!map[key]) map[key] = { tasks: [], milestones: [] };
      map[key].milestones.push(m);
    });
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [data.data]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Task Scheduler</p>
          <p className="text-sm text-ink-muted">Upcoming deadlines and overdue items, grouped by due date.</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Horizon (days)</label>
            <select className="ec-input" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
            </select>
          </div>
        </div>
      </div>

      {(data.data?.overdue.length ?? 0) > 0 && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-900/20 p-4">
          <div className="mb-3 flex items-center gap-2 text-rose-700 dark:text-rose-300">
            <AlertCircle size={18} />
            <p className="font-semibold">{data.data?.overdue.length} overdue task{(data.data?.overdue.length ?? 0) === 1 ? '' : 's'}</p>
          </div>
          <div className="space-y-2">
            {data.data?.overdue.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg bg-surface-elevated p-3">
                <div>
                  <p className="text-sm font-medium">{t.title}</p>
                  <p className="text-xs text-ink-muted">Due {formatDate(t.due_date)} — {t.days_overdue} day{t.days_overdue === 1 ? '' : 's'} overdue</p>
                </div>
                <span className={PRIORITY_COLORS[t.priority] ?? 'ec-badge'}>{t.priority}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="ec-card p-3"><p className="text-xs text-ink-muted">Upcoming tasks</p><p className="text-2xl font-semibold">{data.data?.tasks.length ?? 0}</p></div>
        <div className="ec-card p-3"><p className="text-xs text-ink-muted">Upcoming milestones</p><p className="text-2xl font-semibold">{data.data?.milestones.length ?? 0}</p></div>
        <div className="ec-card p-3"><p className="text-xs text-ink-muted">Overdue</p><p className="text-2xl font-semibold text-rose-600">{data.data?.overdue.length ?? 0}</p></div>
      </div>

      <div className="ec-card overflow-hidden">
        <div className="border-b border-border bg-surface-muted px-3 py-2 text-sm font-semibold">Schedule — next {horizon} days</div>
        <div className="divide-y divide-border/60">
          {byDate.length === 0 && <p className="p-6 text-center text-sm text-ink-muted">No tasks or milestones in the selected window.</p>}
          {byDate.map(([date, group]) => (
            <div key={date} className="p-3">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Calendar size={14} className="text-brand-600" />
                {formatDate(date)}
              </div>
              <div className="space-y-1.5 pl-5">
                {group.milestones.map((m) => (
                  <div key={m.id} className="flex items-center gap-2 rounded-lg bg-rose-50 dark:bg-rose-900/20 px-3 py-2">
                    <Flag size={14} className="text-rose-600" />
                    <div className="flex-1">
                      <p className="text-sm font-medium">{m.title}</p>
                      <p className="text-xs text-ink-muted">Milestone · {m.progress}% complete</p>
                    </div>
                    <span className="ec-badge bg-rose-100 text-rose-700">{m.status}</span>
                  </div>
                ))}
                {group.tasks.map((t) => (
                  <div key={t.id} className="flex items-center gap-2 rounded-lg bg-surface-muted px-3 py-2">
                    <div className="flex-1">
                      <p className="text-sm font-medium">{t.title}</p>
                      <p className="text-xs text-ink-muted">Status: {t.status}</p>
                    </div>
                    <span className={PRIORITY_COLORS[t.priority] ?? 'ec-badge'}>{t.priority}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
