import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Plus, Scale, Trash2, Users2, Wand2, X } from 'lucide-react';
import {
  academicApi,
  academicDeepApi,
  type GroupProjectInput,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';

const EMPTY: GroupProjectInput = {
  class_id: null,
  title: '',
  description: '',
  due_date: '',
};

export function AcademicGroupProjectsPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = isAcademicStaff(user?.role);

  const listQ = useQuery({
    queryKey: ['academic', 'group-projects'],
    queryFn: () => academicApi.listGroupProjects(),
  });
  const [creating, setCreating] = useState(false);
  const [openAssignments, setOpenAssignments] = useState<string | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteGroupProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'group-projects'] });
      toast.success('Project removed');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Group Projects</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Assignments shared by a team of students.
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> New project
          </button>
        )}
      </div>

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No group projects yet.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {listQ.data.map((p) => (
            <article key={p.id} className="ec-card flex flex-col gap-2 p-4">
              <div className="flex items-start justify-between">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <Users2 size={16} />
                </span>
                {p.due_date && (
                  <span className="ec-badge bg-surface-muted text-ink-muted">
                    due {p.due_date}
                  </span>
                )}
              </div>
              <p className="font-semibold">{p.title}</p>
              {p.description && (
                <p className="line-clamp-2 text-xs text-ink-muted">
                  {p.description}
                </p>
              )}
              <p className="text-xs text-ink-muted">
                {p.member_count ?? 0} member{(p.member_count ?? 0) === 1 ? '' : 's'}
              </p>
              <FairnessBadge projectId={p.id} />
              <div className="mt-auto flex justify-between pt-2">
                <button
                  type="button"
                  className="ec-btn-ghost !px-2 !py-1 text-xs"
                  onClick={() => setOpenAssignments(p.id)}
                >
                  Manage team
                </button>
                {canEdit && (
                  <AutoBalanceButton projectId={p.id} />
                )}
                {canEdit && (
                  <button
                    type="button"
                    className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                    onClick={() => {
                      if (confirm(`Delete "${p.title}"?`)) remove.mutate(p.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {creating && <GroupProjectModal onClose={() => setCreating(false)} />}
      {openAssignments && (
        <AssignmentsModal
          projectId={openAssignments}
          onClose={() => setOpenAssignments(null)}
        />
      )}
    </div>
  );
}

function GroupProjectModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<GroupProjectInput>(EMPTY);
  const save = useMutation({
    mutationFn: () => academicApi.createGroupProject(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'group-projects'] });
      toast.success('Project created');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">New group project</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form
          className="space-y-3 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div>
            <label className="ec-label">Title</label>
            <input
              required
              className="ec-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div>
            <label className="ec-label">Due date</label>
            <input
              type="date"
              className="ec-input"
              value={form.due_date ?? ''}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
            />
          </div>
          <div>
            <label className="ec-label">Description</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.description ?? ''}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={save.isPending || !form.title.trim()}
            >
              {save.isPending ? 'Saving…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AssignmentsModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['academic', 'assignments', projectId],
    queryFn: () => academicApi.listAssignments(projectId),
  });
  const [studentId, setStudentId] = useState('');
  const [role, setRole] = useState('member');

  const add = useMutation({
    mutationFn: () =>
      academicApi.createAssignment(projectId, {
        project_id: projectId,
        student_id: studentId,
        role,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['academic', 'assignments', projectId],
      });
      qc.invalidateQueries({ queryKey: ['academic', 'group-projects'] });
      setStudentId('');
      toast.success('Member added');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to add');
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteAssignment(projectId, id),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['academic', 'assignments', projectId],
      });
      qc.invalidateQueries({ queryKey: ['academic', 'group-projects'] });
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">Team members</p>
          <button type="button" className="ec-btn-ghost !p-2" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="space-y-3 p-5">
          {listQ.isLoading && (
            <p className="text-sm text-ink-muted">Loading…</p>
          )}
          {listQ.data && listQ.data.length === 0 && (
            <p className="text-sm text-ink-muted">No members yet.</p>
          )}
          {listQ.data && listQ.data.length > 0 && (
            <ul className="space-y-1">
              {listQ.data.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm"
                >
                  <span>
                    {a.student_name ?? a.student_id}
                    {a.role && (
                      <span className="ml-2 text-xs text-ink-muted">
                        ({a.role})
                      </span>
                    )}
                  </span>
                  <button
                    type="button"
                    className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                    onClick={() => remove.mutate(a.id)}
                  >
                    <Trash2 size={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (studentId) add.mutate();
            }}
          >
            <input
              placeholder="Student ID"
              className="ec-input flex-1"
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
            />
            <input
              placeholder="role"
              className="ec-input w-28"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            />
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={add.isPending || !studentId.trim()}
            >
              Add
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function FairnessBadge({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ['academic', 'group-projects', projectId, 'fairness'],
    queryFn: () => academicDeepApi.projectFairness(projectId),
  });
  if (q.isLoading || !q.data) return null;
  const f = q.data;
  return (
    <span
      title={f.suggestions.join('\n')}
      className={
        f.balanced
          ? 'inline-flex items-center gap-1 text-xs text-emerald-600'
          : 'inline-flex items-center gap-1 text-xs text-amber-600'
      }
    >
      <Scale size={11} />
      {f.balanced ? 'balanced' : `unbalanced (σ=${f.weight_std_dev.toFixed(2)})`}
    </span>
  );
}

function AutoBalanceButton({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [ids, setIds] = useState('');
  const [open, setOpen] = useState(false);
  const run = useMutation({
    mutationFn: () =>
      academicDeepApi.autoBalanceProject(
        projectId,
        ids
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        { commit: true },
      ),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['academic', 'group-projects', projectId, 'fairness'],
      });
      toast.success('Project balanced');
      setOpen(false);
      setIds('');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Auto-balance failed');
    },
  });
  if (!open) {
    return (
      <button
        type="button"
        className="ec-btn-ghost !px-2 !py-1 text-xs"
        onClick={() => setOpen(true)}
      >
        <Wand2 size={11} /> Auto-balance
      </button>
    );
  }
  return (
    <form
      className="flex w-full items-center gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        if (!ids.trim() || !confirm('Wipe existing assignments and balance?'))
          return;
        run.mutate();
      }}
    >
      <input
        className="ec-input !py-1 text-xs"
        placeholder="student id,student id,..."
        value={ids}
        onChange={(e) => setIds(e.target.value)}
      />
      <button
        type="submit"
        className="ec-btn-primary !px-2 !py-1 text-xs"
        disabled={run.isPending || !ids.trim()}
      >
        Go
      </button>
      <button
        type="button"
        className="ec-btn-ghost !px-2 !py-1 text-xs"
        onClick={() => setOpen(false)}
      >
        Cancel
      </button>
    </form>
  );
}
