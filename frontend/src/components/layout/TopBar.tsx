import { LogOut, Menu, Moon, Search, Sun, UserCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion } from 'framer-motion';
import { GlobalSearch } from '../search/GlobalSearch';
import { NotificationBell } from '../notifications/NotificationBell';
import { LocaleSwitcher } from '../LocaleSwitcher';
import { useAuthStore } from '../../store/auth';
import { useThemeStore } from '../../store/theme';
import { cn } from '../../lib/utils';
import { LevelMeter } from '../gamification/LevelMeter';
import { StreakChip } from '../gamification/StreakChip';
import { useGamification } from '../../store/gamification';

type TopBarProps = {
  online: boolean;
  onOpenMobileSidebar: () => void;
  onOpenSearch: () => void;
};

export function TopBar({ online, onOpenMobileSidebar, onOpenSearch }: TopBarProps) {
  const { user, logout } = useAuthStore();
  const { resolved, toggle } = useThemeStore();
  const navigate = useNavigate();
  const { t } = useTranslation();

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-surface-elevated/70 px-3 backdrop-blur-xl supports-[backdrop-filter]:bg-surface-elevated/60 lg:px-6">
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
          {online ? t('common.online') : t('common.offline')}
        </span>
        {/* Gamification chips — hidden on mobile to save bar real estate. */}
        <div className="hidden md:flex md:items-center md:gap-1.5">
          <LevelMeter compact />
          <StreakChip />
        </div>
        <LocaleSwitcher />
        <button
          aria-label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          title={resolved === 'dark' ? 'Light mode' : 'Dark mode'}
          onClick={toggle}
          className="ec-btn-ghost relative overflow-hidden"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={resolved}
              initial={{ y: -10, opacity: 0, rotate: -90 }}
              animate={{ y: 0, opacity: 1, rotate: 0 }}
              exit={{ y: 10, opacity: 0, rotate: 90 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="inline-flex"
            >
              {resolved === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </motion.span>
          </AnimatePresence>
        </button>
        <NotificationBell />
        <button
          onClick={() => navigate('/settings')}
          className="group flex items-center gap-2 rounded-lg px-2 py-1 text-left text-sm transition hover:bg-surface-muted"
          title="Open settings"
        >
          <AvatarWithRing user={user} />
          <div className="hidden text-left lg:block">
            <p className="text-sm font-medium leading-tight">{user?.full_name ?? 'Account'}</p>
            <p className="text-[11px] text-ink-muted leading-tight">{user?.role ?? '—'}</p>
          </div>
        </button>
        <button
          aria-label={t('auth.signOut')}
          title={t('auth.signOut')}
          onClick={() => logout()}
          className="ec-btn-ghost"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}

/**
 * Avatar with an animated gradient ring. The ring is brand by default;
 * once the user is on a 7+ day login streak it switches to flame colours
 * (orange → rose → amber). Animated only when motion is enabled.
 */
function AvatarWithRing({ user }: { user: ReturnType<typeof useAuthStore.getState>['user'] }) {
  // Pull streak from the gamification store without importing it eagerly —
  // lazy require keeps this file small for code-splitting.
  const streak = useGamificationStreak();
  const hot = streak >= 7;
  const ringGradient = hot
    ? 'conic-gradient(from 0deg, #fb923c, #f43f5e, #f59e0b, #fb923c)'
    : 'conic-gradient(from 0deg, rgb(var(--brand-400)), rgb(var(--brand-700)), rgb(var(--brand-500)), rgb(var(--brand-400)))';
  return (
    <span className="relative inline-grid h-9 w-9 place-items-center">
      <motion.span
        aria-hidden="true"
        className="absolute inset-0 rounded-full"
        style={{ background: ringGradient }}
        animate={{ rotate: 360 }}
        transition={{ duration: hot ? 6 : 14, ease: 'linear', repeat: Infinity }}
      />
      <span className="absolute inset-[2px] rounded-full bg-surface-elevated" />
      <span className="relative grid h-[28px] w-[28px] place-items-center overflow-hidden rounded-full bg-brand-600/15 text-brand-700 dark:text-brand-300">
        {user?.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={user.full_name}
            className="h-full w-full object-cover"
          />
        ) : (
          <UserCircle2 size={18} />
        )}
      </span>
    </span>
  );
}

function useGamificationStreak(): number {
  return useGamification((s) => s.progress?.streak?.current ?? 0);
}
