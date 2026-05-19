import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, Trash2, X, GripVertical, Edit3 } from 'lucide-react';
import toast from 'react-hot-toast';
import { api } from '../../lib/api';
import { PRIORITIES, PRIORITY_COLORS, Project, Task, STATUS_COLUMNS } from './types';

type KanbanData = {
  columns: { status: string; tasks: any[] }[];
};

const COLUMN_LABELS: Record<string, string> = {
  backlog: 'Backlog', todo: 'To Do', in_progress: 'In Progress',
  in_review: 'Review', done: 'Done',
};

export function KanbanTab() {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);

  const projects = useQuery({
    queryKey: ['projects', 'list'],
    queryFn: async () => (await api.get<Project[]>('/projects/projects')).data,
  });

  const board = useQuery({
    queryKey: ['projects', 'kanban', projectId],
    queryFn: async () => (await api.get<KanbanData>('/projects/tasks/kanban', {
      params: projectId ? { project_id: projectId } : {},
    })).data,
  });

  const updateStatus = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      (await api.post(`/projects/tasks/${id}/status`, { status })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects', 'kanban'] }),
  });

  const removeTask = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/projects/tasks/${id}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects', 'kanban'] });
      toast.success('Task deleted');
    },
  });

  function onDragStart(e: React.DragEvent, taskId: string) {
    e.dataTransfer.setData('text/plain', taskId);
  }

  function onDrop(e: React.DragEvent, status: string) {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain');
    if (id) updateStatus.mutate({ id, status });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-muted">Kanban Board</p>
          <p className="text-sm text-ink-muted">Drag tasks between columns to update status.</p>
        </div>
        <div className="flex items-end gap-2">
          <div>
            <label className="ec-label">Project</label>
            <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">All projects</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <button className="ec-btn-primary" onClick={() => { setEditing(null); setShowForm(true); }}>
            <Plus size={16} /> New task
          </button>
        </div>
      </div>

      {(showForm || editing) && (
        <TaskForm
          editing={editing}
          projects={projects.data ?? []}
          defaultProjectId={projectId}
          onSaved={() => {
            setShowForm(false); setEditing(null);
            qc.invalidateQueries({ queryKey: ['projects', 'kanban'] });
          }}
          onCancel={() => { setShowForm(false); setEditing(null); }}
        />
      )}

      <div className="grid grid-flow-col gap-3 overflow-x-auto pb-2" style={{ gridAutoColumns: 'minmax(260px,1fr)' }}>
        {STATUS_COLUMNS.map((status) => {
          const tasks = board.data?.columns.find((c) => c.status === status)?.tasks ?? [];
          return (
            <div
              key={status}
              className="rounded-xl border border-border bg-surface-muted p-2"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDrop(e, status)}
            >
              <div className="mb-2 flex items-center justify-between px-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{COLUMN_LABELS[status]}</p>
                <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-xs text-ink-muted">{tasks.length}</span>
              </div>
              <div className="space-y-2 min-h-[200px]">
                {tasks.map((t: any) => (
                  <div
                    key={t.id}
                    draggable
                    onDragStart={(e) => onDragStart(e, t.id)}
                    className="ec-card group p-3 cursor-grab"
                  >
                    <div className="flex items-start gap-1">
                      <GripVertical size={14} className="text-ink-subtle mt-0.5" />
                      <div className="flex-1">
                        <p className="text-sm font-medium leading-tight">{t.title}</p>
                        {t.description && <p className="mt-1 text-xs text-ink-muted line-clamp-2">{t.description}</p>}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span className={PRIORITY_COLORS[t.priority] ?? 'ec-badge'}>{t.priority}</span>
                          {t.due_date && <span className="text-xs text-ink-muted">{t.due_date}</span>}
                          {t.story_points > 0 && <span className="ec-badge bg-purple-100 text-purple-700">{t.story_points}pt</span>}
                        </div>
                      </div>
                      <div className="opacity-0 group-hover:opacity-100 flex flex-col">
                        <button className="ec-btn-ghost !p-1" onClick={() => setEditing(t)}><Edit3 size={12} /></button>
                        <button className="ec-btn-ghost !p-1 text-rose-600" onClick={() => { if (confirm('Delete task?')) removeTask.mutate(t.id); }}><Trash2 size={12} /></button>
                      </div>
                    </div>
                  </div>
                ))}
                {tasks.length === 0 && <p className="px-2 py-6 text-center text-xs text-ink-subtle">Drop tasks here</p>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TaskForm({ editing, projects, defaultProjectId, onSaved, onCancel }: {
  editing: Task | null;
  projects: Project[];
  defaultProjectId: string;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(editing?.title ?? '');
  const [description, setDescription] = useState(editing?.description ?? '');
  const [projectId, setProjectId] = useState(editing?.project_id ?? defaultProjectId);
  const [status, setStatus] = useState(editing?.status ?? 'todo');
  const [priority, setPriority] = useState(editing?.priority ?? 'medium');
  const [dueDate, setDueDate] = useState(editing?.due_date ?? '');
  const [startDate, setStartDate] = useState(editing?.start_date ?? '');
  const [estimatedHours, setEstimatedHours] = useState(editing?.estimated_hours ?? '0');
  const [storyPoints, setStoryPoints] = useState(editing?.story_points ?? 0);
  const [tags, setTags] = useState(editing?.tags ?? '');

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        title, description, project_id: projectId || null,
        sprint_id: editing?.sprint_id ?? null,
        assignee_id: editing?.assignee_id ?? null,
        status, priority,
        due_date: dueDate || null,
        start_date: startDate || null,
        estimated_hours: estimatedHours || '0',
        actual_hours: editing?.actual_hours ?? '0',
        story_points: storyPoints,
        position: editing?.position ?? 0,
        tags,
      };
      if (editing) return (await api.patch(`/projects/tasks/${editing.id}`, body)).data;
      return (await api.post('/projects/tasks', body)).data;
    },
    onSuccess: () => { toast.success(editing ? 'Task updated' : 'Task created'); onSaved(); },
    onError: () => toast.error('Save failed'),
  });

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold">{editing ? 'Edit task' : 'New task'}</h3>
        <button className="ec-btn-ghost" onClick={onCancel}><X size={16} /></button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="md:col-span-2">
          <label className="ec-label">Title</label>
          <input className="ec-input" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className="ec-label">Project</label>
          <select className="ec-input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">No project</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div className="md:col-span-3">
          <label className="ec-label">Description</label>
          <textarea className="ec-input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div>
          <label className="ec-label">Status</label>
          <select className="ec-input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_COLUMNS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="ec-label">Priority</label>
          <select className="ec-input" value={priority} onChange={(e) => setPriority(e.target.value)}>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label className="ec-label">Story points</label>
          <input type="number" className="ec-input" min={0} value={storyPoints} onChange={(e) => setStoryPoints(Number(e.target.value))} />
        </div>
        <div>
          <label className="ec-label">Start date</label>
          <input type="date" className="ec-input" value={startDate ?? ''} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div>
          <label className="ec-label">Due date</label>
          <input type="date" className="ec-input" value={dueDate ?? ''} onChange={(e) => setDueDate(e.target.value)} />
        </div>
        <div>
          <label className="ec-label">Estimated hours</label>
          <input type="number" className="ec-input" step="0.25" value={estimatedHours} onChange={(e) => setEstimatedHours(e.target.value)} />
        </div>
        <div className="md:col-span-3">
          <label className="ec-label">Tags (comma-separated)</label>
          <input className="ec-input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="frontend, urgent, ux" />
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="ec-btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="ec-btn-primary" disabled={!title || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : editing ? 'Save changes' : 'Create task'}
        </button>
      </div>
    </div>
  );
}
