import { LogOut, Menu, Moon, Search, Sun, UserCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { GlobalSearch } from '../search/GlobalSearch';
import { NotificationBell } from '../notifications/NotificationBell';
import { useAuthStore } from '../../store/auth';
import { useThemeStore } from '../../store/theme';
import { cn } from '../../lib/utils';

type TopBarProps = {
  online: boolean;
  onOpenMobileSidebar: () => void;
  onOpenSearch: () => void;
};

export function TopBar({ online, onOpenMobileSidebar, onOpenSearch }: TopBarProps) {
  const { user, logout } = useAuthStore();
  const { resolved, toggle } = useThemeStore();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-surface-elevated/95 px-3 backdrop-blur lg:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <button
          aria-label="Open menu"
          onClick={onOpenMobileSidebar}
          className="ec-btn-ghost lg:hidden"
        >
          <Menu size={20} />
        </button>
        <div className="hidden flex-1 md:block">
          <GlobalSearch onSubmit={onOpenSearch} />
        </div>
        <button
          aria-label="Search"
          onClick={onOpenSearch}
          className="ec-btn-ghost md:hidden"
        >
          <Search size={18} />
        </button>
      </div>
      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            'ec-badge hidden sm:inline-flex',
            online ? 'ec-badge-green' : 'ec-badge-amber',
          )}
        >
          <span className={cn('mr-1 inline-block h-1.5 w-1.5 rounded-full', online ? 'bg-emerald-500' : 'bg-amber-500')} />
          {online ? 'Online' : 'Offline'}
        </span>
        <button
          aria-label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={resolved === 'dark' ? 'Light mode' : 'Dark mode'}
          onClick={toggle}
          className="ec-btn-ghost"
        >
          {resolved === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <NotificationBell />
        <button
          onClick={() => navigate('/settings')}
          className="flex items-center gap-2 rounded-lg px-2 py-1 text-left text-sm hover:bg-surface-muted"
          title="Open settings"
        >
          <div className="grid h-8 w-8 place-items-center rounded-full bg-brand-600/15 text-brand-700 dark:text-brand-300">
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.full_name}
                className="h-8 w-8 rounded-full object-cover"
              />
            ) : (
              <UserCircle2 size={20} />
            )}
          </div>
          <div className="hidden text-left lg:block">
            <p className="text-sm font-medium leading-tight">{user?.full_name ?? 'Account'}</p>
            <p className="text-[11px] text-ink-muted leading-tight">{user?.role ?? '—'}</p>
          </div>
        </button>
        <button
          aria-label="Log out"
          title="Log out"
          onClick={() => logout()}
          className="ec-btn-ghost"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
