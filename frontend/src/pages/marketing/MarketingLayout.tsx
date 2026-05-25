import { useMemo } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  ExternalLink,
  FileText,
  HelpCircle,
  Image as ImageIcon,
  LayoutDashboard,
  LayoutGrid,
  LayoutTemplate,
  Megaphone,
  MessageSquareQuote,
  Navigation as NavigationIcon,
  Newspaper,
  Settings as SettingsIcon,
  Share2,
  Sparkles,
  Users,
} from 'lucide-react';
import { cn } from '../../lib/utils';

type SubNavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
};

const SUB_NAV: SubNavItem[] = [
  { to: '/marketing',                label: 'Dashboard',    icon: LayoutDashboard,    end: true },
  { to: '/marketing/pages',          label: 'Pages',        icon: LayoutGrid },
  { to: '/marketing/templates',      label: 'Templates',    icon: LayoutTemplate },
  { to: '/marketing/settings',       label: 'Settings',     icon: SettingsIcon },
  { to: '/marketing/navigation',     label: 'Navigation',   icon: NavigationIcon },
  { to: '/marketing/portfolio',      label: 'Portfolio',    icon: Sparkles },
  { to: '/marketing/blog',           label: 'Blog',         icon: Newspaper },
  { to: '/marketing/services',       label: 'Services',     icon: FileText },
  { to: '/marketing/testimonials',   label: 'Testimonials', icon: MessageSquareQuote },
  { to: '/marketing/faqs',           label: 'FAQs',         icon: HelpCircle },
  { to: '/marketing/team',           label: 'Team',         icon: Users },
  { to: '/marketing/social',         label: 'Social',       icon: Share2 },
  { to: '/marketing/media',          label: 'Media',        icon: ImageIcon },
];

/**
 * Wrapper around every /marketing/* route. Renders a sticky secondary
 * sidebar on lg+ screens and a horizontal scroll tab strip on mobile. The
 * actual page lives in the right-hand column via <Outlet />.
 */
export function MarketingLayout() {
  // Memo'd nav so NavLink renders aren't churning identity-checked props.
  const nav = useMemo(() => SUB_NAV, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-brand-600">Module workspace</p>
          <h1 className="mt-1 flex items-center gap-2 text-3xl font-semibold">
            <Megaphone className="text-brand-600" size={26} />
            Marketing
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Build and publish the public marketing site for your business.
            Edits land instantly — the live site re-renders on every save.
          </p>
        </div>
        <a
          href="/site/"
          target="_blank"
          rel="noopener noreferrer"
          className="ec-btn-secondary"
        >
          <ExternalLink size={16} /> Preview site
        </a>
      </div>

      <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        {/* Secondary sidebar — sticky on desktop, horizontal tabs on mobile. */}
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

