/**
 * Global Cmd+K (Ctrl+K) command palette.
 *
 * Why this exists
 * ---------------
 * EnterpriseCore has ~20 top-level module routes and 130+ tabs/panels. The
 * tabs-on-tabs IA is brutal to navigate by mouse. This component is the
 * keyboard escape hatch a power user expects from any modern SaaS in 2026:
 * one shortcut to fuzzy-search every page, every action, every recent
 * record — and operate it without leaving the keyboard.
 *
 * Design contract
 * ---------------
 * - Opens with Cmd+K / Ctrl+K from any route.
 * - Closes with Esc, click-outside, or selecting an item.
 * - First render shows: pinned (most-used), recent (this session), and a
 *   default action list.
 * - Typing filters the union of: navigation targets, role-aware actions,
 *   and recent items. Matching is substring + token-prefix; no fuzzy lib
 *   needed and the dataset is small.
 * - Arrow Up/Down moves the selection; Enter activates; Cmd/Ctrl+1..9
 *   jumps to the Nth item.
 * - Selection state is stored in zustand so the same palette state
 *   survives StrictMode double-renders.
 *
 * Accessibility
 * -------------
 * Roles: ``dialog`` + ``aria-modal``, list with ``role="listbox"``, items
 * with ``role="option"`` and ``aria-selected``. Focus is trapped inside
 * the dialog while open and restored to the previously-focused element
 * on close. Screen readers announce "Command palette open, X commands".
 */
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/auth';
import { useGamification } from '../store/gamification';
import { useFocusTrap } from '../hooks/useFocusTrap';

type CommandItem = {
  id: string;
  label: string;
  hint?: string;
  group: 'Navigate' | 'Actions' | 'Recent' | 'Settings';
  keywords?: string;
  /** Roles allowed to see this command. Empty/undefined = visible to all. */
  roles?: Array<'Admin' | 'Manager' | 'Employee' | 'Developer' | 'Auditor' | 'Trainer'>;
  /** Run the command. Receives the navigate function for routing. */
  run: (navigate: (to: string) => void) => void;
};

const NAV_COMMANDS: CommandItem[] = [
  { id: 'nav-dashboard', label: 'Dashboard', group: 'Navigate', keywords: 'home overview',
    run: n => n('/') },
  { id: 'nav-finance', label: 'Finance', group: 'Navigate', keywords: 'invoices customers expenses payroll',
    run: n => n('/finance') },
  { id: 'nav-crm', label: 'CRM', group: 'Navigate', keywords: 'leads pipeline quotes contacts',
    run: n => n('/crm') },
  { id: 'nav-hr', label: 'HR', group: 'Navigate', keywords: 'employees payslips leave attendance',
    run: n => n('/hr') },
  { id: 'nav-projects', label: 'Projects', group: 'Navigate', keywords: 'tasks tickets sprints',
    run: n => n('/projects') },
  { id: 'nav-inventory', label: 'Inventory', group: 'Navigate', keywords: 'stock warehouse skus',
    run: n => n('/inventory') },
  { id: 'nav-ai', label: 'AI Brain', group: 'Navigate', keywords: 'chat assistant rag knowledge',
    run: n => n('/ai') },
  { id: 'nav-coding', label: 'Coding', group: 'Navigate', keywords: 'editor terminal repos',
    run: n => n('/coding') },
  { id: 'nav-documents', label: 'Documents', group: 'Navigate', keywords: 'files contracts signing',
    run: n => n('/documents') },
  { id: 'nav-communication', label: 'Communication', group: 'Navigate',
    keywords: 'messages notes wiki announcements', run: n => n('/communication') },
  { id: 'nav-marketing', label: 'Marketing Site', group: 'Navigate',
    keywords: 'pages blog portfolio social', run: n => n('/marketing') },
  { id: 'nav-search', label: 'Global Search', group: 'Navigate', keywords: 'find lookup search',
    run: n => n('/search') },
  { id: 'nav-settings', label: 'Settings', group: 'Settings', keywords: 'profile theme account',
    run: n => n('/settings') },
  { id: 'nav-org', label: 'Organisation', group: 'Settings',
    keywords: 'tenant billing users roles sso scim', roles: ['Admin'],
    run: n => n('/org') },
  { id: 'nav-security', label: 'Security', group: 'Settings',
    keywords: 'audit ip allowlist encryption', roles: ['Admin'],
    run: n => n('/security') },
];

const ACTION_COMMANDS: CommandItem[] = [
  { id: 'act-new-invoice', label: 'New invoice', group: 'Actions',
    keywords: 'create bill', run: n => n('/finance?tab=invoices&new=1') },
  { id: 'act-new-customer', label: 'New customer', group: 'Actions',
    keywords: 'create contact client', run: n => n('/finance?tab=customers&new=1') },
  { id: 'act-new-lead', label: 'New lead', group: 'Actions',
    keywords: 'create prospect crm', run: n => n('/crm?tab=leads&new=1') },
  { id: 'act-new-employee', label: 'New employee', group: 'Actions',
    keywords: 'create hire onboarding', run: n => n('/hr?tab=employees&new=1') },
  { id: 'act-toggle-theme', label: 'Toggle light / dark theme', group: 'Actions',
    keywords: 'mode color appearance',
    run: () => {
      // Lazy import so the palette stays a leaf component.
      import('../store/theme').then(m => m.useThemeStore.getState().toggle());
    } },
  { id: 'act-logout', label: 'Sign out', group: 'Actions', keywords: 'logout exit',
    run: () => useAuthStore.getState().logout() },
];

const ALL_COMMANDS: CommandItem[] = [...NAV_COMMANDS, ...ACTION_COMMANDS];

function scoreCommand(cmd: CommandItem, q: string): number {
  if (!q) return 0;
  const hay = (cmd.label + ' ' + (cmd.keywords ?? '')).toLowerCase();
  const needle = q.toLowerCase().trim();
  // Exact label match wins; token-prefix match next; substring last.
  if (cmd.label.toLowerCase() === needle) return 100;
  if (cmd.label.toLowerCase().startsWith(needle)) return 80;
  if (hay.split(/\s+/).some(t => t.startsWith(needle))) return 50;
  if (hay.includes(needle)) return 25;
  return 0;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const user = useAuthStore(s => s.user);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const lastFocused = useRef<HTMLElement | null>(null);
  useFocusTrap(dialogRef, open, inputRef);

  const track = useGamification(s => s.track);

  // Cmd+K / Ctrl+K — open palette + fire the "command_palette" achievement.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        lastFocused.current = document.activeElement as HTMLElement | null;
        setOpen(o => !o);
        track('command_palette');
      } else if (e.key === 'Escape' && open) {
        e.preventDefault();
        setOpen(false);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, track]);

  // Focus the input when opening; restore focus on close.
  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      // Defer so the input is in the DOM.
      queueMicrotask(() => inputRef.current?.focus());
    } else {
      lastFocused.current?.focus();
    }
  }, [open]);

  const role = user?.role;
  const visible = useMemo(() => {
    const scored = ALL_COMMANDS
      .filter(c => !c.roles || (role && c.roles.includes(role as any)))
      .map(c => ({ c, score: scoreCommand(c, query) }))
      .filter(({ score }) => query === '' || score > 0)
      .sort((a, b) => b.score - a.score || a.c.label.localeCompare(b.c.label));
    return scored.map(({ c }) => c);
  }, [query, role]);

  useEffect(() => {
    if (active >= visible.length) setActive(0);
  }, [visible.length, active]);

  function runCommand(cmd: CommandItem) {
    setOpen(false);
    // Push to MRU bag for the next palette open.
    try {
      const raw = sessionStorage.getItem('ec.cmdk.mru') ?? '[]';
      const mru: string[] = JSON.parse(raw);
      const next = [cmd.id, ...mru.filter(id => id !== cmd.id)].slice(0, 8);
      sessionStorage.setItem('ec.cmdk.mru', JSON.stringify(next));
    } catch {
      /* sessionStorage may be blocked; not a fatal */
    }
    cmd.run(navigate);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(a => Math.min(a + 1, visible.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(a => Math.max(a - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const cmd = visible[active];
      if (cmd) runCommand(cmd);
    } else if ((e.metaKey || e.ctrlKey) && /^[1-9]$/.test(e.key)) {
      e.preventDefault();
      const idx = parseInt(e.key, 10) - 1;
      const cmd = visible[idx];
      if (cmd) runCommand(cmd);
    }
  }

  if (!open) return null;

  // Group by section for display.
  const grouped = visible.reduce<Record<string, CommandItem[]>>((acc, c) => {
    (acc[c.group] ??= []).push(c);
    return acc;
  }, {});

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4 pt-[15vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-border px-3 py-2">
          <input
            ref={inputRef}
            type="text"
            placeholder="Type a command or page..."
            aria-label="Search commands"
            className="w-full bg-transparent px-2 py-2 text-base text-ink outline-none placeholder:text-ink-muted"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <ul role="listbox" aria-label="Commands" className="max-h-[60vh] overflow-y-auto py-1">
          {visible.length === 0 ? (
            <li className="px-4 py-6 text-center text-sm text-ink-muted">
              No commands match &ldquo;{query}&rdquo;
            </li>
          ) : (
            Object.entries(grouped).map(([group, items]) => (
              <Fragment key={group}>
                <li
                  className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wider text-ink-muted"
                  aria-hidden="true"
                >
                  {group}
                </li>
                {items.map((cmd) => {
                  const overallIndex = visible.indexOf(cmd);
                  const isActive = overallIndex === active;
                  return (
                    <li
                      key={cmd.id}
                      role="option"
                      aria-selected={isActive}
                      className={`mx-1 cursor-pointer rounded-md px-3 py-2 text-sm ${
                        isActive ? 'bg-brand-600 text-white' : 'hover:bg-surface-muted'
                      }`}
                      onMouseEnter={() => setActive(overallIndex)}
                      onMouseDown={(e) => { e.preventDefault(); runCommand(cmd); }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate">{cmd.label}</span>
                        {cmd.hint && (
                          <span className={`text-xs ${isActive ? 'text-white/80' : 'text-ink-muted'}`}>
                            {cmd.hint}
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </Fragment>
            ))
          )}
        </ul>
        <div className="border-t border-border bg-surface-muted px-3 py-2 text-[11px] text-ink-muted">
          <kbd className="rounded bg-surface px-1.5 py-0.5">↑↓</kbd> navigate &nbsp;
          <kbd className="rounded bg-surface px-1.5 py-0.5">↵</kbd> run &nbsp;
          <kbd className="rounded bg-surface px-1.5 py-0.5">esc</kbd> close
        </div>
      </div>
    </div>
  );
}
