/**
 * AchievementsGrid — render every achievement (locked + unlocked) in a
 * responsive grid. Tier-coloured halos, animated unlock state, tooltips
 * with description + XP. Hover lifts the card; click flips for unlock
 * date.
 */
import { motion } from 'framer-motion';
import * as Icons from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useGamification, type Achievement } from '../../store/gamification';

const TIER_LABEL: Record<string, string> = {
  common: 'Common',
  rare: 'Rare',
  epic: 'Epic',
  legendary: 'Legendary',
};

const TIER_RING: Record<string, string> = {
  common: 'ring-1 ring-border',
  rare: 'ring-1 ring-brand-500/40',
  epic: 'ring-2 ring-fuchsia-500/40',
  legendary: 'ring-2 ring-amber-500/60 animate-pulse-glow',
};

function AchievementCard({ a }: { a: Achievement }) {
  const Icon = (Icons as any)[a.icon] ?? Icons.Trophy;
  const [flipped, setFlipped] = useState(false);
  return (
    <motion.button
      type="button"
      onClick={() => setFlipped((f) => !f)}
      whileHover={{ y: -3 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: 'spring', stiffness: 280, damping: 22 }}
      className={`relative w-full overflow-hidden rounded-xl border border-border bg-surface-elevated p-4 text-left transition ${
        a.unlocked ? TIER_RING[a.tier] ?? '' : 'opacity-70 grayscale'
      }`}
      aria-label={`${a.label} — ${a.unlocked ? 'unlocked' : 'locked'}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl text-white shadow-sm ${
            !a.unlocked ? 'bg-surface-muted text-ink-muted' : ''
          }`}
          style={a.unlocked ? { backgroundColor: `#${a.color}` } : undefined}
        >
          <Icon className="h-6 w-6" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink">{a.label}</p>
          {flipped && a.unlocked && a.unlocked_at ? (
            <p className="mt-0.5 text-xs text-ink-muted">
              Unlocked {new Date(a.unlocked_at).toLocaleString()}
            </p>
          ) : (
            <p className="mt-0.5 line-clamp-2 text-xs text-ink-muted">{a.description}</p>
          )}
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            a.tier === 'legendary'
              ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
              : a.tier === 'epic'
                ? 'bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-900/40 dark:text-fuchsia-200'
                : a.tier === 'rare'
                  ? 'bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-200'
                  : 'bg-surface-muted text-ink-muted'
          }`}
        >
          {TIER_LABEL[a.tier]}
        </span>
        <span className="text-xs font-semibold text-ink-muted">+{a.xp} XP</span>
      </div>
    </motion.button>
  );
}

export function AchievementsGrid() {
  const achievements = useGamification(s => s.achievements);
  const fetch = useGamification(s => s.fetch);
  const [filter, setFilter] = useState<'all' | 'unlocked' | 'locked'>('all');

  useEffect(() => {
    fetch();
  }, [fetch]);

  const unlockedCount = achievements.filter(a => a.unlocked).length;

  const list = useMemo(() => {
    if (filter === 'unlocked') return achievements.filter(a => a.unlocked);
    if (filter === 'locked') return achievements.filter(a => !a.unlocked);
    return achievements;
  }, [achievements, filter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Achievements</h2>
          <p className="text-xs text-ink-muted">
            {unlockedCount} of {achievements.length} unlocked
          </p>
        </div>
        <div role="tablist" aria-label="Filter achievements" className="inline-flex rounded-lg border border-border bg-surface-muted p-1 text-xs">
          {(['all', 'unlocked', 'locked'] as const).map((k) => (
            <button
              key={k}
              role="tab"
              aria-selected={filter === k}
              onClick={() => setFilter(k)}
              className={`rounded-md px-3 py-1 capitalize transition ${
                filter === k ? 'bg-surface-elevated text-ink shadow-card' : 'text-ink-muted hover:text-ink'
              }`}
            >
              {k}
            </button>
          ))}
        </div>
      </div>
      <div className="ec-stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {list.map((a) => (
          <AchievementCard key={a.key} a={a} />
        ))}
      </div>
    </div>
  );
}
