import { useQuery } from '@tanstack/react-query';
import { Activity, BellRing, CheckCircle2, Database, LayoutDashboard, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import { api, type ModuleGroup } from '../../lib/api';
import { useAuthStore } from '../../store/auth';
import { useOnline } from '../../hooks/useOnline';
import { formatCurrency, formatNumber } from '../../lib/utils';

type Kpi = { label: string; value: number; format: 'currency' | 'number' };

type DashboardData = {
  user: { name: string; role: string };
  kpis: Kpi[];
  modules: ModuleGroup[];
  unread_notifications: number;
  offline_ready: boolean;
  projects: number;
};

export function DashboardPage() {
  const online = useOnline();
  const { user } = useAuthStore();
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardData>('/dashboard')).data,
  });

  return (
    <div className="space-y-6">
      <section className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <p className="text-sm font-medium text-brand-600">Command center</p>
          <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">
            {greeting()}, {user?.full_name?.split(' ')[0] ?? 'there'}.
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-muted">
            Everything your business needs — running locally on this machine. Add the modules you need, ignore the rest.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="ec-badge-green"><CheckCircle2 size={13} /> SQLite ready</span>
          <span className="ec-badge-blue"><Database size={13} /> Local-first</span>
          <span className={online ? 'ec-badge-green' : 'ec-badge-amber'}>
            {online ? <Wifi size={13} /> : <WifiOff size={13} />} {online ? 'Online' : 'Offline'}
          </span>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isLoading ? (
          [0, 1, 2, 3].map((i) => (
            <div key={i} className="ec-card h-24 animate-pulse p-5">
              <div className="h-3 w-20 rounded bg-surface-muted" />
              <div className="mt-3 h-6 w-32 rounded bg-surface-muted" />
            </div>
          ))
        ) : (
          data?.kpis.map((kpi) => (
            <div key={kpi.label} className="ec-card p-5">
              <p className="text-sm text-ink-muted">{kpi.label}</p>
              <p className="mt-2 text-2xl font-semibold">
                {kpi.format === 'currency' ? formatCurrency(kpi.value) : formatNumber(kpi.value)}
              </p>
            </div>
          ))
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="ec-card p-5">
          <div className="mb-4 flex items-center gap-2">
            <LayoutDashboard size={18} />
            <h2 className="text-lg font-semibold">Suite modules</h2>
          </div>
          {isLoading ? (
            <div className="grid gap-3 md:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-20 animate-pulse rounded-lg border border-border bg-surface-muted" />
              ))}
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {data?.modules.map((group) => (
                <div key={group.group} className="rounded-lg border border-border bg-surface p-4">
                  <p className="font-medium">{group.group}</p>
                  <p className="mt-2 text-xs text-ink-muted">{group.items.join(' • ')}</p>
                </div>
              ))}
            </div>
          )}
        </div>
        <aside className="space-y-4">
          <div className="ec-card p-5">
            <div className="mb-3 flex items-center gap-2">
              <Activity size={18} />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-muted">System status</h2>
            </div>
            <ul className="space-y-2 text-sm">
              <li className="flex items-center justify-between"><span>Backend</span><strong>FastAPI</strong></li>
              <li className="flex items-center justify-between"><span>Database</span><strong>{import.meta.env.DEV ? 'SQLite (dev)' : 'SQLite / PostgreSQL'}</strong></li>
              <li className="flex items-center justify-between"><span>Offline mode</span><strong>{data?.offline_ready ? 'Ready' : 'Disabled'}</strong></li>
              <li className="flex items-center justify-between"><span>Active projects</span><strong>{data?.projects ?? 0}</strong></li>
            </ul>
          </div>
          <div className="ec-card p-5">
            <div className="mb-3 flex items-center gap-2">
              <BellRing size={18} />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-muted">Inbox</h2>
            </div>
            <p className="text-3xl font-semibold">{data?.unread_notifications ?? 0}</p>
            <p className="text-xs text-ink-muted">unread notifications</p>
          </div>
          <div className="ec-card p-5">
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck size={18} />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-muted">Security</h2>
            </div>
            <p className="text-sm text-ink-muted">
              JWT auth, bcrypt password hashing, audit log on every login.
            </p>
          </div>
        </aside>
      </section>
    </div>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}
