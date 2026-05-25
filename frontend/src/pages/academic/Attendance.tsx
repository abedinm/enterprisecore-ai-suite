import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ClipboardCheck, FileBarChart2, Save } from 'lucide-react';
import {
  academicApi,
  ATTENDANCE_STATUS_OPTIONS,
  todayIso,
  type AttendanceRecord,
  type AttendanceStatus,
  type EnrolledStudent,
} from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';

/**
 * Attendance hub. Staff (admin/manager/registrar/dean + teacher) mark a roster
 * per class + date. Students see a read-only summary table of their own
 * attendance across all enrolled classes — they never see a marking UI.
 */
export function AcademicAttendancePage() {
  const user = useAuthStore((s) => s.user);
  const isStaff = isAcademicStaff(user?.role);

  if (!isStaff) return <StudentAttendanceView />;
  return <StaffAttendanceView />;
}

/* -------------------------------------------------------------------------- */
/*  Student view: read-only summary                                            */
/* -------------------------------------------------------------------------- */

function StudentAttendanceView() {
  const summaryQ = useQuery({
    queryKey: ['academic', 'my-attendance'],
    queryFn: () => academicApi.getMyAttendance(),
  });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">My attendance</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Your attendance across every class you're enrolled in. Talk to your
          teacher about anything that looks wrong — only staff can edit these records.
        </p>
      </div>
      {summaryQ.isLoading && (
        <p className="text-sm text-ink-muted">Loading…</p>
      )}
      {summaryQ.data && summaryQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No attendance records yet.
        </p>
      )}
      {summaryQ.data && summaryQ.data.length > 0 && (
        <div className="ec-card overflow-x-auto">
          <table className="ec-table">
            <thead>
              <tr>
                <th>Class</th>
                <th className="text-right">Present</th>
                <th className="text-right">Late</th>
                <th className="text-right">Excused</th>
                <th className="text-right">Absent</th>
                <th className="text-right">Total</th>
                <th className="text-right">%</th>
              </tr>
            </thead>
            <tbody>
              {summaryQ.data.map((row) => (
                <tr key={row.class_id}>
                  <td>
                    <p className="font-medium">{row.class_name}</p>
                    {row.course_code && (
                      <p className="text-xs font-mono text-ink-muted">
                        {row.course_code}
                      </p>
                    )}
                  </td>
                  <td className="text-right">{row.present}</td>
                  <td className="text-right">{row.late}</td>
                  <td className="text-right">{row.excused}</td>
                  <td className="text-right">{row.absent}</td>
                  <td className="text-right text-ink-muted">{row.total}</td>
                  <td className="text-right">
                    <span
                      className={
                        row.percentage >= 75
                          ? 'ec-badge-green'
                          : row.percentage >= 60
                          ? 'ec-badge-amber'
                          : 'ec-badge-rose'
                      }
                    >
                      {Math.round(row.percentage)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Staff view: mark + report                                                  */
/* -------------------------------------------------------------------------- */

function StaffAttendanceView() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const initialClassId = params.get('classId') ?? '';
  const initialMode = params.get('mode') === 'report' ? 'report' : 'mark';

  const [classId, setClassId] = useState(initialClassId);
  const [date, setDate] = useState(todayIso());
  const [mode, setMode] = useState<'mark' | 'report'>(initialMode);
  const [roster, setRoster] = useState<
    Record<string, AttendanceStatus>
  >({});

  // Sync URL with state so deep-links from class detail keep working.
  useEffect(() => {
    const next: Record<string, string> = {};
    if (classId) next.classId = classId;
    if (mode === 'report') next.mode = 'report';
    setParams(next, { replace: true });
  }, [classId, mode, setParams]);

  const classesQ = useQuery({
    queryKey: ['academic', 'classes'],
    queryFn: () => academicApi.listClasses(),
  });

  const detailQ = useQuery({
    queryKey: ['academic', 'class', classId],
    queryFn: () => academicApi.getClass(classId),
    enabled: !!classId,
  });

  const sessionQ = useQuery({
    queryKey: ['academic', 'attendance-session', classId, date],
    queryFn: () => academicApi.getAttendanceSession(classId, date),
    enabled: !!classId && mode === 'mark',
  });

  const reportQ = useQuery({
    queryKey: ['academic', 'attendance-report', classId],
    queryFn: () => academicApi.getAttendanceReport(classId),
    enabled: !!classId,
  });

  // Whenever the roster + session arrive, hydrate the local roster state.
  useEffect(() => {
    if (!detailQ.data) return;
    const next: Record<string, AttendanceStatus> = {};
    for (const s of detailQ.data.students ?? []) {
      next[s.student_id] = 'present';
    }
    for (const r of sessionQ.data ?? []) {
      next[r.student_id] = r.status;
    }
    setRoster(next);
  }, [detailQ.data, sessionQ.data]);

  const save = useMutation({
    mutationFn: () => {
      const records: AttendanceRecord[] = Object.entries(roster).map(
        ([student_id, status]) => ({ student_id, status }),
      );
      return academicApi.markAttendance(classId, {
        session_date: date,
        records,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ['academic', 'attendance-session', classId, date],
      });
      qc.invalidateQueries({
        queryKey: ['academic', 'attendance-report', classId],
      });
      toast.success('Attendance saved');
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      toast.error(detail ?? 'Failed to save attendance');
    },
  });

  const reportLookup = useMemo(() => {
    const out: Record<string, { pct: number; total: number }> = {};
    for (const row of reportQ.data ?? []) {
      out[row.student_id] = { pct: row.percentage, total: row.total };
    }
    return out;
  }, [reportQ.data]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Attendance</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Pick a class, choose a date, and tag each student. Records save in bulk.
        </p>
      </div>

      <div className="ec-card grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
        <div>
          <label className="ec-label">Class</label>
          <select
            className="ec-input"
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
          >
            <option value="">Select a class…</option>
            {(classesQ.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.course_code ? `${c.course_code} — ${c.name}` : c.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="ec-label">Date</label>
          <input
            type="date"
            className="ec-input"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            disabled={mode === 'report'}
          />
        </div>
        <div className="flex flex-col">
          <label className="ec-label">Mode</label>
          <div className="flex h-full items-stretch overflow-hidden rounded-lg border border-border">
            <button
              type="button"
              className={
                mode === 'mark'
                  ? 'bg-brand-600 px-3 text-sm font-medium text-white'
                  : 'px-3 text-sm text-ink-muted hover:text-ink'
              }
              onClick={() => setMode('mark')}
            >
              <ClipboardCheck size={14} className="inline mr-1" /> Mark
            </button>
            <button
              type="button"
              className={
                mode === 'report'
                  ? 'bg-brand-600 px-3 text-sm font-medium text-white'
                  : 'px-3 text-sm text-ink-muted hover:text-ink'
              }
              onClick={() => setMode('report')}
            >
              <FileBarChart2 size={14} className="inline mr-1" /> Report
            </button>
          </div>
        </div>
        <div className="flex items-end">
          {mode === 'mark' && (
            <button
              type="button"
              className="ec-btn-primary"
              onClick={() => save.mutate()}
              disabled={!classId || save.isPending}
            >
              <Save size={14} /> {save.isPending ? 'Saving…' : 'Save attendance'}
            </button>
          )}
        </div>
      </div>

      {!classId && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          Pick a class above to begin.
        </p>
      )}

      {classId && mode === 'mark' && (
        <MarkRoster
          students={detailQ.data?.students ?? []}
          roster={roster}
          onChange={(student_id, status) =>
            setRoster((r) => ({ ...r, [student_id]: status }))
          }
          lookup={reportLookup}
          loading={detailQ.isLoading || sessionQ.isLoading}
        />
      )}

      {classId && mode === 'report' && (
        <ReportTable loading={reportQ.isLoading} rows={reportQ.data ?? []} />
      )}
    </div>
  );
}

function MarkRoster({
  students,
  roster,
  onChange,
  lookup,
  loading,
}: {
  students: EnrolledStudent[];
  roster: Record<string, AttendanceStatus>;
  onChange: (id: string, status: AttendanceStatus) => void;
  lookup: Record<string, { pct: number; total: number }>;
  loading: boolean;
}) {
  if (loading) return <p className="text-sm text-ink-muted">Loading roster…</p>;
  if (!students.length)
    return (
      <p className="ec-card p-6 text-center text-sm text-ink-muted">
        No students enrolled in this class.
      </p>
    );

  return (
    <div className="ec-card overflow-x-auto">
      <table className="ec-table">
        <thead>
          <tr>
            <th>Student</th>
            {ATTENDANCE_STATUS_OPTIONS.map((opt) => (
              <th key={opt.value} className="text-center">
                {opt.label}
              </th>
            ))}
            <th className="text-right">Running %</th>
          </tr>
        </thead>
        <tbody>
          {students.map((s) => {
            const current = roster[s.student_id] ?? 'present';
            const stats = lookup[s.student_id];
            return (
              <tr key={s.student_id}>
                <td>
                  <p className="font-medium">{s.name}</p>
                  {s.email && (
                    <p className="text-xs text-ink-muted">{s.email}</p>
                  )}
                </td>
                {ATTENDANCE_STATUS_OPTIONS.map((opt) => (
                  <td key={opt.value} className="text-center">
                    <input
                      type="radio"
                      name={`attendance-${s.student_id}`}
                      checked={current === opt.value}
                      onChange={() => onChange(s.student_id, opt.value)}
                      aria-label={`${opt.label} for ${s.name}`}
                    />
                  </td>
                ))}
                <td className="text-right">
                  {stats && stats.total > 0 ? (
                    <span
                      className={
                        stats.pct >= 75
                          ? 'ec-badge-green'
                          : stats.pct >= 60
                          ? 'ec-badge-amber'
                          : 'ec-badge-rose'
                      }
                    >
                      {Math.round(stats.pct)}%
                    </span>
                  ) : (
                    <span className="text-xs text-ink-subtle">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ReportTable({
  loading,
  rows,
}: {
  loading: boolean;
  rows: { student_id: string; name: string; present: number; absent: number; late: number; excused: number; total: number; percentage: number }[];
}) {
  if (loading) return <p className="text-sm text-ink-muted">Loading report…</p>;
  if (!rows.length)
    return (
      <p className="ec-card p-6 text-center text-sm text-ink-muted">
        No attendance recorded yet for this class.
      </p>
    );
  return (
    <div className="ec-card overflow-x-auto">
      <table className="ec-table">
        <thead>
          <tr>
            <th>Student</th>
            <th className="text-right">Present</th>
            <th className="text-right">Late</th>
            <th className="text-right">Excused</th>
            <th className="text-right">Absent</th>
            <th className="text-right">Total</th>
            <th className="text-right">%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.student_id}>
              <td className="font-medium">{r.name}</td>
              <td className="text-right">{r.present}</td>
              <td className="text-right">{r.late}</td>
              <td className="text-right">{r.excused}</td>
              <td className="text-right">{r.absent}</td>
              <td className="text-right text-ink-muted">{r.total}</td>
              <td className="text-right">
                <span
                  className={
                    r.percentage >= 75
                      ? 'ec-badge-green'
                      : r.percentage >= 60
                      ? 'ec-badge-amber'
                      : 'ec-badge-rose'
                  }
                >
                  {Math.round(r.percentage)}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
