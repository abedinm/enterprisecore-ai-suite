import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ClipboardCheck, FileBarChart2, Users } from 'lucide-react';
import { academicApi } from '../../lib/academic';
import { useAuthStore } from '../../store/auth';
import { isAcademicStaff } from '../../lib/academicRoles';

export function AcademicClassDetailPage() {
  const { classId = '' } = useParams();
  const user = useAuthStore((s) => s.user);
  const isStaff = isAcademicStaff(user?.role);

  const detailQ = useQuery({
    queryKey: ['academic', 'class', classId],
    queryFn: () => academicApi.getClass(classId),
    enabled: !!classId,
  });

  if (detailQ.isLoading) {
    return <p className="text-sm text-ink-muted">Loading class…</p>;
  }
  if (detailQ.isError || !detailQ.data) {
    return (
      <div className="ec-card border-rose-300 bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
        <p className="font-semibold">Could not load class</p>
        <p className="mt-1">It may have been removed or you don't have access.</p>
      </div>
    );
  }

  const cls = detailQ.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to="/academic/classes"
            className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink"
          >
            <ArrowLeft size={12} /> Back to classes
          </Link>
          <h2 className="mt-2 text-xl font-semibold">{cls.name}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            {cls.course_code && (
              <span className="font-mono">{cls.course_code}</span>
            )}
            {cls.teacher_name && <span>· {cls.teacher_name}</span>}
            {cls.credit_hours > 0 && <span>· {cls.credit_hours} credits</span>}
          </div>
          {cls.description && (
            <p className="mt-2 max-w-2xl text-sm text-ink-muted">{cls.description}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {isStaff && (
            <Link
              to={`/academic/attendance?classId=${cls.id}`}
              className="ec-btn-primary"
            >
              <ClipboardCheck size={14} /> Mark attendance
            </Link>
          )}
          {isStaff && (
            <Link
              to={`/academic/attendance?classId=${cls.id}&mode=report`}
              className="ec-btn-secondary"
            >
              <FileBarChart2 size={14} /> Attendance report
            </Link>
          )}
          {!isStaff && (
            <Link
              to={`/academic/attendance`}
              className="ec-btn-secondary"
            >
              <FileBarChart2 size={14} /> View my attendance
            </Link>
          )}
        </div>
      </div>

      <div className="ec-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="font-semibold inline-flex items-center gap-2">
            <Users size={16} className="text-brand-600" /> Roster
          </p>
          <span className="text-xs text-ink-muted">{cls.students?.length ?? 0} enrolled</span>
        </div>
        {(!cls.students || cls.students.length === 0) && (
          <p className="p-6 text-center text-sm text-ink-muted">
            No students enrolled yet.
          </p>
        )}
        {cls.students && cls.students.length > 0 && (
          <table className="ec-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Enrolled</th>
              </tr>
            </thead>
            <tbody>
              {cls.students.map((s) => (
                <tr key={s.student_id}>
                  <td className="font-medium">{s.name}</td>
                  <td className="text-ink-muted">{s.email ?? '—'}</td>
                  <td className="text-ink-muted">{s.enrolled_at ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
