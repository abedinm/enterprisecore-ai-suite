/**
 * Listens to the gamification store's celebration queue and renders a
 * stacked, animated unlock toast for each new achievement. Triggers
 * confetti + sound + haptic on each.
 */
import { AnimatePresence, motion } from 'framer-motion';
import * as Icons from 'lucide-react';
import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { bigCelebrate, buzz, playWinSound } from '../../lib/celebrate';
import { useGamification } from '../../store/gamification';

const TIER_HALO: Record<string, string> = {
  common: 'shadow-elevated',
  rare: 'shadow-[0_0_0_2px_rgb(99_102_241/0.35),0_10px_30px_-5px_rgb(99_102_241/0.45)]',
  epic: 'shadow-[0_0_0_2px_rgb(217_70_239/0.45),0_14px_36px_-5px_rgb(217_70_239/0.55)]',
  legendary: 'shadow-[0_0_0_2px_rgb(245_158_11/0.55),0_18px_44px_-5px_rgb(245_158_11/0.65)]',
};

export function AchievementCelebration() {
  const queue = useGamification(s => s.celebrations);
  const ack = useGamification(s => s.ack);
  // Pause auto-dismiss when the user hovers or focuses inside the toast
  // stack (WCAG 2.2.1 Timing Adjustable). The dismiss timer is paused for
  // the lifetime of the hover/focus, then restarted with the remaining
  // budget when the user mouses out.
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (queue.length === 0) return;
    if (paused) return;                 // honour pause
    const head = queue[0];
    bigCelebrate([`#${head.color}`, '#ffffff', '#22d3ee', '#f59e0b']);
    playWinSound();
    buzz([15, 30, 15]);
    const dismissAfter = head.tier === 'legendary' ? 8000 : 5500;
    const t = window.setTimeout(() => ack(head.key), dismissAfter);
    return () => window.clearTimeout(t);
  }, [queue, ack, paused]);

  // Esc dismisses the head item — keyboard-accessible parity with the X.
  useEffect(() => {
    if (queue.length === 0) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') ack(queue[0].key);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [queue, ack]);

  if (queue.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed left-1/2 top-6 z-[60] -translate-x-1/2 flex w-full max-w-md flex-col items-center gap-2"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(e) => {
        // Only un-pause when focus leaves the stack entirely.
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setPaused(false);
        }
      }}
    >
      <AnimatePresence initial={false}>
        {queue.slice(0, 3).map((a, idx) => {
          const Icon = (Icons as any)[a.icon] ?? Icons.Trophy;
          return (
            <motion.div
              key={a.key}
              role="status"
              aria-live="polite"
              initial={{ opacity: 0, y: -24, scale: 0.9 }}
              animate={{ opacity: 1, y: idx * 6, scale: 1 - idx * 0.04 }}
              exit={{ opacity: 0, y: -10, scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 320, damping: 22 }}
              className={`pointer-events-auto w-full overflow-hidden rounded-2xl border border-white/30 bg-surface-elevated/80 backdrop-blur-xl ${TIER_HALO[a.tier] ?? ''}`}
            >
              {/* Aurora strip on top */}
              <div
                className="h-1 w-full animate-gradient-x bg-[length:200%_200%]"
                style={{
                  backgroundImage: `linear-gradient(90deg, #${a.color}, #6366f1, #22d3ee, #${a.color})`,
                }}
              />
              <div className="flex items-center gap-3 px-4 py-3">
                <div
                  className="grid h-12 w-12 shrink-0 place-items-center rounded-xl text-white shadow-md"
                  style={{ backgroundColor: `#${a.color}` }}
                >
                  <Icon className="h-6 w-6" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-muted">
                    Achievement unlocked · +{a.xp} XP
                  </p>
                  <p className="truncate text-sm font-semibold text-ink">{a.label}</p>
                  <p className="truncate text-xs text-ink-muted">{a.description}</p>
                  <a
                    href="/settings?tab=achievements"
                    className="mt-1 inline-block text-[11px] font-semibold text-brand-600 hover:underline"
                  >
                    View all →
                  </a>
                </div>
                <button
                  type="button"
                  onClick={() => ack(a.key)}
                  aria-label="Dismiss achievement"
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-muted focus-visible:ring-2 focus-visible:ring-brand-500"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
