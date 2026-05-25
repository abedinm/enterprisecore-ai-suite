import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Building2, HardHat, MapPin, Plus, X } from 'lucide-react';
import {
  constructionApi,
  PROJECT_TYPE_OPTIONS,
  formatMoney,
  shortDate,
  type ConstructionProject,
  type ConstructionProjectInput,
  type ProjectType,
} from '../../lib/construction';

function statusBadge(status: string): string {
  const s = status.toLowerCase();
  if (s.includes('complete') || s.includes('closed') || s.includes('done')) return 'ec-badge-green';
  if (s.includes('hold') || s.includes('paused')) return 'ec-badge-amber';
  if (s.includes('cancel')) return 'ec-badge-rose';
  return 'ec-badge-blue';
}

function typeBadge(t: ProjectType): string {
  switch (t) {
    case 'residential': return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300';
    case 'commercial': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
    case 'industrial': return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300';
    case 'infrastructure': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300';
  }
}

const EMPTY: ConstructionProjectInput = {
  name: '',
  client_name: '',
  location: '',
  project_type: 'commercial',
  contract_value: '0',
  currency: 'USD',
  start_date: '',
  expected_end_date: '',
  actual_end_date: null,
  status: 'planning',
  description: '',
};

export function ConstructionProjectsList() {
  const listQ = useQuery({
    queryKey: ['construction', 'projects'],
    queryFn: () => constructionApi.listProjects(),
  });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ConstructionProject | null>(null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Module workspace</p>
          <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
            <HardHat className="text-brand-600" size={26} />
            Construction Projects
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            All active construction projects. Click a project to open its workspace —
            risks, schedule, milestones, variations, contracts, and more.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => setCreating(true)}
        >
          <Plus size={14} /> New project
        </button>
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading projects…</p>}

      {listQ.data && listQ.data.length === 0 && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <HardHat size={22} />
          </div>
          <div>
            <h2 className="text-lg font-semibold">No construction projects yet</h2>
            <p className="mt-1 max-w-xl text-sm text-ink-muted">
              Start by creating your first project. You can then add risks, schedule,
              milestones, permits, contracts, and the full suite of construction
              management tools.
            </p>
          </div>
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> Create your first project
          </button>
        </div>
      )}

      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {listQ.data.map((p) => (
            <ProjectCard key={p.id} project={p} onEdit={() => setEditing(p)} />
          ))}
        </div>
      )}

      {(creating || editing) && (
        <ProjectEditorModal
          project={editing ?? null}
          isNew={creating}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function ProjectCard({
  project,
  onEdit,
}: {
  project: ConstructionProject;
  onEdit: () => void;
}) {
  const dashboardQ = useQuery({
    queryKey: ['construction', 'dashboard', project.id],
    queryFn: () => constructionApi.getDashboard(project.id),
    staleTime: 60_000,
    retry: 0,
  });

  const progress = dashboardQ.data?.schedule_progress_percent ?? 0;

  return (
    <Link
      to={`/construction/projects/${project.id}`}
      className="ec-card flex flex-col gap-3 p-4 transition hover:border-brand-500/40 hover:bg-surface-muted/30"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-base font-semibold">{project.name}</p>
          <p className="mt-0.5 truncate text-xs text-ink-muted">{project.client_name}</p>
        </div>
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
          <Building2 size={16} />
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`ec-badge ${typeBadge(project.project_type)}`}>
          {PROJECT_TYPE_OPTIONS.find((o) => o.value === project.project_type)?.label}
        </span>
        <span className={statusBadge(project.status)}>{project.status}</span>
        {project.location && (
          <span className="inline-flex items-center gap-1 text-ink-muted">
            <MapPin size={11} /> {project.location}
          </span>
        )}
      </div>

      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Contract value</p>
          <p className="text-sm font-semibold">
            {formatMoney(project.contract_value, project.currency)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Due</p>
          <p className="text-xs">{shortDate(project.expected_end_date)}</p>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-ink-muted">Schedule progress</span>
          <span className="font-mono">{progress}%</span>
        </div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-muted">
          <div
            className="h-full bg-brand-600 transition-all"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      </div>

      <div className="mt-1 flex items-center justify-end">
        <button
          type="button"
          className="ec-btn-ghost text-xs"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onEdit();
          }}
        >
          Edit details
        </button>
      </div>
    </Link>
  );
}

/* -------------------------------------------------------------------------- */

function ProjectEditorModal({
  project,
  isNew,
  onClose,
}: {
  project: ConstructionProject | null;
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ConstructionProjectInput>(
    project
      ? {
          name: project.name,
          client_name: project.client_name,
          location: project.location,
          project_type: project.project_type,
          contract_value: project.contract_value,
          currency: project.currency,
          start_date: project.start_date,
          expected_end_date: project.expected_end_date,
          actual_end_date: project.actual_end_date,
          status: project.status,
          description: project.description ?? '',
        }
      : EMPTY,
  );

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createProject(form);
      if (!project) throw new Error('No project to update');
      return constructionApi.updateProject(project.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'projects'] });
      toast.success(isNew ? 'Project created' : 'Project saved');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })
        .response?.data?.detail ?? (err as Error).message ?? 'Failed to save';
      toast.error(typeof detail === 'string' ? detail : 'Failed to save');
    },
  });

  const remove = useMutation({
    mutationFn: () => {
      if (!project) throw new Error('No project');
      return constructionApi.deleteProject(project.id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'projects'] });
      toast.success('Project removed');
      onClose();
    },
  });

  const update = <K extends keyof ConstructionProjectInput>(
    key: K,
    value: ConstructionProjectInput[K],
  ) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-ink-subtle">
              {isNew ? 'New project' : 'Edit project'}
            </p>
            <p className="font-semibold">{form.name || 'Untitled project'}</p>
          </div>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <label className="ec-label">Project name</label>
              <input
                required
                className="ec-input"
                value={form.name}
                onChange={(e) => update('name', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Client</label>
              <input
                required
                className="ec-input"
                value={form.client_name}
                onChange={(e) => update('client_name', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Location</label>
              <input
                className="ec-input"
                value={form.location}
                onChange={(e) => update('location', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Type</label>
              <select
                className="ec-input"
                value={form.project_type}
                onChange={(e) => update('project_type', e.target.value as ProjectType)}
              >
                {PROJECT_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="ec-label">Status</label>
              <input
                className="ec-input"
                value={form.status}
                onChange={(e) => update('status', e.target.value)}
                placeholder="planning / active / on-hold / complete"
              />
            </div>
            <div>
              <label className="ec-label">Contract value</label>
              <input
                className="ec-input"
                inputMode="decimal"
                value={form.contract_value}
                onChange={(e) => update('contract_value', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Currency</label>
              <input
                className="ec-input"
                value={form.currency}
                onChange={(e) => update('currency', e.target.value.toUpperCase())}
                maxLength={3}
              />
            </div>
            <div>
              <label className="ec-label">Start date</label>
              <input
                type="date"
                className="ec-input"
                value={form.start_date}
                onChange={(e) => update('start_date', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Expected end date</label>
              <input
                type="date"
                className="ec-input"
                value={form.expected_end_date}
                onChange={(e) => update('expected_end_date', e.target.value)}
              />
            </div>
            <div className="md:col-span-2">
              <label className="ec-label">Description</label>
              <textarea
                className="ec-input min-h-[80px]"
                value={form.description ?? ''}
                onChange={(e) => update('description', e.target.value)}
              />
            </div>
          </div>
        </form>
        <div className="flex justify-between gap-2 border-t border-border px-5 py-3">
          <div>
            {!isNew && project && (
              <button
                type="button"
                className="ec-btn-ghost text-rose-600"
                onClick={() => {
                  if (confirm(`Delete project ${project.name}?`)) remove.mutate();
                }}
              >
                Delete project
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="ec-btn-primary"
              disabled={save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? 'Saving…' : isNew ? 'Create project' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
