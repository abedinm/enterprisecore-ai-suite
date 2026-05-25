import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Calendar, Handshake, LineChart, Plus, Trash2 } from 'lucide-react';
import { Modal, ModalHeader, ModalBody, ModalFooter, ModalClose } from '../../components/Modal';
import {
  academicApi,
  academicDeepApi,
  type AdvisingSessionInput,
  type CgpaTrend,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';
import { formatDateTime } from '../../lib/utils';

const EMPTY: AdvisingSessionInput = {
  advisor_id: null,
  student_id: null,
  scheduled_at: '',
  duration_minutes: 30,
  notes: '',
  status: 'scheduled',
};

export function AcademicAdvisingPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = isAcademicStaff(user?.role);

  const listQ = useQuery({
    queryKey: ['academic', 'advising'],
    queryFn: () => academicApi.listAdvisingSessions(),
  });
  const [creating, setCreating] = useState(false);

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteAdvisingSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'advising'] });
      toast.success('Session cancelled');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Advising</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Schedule and track 1:1 academic advising sessions.
          </p>
        </div>
        <button
          type="button"
          className="ec-btn-primary"
          onClick={() => setCreating(true)}
        >
          <Plus size={14} /> Book session
        </button>
      </div>

      {!canEdit && user && <MyCgpaTrendPanel studentId={user.id} />}
      {!canEdit && user && <MyAdvisingHistoryPanel />}

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No advising sessions on the calendar.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="ec-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Advisor</th>
                <th>Student</th>
                <th>Duration</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {listQ.data.map((s) => (
                <tr key={s.id}>
                  <td className="font-medium inline-flex items-center gap-2">
                    <Calendar size={13} className="text-brand-600" />
                    {s.scheduled_at}
                  </td>
                  <td>
                    <span className="inline-flex items-center gap-1">
                      <Handshake size={12} className="text-ink-muted" />
                      {s.advisor_name ?? '—'}
                    </span>
                  </td>
                  <td className="text-ink-muted">{s.student_name ?? '—'}</td>
                  <td className="text-ink-muted">
                    {s.duration_minutes ? `${s.duration_minutes} min` : '—'}
                  </td>
                  <td>
                    <span className="ec-badge bg-surface-muted text-ink-muted">
                      {s.status ?? 'scheduled'}
                    </span>
                  </td>
                  <td className="text-right">
                    {canEdit && (
                      <button
                        type="button"
                        className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                        onClick={() => {
                          if (confirm('Cancel this session?')) remove.mutate(s.id);
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

      {creating && <AdvisingModal onClose={() => setCreating(false)} />}
    </div>
  );
}

function MyCgpaTrendPanel({ studentId }: { studentId: string }) {
  const q = useQuery({
    queryKey: ['academic', 'advising', 'cgpa-trend', studentId],
    queryFn: () => academicDeepApi.cgpaTrend(studentId),
  });
  if (q.isLoading) return null;
  const data = q.data as CgpaTrend | undefined;
  if (!data || !data.points.length) return null;
  const sequence = data.points
    .filter((p) => p.current_cgpa != null)
    .map((p) => p.current_cgpa)
    .join(' → ');
  return (
    <section className="ec-card p-4">
      <p className="mb-1 inline-flex items-center gap-2 font-semibold">
        <LineChart size={14} className="text-brand-600" />
        Your CGPA trend
      </p>
      <p className="font-mono text-sm">{sequence || '—'}</p>
    </section>
  );
}

function MyAdvisingHistoryPanel() {
  const q = useQuery({
    queryKey: ['academic', 'advising', 'mine'],
    queryFn: () => academicDeepApi.myAdvisingSessions(),
  });
  if (q.isLoading) return null;
  const data = (q.data ?? []) as { id: string; scheduled_at: string }[];
  if (!data.length) return null;
  return (
    <section className="ec-card p-4">
      <p className="mb-2 inline-flex items-center gap-2 font-semibold">
        <Handshake size={14} className="text-brand-600" />
        Your past sessions
      </p>
      <ul className="space-y-1 text-sm">
        {data.slice(0, 5).map((s) => (
          <li key={s.id} className="text-ink-muted">
            · {formatDateTime(s.scheduled_at)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function AdvisingModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<AdvisingSessionInput>(EMPTY);
  const save = useMutation({
    mutationFn: () => academicApi.createAdvisingSession(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'advising'] });
      toast.success('Session booked');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save');
    },
  });
  return (
    <Modal open onClose={onClose} size="md" labelledBy="advising-modal-title">
      <ModalHeader>
        <p id="advising-modal-title" className="font-semibold">Book advising session</p>
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
            <label className="ec-label">When</label>
            <input
              required
              type="datetime-local"
              className="ec-input"
              value={form.scheduled_at}
              onChange={(e) =>
                setForm({ ...form, scheduled_at: e.target.value })
              }
            />
          </div>
          <div>
            <label className="ec-label">Duration (min)</label>
            <input
              type="number"
              min={0}
              className="ec-input"
              value={form.duration_minutes ?? 30}
              onChange={(e) =>
                setForm({
                  ...form,
                  duration_minutes: parseInt(e.target.value, 10) || 0,
                })
              }
            />
          </div>
          <div>
            <label className="ec-label">Notes</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.notes ?? ''}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
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
            disabled={save.isPending || !form.scheduled_at}
          >
            {save.isPending ? 'Booking…' : 'Book'}
          </button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
