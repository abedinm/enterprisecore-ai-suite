import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { BookMarked, Users } from 'lucide-react';
import { academicApi } from '../../lib/academic';

export function AcademicClassesPage() {
  const classesQ = useQuery({
    queryKey: ['academic', 'classes'],
    queryFn: () => academicApi.listClasses(),
  });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Classes</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Every class visible to you under the current license. Open a class to
          view its roster, mark attendance, or pull the per-student report.
        </p>
      </div>

      {classesQ.isLoading && (
        <p className="text-sm text-ink-muted">Loading classes…</p>
      )}

      {classesQ.data && classesQ.data.length === 0 && (
        <p className="ec-card p-6 text-center text-sm text-ink-muted">
          No classes yet. Once classes are created in the academic schema they'll appear here.
        </p>
      )}

      {classesQ.data && classesQ.data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {classesQ.data.map((cls) => (
            <Link
              key={cls.id}
              to={`/academic/classes/${cls.id}`}
              className="ec-card flex flex-col gap-3 p-4 transition hover:border-brand-500/40 hover:bg-surface-muted/30"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-base font-semibold">{cls.name}</p>
                  {cls.course_code && (
                    <p className="mt-0.5 text-xs font-mono text-ink-muted">
                      {cls.course_code}
                    </p>
                  )}
                </div>
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-600/10 text-brand-600">
                  <BookMarked size={16} />
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                {cls.teacher_name && (
                  <span className="ec-badge bg-surface-muted text-ink-muted">
                    {cls.teacher_name}
                  </span>
                )}
                <span className="ec-badge bg-surface-muted text-ink-muted inline-flex items-center gap-1">
                  <Users size={11} /> {cls.enrollment_count} enrolled
                </span>
                {cls.credit_hours > 0 && (
                  <span className="ec-badge bg-surface-muted text-ink-muted">
                    {cls.credit_hours} cr
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
