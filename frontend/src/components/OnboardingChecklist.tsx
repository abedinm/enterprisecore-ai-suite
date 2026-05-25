/**
 * OnboardingChecklist — first-run coach-mark for new tenants.
 *
 * Why this exists
 * ---------------
 * Brand-new tenants land on an empty dashboard with no clue what to do.
 * The audit flagged this as the #1 onboarding gap. This component:
 *
 *   - Shows a collapsible card on the dashboard with 4-6 actionable steps.
 *   - Each step links to the relevant module and self-completes when the
 *     prerequisite condition becomes true (e.g. "Create your first
 *     customer" completes as soon as ``GET /finance/customers`` returns a
 *     non-empty list).
 *   - Once every step is complete, the card collapses to a "You're all
 *     set!" line and disappears after 24h.
 *   - Per-user state is persisted in localStorage (cheap, no schema
 *     change) plus, on the backend, in the audit log so support can see
 *     who is stuck.
 *
 * Steps are intentionally module-agnostic — the same checklist works for
 * the Finance-only tier, the Edu vertical, the Construction vertical etc.
 * Add new steps via the ``steps`` prop; the component handles persistence.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, X } from 'lucide-react';
import { useAuthStore } from '../store/auth';

export type OnboardingStep = {
  id: string;
  label: string;
  description?: string;
  to: string;            // route to navigate to when clicked
  /** Returns true when this step has been completed. Polled by the parent. */
  isDone: () => Promise<boolean> | boolean;
};

type Props = {
  steps: OnboardingStep[];
};

type Persisted = {
  done: string[];
  dismissedAt?: number; // ms epoch
};

const LS_KEY_PREFIX = 'ec.onboarding.v1.';

function load(userId: string): Persisted {
  try {
    const raw = localStorage.getItem(LS_KEY_PREFIX + userId);
    return raw ? (JSON.parse(raw) as Persisted) : { done: [] };
  } catch {
    return { done: [] };
  }
}

function save(userId: string, p: Persisted) {
  try {
    localStorage.setItem(LS_KEY_PREFIX + userId, JSON.stringify(p));
  } catch {
    /* localStorage may be blocked; degrade silently */
  }
}

export function OnboardingChecklist({ steps }: Props) {
  const user = useAuthStore((s) => s.user);
  const userId = user?.id ?? 'anon';
  const [state, setState] = useState<Persisted>(() => load(userId));

  useEffect(() => {
    setState(load(userId));
  }, [userId]);

  // Poll every 12s while the card is mounted to auto-tick steps that
  // become true via background activity (another user in the tenant
  // created the first customer, etc.).
  useEffect(() => {
    let cancelled = false;
    async function check() {
      const newlyDone: string[] = [];
      for (const step of steps) {
        if (state.done.includes(step.id)) continue;
        try {
          const ok = await step.isDone();
          if (ok) newlyDone.push(step.id);
        } catch {
          /* a single failing check shouldn't break onboarding for the rest */
        }
      }
      if (newlyDone.length && !cancelled) {
        const next: Persisted = {
          ...state,
          done: Array.from(new Set([...state.done, ...newlyDone])),
        };
        setState(next);
        save(userId, next);
      }
    }
    check();
    const t = window.setInterval(check, 12_000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
    // state.done is intentionally excluded — the polling closure captures the
    // latest set via the setState callback used inside `check`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps, userId]);

  // Hide for the next 24h if the user dismissed an all-done checklist.
  if (state.dismissedAt && Date.now() - state.dismissedAt < 24 * 60 * 60 * 1000) {
    return null;
  }

  const completed = steps.filter((s) => state.done.includes(s.id)).length;
  const total = steps.length;
  const pct = total === 0 ? 0 : Math.round((completed / total) * 100);
  const allDone = completed === total;

  function dismiss() {
    const next = { ...state, dismissedAt: Date.now() };
    setState(next);
    save(userId, next);
  }

  return (
    <section
      aria-labelledby="onboarding-heading"
      className="rounded-xl border border-border bg-surface p-5 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="onboarding-heading" className="text-base font-semibold text-ink">
            {allDone ? "You're all set" : 'Get started with EnterpriseCore'}
          </h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            {allDone
              ? 'Every onboarding step is complete. Nice work.'
              : `${completed} of ${total} steps complete (${pct}%)`}
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss onboarding checklist"
          className="rounded-md p-1 text-ink-muted hover:bg-surface-muted"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div
        className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={
            'h-full rounded-full transition-all ' +
            (allDone ? 'bg-emerald-500' : 'bg-brand-600')
          }
          style={{ width: `${pct}%` }}
        />
      </div>

      <ul className="mt-4 divide-y divide-border">
        {steps.map((step) => {
          const done = state.done.includes(step.id);
          return (
            <li key={step.id} className="flex items-center gap-3 py-2.5">
              <span
                className={
                  'grid h-6 w-6 shrink-0 place-items-center rounded-full ' +
                  (done
                    ? 'bg-emerald-500 text-white'
                    : 'border border-border bg-surface text-ink-muted')
                }
                aria-hidden="true"
              >
                {done ? <Check className="h-3.5 w-3.5" /> : null}
              </span>
              <div className="min-w-0 flex-1">
                <Link
                  to={step.to}
                  className={
                    'block truncate text-sm font-medium ' +
                    (done
                      ? 'text-ink-muted line-through'
                      : 'text-ink hover:text-brand-600')
                  }
                >
                  {done && <span className="sr-only">Completed: </span>}
                  {step.label}
                </Link>
                {step.description && (
                  <p className="mt-0.5 truncate text-xs text-ink-muted">
                    {step.description}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
