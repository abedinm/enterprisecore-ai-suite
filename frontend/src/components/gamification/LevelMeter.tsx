/**
 * LevelMeter — small "Level N" pill with an animated XP progress ring.
 *
 * Usage:
 *   <LevelMeter compact />            // for the topbar
 *   <LevelMeter />                    // full size for the dashboard card
 */
import { motion } from 'framer-motion';
import { Sparkles, Star } from 'lucide-react';
import { useEffect } from 'react';
import { useGamification } from '../../store/gamification';

type Props = { compact?: boolean; className?: string };

export function LevelMeter({ compact = false, className = '' }: Props) {
  const progress = useGamification(s => s.progress);
  const fetch = useGamification(s => s.fetch);

  useEffect(() => {
    if (!progress) fetch();
  }, [progress, fetch]);

  const level = progress?.level.level ?? 1;
  const pct = Math.round((progress?.level.progress ?? 0) * 100);
  const xp = progress?.xp ?? 0;
  const nextXp = (progress?.level.next_threshold ?? 50) - xp;

  if (compact) {
    return (
      <button
        type="button"
        aria-label={`Level ${level}, ${pct}% to next`}
        title={`Level ${level} — ${nextXp} XP to next level`}
        className={`group inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-muted/60 px-2.5 py-1 text-xs font-medium text-ink transition hover:bg-surface-muted ${className}`}
      >
        <Star className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
        <span>Lv {level}</span>
        <span className="relative h-1.5 w-16 overflow-hidden rounded-full bg-surface">
          <motion.span
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-brand-400 to-brand-600"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          />
        </span>
      </button>
    );
  }

  return (
    <div className={`ec-card-static p-4 ${className}`}>
      <div className="flex items-center gap-3">
        <div className="grid h-12 w-12 place-items-center rounded-xl bg-gradient-brand text-white shadow-md">
          <Sparkles className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
            Your level
          </p>
          <p className="text-2xl font-semibold text-ink">{level}</p>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">XP</p>
          <p className="text-lg font-semibold text-ink">{xp.toLocaleString()}</p>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-ink-muted">
        <span id="lvl-meter-label">Progress to level {level + 1}</span>
        <span>{pct}%</span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-labelledby="lvl-meter-label"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-brand-400 to-brand-600"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  );
}
