import { useQuery } from '@tanstack/react-query';
import { Activity, BellRing, CheckCircle2, Database, LayoutDashboard, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import { api, type ModuleGroup } from '../../lib/api';
import { useAuthStore } from '../../store/auth';
import { useOnline } from '../../hooks/useOnline';
import { formatCurrency, formatNumber } from '../../lib/utils';
import { OnboardingChecklist, type OnboardingStep } from '../../components/OnboardingChecklist';
import { Counter, FadeIn, Stagger } from '../../components/motion';
import { LevelMeter } from '../../components/gamification/LevelMeter';
import { StreakChip } from '../../components/gamification/StreakChip';
import { TipOfTheDay } from '../../components/TipOfTheDay';

// Default first-run onboarding for the Core SKU. Each step's ``isDone`` returns
// a Promise<boolean>; the checklist auto-ticks when the prerequisite becomes
// true (e.g. a customer is created in another tab).
const DEFAULT_ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 'invite-user',
    label: 'Invite a teammate',
    description: 'Open Organisation → Users and send your first invite.',
    to: '/org/users',
    isDone: async () => {
      try {
        const r = await api.get<unknown[]>('/users');
        return Array.isArray(r.data) && r.data.length > 1;
      } catch { return false; }
    },
  },
  {
    id: 'create-customer',
    label: 'Add your first customer',
    description: 'Finance → Customers. Sets you up to invoice in minutes.',
    to: '/finance?tab=customers',
    isDone: async () => {
      try {
        const r = await api.get<unknown[]>('/finance/customers');
        return Array.isArray(r.data) && r.data.length > 0;
      } catch { return false; }
    },
  },
  {
    id: 'send-invoice',
    label: 'Send your first invoice',
    description: 'Pick a customer, set an amount, hit Send.',
    to: '/finance?tab=invoices',
    isDone: async () => {
      try {
        const r = await api.get<unknown[]>('/finance/invoices');
        return Array.isArray(r.data) && r.data.length > 0;
      } catch { return false; }
    },
  },
  {
    id: 'add-employee',
    label: 'Add an employee record',
    description: 'HR → Employees. Even one record unlocks the org chart.',
    to: '/hr?tab=employees',
    isDone: async () => {
      try {
        const r = await api.get<unknown[]>('/hr/employees');
        return Array.isArray(r.data) && r.data.length > 0;
      } catch { return false; }
    },
  },
  {
    id: 'enable-mfa',
    label: 'Enable multi-factor auth',
    description: 'Settings → Security. Protects your tenant from credential theft.',
    to: '/settings?tab=security',
    isDone: async () => {
      try {
        const r = await api.get<{ enabled: boolean }>('/auth/mfa/status');
        return Boolean(r.data?.enabled);
      } catch { return false; }
    },
  },
];

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
            {moodLine()}
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

      <TipOfTheDay />

      <OnboardingChecklist steps={DEFAULT_ONBOARDING_STEPS} />

      {isLoading && (
        <div role="status" aria-live="polite" className="sr-only">
          Loading dashboard KPIs
        </div>
      )}
      <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {isLoading ? (
          [0, 1, 2, 3].map((i) => (
            <FadeIn key={i}>
              <div className="ec-card-static h-24 p-5" aria-hidden="true">
                <div className="ec-shimmer h-3 w-20 rounded" />
                <div className="ec-shimmer mt-3 h-6 w-32 rounded" />
              </div>
            </FadeIn>
          ))
        ) : (
          (data?.kpis ?? []).map((kpi) => (
            <FadeIn key={kpi.label}>
              <div className="ec-card-gradient p-5 ec-lift cursor-default">
                <p className="text-sm text-ink-muted">{kpi.label}</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums">
                  {kpi.format === 'currency' ? (
                    <Counter
                      to={kpi.value}
                      duration={1.1}
                      format={(v) => formatCurrency(Math.round(v))}
                    />
                  ) : (
                    <Counter
                      to={kpi.value}
                      duration={1.1}
                      format={(v) => formatNumber(Math.round(v))}
                    />
                  )}
                </p>
              </div>
            </FadeIn>
          ))
        )}
      </Stagger>

      {/* Gamification strip — level meter + streak. Renders gracefully even
          when the gamification fetch hasn't returned yet. */}
      <FadeIn>
        <section className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <LevelMeter />
          <div className="ec-card-static flex items-center gap-3 p-4">
            <div className="text-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Streak</p>
              <p className="text-ink">Keep the rhythm going.</p>
            </div>
            <StreakChip />
          </div>
        </section>
      </FadeIn>

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
  if (hour < 5)  return 'Burning the midnight oil';
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  if (hour < 21) return 'Good evening';
  return 'Working late';
}

/** Sub-line that picks a tiny mood line based on time + day-of-week. */
function moodLine(): string {
  const d = new Date();
  const dow = d.getDay();          // 0 = Sunday
  const hour = d.getHours();
  if (dow === 1 && hour < 12)  return 'Fresh start. One step at a time.';
  if (dow === 5 && hour >= 15) return 'Friday wind-down — finish strong.';
  if (dow === 0 || dow === 6)  return 'A quiet weekend session.';
  if (hour < 9)                return 'Quiet morning — perfect for clearing the inbox.';
  if (hour >= 21)              return 'Late shift. We see you.';
  if (hour >= 14 && hour < 16) return 'Post-lunch focus block.';
  return "Let's make today count.";
}
