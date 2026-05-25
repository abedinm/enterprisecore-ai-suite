import { useMemo } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Activity,
  Building2,
  CreditCard,
  KeyRound,
  Lock,
  ScrollText,
  Settings as SettingsIcon,
  Shield,
  ShieldCheck,
  UserCog,
  Users,
  Webhook,
} from 'lucide-react';
import { cn } from '../../lib/utils';

type SubNavItem = {
  to: string;
  label: string;
  icon: typeof SettingsIcon;
  end?: boolean;
};

const SUB_NAV: SubNavItem[] = [
  { to: '/org',             label: 'General',     icon: SettingsIcon, end: true },
  { to: '/org/users',       label: 'Users',       icon: Users },
  { to: '/org/billing',     label: 'Billing',     icon: CreditCard },
  { to: '/org/sso',         label: 'SSO',         icon: ShieldCheck },
  { to: '/org/scim',        label: 'SCIM',        icon: KeyRound },
  { to: '/org/roles',       label: 'Roles',       icon: UserCog },
  { to: '/org/encryption',  label: 'Encryption',  icon: Lock },
  { to: '/org/security',    label: 'Security',    icon: Shield },
  { to: '/org/webhooks',    label: 'Webhooks',    icon: Webhook },
  { to: '/org/privacy',     label: 'Privacy',     icon: ScrollText },
  { to: '/org/usage',       label: 'Usage',       icon: Activity },
];

/**
 * Top-level org-settings shell. Mirrors the marketing/academic layout —
 * vertical sub-nav on lg+, horizontal scroll strip on mobile.
 */
export function OrgLayout() {
  const nav = useMemo(() => SUB_NAV, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Account</p>
          <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
            <Building2 className="text-brand-600" size={26} />
            Organization settings
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Manage your tenant: billing, identity, security, compliance, and integrations.
          </p>
        </div>
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

/** Common helper to render the 403 (insufficient permission) state. */
export function PermissionDenied({ what }: { what: string }) {
  return (
    <div className="ec-card border-amber-300 bg-amber-50 p-4 text-sm text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
      You don&apos;t have permission to {what}. Ask an admin in your organization.
    </div>
  );
}
