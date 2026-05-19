import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Plus, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { Project } from './types';

type GanttData = {
  project: { id: string; name: string; start_date: string | null; end_date: string | null; color: string; progress: number };
  tasks: { id: string; title: string; status: string; start_date: string | null; due_date: string | null; priority: string; assignee_id: string | null; estimated_hours: number; actual_hours: number }[];
  milestones: { id: string; title: string; status: string; due_date: string | null; progress: number }[];
  dependencies: { id: string; task_id: string; depends_on_task_id: string; dep_type: string }[];
};

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

const STATUS_COLOR: Record<string, string> = {
  backlog: '#94a3b8', todo: '#60a5fa', in_progress: '#fbbf24',
  in_review: '#a78bfa', done: '#10b981',
};

export function GanttTab() {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState<string>('');
  const [showProjectForm, setShowProjectForm] = useState(false);

  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });

  const gantt = useQuery({
    queryKey: ['projects', 'gantt', projectId],
    queryFn: async () => projectId ? (await api.get<GanttData>(`/projects/projects/${projectId}/gantt`)).data : null,
    enabled: !!projectId,
  });

  const range = useMemo(() => {
    if (!gantt.data) return { start: new Date(), end: new Date(), days: 30 };
    const dates: Date[] = [];
    if (gantt.data.project.start_date) dates.push(new Date(gantt.data.project.start_date));
    if (gantt.data.project.end_date) dates.push(new Date(gantt.data.project.end_date));
    gantt.data.tasks.forEach((t) => {
      if (t.start_date) dates.push(new Date(t.start_date));
      if (t.due_date) dates.push(new Date(t.due_date));
    });
    gantt.data.milestones.forEach((m) => { if (m.due_date) dates.push(new Date(m.due_date)); });
    if (dates.length === 0) {
      const today = new Date();
      return { start: today, end: new Date(today.getTime() + 30 * 86400000), days: 30 };
    }
    const start = new Date(Math.min(...dates.map((d) => d.getTime())));
    const end = new Date(Math.max(...dates.map((d) => d.getTime())));
    start.setDate(start.getDate() - 2);
    end.setDate(end.getDate() + 2);
    return { start, end, days: Math.max(daysBetween(start, end), 14) };
  }, [gantt.data]);

  const today = new Date();
  const todayOffset = daysBetween(range.start, today);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Gantt Builder</p>
          <p className="text-sm text-ink-muted">Visualize task & milestone schedules across project timelines.</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Project</label>
            <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Select a project…</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => setShowProjectForm(true)}>
            <Plus size={16} /> New project
          </button>
        </div>
      </div>

      {showProjectForm && (
        <ProjectForm
          onSaved={() => {
            setShowProjectForm(false);
            qc.invalidateQueries({ queryKey: ['projects', 'list'] });
          }}
          onCancel={() => setShowProjectForm(false)}
        />
      )}

      {!projectId && (
        <div className="ec-card p-6 text-center text-sm text-ink-muted">
          Select a project to render its Gantt timeline. Tasks and milestones with dates appear as bars.
        </div>
      )}

      {projectId && gantt.data && (
        <div className="ec-card overflow-x-auto">
          <div className="min-w-[800px]">
            <div className="grid border-b border-border bg-surface-muted px-3 py-2 text-xs uppercase tracking-wider text-ink-muted" style={{ gridTemplateColumns: '200px 1fr' }}>
              <div>Item</div>
              <div className="relative h-4">
                {Array.from({ length: Math.min(range.days, 60) + 1 }).map((_, i) => {
                  if (i % 7 !== 0) return null;
                  const date = new Date(range.start.getTime() + i * 86400000);
                  return (
                    <span key={i} className="absolute -translate-x-1/2 text-[10px]" style={{ left: `${(i / range.days) * 100}%` }}>
                      {date.toISOString().slice(5, 10)}
                    </span>
                  );
                })}
              </div>
            </div>
            <div>
              {gantt.data.tasks.map((t) => {
                const s = t.start_date ? new Date(t.start_date) : null;
                const e = t.due_date ? new Date(t.due_date) : null;
                if (!s || !e) {
                  return (
                    <div key={t.id} className="grid items-center border-b border-border/60 px-3 py-2" style={{ gridTemplateColumns: '200px 1fr' }}>
                      <div className="truncate text-sm" title={t.title}>{t.title}</div>
                      <div className="text-xs text-ink-subtle">— missing dates —</div>
                    </div>
                  );
                }
                const offset = daysBetween(range.start, s);
                const length = Math.max(daysBetween(s, e), 1);
                return (
                  <div key={t.id} className="grid items-center border-b border-border/60 px-3 py-2" style={{ gridTemplateColumns: '200px 1fr' }}>
                    <div className="truncate pr-2 text-sm" title={t.title}>{t.title}</div>
                    <div className="relative h-6">
                      <div
                        className="absolute top-1 h-4 rounded text-[10px] text-white px-1.5 overflow-hidden whitespace-nowrap"
                        style={{
                          left: `${(offset / range.days) * 100}%`,
                          width: `${(length / range.days) * 100}%`,
                          background: STATUS_COLOR[t.status] ?? '#64748b',
                        }}
                        title={`${t.title} · ${s.toISOString().slice(0,10)} → ${e.toISOString().slice(0,10)}`}
                      >
                        {t.status}
                      </div>
                    </div>
                  </div>
                );
              })}
              {gantt.data.milestones.filter((m) => m.due_date).map((m) => {
                const d = new Date(m.due_date!);
                const offset = daysBetween(range.start, d);
                return (
                  <div key={m.id} className="grid items-center border-b border-border/60 px-3 py-2" style={{ gridTemplateColumns: '200px 1fr' }}>
                    <div className="truncate pr-2 text-sm">◇ {m.title}</div>
                    <div className="relative h-6">
                      <div
                        className="absolute top-0 h-6 w-3 rotate-45 bg-rose-500 shadow"
                        style={{ left: `${(offset / range.days) * 100}%` }}
                        title={`Milestone: ${m.title} · ${m.due_date}`}
                      />
                    </div>
                  </div>
                );
              })}
              {todayOffset >= 0 && todayOffset <= range.days && (
                <div className="relative">
                  <div className="absolute top-[-1000px] bottom-0 w-px bg-rose-400 z-10 pointer-events-none" style={{ left: `calc(200px + ${(todayOffset / range.days) * (100 - (200 / 1))}%)` }} />
                </div>
              )}
            </div>
          </div>
          <div className="border-t border-border bg-surface-muted px-3 py-2 text-xs text-ink-muted">
            Timeline: {range.start.toISOString().slice(0, 10)} → {new Date(range.start.getTime() + range.days * 86400000).toISOString().slice(0, 10)}
            · Tasks: {gantt.data.tasks.length} · Milestones: {gantt.data.milestones.length} · Dependencies: {gantt.data.dependencies.length}
          </div>
        </div>
      )}
    </div>
  );
}

function ProjectForm({ onSaved, onCancel }: { onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [startDate, setStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState(new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10));
  const [budget, setBudget] = useState('0');
  const [color, setColor] = useState('#4F46E5');

  const save = useMutation({
    mutationFn: async () => (await api.post('/projects/projects', {
      name, description, status: 'active', start_date: startDate, end_date: endDate,
      budget, color, progress: 0,
    })).data,
    onSuccess: () => { toast.success('Project created'); onSaved(); },
    onError: () => toast.error('Failed to create'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">New project</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Name</label><input className="ec-input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="ec-label">Color</label><input type="color" className="ec-input !h-10" value={color} onChange={(e) => setColor(e.target.value)} /></div>
        <div className="md:col-span-3"><label className="ec-label">Description</label><textarea className="ec-input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
        <div><label className="ec-label">Start</label><input type="date" className="ec-input" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></div>
        <div><label className="ec-label">End</label><input type="date" className="ec-input" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></div>
        <div><label className="ec-label">Budget</label><input type="number" className="ec-input" value={budget} step="any" onChange={(e) => setBudget(e.target.value)} /></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!name || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : 'Create'}
        </button>
      </div>
    </div>
  );
}
