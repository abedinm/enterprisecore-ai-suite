import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, Edit3, X, Flag } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { formatDate } from '../../lib/utils';
import { Milestone, Project } from './types';

const STATUSES = ['open', 'in_progress', 'completed', 'cancelled'] as const;
const STATUS_BADGE: Record<string, string> = {
  open: 'ec-badge-blue', in_progress: 'ec-badge-amber',
  completed: 'ec-badge-green', cancelled: 'ec-badge-rose',
};

export function MilestonesTab() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [projectFilter, setProjectFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Milestone | null>(null);

  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });
  const milestones = useQuery({
    queryKey: ['projects', 'milestones', projectFilter, statusFilter],
    queryFn: async () => (await api.get<Milestone[]>('/projects/milestones', {
      params: {
        ...(projectFilter ? { project_id: projectFilter } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
      },
    })).data,
  });

  const remove = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/milestones/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects', 'milestones'] }),
  });

  const counts = STATUSES.reduce<Record<string, number>>((acc, s) => {
    acc[s] = (milestones.data ?? []).filter((m) => m.status === s).length;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Milestone Tracker</p>
          <p className="text-sm text-ink-muted">{milestones.data?.length ?? 0} milestones across projects.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="ec-label">Project</label>
            <select className="ec-input" value={projectFilter} onChange={(e) => setProjectFilter(e.target.value)}>
              <option value="">All</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="ec-label">Status</label>
            <select className="ec-input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}><Plus size={16} /> New milestone</button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4">
        {STATUSES.map((s) => (
          <div key={s} className="ec-card p-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-muted">{s}</p>
            <p className="text-2xl font-semibold">{counts[s]}</p>
          </div>
        ))}
      </div>

      {(showForm || editing) && (
        <MilestoneForm
          editing={editing}
          projects={projects.data ?? []}
          defaultProjectId={projectFilter}
          onSaved={() => { setShowForm(false); setEditing(null); qc.invalidateQueries({ queryKey: ['projects', 'milestones'] }); }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="space-y-2">
        {milestones.data?.length ? milestones.data.map((m) => (
          <div key={m.id} className="ec-card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex flex-1 items-start gap-3">
                <Flag size={20} className="mt-0.5 shrink-0 text-rose-600" />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-base font-semibold">{m.title}</h4>
                    <span className={STATUS_BADGE[m.status] ?? 'ec-badge'}>{m.status}</span>
                  </div>
                  {m.description && <p className="mt-1 text-sm text-ink-muted">{m.description}</p>}
                  <p className="mt-1 text-xs text-ink-muted">
                    Project: {projects.data?.find((p) => p.id === m.project_id)?.name ?? '—'}
                    {' · '}Due: {m.due_date ? formatDate(m.due_date) : '—'}
                  </p>
                  <div className="mt-2">
                    <div className="h-2 w-full rounded-full bg-surface-muted">
                      <div className="h-2 rounded-full bg-brand-600 transition-all" style={{ width: `${m.progress}%` }} />
                    </div>
                    <p className="mt-1 text-xs text-ink-muted">{m.progress}% complete</p>
                  </div>
                </div>
              </div>
              <div className="flex gap-1">
                <button className="ec-btn-ghost" onClick={() => setEditing(m)}><Edit3 size={14} /></button>
                <button className="ec-btn-ghost text-rose-600" onClick={() => { if (confirm('Delete milestone?')) remove.mutate(m.id); }}><Trash2 size={14} /></button>
              </div>
            </div>
          </div>
        )) : <div className="ec-card p-10 text-center text-ink-muted">No milestones — create one to track major deliverables.</div>}
      </div>
    </div>
  );
}

function MilestoneForm({ editing, projects, defaultProjectId, onSaved, onCancel }: {
  editing: Milestone | null; projects: Project[]; defaultProjectId: string;
  onSaved: () => void; onCancel: () => void;
}) {
  const [title, setTitle] = useState(editing?.title ?? '');
  const [description, setDescription] = useState(editing?.description ?? '');
  const [projectId, setProjectId] = useState(editing?.project_id ?? defaultProjectId ?? '');
  const [status, setStatus] = useState(editing?.status ?? 'open');
  const [dueDate, setDueDate] = useState(editing?.due_date ?? '');
  const [progress, setProgress] = useState(editing?.progress ?? 0);

  const save = useMutation({
    mutationFn: async () => {
      const body = { project_id: projectId, title, description, due_date: dueDate || null, status, progress };
      if (editing) return (await api.patch(`/projects/milestones/${editing.id}`, body)).data;
      return (await api.post('/projects/milestones', body)).data;
    },
    onSuccess: () => { toast.success('Saved'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit milestone' : 'New milestone'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2"><label className="ec-label">Title</label><input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="ec-label">Project</label>
          <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="md:col-span-3"><label className="ec-label">Description</label><textarea className="ec-input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
        <div><label className="ec-label">Due date</label><input type="date" className="ec-input" value={dueDate ?? ''} onChange={(e) => setDueDate(e.target.value)} /></div>
        <div><label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="ec-label">Progress %</label><input type="range" min={0} max={100} value={progress} onChange={(e) => setProgress(Number(e.target.value))} className="w-full" /><p className="text-xs">{progress}%</p></div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!title || !projectId || save.isPending} onClick={() => save.mutate()}>{editing ? 'Save' : 'Create'}</button>
      </div>
    </div>
  );
}
