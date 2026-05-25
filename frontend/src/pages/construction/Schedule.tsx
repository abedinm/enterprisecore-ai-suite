import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { CalendarClock, GitBranch, Plus, Trash2 } from 'lucide-react';
import { Modal, ModalHeader, ModalBody, ModalFooter, ModalClose } from '../../components/Modal';
import {
  constructionApi,
  shortDate,
  type ScheduleDependency,
  type ScheduleDependencyInput,
  type ScheduleTask,
  type ScheduleTaskInput,
} from '../../lib/construction';

const EMPTY_TASK: ScheduleTaskInput = {
  name: '',
  description: '',
  parent_task_id: null,
  start_date: new Date().toISOString().slice(0, 10),
  end_date: new Date().toISOString().slice(0, 10),
  duration_days: 1,
  assigned_to_id: null,
  progress_percent: 0,
  status: 'pending',
};

/** Days between two ISO date strings (inclusive of start). */
function daysBetween(startIso: string, endIso: string): number {
  const s = new Date(startIso).getTime();
  const e = new Date(endIso).getTime();
  return Math.max(0, Math.floor((e - s) / 86_400_000));
}

export function ConstructionSchedulePage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const tasksQ = useQuery({
    queryKey: ['construction', 'schedule-tasks', projectId],
    queryFn: () => constructionApi.listScheduleTasks(projectId),
    enabled: !!projectId,
  });
  const depsQ = useQuery({
    queryKey: ['construction', 'schedule-deps', projectId],
    queryFn: () => constructionApi.listScheduleDependencies(projectId),
    enabled: !!projectId,
  });

  const [editingTask, setEditingTask] = useState<ScheduleTask | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);
  const [creatingDep, setCreatingDep] = useState(false);

  const removeTask = useMutation({
    mutationFn: (id: string) => constructionApi.deleteScheduleTask(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'schedule-tasks', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'schedule-deps', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success('Task removed');
    },
  });
  const removeDep = useMutation({
    mutationFn: (id: string) => constructionApi.deleteScheduleDependency(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'schedule-deps', projectId] });
      toast.success('Dependency removed');
    },
  });

  const { tasks, span, taskIndex } = useMemo(() => {
    const list = (tasksQ.data ?? []).slice().sort(
      (a, b) => new Date(a.start_date).getTime() - new Date(b.start_date).getTime(),
    );
    if (list.length === 0) {
      return { tasks: list, span: 0, taskIndex: new Map<string, number>() };
    }
    const minStart = Math.min(...list.map((t) => new Date(t.start_date).getTime()));
    const maxEnd = Math.max(...list.map((t) => new Date(t.end_date).getTime()));
    const totalDays = Math.max(1, Math.ceil((maxEnd - minStart) / 86_400_000) + 1);
    const idx = new Map<string, number>();
    list.forEach((t, i) => idx.set(t.id, i));
    return { tasks: list, span: totalDays, taskIndex: idx, minStart };
  }, [tasksQ.data]);

  const minStartMs = useMemo(() => {
    if (!tasks.length) return Date.now();
    return Math.min(...tasks.map((t) => new Date(t.start_date).getTime()));
  }, [tasks]);

  function offsetDays(iso: string): number {
    return Math.floor((new Date(iso).getTime() - minStartMs) / 86_400_000);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <CalendarClock size={18} className="text-brand-600" /> Schedule
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Gantt view of all scheduled tasks. Dependencies (FS by default) are drawn between bars.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="ec-btn-secondary"
            disabled={tasks.length < 2}
            onClick={() => setCreatingDep(true)}
          >
            <GitBranch size={14} /> Link tasks
          </button>
          <button type="button" className="ec-btn-primary" onClick={() => setCreatingTask(true)}>
            <Plus size={14} /> New task
          </button>
        </div>
      </div>

      {tasksQ.isLoading && <p className="text-sm text-ink-muted">Loading schedule…</p>}

      {tasks.length === 0 && !tasksQ.isLoading && (
        <div className="ec-card flex flex-col items-start gap-3 p-6">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
            <CalendarClock size={22} />
          </div>
          <div>
            <h3 className="font-semibold">No schedule tasks yet</h3>
            <p className="mt-1 text-sm text-ink-muted">
              Add tasks to build the project schedule. Once you have multiple tasks you can
              create finish-to-start dependencies between them.
            </p>
          </div>
          <button type="button" className="ec-btn-primary" onClick={() => setCreatingTask(true)}>
            <Plus size={14} /> Create first task
          </button>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="ec-card overflow-hidden">
          <div className="border-b border-border bg-surface-muted/30 px-3 py-2 text-xs text-ink-muted">
            <span className="font-mono">{shortDate(tasks[0].start_date)}</span>
            <span className="px-2">→</span>
            <span className="font-mono">
              {shortDate(
                new Date(minStartMs + span * 86_400_000 - 86_400_000)
                  .toISOString()
                  .slice(0, 10),
              )}
            </span>
            <span className="ml-3 text-ink-subtle">{span} day window</span>
          </div>

          {/* Gantt grid */}
          <div className="overflow-x-auto">
            <div
              className="relative grid"
              style={{
                gridTemplateColumns: `220px repeat(${span}, 14px)`,
              }}
            >
              {/* Header row */}
              <div className="sticky left-0 z-10 bg-surface-elevated px-3 py-2 text-xs font-semibold text-ink-muted">
                Task
              </div>
              {Array.from({ length: span }, (_, i) => (
                <div
                  key={`hdr-${i}`}
                  className="border-l border-border/40 py-2 text-center text-[9px] text-ink-subtle"
                >
                  {i % 7 === 0 ? i + 1 : ''}
                </div>
              ))}

              {/* Task rows */}
              {tasks.map((t) => {
                const startOff = offsetDays(t.start_date);
                const duration = Math.max(1, daysBetween(t.start_date, t.end_date) + 1);
                return (
                  <div
                    key={`row-${t.id}`}
                    className="contents"
                  >
                    <div
                      role="button"
                      tabIndex={0}
                      aria-label={`${t.name}, from ${shortDate(t.start_date)} to ${shortDate(t.end_date)}, ${t.progress_percent}% complete. Press Enter to edit.`}
                      className="sticky left-0 z-10 cursor-pointer border-t border-border/40 bg-surface-elevated px-3 py-2 text-xs hover:bg-surface-muted/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                      onClick={() => setEditingTask(t)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setEditingTask(t);
                        } else if (e.key === 'ArrowDown') {
                          e.preventDefault();
                          const next = tasks[tasks.indexOf(t) + 1];
                          if (next) {
                            const el = document.querySelector<HTMLElement>(
                              `[data-gantt-task="${next.id}"]`,
                            );
                            el?.focus();
                          }
                        } else if (e.key === 'ArrowUp') {
                          e.preventDefault();
                          const prev = tasks[tasks.indexOf(t) - 1];
                          if (prev) {
                            const el = document.querySelector<HTMLElement>(
                              `[data-gantt-task="${prev.id}"]`,
                            );
                            el?.focus();
                          }
                        }
                      }}
                      data-gantt-task={t.id}
                    >
                      <p className="truncate text-sm font-medium">{t.name}</p>
                      <p className="truncate text-[10px] text-ink-muted">
                        {shortDate(t.start_date)} → {shortDate(t.end_date)} · {t.progress_percent}%
                      </p>
                    </div>
                    {Array.from({ length: span }, (_, i) => (
                      <div
                        key={`cell-${t.id}-${i}`}
                        className="relative border-t border-l border-border/30 py-3"
                      >
                        {i === startOff && (
                          <div
                            className="absolute inset-y-1 left-0 overflow-hidden rounded-md bg-brand-600/30 ring-1 ring-brand-600/40"
                            style={{ width: `${duration * 14}px` }}
                            title={`${t.name}: ${shortDate(t.start_date)} → ${shortDate(t.end_date)} (${t.progress_percent}%)`}
                          >
                            <div
                              className="h-full bg-brand-600"
                              style={{ width: `${Math.min(100, Math.max(0, t.progress_percent))}%` }}
                            />
                            <span className="absolute inset-0 flex items-center px-1.5 text-[10px] font-medium text-white drop-shadow">
                              {duration * 14 > 50 ? t.name : ''}
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}

              {/* Dependency arrows — drawn as SVG over the grid */}
              <DependencyArrows
                deps={depsQ.data ?? []}
                tasks={tasks}
                taskIndex={taskIndex}
                offsetDays={offsetDays}
                rowHeight={36}
                colWidth={14}
                labelWidth={220}
                headerHeight={31}
                span={span}
              />
            </div>
          </div>
        </div>
      )}

      {/* Flat task table for editing */}
      {tasks.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="px-3 py-2">Task</th>
                <th className="px-3 py-2">Start</th>
                <th className="px-3 py-2">End</th>
                <th className="px-3 py-2">Duration</th>
                <th className="px-3 py-2">Progress</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr
                  key={t.id}
                  className="cursor-pointer border-b border-border/60 last:border-b-0 hover:bg-surface-muted/30"
                  onClick={() => setEditingTask(t)}
                >
                  <td className="px-3 py-2 font-medium">{t.name}</td>
                  <td className="px-3 py-2 text-ink-muted">{shortDate(t.start_date)}</td>
                  <td className="px-3 py-2 text-ink-muted">{shortDate(t.end_date)}</td>
                  <td className="px-3 py-2 font-mono text-ink-muted">{t.duration_days}d</td>
                  <td className="px-3 py-2 font-mono">{t.progress_percent}%</td>
                  <td className="px-3 py-2 capitalize text-ink-muted">{t.status}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete task "${t.name}"?`)) removeTask.mutate(t.id);
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Dependencies list */}
      {(depsQ.data ?? []).length > 0 && (
        <div className="ec-card overflow-x-auto">
          <div className="border-b border-border px-4 py-3">
            <p className="font-semibold flex items-center gap-2">
              <GitBranch size={16} className="text-brand-600" /> Dependencies
            </p>
          </div>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-surface-muted/40 text-left text-xs uppercase tracking-wider text-ink-subtle">
                <th className="px-3 py-2">Predecessor</th>
                <th className="px-3 py-2">Successor</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Lag</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {(depsQ.data ?? []).map((d) => {
                const pre = tasks.find((t) => t.id === d.predecessor_id);
                const succ = tasks.find((t) => t.id === d.successor_id);
                return (
                  <tr key={d.id} className="border-b border-border/60 last:border-b-0">
                    <td className="px-3 py-2">{pre?.name ?? d.predecessor_id}</td>
                    <td className="px-3 py-2">{succ?.name ?? d.successor_id}</td>
                    <td className="px-3 py-2 font-mono">{d.type ?? 'FS'}</td>
                    <td className="px-3 py-2 font-mono">{d.lag_days ?? 0}d</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="ec-btn-ghost !px-1.5 !py-1 text-rose-600"
                        onClick={() => {
                          if (confirm('Remove dependency?')) removeDep.mutate(d.id);
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(creatingTask || editingTask) && (
        <TaskModal
          projectId={projectId}
          task={editingTask}
          tasks={tasks}
          isNew={creatingTask}
          onClose={() => {
            setCreatingTask(false);
            setEditingTask(null);
          }}
        />
      )}
      {creatingDep && (
        <DependencyModal
          projectId={projectId}
          tasks={tasks}
          onClose={() => setCreatingDep(false)}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function DependencyArrows({
  deps,
  tasks,
  taskIndex,
  offsetDays,
  rowHeight,
  colWidth,
  labelWidth,
  headerHeight,
  span,
}: {
  deps: ScheduleDependency[];
  tasks: ScheduleTask[];
  taskIndex: Map<string, number>;
  offsetDays: (iso: string) => number;
  rowHeight: number;
  colWidth: number;
  labelWidth: number;
  headerHeight: number;
  span: number;
}) {
  if (deps.length === 0 || tasks.length === 0) return null;
  const totalWidth = labelWidth + span * colWidth;
  const totalHeight = headerHeight + tasks.length * rowHeight + 4;

  return (
    <svg
      className="pointer-events-none absolute left-0 top-0"
      width={totalWidth}
      height={totalHeight}
      style={{ overflow: 'visible' }}
    >
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="rgb(var(--color-brand-600, 79 70 229))" opacity="0.7" />
        </marker>
      </defs>
      {deps.map((d) => {
        const preIdx = taskIndex.get(d.predecessor_id);
        const succIdx = taskIndex.get(d.successor_id);
        if (preIdx === undefined || succIdx === undefined) return null;
        const pre = tasks[preIdx];
        const succ = tasks[succIdx];
        const preEndX = labelWidth + (offsetDays(pre.end_date) + 1) * colWidth;
        const preY = headerHeight + preIdx * rowHeight + rowHeight / 2;
        const succStartX = labelWidth + offsetDays(succ.start_date) * colWidth;
        const succY = headerHeight + succIdx * rowHeight + rowHeight / 2;
        const midX = (preEndX + succStartX) / 2;
        return (
          <path
            key={d.id}
            d={`M${preEndX},${preY} L${midX},${preY} L${midX},${succY} L${succStartX},${succY}`}
            stroke="currentColor"
            className="text-brand-600/60"
            strokeWidth="1.5"
            fill="none"
            markerEnd="url(#arrow)"
          />
        );
      })}
    </svg>
  );
}

/* -------------------------------------------------------------------------- */

function TaskModal({
  projectId,
  task,
  tasks,
  isNew,
  onClose,
}: {
  projectId: string;
  task: ScheduleTask | null;
  tasks: ScheduleTask[];
  isNew: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ScheduleTaskInput>(
    task
      ? {
          name: task.name,
          description: task.description ?? '',
          parent_task_id: task.parent_task_id,
          start_date: task.start_date,
          end_date: task.end_date,
          duration_days: task.duration_days,
          assigned_to_id: task.assigned_to_id ?? null,
          progress_percent: task.progress_percent,
          status: task.status,
        }
      : EMPTY_TASK,
  );

  const update = <K extends keyof ScheduleTaskInput>(key: K, value: ScheduleTaskInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      if (isNew) return constructionApi.createScheduleTask(projectId, form);
      if (!task) throw new Error('No task');
      return constructionApi.updateScheduleTask(projectId, task.id, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'schedule-tasks', projectId] });
      qc.invalidateQueries({ queryKey: ['construction', 'dashboard', projectId] });
      toast.success(isNew ? 'Task created' : 'Task saved');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail ?? 'Failed';
      toast.error(typeof detail === 'string' ? detail : 'Failed');
    },
  });

  return (
    <Modal open onClose={onClose} size="lg" labelledBy="task-modal-title">
      <ModalHeader>
        <p id="task-modal-title" className="font-semibold">{isNew ? 'New task' : 'Edit task'}</p>
        <ModalClose onClose={onClose} />
      </ModalHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="max-h-[70vh] space-y-3 overflow-y-auto p-5">
          <div>
            <label className="ec-label">Name</label>
            <input
              required
              className="ec-input"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
            />
          </div>
          <div>
            <label className="ec-label">Description</label>
            <textarea
              className="ec-input min-h-[60px]"
              value={form.description ?? ''}
              onChange={(e) => update('description', e.target.value)}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="ec-label">Parent task</label>
              <select
                className="ec-input"
                value={form.parent_task_id ?? ''}
                onChange={(e) => update('parent_task_id', e.target.value || null)}
              >
                <option value="">— None —</option>
                {tasks.filter((t) => t.id !== task?.id).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="ec-label">Status</label>
              <input
                className="ec-input"
                value={form.status}
                onChange={(e) => update('status', e.target.value)}
                placeholder="pending / in_progress / done"
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
              <label className="ec-label">End date</label>
              <input
                type="date"
                className="ec-input"
                value={form.end_date}
                onChange={(e) => update('end_date', e.target.value)}
              />
            </div>
            <div>
              <label className="ec-label">Duration (days)</label>
              <input
                type="number"
                min={1}
                className="ec-input"
                value={form.duration_days}
                onChange={(e) => update('duration_days', Math.max(1, Number(e.target.value) || 1))}
              />
            </div>
            <div>
              <label className="ec-label">Progress (%)</label>
              <input
                type="number"
                min={0}
                max={100}
                className="ec-input"
                value={form.progress_percent}
                onChange={(e) => update('progress_percent', Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
              />
            </div>
          </div>
        </div>
        <ModalFooter>
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="ec-btn-primary" disabled={save.isPending}>
            {save.isPending ? 'Saving…' : isNew ? 'Create task' : 'Save'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */

function DependencyModal({
  projectId,
  tasks,
  onClose,
}: {
  projectId: string;
  tasks: ScheduleTask[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ScheduleDependencyInput>({
    predecessor_id: tasks[0]?.id ?? '',
    successor_id: tasks[1]?.id ?? '',
    type: 'FS',
    lag_days: 0,
  });

  const save = useMutation({
    mutationFn: () => constructionApi.createScheduleDependency(projectId, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['construction', 'schedule-deps', projectId] });
      toast.success('Dependency added');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail ?? 'Failed';
      toast.error(typeof detail === 'string' ? detail : 'Failed');
    },
  });

  return (
    <Modal open onClose={onClose} size="md" labelledBy="dep-modal-title">
      <ModalHeader>
        <p id="dep-modal-title" className="font-semibold">Link tasks</p>
        <ModalClose onClose={onClose} />
      </ModalHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <ModalBody className="space-y-3">
          <div>
            <label className="ec-label">Predecessor</label>
            <select
              className="ec-input"
              value={form.predecessor_id}
              onChange={(e) => setForm((f) => ({ ...f, predecessor_id: e.target.value }))}
            >
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="ec-label">Successor</label>
            <select
              className="ec-input"
              value={form.successor_id}
              onChange={(e) => setForm((f) => ({ ...f, successor_id: e.target.value }))}
            >
              {tasks.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="ec-label">Type</label>
              <select
                className="ec-input"
                value={form.type}
                onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
              >
                <option value="FS">Finish to Start (FS)</option>
                <option value="SS">Start to Start (SS)</option>
                <option value="FF">Finish to Finish (FF)</option>
                <option value="SF">Start to Finish (SF)</option>
              </select>
            </div>
            <div>
              <label className="ec-label">Lag (days)</label>
              <input
                type="number"
                className="ec-input"
                value={form.lag_days ?? 0}
                onChange={(e) => setForm((f) => ({ ...f, lag_days: Number(e.target.value) || 0 }))}
              />
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <button type="button" className="ec-btn-secondary" onClick={onClose}>Cancel</button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || form.predecessor_id === form.successor_id}
          >
            {save.isPending ? 'Linking…' : 'Add dependency'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
