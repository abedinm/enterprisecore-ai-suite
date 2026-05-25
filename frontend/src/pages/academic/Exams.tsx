import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { CalendarRange, ClipboardList, MapPin, Plus, Trash2, X } from 'lucide-react';
import {
  academicApi,
  academicDeepApi,
  type ExamDeep,
  type ExamInput,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';

const EMPTY: ExamInput = {
  class_id: null,
  title: '',
  exam_date: '',
  duration_minutes: 90,
  weight: 1,
  notes: '',
};

export function AcademicExamsPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = isAcademicStaff(user?.role);

  const listQ = useQuery({
    queryKey: ['academic', 'exams'],
    queryFn: () => academicApi.listExams(),
  });
  const [editing, setEditing] = useState<{ open: boolean; id: string | null }>({
    open: false,
    id: null,
  });

  const remove = useMutation({
    mutationFn: (id: string) => academicApi.deleteExam(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'exams'] });
      toast.success('Exam removed');
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Exams</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Scheduled assessments per class. Students see read-only listings.
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setEditing({ open: true, id: null })}
          >
            <Plus size={14} /> Schedule exam
          </button>
        )}
      </div>

      <UpcomingExamsPanel canSchedule={canEdit} />

      {listQ.isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
      {listQ.data && listQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No exams scheduled yet.
        </p>
      )}
      {listQ.data && listQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {listQ.data.map((e) => (
            <article key={e.id} className="ec-card flex flex-col gap-2 p-4">
              <div className="flex items-start justify-between">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <ClipboardList size={16} />
                </span>
                {e.weight != null && (
                  <span className="ec-badge bg-surface-muted text-ink-muted">
                    × {e.weight}
                  </span>
                )}
              </div>
              <p className="font-semibold">{e.title}</p>
              <p className="text-xs text-ink-muted">
                {e.class_name && <span>{e.class_name} · </span>}
                {e.exam_date}
                {e.duration_minutes ? ` · ${e.duration_minutes} min` : ''}
              </p>
              {e.notes && (
                <p className="line-clamp-2 text-xs text-ink-muted">{e.notes}</p>
              )}
              {canEdit && (
                <div className="mt-auto flex justify-end pt-2">
                  <button
                    type="button"
                    className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                    onClick={() => {
                      if (confirm(`Remove "${e.title}"?`)) remove.mutate(e.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      {editing.open && (
        <ExamModal
          existingId={editing.id}
          onClose={() => setEditing({ open: false, id: null })}
        />
      )}
    </div>
  );
}

function UpcomingExamsPanel({ canSchedule }: { canSchedule: boolean }) {
  const qc = useQueryClient();
  const upQ = useQuery({
    queryKey: ['academic', 'exams', 'upcoming'],
    queryFn: () => academicDeepApi.upcomingExams(14),
  });
  const [scheduling, setScheduling] = useState<string | null>(null);
  const [room, setRoom] = useState('');
  const sched = useMutation({
    mutationFn: ({ examId, roomId }: { examId: string; roomId: string }) =>
      academicDeepApi.scheduleExamRoom(examId, roomId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'exams', 'upcoming'] });
      qc.invalidateQueries({ queryKey: ['academic', 'exams'] });
      toast.success('Room scheduled');
      setScheduling(null);
      setRoom('');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to schedule');
    },
  });
  if (upQ.isLoading) return null;
  const rows = (upQ.data ?? []) as ExamDeep[];
  if (!rows.length) return null;
  return (
    <section className="ec-card overflow-hidden">
      <header className="border-b border-border/60 px-4 py-3">
        <p className="font-semibold inline-flex items-center gap-2">
          <CalendarRange size={14} className="text-brand-600" />
          Upcoming exams (14 days)
        </p>
      </header>
      <ul>
        {rows.map((e) => (
          <li
            key={e.id}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0"
          >
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
              <ClipboardList size={16} />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium">{e.course_code}</p>
              <p className="text-xs text-ink-muted">
                {e.exam_date} · {e.start_time} · {e.duration_min} min
              </p>
            </div>
            <span className="ec-badge bg-surface-muted text-ink-muted">
              {e.room_id ? <><MapPin size={10} /> {e.room_id.slice(0, 8)}</> : 'no room'}
            </span>
            {canSchedule && (
              <button
                type="button"
                className="ec-btn-ghost !px-2 !py-1 text-xs"
                onClick={() => setScheduling(e.id)}
              >
                Schedule room
              </button>
            )}
          </li>
        ))}
      </ul>
      {scheduling && (
        <div className="border-t border-border/60 p-3">
          <form
            className="flex items-center gap-2"
            onSubmit={(ev) => {
              ev.preventDefault();
              sched.mutate({ examId: scheduling, roomId: room });
            }}
          >
            <input
              className="ec-input flex-1"
              placeholder="Room id"
              value={room}
              onChange={(ev) => setRoom(ev.target.value)}
              required
            />
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={sched.isPending || !room.trim()}
            >
              {sched.isPending ? 'Saving…' : 'Assign'}
            </button>
            <button
              type="button"
              className="ec-btn-secondary"
              onClick={() => setScheduling(null)}
            >
              Cancel
            </button>
          </form>
        </div>
      )}
    </section>
  );
}

function ExamModal({
  existingId,
  onClose,
}: {
  existingId: string | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ExamInput>(EMPTY);
  const save = useMutation({
    mutationFn: () =>
      existingId
        ? academicApi.updateExam(existingId, form)
        : academicApi.createExam(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'exams'] });
      toast.success('Exam saved');
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
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{existingId ? 'Edit exam' : 'Schedule exam'}</p>
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
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="ec-label">Date</label>
              <input
                required
                type="date"
                className="ec-input"
                value={form.exam_date}
                onChange={(e) =>
                  setForm({ ...form, exam_date: e.target.value })
                }
              />
            </div>
            <div>
              <label className="ec-label">Duration (min)</label>
              <input
                type="number"
                min={0}
                className="ec-input"
                value={form.duration_minutes ?? 0}
                onChange={(e) =>
                  setForm({
                    ...form,
                    duration_minutes: parseInt(e.target.value, 10) || 0,
                  })
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
                  setForm({
                    ...form,
                    weight: parseFloat(e.target.value) || 0,
                  })
                }
              />
            </div>
          </div>
          <div>
            <label className="ec-label">Notes</label>
            <textarea
              className="ec-input min-h-[80px]"
              value={form.notes ?? ''}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="ec-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="ec-btn-primary"
              disabled={save.isPending || !form.title.trim() || !form.exam_date}
            >
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
