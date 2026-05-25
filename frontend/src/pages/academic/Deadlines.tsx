import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { AlertTriangle, Calendar, Clock, Plus, Trash2, Upload } from 'lucide-react';
import { Modal, ModalHeader, ModalBody, ModalFooter, ModalClose } from '../../components/Modal';
import {
  academicApi,
  academicDeepApi,
  type AssignmentInput,
  type UpcomingDeadline,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';
import { formatDateTime } from '../../lib/utils';

const EMPTY: AssignmentInput = {
  class_id: null,
  title: '',
  description: '',
  due_date: '',
  weight: 1,
};

export function AcademicDeadlinesPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = isAcademicStaff(user?.role);

  const listQ = useQuery({
    queryKey: ['academic', 'assignments'],
    queryFn: () => academicApi.listAssignments_(),
  });
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteAssignment_(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'assignments'] });
      toast.success('Assignment removed');
    },
  });

  // Sort by due_date ascending so closest deadlines surface first.
  const sorted = useMemo(
    () =>
      [...(listQ.data ?? [])].sort((a, b) =>
        a.due_date.localeCompare(b.due_date),
      ),
    [listQ.data],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Deadlines</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Upcoming assignments across your enrolled classes.
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreating(true)}
          >
            <Plus size={14} /> New assignment
          </button>
        )}
      </div>

      <StudentUpcomingPanel />

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
      {sorted.length === 0 && !listQ.isLoading && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          Nothing on the deadline horizon.
        </p>
      )}
      {sorted.length > 0 && (
        <div className="ec-card overflow-hidden">
          <ul>
            {sorted.map((a) => {
              const due = new Date(a.due_date);
              const days = Math.ceil(
                (due.getTime() - Date.now()) / (1000 * 60 * 60 * 24),
              );
              const badge =
                days < 0
                  ? 'ec-badge-rose'
                  : days <= 3
                  ? 'ec-badge-amber'
                  : 'ec-badge-blue';
              return (
                <li
                  key={a.id}
                  className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0"
                >
                  <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                    <Calendar size={16} />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium">{a.title}</p>
                    <p className="text-xs text-ink-muted">
                      {a.class_name ? `${a.class_name} · ` : ''}
                      due {a.due_date}
                    </p>
                  </div>
                  <span className={badge}>
                    {days < 0
                      ? `${Math.abs(days)}d overdue`
                      : days === 0
                      ? 'today'
                      : `${days}d`}
                  </span>
                  {canEdit && (
                    <button
                      type="button"
                      className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                      onClick={() => {
                        if (confirm(`Delete "${a.title}"?`)) remove.mutate(a.id);
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {creating && <AssignmentModal onClose={() => setCreating(false)} />}
    </div>
  );
}

function StudentUpcomingPanel() {
  const upcomingQ = useQuery({
    queryKey: ['academic', 'deadlines', 'upcoming-mine'],
    queryFn: () => academicDeepApi.myUpcomingDeadlines(14),
  });
  const [submittingFor, setSubmittingFor] = useState<string | null>(null);
  if (upcomingQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading your deadlines…</p>;
  }
  const rows = upcomingQ.data ?? [];
  if (!rows.length) return null;
  return (
    <section className="ec-card overflow-hidden">
      <header className="border-b border-border/60 px-4 py-3">
        <p className="font-semibold inline-flex items-center gap-2">
          <Clock size={14} className="text-brand-600" />
          Upcoming for you (next 14 days)
        </p>
      </header>
      <ul>
        {rows.map((row: UpcomingDeadline) => {
          const due = new Date(row.assignment.deadline);
          return (
            <li
              key={row.assignment.id}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0"
            >
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                <Calendar size={16} />
              </span>
              <div className="min-w-0">
                <p className="truncate font-medium">{row.assignment.title}</p>
                <p className="text-xs text-ink-muted">
                  due {formatDateTime(due)}
                </p>
              </div>
              <span
                className={
                  row.is_overdue
                    ? 'ec-badge-rose inline-flex items-center gap-1'
                    : 'ec-badge-blue'
                }
              >
                {row.is_overdue && <AlertTriangle size={11} />}
                {row.is_overdue ? 'overdue' : row.submission_status}
              </span>
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1 text-xs"
                onClick={() => setSubmittingFor(row.assignment.id)}
              >
                <Upload size={11} /> Submit
              </button>
            </li>
          );
        })}
      </ul>
      {submittingFor && (
        <SubmitWorkModal
          assignmentId={submittingFor}
          onClose={() => setSubmittingFor(null)}
        />
      )}
    </section>
  );
}

function SubmitWorkModal({
  assignmentId,
  onClose,
}: {
  assignmentId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [url, setUrl] = useState('');
  const [notes, setNotes] = useState('');
  const [wordCount, setWordCount] = useState(0);
  const submit = useMutation({
    mutationFn: () =>
      academicDeepApi.upsertMySubmission(assignmentId, {
        submission_url: url,
        notes,
        word_count: wordCount,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['academic', 'deadlines', 'upcoming-mine'],
      });
      toast.success('Submitted');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to submit');
    },
  });
  return (
    <Modal open onClose={onClose} size="md" labelledBy="submit-modal-title">
      <ModalHeader>
        <p id="submit-modal-title" className="font-semibold">Submit your work</p>
        <ModalClose onClose={onClose} />
      </ModalHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <ModalBody className="space-y-3">
          <div>
            <label className="ec-label">Submission URL</label>
            <input
              type="url"
              required
              className="ec-input font-mono"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>
          <div>
            <label className="ec-label">Word count</label>
            <input
              type="number"
              min={0}
              className="ec-input"
              value={wordCount}
              onChange={(e) => setWordCount(parseInt(e.target.value, 10) || 0)}
            />
          </div>
          <div>
            <label className="ec-label">Notes</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </ModalBody>
        <ModalFooter>
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={submit.isPending || !url.trim()}
          >
            {submit.isPending ? 'Saving…' : 'Submit'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

function AssignmentModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<AssignmentInput>(EMPTY);
  const save = useMutation({
    mutationFn: () => academicApi.createAssignment_(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'assignments'] });
      toast.success('Assignment created');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });
  return (
    <Modal open onClose={onClose} size="lg" labelledBy="assignment-modal-title">
      <ModalHeader>
        <p id="assignment-modal-title" className="font-semibold">New assignment</p>
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
            <label className="ec-label">Title</label>
            <input
              required
              className="ec-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="ec-label">Due date</label>
              <input
                required
                type="date"
                className="ec-input"
                value={form.due_date}
                onChange={(e) =>
                  setForm({ ...form, due_date: e.target.value })
                }
              />
            </div>
            <div>
              <label className="ec-label">Weight</label>
              <input
                type="number"
                step="0.1"
                min={0}
                className="ec-input"
                value={form.weight ?? 1}
                onChange={(e) =>
                  setForm({ ...form, weight: parseFloat(e.target.value) || 0 })
                }
              />
            </div>
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
        </ModalBody>
        <ModalFooter>
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.title.trim() || !form.due_date}
          >
            {save.isPending ? 'Saving…' : 'Create'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
