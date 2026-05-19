import {
  BookOpen,
  Boxes,
  Brain,
  Building2,
  Code2,
  FileText,
  Home,
  MessageSquare,
  Search,
  Settings,
  Shield,
  Sparkles,
  Users,
  WalletCards,
  X,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '../../lib/utils';

type NavItem = {
  to: string;
  label: string;
  icon: typeof Home;
  group: string;
};

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: Home, group: 'Overview' },
  { to: '/search', label: 'Search', icon: Search, group: 'Overview' },

  { to: '/finance', label: 'Finance', icon: WalletCards, group: 'Operations' },
  { to: '/hr', label: 'HR', icon: Users, group: 'Operations' },
  { to: '/crm', label: 'CRM', icon: Building2, group: 'Operations' },
  { to: '/projects', label: 'Projects', icon: Boxes, group: 'Operations' },
  { to: '/inventory', label: 'Inventory', icon: Boxes, group: 'Operations' },

  { to: '/documents', label: 'Documents', icon: FileText, group: 'Workspace' },
  { to: '/communication', label: 'Communication', icon: MessageSquare, group: 'Workspace' },
  { to: '/wiki', label: 'Wiki', icon: BookOpen, group: 'Workspace' },

  { to: '/coding', label: 'AI Coding', icon: Code2, group: 'AI' },
  { to: '/ai', label: 'AI Brain', icon: Brain, group: 'AI' },

  { to: '/security', label: 'Security', icon: Shield, group: 'System' },
  { to: '/settings', label: 'Settings', icon: Settings, group: 'System' },
];

const GROUPS = ['Overview', 'Operations', 'Workspace', 'AI', 'System'] as const;

type SidebarProps = {
  mobileOpen: boolean;
  onCloseMobile: () => void;
};

function SidebarBody({ onItemClick }: { onItemClick?: () => void }) {
  return (
    <>
      <div className="flex h-16 items-center gap-3 border-b border-border px-5">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
          <Sparkles size={20} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">EnterpriseCore</p>
          <p className="truncate text-xs text-ink-muted">AI Suite</p>
        </div>
      </div>
      <nav className="space-y-5 overflow-y-auto p-3">
        {GROUPS.map((group) => {
          const items = NAV.filter((n) => n.group === group);
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
                          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition',
                          isActive
                            ? 'bg-brand-600 text-white shadow-sm'
                            : 'text-ink-muted hover:bg-surface-muted hover:text-ink',
                        )
                      }
                    >
                      <Icon size={17} />
                      <span>{item.label}</span>
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
