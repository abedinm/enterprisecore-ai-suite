/**
 * StreakChip — animated flame + day count. Renders inline next to the
 * user's name in the topbar and as a hero element on the dashboard.
 */
import { Flame } from 'lucide-react';
import { useEffect } from 'react';
import { useGamification } from '../../store/gamification';

export function StreakChip({ className = '' }: { className?: string }) {
  const progress = useGamification(s => s.progress);
  const fetch = useGamification(s => s.fetch);

  useEffect(() => {
    if (!progress) fetch();
  }, [progress, fetch]);

  const current = progress?.streak.current ?? 0;
  const best = progress?.streak.best ?? 0;
  if (current === 0) return null;
  const flameColor =
    current >= 30 ? 'text-rose-500'
    : current >= 7  ? 'text-amber-500'
    : 'text-orange-500';

  return (
    <span
      className={`group inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-muted/60 px-2.5 py-1 text-xs font-medium text-ink transition hover:bg-surface-muted ${className}`}
      title={`${current}-day login streak (best: ${best})`}
      aria-label={`${current} day login streak`}
    >
      <Flame className={`h-3.5 w-3.5 animate-flame ${flameColor}`} aria-hidden="true" />
      <span>{current}d</span>
    </span>
  );
}
