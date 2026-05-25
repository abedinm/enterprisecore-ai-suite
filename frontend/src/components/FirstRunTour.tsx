/**
 * FirstRunTour — spotlight-style coach marks shown to new users on first
 * dashboard load. Five steps, each highlighting a real DOM element by id,
 * with a tooltip card next to it.
 *
 *  - Step 1: sidebar — "Your modules live here"
 *  - Step 2: topbar search — "Find anything in seconds"
 *  - Step 3: command palette hint — "Press Cmd+K from anywhere"
 *  - Step 4: notifications — "Stay on top of what's new"
 *  - Step 5: theme toggle — "Make it yours"
 *
 * Persists "completed" per user in localStorage; never shows twice.
 */
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../store/auth';

type Step = {
  id: string;
  title: string;
  body: string;
  /** Optional CSS selector to highlight. If omitted, centred card only. */
  selector?: string;
};

const STEPS: Step[] = [
  { id: 'sidebar',
    selector: 'aside.lg\\:flex',
    title: 'Your modules live here',
    body: 'Finance, CRM, HR, AI Brain, and more. Switch any time.' },
  { id: 'search',
    selector: 'header [role="search"], header input[type="search"]',
    title: 'Find anything in seconds',
    body: 'Search across invoices, customers, employees, deals, and notes.' },
  { id: 'cmdk',
    title: 'Press Cmd or Ctrl + K',
    body: 'Open the command palette to jump between modules without a mouse.' },
  { id: 'bell',
    selector: 'header button[aria-label*="Notification" i]',
    title: 'Stay on top of what\'s new',
    body: 'Real-time alerts surface here. We never spam.' },
  { id: 'theme',
    selector: 'header button[aria-label*="mode" i]',
    title: 'Make it yours',
    body: 'Pick light or dark, change the colour palette, or turn off animations.' },
];

const LS_KEY_PREFIX = 'ec.tour.v1.';

function isCompleted(userId: string): boolean {
  try { return localStorage.getItem(LS_KEY_PREFIX + userId) === 'done'; }
  catch { return true; }
}
function markCompleted(userId: string) {
  try { localStorage.setItem(LS_KEY_PREFIX + userId, 'done'); } catch { /* */ }
}

export function FirstRunTour() {
  const user = useAuthStore(s => s.user);
  const userId = user?.id ?? '';
  const [stepIdx, setStepIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [active, setActive] = useState(false);
  const ref = useRef<number | null>(null);

  // Show only when authenticated AND not previously completed AND not on
  // first paint (give the layout a beat to mount).
  useEffect(() => {
    if (!userId || isCompleted(userId)) return;
    const t = window.setTimeout(() => setActive(true), 800);
    return () => window.clearTimeout(t);
  }, [userId]);

  // Recompute highlight rect when step changes or window resizes.
  useEffect(() => {
    if (!active) return;
    const step = STEPS[stepIdx];
    function compute() {
      if (!step.selector) {
        setRect(null);
        return;
      }
      const el = document.querySelector(step.selector) as HTMLElement | null;
      if (!el) {
        setRect(null);
        return;
      }
      const r = el.getBoundingClientRect();
      setRect(r);
    }
    compute();
    window.addEventListener('resize', compute);
    window.addEventListener('scroll', compute, true);
    return () => {
      window.removeEventListener('resize', compute);
      window.removeEventListener('scroll', compute, true);
    };
  }, [active, stepIdx]);

  function next() {
    if (stepIdx < STEPS.length - 1) setStepIdx(stepIdx + 1);
    else finish();
  }
  function finish() {
    setActive(false);
    if (userId) markCompleted(userId);
  }

  if (!active) return null;
  const step = STEPS[stepIdx];

  // Card position: if we have a rect, anchor near it; otherwise centre.
  let cardStyle: React.CSSProperties = {
    left: '50%',
    top: '50%',
    transform: 'translate(-50%, -50%)',
  };
  if (rect) {
    const cardTop = Math.min(window.innerHeight - 220, Math.max(80, rect.bottom + 12));
    const cardLeft = Math.min(window.innerWidth - 360, Math.max(16, rect.left));
    cardStyle = { left: cardLeft, top: cardTop };
  }

  return (
    <div className="fixed inset-0 z-[55]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* Spotlight overlay — uses radial-gradient mask to cut a hole around the target. */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-ink/55 backdrop-blur-[2px]"
        style={
          rect
            ? {
                WebkitMaskImage: `radial-gradient(circle at ${rect.left + rect.width / 2}px ${rect.top + rect.height / 2}px, transparent ${Math.max(rect.width, rect.height) / 2 + 20}px, black ${Math.max(rect.width, rect.height) / 2 + 60}px)`,
                maskImage: `radial-gradient(circle at ${rect.left + rect.width / 2}px ${rect.top + rect.height / 2}px, transparent ${Math.max(rect.width, rect.height) / 2 + 20}px, black ${Math.max(rect.width, rect.height) / 2 + 60}px)`,
              }
            : undefined
        }
        onClick={finish}
      />
      <AnimatePresence mode="wait">
        <motion.div
          key={step.id}
          initial={{ opacity: 0, y: 8, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -6, scale: 0.96 }}
          transition={{ type: 'spring', stiffness: 320, damping: 24 }}
          className="absolute w-[320px] rounded-2xl border border-border bg-surface-elevated p-4 shadow-floating"
          style={cardStyle}
        >
          <p className="text-[10px] font-semibold uppercase tracking-wider text-brand-600">
            Step {stepIdx + 1} of {STEPS.length}
          </p>
          <h3 id="tour-title" className="mt-0.5 text-base font-semibold text-ink">{step.title}</h3>
          <p className="mt-1 text-sm text-ink-muted">{step.body}</p>
          <div className="mt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={finish}
              className="text-xs font-medium text-ink-muted hover:text-ink"
            >
              Skip tour
            </button>
            <div className="flex items-center gap-2">
              {STEPS.map((s, i) => (
                <span
                  key={s.id}
                  aria-hidden="true"
                  className={`h-1.5 rounded-full transition-all ${i === stepIdx ? 'w-5 bg-brand-600' : 'w-1.5 bg-surface-muted'}`}
                />
              ))}
              <button
                type="button"
                onClick={next}
                className="ec-btn-primary px-3 py-1.5 text-xs"
              >
                {stepIdx === STEPS.length - 1 ? 'Got it' : 'Next'}
              </button>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
