import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { CheckCircle2, FlaskConical, Plus, Send, Trash2 } from 'lucide-react';
import { Modal, ModalHeader, ModalBody, ModalFooter, ModalClose } from '../../components/Modal';
import {
  academicApi,
  academicDeepApi,
  type LabReportInput,
  type LabReportStudentSummary,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';

const EMPTY: LabReportInput = {
  class_id: null,
  title: '',
  body: '',
  student_id: null,
  grade: null,
  status: 'submitted',
};

export function AcademicLabReportsPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canGrade = isAcademicStaff(user?.role);

  const listQ = useQuery({
    queryKey: ['academic', 'lab-reports'],
    queryFn: () => academicApi.listLabReports(),
  });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteLabReport(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'lab-reports'] });
      toast.success('Report deleted');
    },
  });

  const submit = useMutation({
    mutationFn: (id: string) => academicDeepApi.submitLabReport(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'lab-reports'] });
      toast.success('Submitted for grading');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Submit failed');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Lab Reports</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Lab submissions per class. Teachers grade and review; students submit.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => setCreating(true)}
        >
          <Plus size={14} /> New report
        </button>
      </div>

      {!canGrade && <MyLabSummaryCard />}

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No lab reports yet.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="ec-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Student</th>
                <th>Submitted</th>
                <th>Grade</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {listQ.data.map((r) => (
                <tr key={r.id}>
                  <td>
                    <p className="font-medium inline-flex items-center gap-2">
                      <FlaskConical size={14} className="text-brand-600" />
                      {r.title}
                    </p>
                  </td>
                  <td className="text-ink-muted">{r.student_name ?? '—'}</td>
                  <td className="text-ink-muted">{r.submitted_at ?? '—'}</td>
                  <td>{r.grade ?? '—'}</td>
                  <td>
                    <span className="ec-badge bg-surface-muted text-ink-muted">
                      {r.status ?? '—'}
                    </span>
                  </td>
                  <td className="text-right">
                    {!canGrade && r.status === 'draft' && (
                      <button
                        type="button"
                        className="ec-btn-ghost !px-2 !py-1 text-xs"
                        onClick={() => submit.mutate(r.id)}
                        disabled={submit.isPending}
                      >
                        <Send size={11} /> Submit
                      </button>
                    )}
                    {canGrade && r.status === 'submitted' && (
                      <button
                        type="button"
                        className="ec-btn-ghost !px-2 !py-1 text-xs"
                        onClick={() => setEditing(r.id)}
                      >
                        <CheckCircle2 size={11} /> Grade
                      </button>
                    )}
                    <button
                      type="button"
                      className="ec-btn-ghost !px-2 !py-1 text-xs"
                      onClick={() => setEditing(r.id)}
                    >
                      Edit
                    </button>
                    {canGrade && (
                      <button
                        type="button"
                        className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                        onClick={() => {
                          if (confirm('Delete this report?')) remove.mutate(r.id);
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(creating || editing) && (
        <LabReportModal
          existingId={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

function MyLabSummaryCard() {
  const sumQ = useQuery({
    queryKey: ['academic', 'lab-reports', 'mine-summary'],
    queryFn: () => academicDeepApi.myLabReportSummary(),
  });
  if (sumQ.isLoading) return null;
  const data = sumQ.data as LabReportStudentSummary | undefined;
  if (!data || !data.classes.length) return null;
  return (
    <section className="ec-card p-4">
      <p className="mb-2 inline-flex items-center gap-2 font-semibold">
        <FlaskConical size={14} className="text-brand-600" />
        Your lab work by class
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {data.classes.map((c) => (
          <article
            key={c.class_id}
            className="rounded-lg border border-border/60 p-3 text-xs"
          >
            <p className="font-medium">{c.class_id.slice(0, 12)}…</p>
            <p className="text-ink-muted">
              {c.total} report{c.total === 1 ? '' : 's'}
              {c.avg_numeric_grade != null && (
                <> · avg {c.avg_numeric_grade}</>
              )}
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {Object.entries(c.by_status).map(([k, v]) => (
                <span
                  key={k}
                  className="ec-badge bg-surface-muted text-ink-muted"
                >
                  {k}: {v}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function LabReportModal({
  existingId,
  onClose,
}: {
  existingId: string | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<LabReportInput>(EMPTY);
  const save = useMutation({
    mutationFn: () =>
      existingId
        ? academicApi.updateLabReport(existingId, form)
        : academicApi.createLabReport(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'lab-reports'] });
      toast.success(existingId ? 'Report saved' : 'Report submitted');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });
  return (
    <Modal open onClose={onClose} size="lg" labelledBy="lab-modal-title">
      <ModalHeader>
        <p id="lab-modal-title" className="font-semibold">{existingId ? 'Edit report' : 'New lab report'}</p>
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
          <div>
            <label className="ec-label">Body</label>
            <textarea
              className="ec-input min-h-[140px] font-mono text-xs"
              value={form.body ?? ''}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="ec-label">Grade</label>
              <input
                className="ec-input"
                value={form.grade ?? ''}
                onChange={(e) => setForm({ ...form, grade: e.target.value })}
                placeholder="A / 85 / Pass"
              />
            </div>
            <div>
              <label className="ec-label">Status</label>
              <select
                className="ec-input"
                value={form.status ?? 'submitted'}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
              >
                <option value="draft">Draft</option>
                <option value="submitted">Submitted</option>
                <option value="graded">Graded</option>
                <option value="returned">Returned</option>
              </select>
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <button type="button" className="ec-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.title.trim()}
          >
            {save.isPending ? 'Saving…' : existingId ? 'Save' : 'Submit'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
