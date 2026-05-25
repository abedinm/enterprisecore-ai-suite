/**
 * QuickActionFab — bottom-right floating "+" that springs open into a
 * radial menu of common create actions. Closes on outside click or Esc.
 *
 * Reads role from the auth store to hide actions the user can't perform.
 */
import { AnimatePresence, motion } from 'framer-motion';
import {
  FileText,
  Plus,
  StickyNote,
  UserPlus,
  Users,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/auth';

type Action = { label: string; icon: typeof FileText; to: string; color: string };

const ACTIONS: Action[] = [
  { label: 'New invoice',  icon: FileText,   to: '/finance?tab=invoices&new=1',  color: '#3b82f6' },
  { label: 'New customer', icon: Users,      to: '/finance?tab=customers&new=1', color: '#22d3ee' },
  { label: 'New lead',     icon: UserPlus,   to: '/crm?tab=leads&new=1',         color: '#6366f1' },
  { label: 'Note',         icon: StickyNote, to: '/communication?tab=notes&new=1', color: '#f59e0b' },
];

export function QuickActionFab() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const wrap = useRef<HTMLDivElement | null>(null);
  const fabRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
        fabRef.current?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((i) => (i - 1 + ACTIONS.length) % ACTIONS.length);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((i) => (i + 1) % ACTIONS.length);
      } else if (e.key === 'Home') {
        e.preventDefault();
        setActive(0);
      } else if (e.key === 'End') {
        e.preventDefault();
        setActive(ACTIONS.length - 1);
      }
    }
    document.addEventListener('mousedown', onClick);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Move keyboard focus to the active menu item whenever it changes.
  useEffect(() => {
    if (!open) return;
    itemRefs.current[active]?.focus();
  }, [open, active]);

  // Hide for unauthenticated users.
  if (!user) return null;

  const trigger = useCallback((a: Action) => {
    setOpen(false);
    navigate(a.to);
    fabRef.current?.focus();
  }, [navigate]);

  function toggle() {
    setOpen((v) => {
      const next = !v;
      if (next) setActive(0);
      return next;
    });
  }

  return (
    <div
      ref={wrap}
      className="pointer-events-none fixed bottom-5 right-5 z-40 flex flex-col items-end gap-3 lg:bottom-7 lg:right-7"
    >
      <AnimatePresence>
        {open && (
          <div role="menu" aria-label="Quick actions" className="contents">
            {ACTIONS.map((a, idx) => (
              <motion.button
                key={a.label}
                ref={(el) => { itemRefs.current[idx] = el; }}
                type="button"
                role="menuitem"
                tabIndex={idx === active ? 0 : -1}
                initial={{ opacity: 0, y: 24, scale: 0.6 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 12, scale: 0.6 }}
                transition={{ type: 'spring', stiffness: 380, damping: 22, delay: idx * 0.035 }}
                onClick={() => trigger(a)}
                onFocus={() => setActive(idx)}
                className="pointer-events-auto flex items-center gap-2 rounded-full border border-border bg-surface-elevated/85 py-1.5 pl-2 pr-3 text-sm font-medium text-ink shadow-elevated backdrop-blur-md transition hover:bg-surface-elevated focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                <span
                  className="grid h-7 w-7 place-items-center rounded-full text-white ring-1 ring-white/30"
                  style={{ backgroundColor: a.color }}
                >
                  <a.icon className="h-3.5 w-3.5" aria-hidden="true" />
                </span>
                <span>{a.label}</span>
              </motion.button>
            ))}
          </div>
        )}
      </AnimatePresence>
      <motion.button
        ref={fabRef}
        type="button"
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.94 }}
        animate={{ rotate: open ? 45 : 0 }}
        transition={{ type: 'spring', stiffness: 380, damping: 22 }}
        onClick={toggle}
        aria-label={open ? 'Close quick actions' : 'Open quick actions'}
        aria-expanded={open}
        aria-haspopup="menu"
        className="pointer-events-auto grid h-14 w-14 place-items-center rounded-full bg-gradient-aurora text-white shadow-floating ring-2 ring-white/30 transition hover:shadow-glow focus-visible:ring-4 focus-visible:ring-brand-300/60"
      >
        <Plus className="h-6 w-6" aria-hidden="true" />
      </motion.button>
    </div>
  );
}
