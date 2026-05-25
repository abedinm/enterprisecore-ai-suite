import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  Boxes,
  Brain,
  Building2,
  Code2,
  FileText,
  GraduationCap,
  HardHat,
  Home,
  Megaphone,
  MessageCircle,
  MessageSquare,
  Search,
  Settings,
  Shield,
  Sliders,
  Sparkles,
  Users,
  WalletCards,
  X,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { useRef } from 'react';
import { motion } from 'framer-motion';
import { api, type ModuleGroup } from '../../lib/api';
import { cn } from '../../lib/utils';

type NavItem = {
  to: string;
  label: string;
  icon: typeof Home;
  group: string;
};

// Static nav for the platform sections that aren't part of the backend module
// catalog. Dashboard/Search/Settings are always present regardless of plan.
const STATIC_NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: Home, group: 'Overview' },
  { to: '/search', label: 'Search', icon: Search, group: 'Overview' },
  { to: '/security', label: 'Security', icon: Shield, group: 'System' },
  { to: '/settings', label: 'Settings', icon: Settings, group: 'System' },
  { to: '/org', label: 'Organization', icon: Sliders, group: 'Account' },
];

// Maps a backend ``MODULE_CATALOG`` group name to its sidebar entry. Groups
// not present in this map are skipped (e.g. ``Foundation`` is internal-only).
// The backend filters this list server-side by license plan, so anything
// gated by ``feature`` (Web Chat, Marketing, Academic) auto-hides when the
// active plan doesn't include it — no client-side gate required here.
const MODULE_NAV: Record<string, { to: string; label: string; icon: typeof Home; group: string }> = {
  Finance:        { to: '/finance',       label: 'Finance',       icon: WalletCards,  group: 'Operations' },
  HR:             { to: '/hr',            label: 'HR',            icon: Users,        group: 'Operations' },
  CRM:            { to: '/crm',           label: 'CRM',           icon: Building2,    group: 'Operations' },
  Projects:       { to: '/projects',      label: 'Projects',      icon: Boxes,        group: 'Operations' },
  Inventory:      { to: '/inventory',     label: 'Inventory',     icon: Boxes,        group: 'Operations' },
  Documents:      { to: '/documents',     label: 'Documents',     icon: FileText,     group: 'Workspace' },
  Communication:  { to: '/communication', label: 'Communication', icon: MessageSquare,group: 'Workspace' },
  // "Wiki" lives inside the Communication group on the backend but has its
  // own nav slot. Render it alongside Communication when that group is on.
  'AI Coding':    { to: '/coding',        label: 'AI Coding',     icon: Code2,        group: 'AI' },
  'AI Brain':     { to: '/ai',            label: 'AI Brain',      icon: Brain,        group: 'AI' },
  'Web Chat':     { to: '/webchat',       label: 'Web Chat',      icon: MessageCircle,group: 'AI' },
  Marketing:      { to: '/marketing',     label: 'Marketing',     icon: Megaphone,    group: 'Verticals' },
  Academic:       { to: '/academic',      label: 'Academic',      icon: GraduationCap,group: 'Verticals' },
  Construction:   { to: '/construction',  label: 'Construction',  icon: HardHat,      group: 'Verticals' },
};

// Companion items that aren't module groups themselves but ride alongside
// another group. Keyed by the group that triggers them being shown.
const COMPANION_NAV: Record<string, NavItem[]> = {
  Communication: [{ to: '/wiki', label: 'Wiki', icon: BookOpen, group: 'Workspace' }],
};

const GROUP_ORDER = ['Overview', 'Operations', 'Workspace', 'AI', 'Verticals', 'System', 'Account'] as const;

type SidebarProps = {
  mobileOpen: boolean;
  onCloseMobile: () => void;
};

function useSidebarNav(): NavItem[] {
  const { data } = useQuery<{ groups: ModuleGroup[] }>({
    queryKey: ['modules'],
    queryFn: () => api.get<{ groups: ModuleGroup[] }>('/modules').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const items: NavItem[] = [...STATIC_NAV];

  // While loading, render the static nav only. As soon as /modules returns,
  // the module groups appear — already filtered by license plan server-side.
  for (const group of data?.groups ?? []) {
    const slot = MODULE_NAV[group.group];
    if (slot) items.push(slot);
    const companions = COMPANION_NAV[group.group];
    if (companions) items.push(...companions);
  }

  return items;
}

function SidebarBody({ onItemClick }: { onItemClick?: () => void }) {
  const nav = useSidebarNav();
  // 7-click easter egg on the logo.
  const clickRef = useRef<{ count: number; firstAt: number }>({ count: 0, firstAt: 0 });
  function onLogoClick() {
    const now = Date.now();
    if (now - clickRef.current.firstAt > 4000) {
      clickRef.current = { count: 1, firstAt: now };
    } else {
      clickRef.current.count += 1;
    }
    if (clickRef.current.count >= 7) {
      clickRef.current = { count: 0, firstAt: 0 };
      void import('../../store/gamification').then(m => m.useGamification.getState().track('seven_clicks'));
      void import('../../lib/celebrate').then(m => m.popConfetti({ x: 0.1, y: 0.1 }));
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={onLogoClick}
        className="flex h-16 w-full items-center gap-3 border-b border-border px-5 text-left transition hover:bg-surface-muted/50"
        aria-label="EnterpriseCore"
      >
        <div className="relative grid h-10 w-10 place-items-center overflow-hidden rounded-xl bg-gradient-aurora text-white shadow-md">
          <Sparkles size={20} className="relative z-10" />
          <span className="pointer-events-none absolute inset-0 animate-gradient-x bg-[length:200%_200%] bg-gradient-aurora opacity-90" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">EnterpriseCore</p>
          <p className="truncate text-xs text-ink-muted">AI Suite</p>
        </div>
      </button>
      <nav className="space-y-5 overflow-y-auto p-3">
        {GROUP_ORDER.map((group) => {
          const items = nav.filter((n) => n.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
                {group}
              </p>
              <div className="space-y-0.5">
                {items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      onClick={onItemClick}
                      className={({ isActive }) =>
                        cn(
                          'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-200 ease-out-expo',
                          isActive
                            ? 'text-white'
                            : 'text-ink-muted hover:bg-surface-muted hover:text-ink',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {/* Animated background — shared layoutId means the
                              pill morphs between items instead of cross-fading. */}
                          {isActive && (
                            <motion.span
                              layoutId="sidebar-active"
                              className="absolute inset-0 rounded-lg bg-gradient-brand shadow-elevated"
                              transition={{ type: 'spring', stiffness: 360, damping: 32 }}
                              aria-hidden="true"
                            />
                          )}
                          <Icon
                            size={17}
                            className={cn(
                              'relative z-10 transition-transform duration-200 ease-out-expo',
                              isActive ? '' : 'group-hover:scale-110',
                            )}
                          />
                          <span className="relative z-10">{item.label}</span>
                        </>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>
    </>
  );
}

export function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  return (
    <>
      <aside className="hidden w-72 shrink-0 flex-col border-r border-border bg-surface-elevated lg:flex">
        <SidebarBody />
      </aside>

      <div
        className={cn(
          'fixed inset-0 z-40 bg-ink/40 backdrop-blur-sm transition lg:hidden',
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onCloseMobile}
        aria-hidden
      />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-surface-elevated shadow-xl transition-transform duration-200 lg:hidden',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <button
          aria-label="Close menu"
          onClick={onCloseMobile}
          className="absolute right-2 top-2 rounded-md p-2 text-ink-muted hover:bg-surface-muted"
        >
          <X size={18} />
        </button>
        <SidebarBody onItemClick={onCloseMobile} />
      </aside>
    </>
  );
}
