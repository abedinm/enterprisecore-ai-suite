/**
 * Accessible Tabs primitive — WAI-ARIA Authoring Practices 1.2 compliant.
 *
 * Why a custom primitive
 * ----------------------
 * EnterpriseCore ships 130+ tab pages. Bespoke tab markup means inconsistent
 * keyboard behaviour and inconsistent screen-reader output. This component
 * normalises:
 *
 *   - role="tablist" / "tab" / "tabpanel"
 *   - aria-selected, aria-controls, aria-labelledby
 *   - arrow-key navigation (Left/Right, Home/End) on the tab list
 *   - focus management — only the active tab is in the tab order
 *   - URL sync — the active tab id is mirrored to ``?tab=<id>`` so deep
 *     links work and the back button moves between tabs
 *
 * The API is intentionally tiny: ``<Tabs tabs=[...] active=id onChange=...>``.
 * No render-prop gymnastics, no compound-component plumbing. Tab content
 * lives in the page; this component only owns the strip + a11y wiring.
 */
import { useCallback, useEffect, useId, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

// Track which tab ids currently have an active <TabPanel> mounted, so a
// dev-mode console.warn fires when a tabs strip declares an active id with
// no matching panel. Cheap, zero-cost in production builds.
const MOUNTED_PANELS = new Set<string>();

export type TabSpec = {
  id: string;
  label: string;
  badge?: number | string;
  /** Hide the tab from the strip but keep its id reservable. */
  hidden?: boolean;
  /** Disable the tab without removing it (e.g. plan-gated features). */
  disabled?: boolean;
};

type Props = {
  tabs: TabSpec[];
  active: string;
  onChange: (id: string) => void;
  /** Optional accessible label for the tablist. */
  ariaLabel?: string;
  /** When true, sync the active tab id to ``?tab=...`` and react to back-nav. */
  urlSync?: boolean;
  className?: string;
};

export function Tabs({
  tabs,
  active,
  onChange,
  ariaLabel = 'Tabs',
  urlSync = true,
  className = '',
}: Props) {
  const listId = useId();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  // URL → state on first mount & on browser back-nav.
  useEffect(() => {
    if (!urlSync) return;
    const fromUrl = params.get('tab');
    if (fromUrl && fromUrl !== active && tabs.some(t => t.id === fromUrl && !t.disabled)) {
      onChange(fromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // Dev-only: warn if the active tab has no corresponding <TabPanel>.
  useEffect(() => {
    if (import.meta.env.DEV) {
      const tid = setTimeout(() => {
        if (!MOUNTED_PANELS.has(active) && tabs.some((t) => t.id === active)) {
          // eslint-disable-next-line no-console
          console.warn(
            `[Tabs] active="${active}" but no <TabPanel id="${active}"> is mounted. ` +
            `Add a sibling <TabPanel id="${active}">...</TabPanel> so screen readers can ` +
            `resolve aria-controls.`,
          );
        }
      }, 50);
      return () => clearTimeout(tid);
    }
  }, [active, tabs]);

  // state → URL on change. Replace, not push — every tab click shouldn't
  // grow history; only deep-link in / out moves the entry.
  const handleChange = useCallback(
    (id: string) => {
      onChange(id);
      if (urlSync) {
        const next = new URLSearchParams(params);
        next.set('tab', id);
        navigate({ search: next.toString() }, { replace: true });
      }
    },
    [onChange, navigate, params, urlSync],
  );

  function onKey(e: React.KeyboardEvent<HTMLButtonElement>, idx: number) {
    const enabled = tabs.filter(t => !t.disabled && !t.hidden);
    const enabledIds = enabled.map(t => t.id);
    const curIdx = enabledIds.indexOf(active);
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      const next = enabled[(curIdx + 1) % enabled.length];
      if (next) {
        handleChange(next.id);
        refs.current[next.id]?.focus();
      }
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const next = enabled[(curIdx - 1 + enabled.length) % enabled.length];
      if (next) {
        handleChange(next.id);
        refs.current[next.id]?.focus();
      }
    } else if (e.key === 'Home') {
      e.preventDefault();
      const first = enabled[0];
      if (first) { handleChange(first.id); refs.current[first.id]?.focus(); }
    } else if (e.key === 'End') {
      e.preventDefault();
      const last = enabled[enabled.length - 1];
      if (last) { handleChange(last.id); refs.current[last.id]?.focus(); }
    }
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      id={listId}
      className={
        'flex flex-wrap items-center gap-1 overflow-x-auto border-b border-border ' +
        className
      }
    >
      {tabs.filter(t => !t.hidden).map((tab, idx) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            ref={(el) => { refs.current[tab.id] = el; }}
            role="tab"
            type="button"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            disabled={tab.disabled}
            onClick={() => !tab.disabled && handleChange(tab.id)}
            onKeyDown={(e) => onKey(e, idx)}
            className={[
              'group relative -mb-px inline-flex items-center gap-2 whitespace-nowrap',
              'rounded-t-md px-3 py-2 text-sm font-medium',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500',
              tab.disabled
                ? 'cursor-not-allowed text-ink-muted/60'
                : selected
                  ? 'text-brand-700 dark:text-brand-300'
                  : 'text-ink-muted hover:text-ink',
            ].join(' ')}
          >
            {tab.label}
            {tab.badge !== undefined && tab.badge !== null && tab.badge !== 0 && (
              <span
                className={
                  'ml-0.5 inline-flex h-5 min-w-5 items-center justify-center ' +
                  'rounded-full px-1.5 text-[11px] font-semibold ' +
                  (selected ? 'bg-brand-600 text-white' : 'bg-surface-muted text-ink-muted')
                }
              >
                {tab.badge}
              </span>
            )}
            {selected && (
              <span
                aria-hidden="true"
                className="absolute inset-x-0 -bottom-px h-0.5 rounded bg-brand-600"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Companion: TabPanel — pair with Tabs so the aria-labelledby/aria-controls
 * relationship is correct. Use one per tab content section:
 *
 *   <Tabs ... active={id} onChange={setId} />
 *   <TabPanel id={id}>...content...</TabPanel>
 */
export function TabPanel({
  id,
  children,
  className = '',
}: {
  id: string;
  children: React.ReactNode;
  className?: string;
}) {
  // Register/unregister with the dev-mode mounted-panel tracker.
  useEffect(() => {
    MOUNTED_PANELS.add(id);
    return () => { MOUNTED_PANELS.delete(id); };
  }, [id]);
  return (
    <section
      role="tabpanel"
      id={`tabpanel-${id}`}
      aria-labelledby={`tab-${id}`}
      tabIndex={0}
      className={'focus:outline-none ' + className}
    >
      {children}
    </section>
  );
}
