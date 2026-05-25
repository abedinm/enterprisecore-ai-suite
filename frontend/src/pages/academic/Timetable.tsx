import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  AlertCircle,
  CalendarDays,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import {
  academicApi,
  DAYS_OF_WEEK,
  type DayOfWeek,
  type Semester,
  type TimetableSlot,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { academicRoleView } from '../../lib/academicRoles';

type Audience = 'mine' | 'all' | { kind: 'room'; id: string };

/**
 * Timetable page. The weekly grid is shown to everyone (filtered by audience
 * + semester). Admin-tier users (admin/manager/registrar/dean) additionally
 * see a scheduling block to add slots, with inline conflict reporting from the
 * backend (409 → reason). Teachers get the "my teaching schedule" view.
 */
export function AcademicTimetablePage() {
  const user = useAuthStore((s) => s.user);
  const view = academicRoleView(user?.role);
  const isStaff = view === 'admin';
  const isTeacher = view === 'teacher';

  const qc = useQueryClient();

  const semestersQ = useQuery({
    queryKey: ['academic', 'semesters'],
    queryFn: () => academicApi.listSemesters(),
  });

  const [semesterId, setSemesterId] = useState<string>('');
  useEffect(() => {
    if (!semesterId && semestersQ.data && semestersQ.data.length > 0) {
      const active =
        semestersQ.data.find((s) => s.is_active) ?? semestersQ.data[0];
      setSemesterId(active.id);
    }
  }, [semestersQ.data, semesterId]);

  // Default audience: student/teacher → mine; admin → all.
  const defaultAudience: Audience = isStaff ? 'all' : 'mine';
  const [audience, setAudience] = useState<Audience>(defaultAudience);

  const slotsQ = useQuery({
    queryKey: ['academic', 'slots', semesterId, audienceKey(audience)],
    queryFn: () => fetchSlots(semesterId, audience, isTeacher),
    enabled: !!semesterId,
  });

  const roomsQ = useQuery({
    queryKey: ['academic', 'rooms'],
    queryFn: () => academicApi.listRooms(),
    enabled: isStaff,
  });

  const [creatingSemester, setCreatingSemester] = useState(false);
  const [creatingSlot, setCreatingSlot] = useState(false);
  const [creatingRoom, setCreatingRoom] = useState(false);

  const deleteSlot = useMutation({
    mutationFn: (id: string) => academicApi.deleteSlot(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'slots'] });
      toast.success('Slot removed');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to delete slot');
    },
  });

  // Empty state — no semester at all.
  if (semestersQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading timetable…</p>;
  }
  if (!semestersQ.data || semestersQ.data.length === 0) {
    return (
      <div className="ec-card flex flex-col items-start gap-3 p-6">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
          <CalendarDays size={22} />
        </div>
        <div>
          <h2 className="text-lg font-semibold">No semester yet</h2>
          <p className="mt-1 max-w-xl text-sm text-ink-muted">
            Create a semester to scaffold the academic calendar. Once created,
            you can assign rooms and start building the weekly grid.
          </p>
        </div>
        {isStaff ? (
          <button
            type="button"
            className="ec-btn-primary"
            onClick={() => setCreatingSemester(true)}
          >
            <Plus size={14} /> Create semester
          </button>
        ) : (
          <p className="text-sm text-ink-muted">
            Ask an admin or registrar to create the first semester.
          </p>
        )}
        {creatingSemester && (
          <SemesterModal onClose={() => setCreatingSemester(false)} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls bar */}
      <div className="ec-card grid gap-3 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <div>
          <label className="ec-label">Semester</label>
          <div className="flex gap-2">
            <select
              className="ec-input"
              value={semesterId}
              onChange={(e) => setSemesterId(e.target.value)}
            >
              {semestersQ.data.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.start_date} → {s.end_date})
                </option>
              ))}
            </select>
            {isStaff && (
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={() => setCreatingSemester(true)}
              >
                <Plus size={14} />
              </button>
            )}
          </div>
        </div>
        <div>
          <label className="ec-label">Audience</label>
          <select
            className="ec-input"
            value={audienceKey(audience)}
            onChange={(e) => setAudience(audienceFromKey(e.target.value))}
          >
            <option value="mine">{isTeacher ? 'My teaching schedule' : 'My schedule'}</option>
            {isStaff && <option value="all">All slots</option>}
            {isStaff && roomsQ.data && roomsQ.data.length > 0 && (
              <optgroup label="By room">
                {roomsQ.data.map((r) => (
                  <option key={r.id} value={`room:${r.id}`}>
                    Room: {r.name}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
        <div className="flex items-end gap-2">
          {isStaff && (
            <>
              <button
                type="button"
                className="ec-btn-secondary"
                onClick={() => setCreatingRoom(true)}
              >
                <Plus size={14} /> Room
              </button>
              <button
                type="button"
                className="ec-btn-primary"
                onClick={() => setCreatingSlot(true)}
              >
                <Plus size={14} /> Slot
              </button>
            </>
          )}
        </div>
      </div>

      {/* Weekly grid */}
      <WeeklyGrid
        slots={slotsQ.data ?? []}
        loading={slotsQ.isLoading}
        canDelete={isStaff}
        onDelete={(id) => {
          if (confirm('Remove this scheduled slot?')) deleteSlot.mutate(id);
        }}
      />

      {/* Admin slot list */}
      {isStaff && (
        <div className="ec-card overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <p className="font-semibold">All slots this semester</p>
            <span className="text-xs text-ink-muted">
              {(slotsQ.data ?? []).length} slots
            </span>
          </div>
          {(!slotsQ.data || slotsQ.data.length === 0) && (
            <p className="p-6 text-center text-sm text-ink-muted">
              No slots scheduled yet.
            </p>
          )}
          {slotsQ.data && slotsQ.data.length > 0 && (
            <table className="ec-table">
              <thead>
                <tr>
                  <th>Class</th>
                  <th>Day</th>
                  <th>Time</th>
                  <th>Room</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {[...slotsQ.data]
                  .sort(
                    (a, b) =>
                      a.day_of_week - b.day_of_week ||
                      a.start_time.localeCompare(b.start_time),
                  )
                  .map((slot) => (
                    <tr key={slot.id}>
                      <td>
                        <p className="font-medium">
                          {slot.class_name ?? slot.class_id}
                        </p>
                        {slot.course_code && (
                          <p className="text-xs font-mono text-ink-muted">
                            {slot.course_code}
                          </p>
                        )}
                      </td>
                      <td className="text-ink-muted">
                        {DAYS_OF_WEEK[slot.day_of_week]?.label ?? slot.day_of_week}
                      </td>
                      <td className="font-mono text-xs text-ink-muted">
                        {slot.start_time}–{slot.end_time}
                      </td>
                      <td className="text-ink-muted">{slot.room_name ?? slot.room_id}</td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="ec-btn-ghost !px-2 !py-1 text-rose-600"
                          onClick={() => {
                            if (confirm('Remove this slot?'))
                              deleteSlot.mutate(slot.id);
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {creatingSemester && (
        <SemesterModal onClose={() => setCreatingSemester(false)} />
      )}
      {creatingRoom && <RoomModal onClose={() => setCreatingRoom(false)} />}
      {creatingSlot && (
        <SlotModal
          semesterId={semesterId}
          onClose={() => setCreatingSlot(false)}
        />
      )}
    </div>
  );
}

function audienceKey(a: Audience): string {
  if (typeof a === 'string') return a;
  return `room:${a.id}`;
}
function audienceFromKey(k: string): Audience {
  if (k === 'mine' || k === 'all') return k;
  if (k.startsWith('room:')) return { kind: 'room', id: k.slice(5) };
  return 'mine';
}

function fetchSlots(
  semesterId: string,
  audience: Audience,
  isTeacher: boolean,
) {
  if (audience === 'mine') {
    return isTeacher
      ? academicApi.myTeacherSchedule(semesterId)
      : academicApi.myStudentSchedule(semesterId);
  }
  if (audience === 'all') return academicApi.listSlots(semesterId);
  return academicApi.roomSchedule(audience.id, semesterId);
}

/* -------------------------------------------------------------------------- */
/*  Weekly grid                                                                */
/* -------------------------------------------------------------------------- */

const PALETTE = [
  'bg-sky-100 text-sky-700 border-sky-300 dark:bg-sky-900/30 dark:text-sky-200',
  'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-200',
  'bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-900/30 dark:text-amber-200',
  'bg-violet-100 text-violet-700 border-violet-300 dark:bg-violet-900/30 dark:text-violet-200',
  'bg-rose-100 text-rose-700 border-rose-300 dark:bg-rose-900/30 dark:text-rose-200',
  'bg-cyan-100 text-cyan-700 border-cyan-300 dark:bg-cyan-900/30 dark:text-cyan-200',
];

function colorFor(classId: string): string {
  let hash = 0;
  for (let i = 0; i < classId.length; i++)
    hash = (hash * 31 + classId.charCodeAt(i)) | 0;
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

function WeeklyGrid({
  slots,
  loading,
  canDelete,
  onDelete,
}: {
  slots: TimetableSlot[];
  loading: boolean;
  canDelete: boolean;
  onDelete: (id: string) => void;
}) {
  const grouped = useMemo(() => {
    const map = new Map<DayOfWeek, TimetableSlot[]>();
    for (const day of DAYS_OF_WEEK) map.set(day.value, []);
    for (const slot of slots) {
      map.get(slot.day_of_week)?.push(slot);
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.start_time.localeCompare(b.start_time));
    }
    return map;
  }, [slots]);

  if (loading) return <p className="text-sm text-ink-muted">Loading grid…</p>;
  if (slots.length === 0)
    return (
      <p className="ec-card p-6 text-center text-sm text-ink-muted">
        No slots match this filter for the selected semester.
      </p>
    );

  return (
    <div className="ec-card overflow-x-auto p-3">
      <div className="grid min-w-[840px] grid-cols-7 gap-2">
        {DAYS_OF_WEEK.map((day) => (
          <div key={day.value} className="flex flex-col gap-2">
            <p className="px-1 text-xs font-semibold uppercase tracking-wider text-ink-subtle">
              {day.short}
            </p>
            <div className="flex flex-col gap-2">
              {(grouped.get(day.value) ?? []).map((slot) => (
                <div
                  key={slot.id}
                  title={`${slot.class_name ?? slot.class_id} · ${slot.room_name ?? ''} · ${slot.start_time}–${slot.end_time}`}
                  className={`relative rounded-lg border px-2 py-1.5 text-xs ${colorFor(slot.class_id)}`}
                >
                  <p className="font-medium leading-tight">
                    {slot.course_code ?? slot.class_name ?? '—'}
                  </p>
                  <p className="font-mono text-[10px] opacity-80">
                    {slot.start_time}–{slot.end_time}
                  </p>
                  {slot.room_name && (
                    <p className="text-[10px] opacity-80">{slot.room_name}</p>
                  )}
                  {canDelete && (
                    <button
                      type="button"
                      aria-label="Delete slot"
                      className="absolute right-1 top-1 rounded p-0.5 text-current/70 hover:bg-white/60"
                      onClick={() => onDelete(slot.id)}
                    >
                      <X size={10} />
                    </button>
                  )}
                </div>
              ))}
              {(grouped.get(day.value) ?? []).length === 0 && (
                <div className="rounded-lg border border-dashed border-border/60 px-2 py-3 text-center text-[11px] text-ink-subtle">
                  —
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Modals: semester, room, slot                                               */
/* -------------------------------------------------------------------------- */

function ModalShell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <p className="font-semibold">{title}</p>
          <button
            type="button"
            className="ec-btn-ghost !p-2"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function SemesterModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Omit<Semester, 'id'>>({
    name: '',
    start_date: '',
    end_date: '',
    is_active: false,
  });
  const save = useMutation({
    mutationFn: () => academicApi.createSemester(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'semesters'] });
      toast.success('Semester created');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to create semester');
    },
  });
  return (
    <ModalShell title="New semester" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div>
          <label className="ec-label">Name</label>
          <input
            required
            className="ec-input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Fall 2026"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="ec-label">Start date</label>
            <input
              required
              type="date"
              className="ec-input"
              value={form.start_date}
              onChange={(e) =>
                setForm({ ...form, start_date: e.target.value })
              }
            />
          </div>
          <div>
            <label className="ec-label">End date</label>
            <input
              required
              type="date"
              className="ec-input"
              value={form.end_date}
              onChange={(e) =>
                setForm({ ...form, end_date: e.target.value })
              }
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!form.is_active}
            onChange={(e) =>
              setForm({ ...form, is_active: e.target.checked })
            }
          />
          Mark as the active semester
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.name}
          >
            {save.isPending ? 'Saving…' : 'Create'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function RoomModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: '',
    building: '',
    capacity: 0,
  });
  const save = useMutation({
    mutationFn: () =>
      academicApi.createRoom({
        name: form.name,
        building: form.building || null,
        capacity: form.capacity || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'rooms'] });
      toast.success('Room added');
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to add room');
    },
  });
  return (
    <ModalShell title="New room" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div>
          <label className="ec-label">Name</label>
          <input
            required
            className="ec-input"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="A-201"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="ec-label">Building</label>
            <input
              className="ec-input"
              value={form.building}
              onChange={(e) =>
                setForm({ ...form, building: e.target.value })
              }
            />
          </div>
          <div>
            <label className="ec-label">Capacity</label>
            <input
              type="number"
              min={0}
              className="ec-input"
              value={form.capacity}
              onChange={(e) =>
                setForm({ ...form, capacity: parseInt(e.target.value, 10) || 0 })
              }
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.name}
          >
            {save.isPending ? 'Saving…' : 'Add room'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

function SlotModal({
  semesterId,
  onClose,
}: {
  semesterId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const classesQ = useQuery({
    queryKey: ['academic', 'classes'],
    queryFn: () => academicApi.listClasses(),
  });
  const roomsQ = useQuery({
    queryKey: ['academic', 'rooms'],
    queryFn: () => academicApi.listRooms(),
  });
  const [form, setForm] = useState({
    class_id: '',
    room_id: '',
    day_of_week: 0 as DayOfWeek,
    start_time: '09:00',
    end_time: '10:30',
  });
  const [conflict, setConflict] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      academicApi.createSlot({
        ...form,
        semester_id: semesterId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['academic', 'slots'] });
      toast.success('Slot scheduled');
      onClose();
    },
    onError: (err: unknown) => {
      const e = err as { response?: { status?: number; data?: { detail?: string } } };
      const detail = e.response?.data?.detail;
      if (e.response?.status === 409) {
        setConflict(detail ?? 'Conflict with an existing slot.');
      } else {
        toast.error(detail ?? 'Failed to create slot');
      }
    },
  });

  return (
    <ModalShell title="Add timetable slot" onClose={onClose}>
      {conflict && (
        <div className="mb-3 flex items-start gap-2 rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <p>{conflict}</p>
        </div>
      )}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setConflict(null);
          save.mutate();
        }}
      >
        <div>
          <label className="ec-label">Class</label>
          <select
            required
            className="ec-input"
            value={form.class_id}
            onChange={(e) => setForm({ ...form, class_id: e.target.value })}
          >
            <option value="">Select class…</option>
            {(classesQ.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.course_code ? `${c.course_code} — ${c.name}` : c.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="ec-label">Room</label>
          <select
            required
            className="ec-input"
            value={form.room_id}
            onChange={(e) => setForm({ ...form, room_id: e.target.value })}
          >
            <option value="">Select room…</option>
            {(roomsQ.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
                {r.building ? ` (${r.building})` : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="ec-label">Day</label>
            <select
              className="ec-input"
              value={form.day_of_week}
              onChange={(e) =>
                setForm({
                  ...form,
                  day_of_week: parseInt(e.target.value, 10) as DayOfWeek,
                })
              }
            >
              {DAYS_OF_WEEK.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="ec-label">Start</label>
            <input
              required
              type="time"
              className="ec-input"
              value={form.start_time}
              onChange={(e) =>
                setForm({ ...form, start_time: e.target.value })
              }
            />
          </div>
          <div>
            <label className="ec-label">End</label>
            <input
              required
              type="time"
              className="ec-input"
              value={form.end_time}
              onChange={(e) =>
                setForm({ ...form, end_time: e.target.value })
              }
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            className="ec-btn-secondary"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="ec-btn-primary"
            disabled={save.isPending || !form.class_id || !form.room_id}
          >
            {save.isPending ? 'Saving…' : 'Schedule slot'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
