import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  BookMarked,
  CalendarClock,
  ClipboardCheck,
  GraduationCap,
  Percent,
  School,
  TimerReset,
  Users,
} from 'lucide-react';
import {
  academicApi,
  jsDayToDow,
  todayIso,
  type TimetableSlot,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { academicRoleView, type AcademicRoleView } from '../../lib/academicRoles';

function StatTile({
  label,
  value,
  icon: Icon,
  to,
}: {
  label: string;
  value: string | number;
  icon: typeof BookMarked;
  to?: string;
}) {
  const body = (
    <>
      <div>
        <p className="text-xs uppercase tracking-wider text-ink-subtle">{label}</p>
        <p className="mt-1 text-2xl font-semibold">{value}</p>
      </div>
      <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
        <Icon size={18} />
      </div>
    </>
  );
  return to ? (
    <Link
      to={to}
      className="ec-card flex items-center justify-between p-4 transition hover:border-brand-500/40 hover:bg-surface-muted/30"
    >
      {body}
    </Link>
  ) : (
    <div className="ec-card flex items-center justify-between p-4">{body}</div>
  );
}

export function AcademicDashboard() {
  const user = useAuthStore((s) => s.user);
  const view: AcademicRoleView = academicRoleView(user?.role);

  const semestersQ = useQuery({
    queryKey: ['academic', 'semesters'],
    queryFn: () => academicApi.listSemesters(),
  });
  const classesQ = useQuery({
    queryKey: ['academic', 'classes'],
    queryFn: () => academicApi.listClasses(),
  });

  const activeSemester = useMemo(
    () =>
      semestersQ.data?.find((s) => s.is_active) ?? semestersQ.data?.[0] ?? null,
    [semestersQ.data],
  );

  // Today's schedule — fetched once we know which semester is active.
  const scheduleQ = useQuery({
    queryKey: ['academic', 'dashboard-schedule', view, activeSemester?.id],
    queryFn: () => {
      if (!activeSemester) return Promise.resolve([] as TimetableSlot[]);
      if (view === 'student')
        return academicApi.myStudentSchedule(activeSemester.id);
      if (view === 'teacher')
        return academicApi.myTeacherSchedule(activeSemester.id);
      return academicApi.listSlots(activeSemester.id);
    },
    enabled: !!activeSemester,
  });

  const myAttendanceQ = useQuery({
    queryKey: ['academic', 'my-attendance'],
    queryFn: () => academicApi.getMyAttendance(),
    enabled: view === 'student',
  });

  const todayDow = jsDayToDow(new Date().getDay());
  const todaySlots = (scheduleQ.data ?? [])
    .filter((s) => s.day_of_week === todayDow)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  // Student aggregate attendance %.
  const studentAvg = useMemo(() => {
    if (view !== 'student' || !myAttendanceQ.data?.length) return null;
    const rows = myAttendanceQ.data;
    const totalSessions = rows.reduce((a, r) => a + r.total, 0);
    if (!totalSessions) return null;
    const totalPresent = rows.reduce((a, r) => a + r.present + r.late, 0);
    return Math.round((totalPresent / totalSessions) * 100);
  }, [myAttendanceQ.data, view]);

  if (semestersQ.isLoading || classesQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading academic state…</p>;
  }

  if (semestersQ.isError || classesQ.isError) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        <p className="font-semibold">Could not load academic data</p>
        <p className="mt-1">
          Make sure your license includes the Academic Module Pack and the API is reachable.
        </p>
      </div>
    );
  }

  // Empty state — no semester configured yet.
  if (!activeSemester) {
    return (
      <div className="ec-card flex flex-col items-start gap-3 p-6">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-brand-600/10 text-brand-600">
          <GraduationCap size={22} />
        </div>
        <div>
          <h2 className="text-lg font-semibold">No semester configured yet</h2>
          <p className="mt-1 max-w-xl text-sm text-ink-muted">
            The academic calendar starts with a semester. Create one to unlock
            timetable scheduling, attendance, and the rest of the module pack.
          </p>
        </div>
        <Link to="/academic/timetable" className="ec-btn-primary">
          Create your first semester <ArrowRight size={14} />
        </Link>
      </div>
    );
  }

  const myClasses = classesQ.data ?? [];

  return (
    <div className="space-y-5">
      <div className="ec-card flex flex-wrap items-start justify-between gap-3 p-5">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-subtle">Active semester</p>
          <h2 className="mt-1 text-xl font-semibold">{activeSemester.name}</h2>
          <p className="mt-1 text-xs text-ink-muted">
            {activeSemester.start_date} — {activeSemester.end_date}
          </p>
        </div>
        <Link to="/academic/timetable" className="ec-btn-secondary">
          Open timetable
        </Link>
      </div>

      {/* Role-specific tile grid */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {view === 'admin' && (
          <>
            <StatTile
              to="/academic/classes"
              label="Classes"
              value={myClasses.length}
              icon={BookMarked}
            />
            <StatTile
              label="Semesters"
              value={semestersQ.data?.length ?? 0}
              icon={GraduationCap}
            />
            <StatTile
              to="/academic/timetable"
              label="Slots today"
              value={todaySlots.length}
              icon={CalendarClock}
            />
            <StatTile
              to="/academic/timetable"
              label="Rooms"
              value="—"
              icon={School}
            />
          </>
        )}
        {view === 'teacher' && (
          <>
            <StatTile
              to="/academic/classes"
              label="My classes"
              value={myClasses.length}
              icon={BookMarked}
            />
            <StatTile
              label="Today's classes"
              value={todaySlots.length}
              icon={CalendarClock}
            />
            <StatTile
              label="Students taught"
              value={myClasses.reduce(
                (a, c) => a + (c.enrollment_count ?? 0),
                0,
              )}
              icon={Users}
            />
            <StatTile
              to="/academic/attendance"
              label="Quick: mark attendance"
              value=">"
              icon={ClipboardCheck}
            />
          </>
        )}
        {view === 'student' && (
          <>
            <StatTile
              to="/academic/attendance"
              label="My attendance"
              value={studentAvg === null ? '—' : `${studentAvg}%`}
              icon={Percent}
            />
            <StatTile
              to="/academic/classes"
              label="Enrolled classes"
              value={myClasses.length}
              icon={BookMarked}
            />
            <StatTile
              label="Today's classes"
              value={todaySlots.length}
              icon={CalendarClock}
            />
            <StatTile
              to="/academic/deadlines"
              label="Pending deadlines"
              value="—"
              icon={TimerReset}
            />
          </>
        )}
      </div>

      {/* Today's slots + alerts */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="ec-card overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <p className="font-semibold">Today's schedule</p>
            <span className="text-xs text-ink-muted">{todayIso()}</span>
          </div>
          {scheduleQ.isLoading && (
            <p className="p-5 text-sm text-ink-muted">Loading schedule…</p>
          )}
          {!scheduleQ.isLoading && todaySlots.length === 0 && (
            <p className="p-5 text-sm text-ink-muted">
              Nothing on the schedule today.
            </p>
          )}
          {todaySlots.length > 0 && (
            <ul>
              {todaySlots.map((slot) => (
                <li
                  key={slot.id}
                  className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 px-4 py-3 last:border-b-0"
                >
                  <span className="font-mono text-sm text-ink-muted">
                    {slot.start_time}–{slot.end_time}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {slot.class_name ?? slot.class_id}
                    </p>
                    {slot.course_code && (
                      <p className="text-xs text-ink-muted">
                        {slot.course_code}
                      </p>
                    )}
                  </div>
                  {slot.room_name && (
                    <span className="ec-badge bg-surface-muted text-ink-muted">
                      {slot.room_name}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-3">
          {view === 'teacher' && (
            <div className="ec-card flex items-start gap-3 border-amber-300 bg-amber-50 p-4 text-sm dark:bg-amber-900/20">
              <AlertCircle size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <p className="text-amber-700 dark:text-amber-300">
                Attendance not yet recorded for today on{' '}
                {todaySlots.length === 0
                  ? 'any class'
                  : `${todaySlots.length} class${todaySlots.length === 1 ? '' : 'es'}`}
                .{' '}
                <Link
                  to="/academic/attendance"
                  className="font-medium underline"
                >
                  Mark now
                </Link>
              </p>
            </div>
          )}
          {view === 'admin' && (
            <div className="ec-card p-4">
              <p className="text-sm font-semibold">Conflict warnings</p>
              <p className="mt-1 text-xs text-ink-muted">
                Schedule conflicts surface in the admin scheduling view inside Timetable.
              </p>
              <Link
                to="/academic/timetable"
                className="ec-btn-secondary mt-3"
              >
                Open scheduling
              </Link>
            </div>
          )}
          {view === 'student' && studentAvg !== null && studentAvg < 75 && (
            <div className="ec-card flex items-start gap-3 border-amber-300 bg-amber-50 p-4 text-sm dark:bg-amber-900/20">
              <AlertCircle size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <p className="text-amber-700 dark:text-amber-300">
                Your attendance is {studentAvg}% — most institutions require 75% to sit finals.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
