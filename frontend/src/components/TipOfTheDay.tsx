/**
 * TipOfTheDay — friendly rotating tip card on the dashboard.
 *
 * Picks a deterministic tip from a curated pool based on the day-of-year,
 * so every user sees the same tip on the same day (helps support
 * conversations: "have you tried the tip on the dashboard today?").
 *
 * Dismissed tips don't reappear for 7 days (per user, per tip).
 */
import { AnimatePresence, motion } from 'framer-motion';
import { Lightbulb, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useAuthStore } from '../store/auth';
import { useThemeStore } from '../store/theme';

type Tip = { id: string; title: string; body: string; cta?: { label: string; to: string } };

const TIPS: Tip[] = [
  { id: 'cmdk', title: 'Speed of thought',
    body: 'Press Cmd or Ctrl + K from anywhere to jump straight to any module, action, or recent record.' },
  { id: 'palette', title: 'Make it yours',
    body: 'Settings → Appearance lets you swap the colour palette, density, and ambient backdrop in seconds.',
    cta: { label: 'Open appearance', to: '/settings?tab=appearance' } },
  { id: 'mfa', title: 'Lock it tighter',
    body: 'Turning on multi-factor auth takes 30 seconds and earns you the "Locked tight" achievement.',
    cta: { label: 'Set up MFA', to: '/settings?tab=security' } },
  { id: 'streak', title: 'Keep the rhythm',
    body: 'Sign in every day to grow your streak. Seven days unlocks a rare achievement and a small fire emoji of pride.' },
  { id: 'sessions', title: 'See where you are signed in',
    body: 'Settings → Security lists every active device. Suspicious one? Revoke it instantly.',
    cta: { label: 'View sessions', to: '/settings?tab=security' } },
  { id: 'theme', title: 'Lights out',
    body: 'Hit the moon icon in the top bar to switch to dark mode. Your eyes will thank you after 9pm.' },
  { id: 'search', title: 'Find anything',
    body: 'The global search at the top of the page indexes invoices, customers, employees, deals, notes — everything.' },
  { id: 'achievements', title: 'Collect them all',
    body: 'There are 25+ achievements waiting to be unlocked. Some are secret. Try clicking the logo seven times.',
    cta: { label: 'See achievements', to: '/settings?tab=achievements' } },
  { id: 'export', title: 'Your data, your way',
    body: 'Every list view has an export button. CSV, JSON — pick your format.' },
  { id: 'webhooks', title: 'Wire up workflows',
    body: 'Connect Slack, Zapier, or your own endpoints in Settings → Organisation → Webhooks.',
    cta: { label: 'Open webhooks', to: '/org/webhooks' } },
];

function dayOfYear(d = new Date()) {
  const start = new Date(d.getFullYear(), 0, 0);
  return Math.floor((d.getTime() - start.getTime()) / 86_400_000);
}

const LS_DISMISS_KEY = 'ec.tip.dismissed.v1';

function loadDismissed(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(LS_DISMISS_KEY) ?? '{}'); }
  catch { return {}; }
}
function saveDismissed(d: Record<string, number>) {
  try { localStorage.setItem(LS_DISMISS_KEY, JSON.stringify(d)); } catch { /* */ }
}

export function TipOfTheDay() {
  const user = useAuthStore(s => s.user);
  const reduced = useThemeStore(s => s.reducedMotion);
  const [hidden, setHidden] = useState(false);

  const tip = useMemo<Tip | null>(() => {
    const dismissed = loadDismissed();
    const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
    const eligible = TIPS.filter((t) => (dismissed[t.id] ?? 0) < sevenDaysAgo);
    if (eligible.length === 0) return null;
    // Day-of-year picks deterministically; user.id seed prevents two users
    // on the same day always seeing the same one.
    const seed = dayOfYear() + (user?.id?.charCodeAt(0) ?? 0);
    return eligible[seed % eligible.length];
  }, [user?.id]);

  if (!tip || hidden) return null;

  function dismiss() {
    const next = { ...loadDismissed(), [tip!.id]: Date.now() };
    saveDismissed(next);
    setHidden(true);
  }

  return (
    <AnimatePresence>
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-brand-500/8 via-brand-500/5 to-transparent p-4"
        aria-label="Tip of the day"
      >
        <div className="flex items-start gap-3">
          <motion.div
            animate={reduced ? { rotate: 0 } : { rotate: [-4, 4, -4] }}
            transition={reduced ? { duration: 0 } : { duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-amber-400/20 text-amber-600"
          >
            <Lightbulb className="h-5 w-5" aria-hidden="true" />
          </motion.div>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">
              Tip of the day
            </p>
            <p className="mt-0.5 text-sm font-semibold text-ink">{tip.title}</p>
            <p className="mt-0.5 text-sm text-ink-muted">{tip.body}</p>
            {tip.cta && (
              <a
                href={tip.cta.to}
                className="mt-2 inline-block text-xs font-semibold text-brand-600 hover:underline"
              >
                {tip.cta.label} →
              </a>
            )}
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss tip"
            className="rounded-md p-1 text-ink-muted hover:bg-surface-muted"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </motion.section>
    </AnimatePresence>
  );
}
