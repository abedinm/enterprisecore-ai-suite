import { useMemo } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  BookMarked,
  Calendar,
  CalendarClock,
  ClipboardCheck,
  ClipboardList,
  FlaskConical,
  GraduationCap,
  Handshake,
  LayoutDashboard,
  Library,
  Lightbulb,
  Users,
  Users2,
  Wallet,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAuthStore } from '../../store/auth';

type SubNavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
};

const SUB_NAV: SubNavItem[] = [
  { to: '/academic',                label: 'Dashboard',     icon: LayoutDashboard, end: true },
  { to: '/academic/classes',        label: 'Classes',       icon: BookMarked },
  { to: '/academic/attendance',     label: 'Attendance',    icon: ClipboardCheck },
  { to: '/academic/timetable',      label: 'Timetable',     icon: CalendarClock },
  { to: '/academic/lms',            label: 'LMS Library',   icon: Library },
  { to: '/academic/lab-reports',    label: 'Lab Reports',   icon: FlaskConical },
  { to: '/academic/exams',          label: 'Exams',         icon: ClipboardList },
  { to: '/academic/advising',       label: 'Advising',      icon: Handshake },
  { to: '/academic/group-projects', label: 'Group Projects',icon: Users2 },
  { to: '/academic/study-aids',     label: 'Study Aids',    icon: Lightbulb },
  { to: '/academic/study-buddies',  label: 'Study Buddies', icon: Users },
  { to: '/academic/finance',        label: 'Finance',       icon: Wallet },
  { to: '/academic/deadlines',      label: 'Deadlines',     icon: Calendar },
];

/**
 * Layout wrapper for every /academic/* route. Mirrors MarketingLayout: a
 * vertical secondary sidebar on lg+ and a horizontal pill strip on mobile.
 * The active user role appears in the header so it's obvious which views are
 * available — the backend gates the data either way.
 */
export function AcademicLayout() {
  const nav = useMemo(() => SUB_NAV, []);
  const user = useAuthStore((s) => s.user);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Module workspace</p>
          <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
            <GraduationCap className="text-brand-600" size={26} />
            Academic
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Classes, attendance, timetable, and the surrounding teaching-and-learning tools.
            Most views are role-aware — teachers see what they teach, students see what they're enrolled in.
          </p>
        </div>
        {user && (
          <div className="ec-card flex items-center gap-2 px-3 py-2 text-xs">
            <span className="text-ink-subtle">Signed in as</span>
            <span className="font-medium">{user.full_name}</span>
            <span className="ec-badge-blue">Role: {user.role}</span>
          </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="ec-card overflow-hidden p-0">
          <nav className="hidden lg:flex flex-col py-2">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2.5 border-l-2 px-3 py-2 text-sm transition',
                    isActive
                      ? 'border-brand-600 bg-brand-600/10 text-ink font-medium'
                      : 'border-transparent text-ink-muted hover:bg-surface-muted hover:text-ink',
                  )
                }
              >
                <item.icon size={16} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="lg:hidden">
            <div className="flex gap-1 overflow-x-auto px-2 py-2">
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      'flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition',
                      isActive
                        ? 'bg-brand-600 text-white'
                        : 'bg-surface-muted text-ink-muted hover:text-ink',
                    )
                  }
                >
                  <item.icon size={13} />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        </aside>

        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
