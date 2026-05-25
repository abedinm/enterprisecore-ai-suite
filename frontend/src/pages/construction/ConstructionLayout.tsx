import { useMemo, useState } from 'react';
import { NavLink, Outlet, useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Calendar,
  CalendarClock,
  ChevronDown,
  ClipboardList,
  ClipboardSignature,
  Clock,
  FileText,
  Flag,
  Folder,
  HardHat,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  Search,
  Shield,
  TrendingUp,
  Users2,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { constructionApi } from '../../lib/construction';

type SubNavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
};

function buildSubNav(projectId: string): SubNavItem[] {
  const base = `/construction/projects/${projectId}`;
  return [
    { to: base,                        label: 'Dashboard',         icon: LayoutDashboard, end: true },
    { to: `${base}/risks`,             label: 'Risks',             icon: AlertTriangle },
    { to: `${base}/schedule`,          label: 'Schedule',          icon: CalendarClock },
    { to: `${base}/milestones`,        label: 'Milestones',        icon: Flag },
    { to: `${base}/progress`,          label: 'Progress',          icon: TrendingUp },
    { to: `${base}/permits`,           label: 'Permits',           icon: FileText },
    { to: `${base}/site-instructions`, label: 'Site Instructions', icon: ClipboardList },
    { to: `${base}/variations`,        label: 'Variations',        icon: ClipboardSignature },
    { to: `${base}/extensions`,        label: 'Extensions',        icon: Clock },
    { to: `${base}/contracts`,         label: 'Contracts',         icon: FileText },
    { to: `${base}/raci`,              label: 'RACI',              icon: Users2 },
    { to: `${base}/insurances`,        label: 'Insurances',        icon: Shield },
    { to: `${base}/toolbox`,           label: 'Toolbox Talks',     icon: MessageSquare },
  ];
}

/**
 * Layout for /construction/projects/:projectId/* — header with a project
 * picker dropdown, secondary sidebar with per-project nav, and the standard
 * Outlet for the active sub-view.
 */
export function ConstructionLayout() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filter, setFilter] = useState('');

  const projectsQ = useQuery({
    queryKey: ['construction', 'projects'],
    queryFn: () => constructionApi.listProjects(),
  });

  const currentProject = useMemo(
    () => projectsQ.data?.find((p) => p.id === projectId) ?? null,
    [projectsQ.data, projectId],
  );

  const nav = useMemo(() => (projectId ? buildSubNav(projectId) : []), [projectId]);

  const filteredProjects = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const all = projectsQ.data ?? [];
    if (!q) return all;
    return all.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.client_name.toLowerCase().includes(q) ||
        (p.location ?? '').toLowerCase().includes(q),
    );
  }, [projectsQ.data, filter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Module workspace</p>
          <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
            <HardHat className="text-brand-600" size={26} />
            Construction
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Site management for construction projects — risk, schedule, milestones,
            variations, EOT, RACI, permits, contracts, insurances, and toolbox talks.
          </p>
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => setPickerOpen((v) => !v)}
            className="ec-card flex min-w-[260px] items-center justify-between gap-3 px-4 py-2.5 text-left transition hover:border-brand-500/40"
          >
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wider text-ink-subtle">Active project</p>
              <p className="truncate text-sm font-semibold">
                {currentProject ? currentProject.name : 'Select a project'}
              </p>
              {currentProject && (
                <p className="truncate text-xs text-ink-muted">{currentProject.client_name}</p>
              )}
            </div>
            <ChevronDown size={16} className="shrink-0 text-ink-muted" />
          </button>

          {pickerOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setPickerOpen(false)}
              />
              <div className="absolute right-0 z-40 mt-2 w-[340px] overflow-hidden rounded-xl border border-border bg-surface-elevated shadow-xl">
                <div className="border-b border-border p-2">
                  <div className="relative">
                    <Search
                      size={14}
                      className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted"
                    />
                    <input
                      autoFocus
                      type="text"
                      className="ec-input !pl-8"
                      placeholder="Search projects…"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    />
                  </div>
                </div>
                <ul className="max-h-72 overflow-y-auto">
                  {filteredProjects.length === 0 && (
                    <li className="p-4 text-center text-xs text-ink-muted">
                      {projectsQ.isLoading ? 'Loading…' : 'No matching projects.'}
                    </li>
                  )}
                  {filteredProjects.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        className={cn(
                          'flex w-full items-start gap-3 px-3 py-2 text-left transition hover:bg-surface-muted',
                          p.id === projectId && 'bg-brand-600/10',
                        )}
                        onClick={() => {
                          setPickerOpen(false);
                          setFilter('');
                          navigate(`/construction/projects/${p.id}`);
                        }}
                      >
                        <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-brand-600/10 text-brand-600">
                          <Folder size={14} />
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{p.name}</span>
                          <span className="block truncate text-xs text-ink-muted">
                            {p.client_name} · {p.location}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="border-t border-border p-2">
                  <button
                    type="button"
                    className="ec-btn-secondary w-full justify-center"
                    onClick={() => {
                      setPickerOpen(false);
                      navigate('/construction');
                    }}
                  >
                    <ListChecks size={14} /> View all projects
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="ec-card overflow-hidden p-0">
          <nav className="hidden flex-col py-2 lg:flex">
            <NavLink
              to="/construction"
              end
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 border-l-2 px-3 py-2 text-sm transition',
                  isActive
                    ? 'border-brand-600 bg-brand-600/10 text-ink font-medium'
                    : 'border-transparent text-ink-muted hover:bg-surface-muted hover:text-ink',
                )
              }
            >
              <ListChecks size={16} />
              <span>Projects</span>
            </NavLink>
            <div className="my-1 mx-3 border-t border-border" />
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
            {nav.length === 0 && (
              <p className="px-3 py-2 text-xs text-ink-muted">
                Select a project to view its module nav.
              </p>
            )}
          </nav>

          <div className="lg:hidden">
            <div className="flex gap-1 overflow-x-auto px-2 py-2">
              <NavLink
                to="/construction"
                end
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition',
                    isActive
                      ? 'bg-brand-600 text-white'
                      : 'bg-surface-muted text-ink-muted hover:text-ink',
                  )
                }
              >
                <ListChecks size={13} />
                <span>Projects</span>
              </NavLink>
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
