/**
 * ConfirmDialog — accessible scale-in confirm prompt with backdrop blur.
 *
 *   const confirm = useConfirm();
 *   const ok = await confirm({
 *     title: 'Delete invoice INV-001?',
 *     body:  'This cannot be undone.',
 *     danger: true,
 *     confirmLabel: 'Delete invoice',
 *   });
 *
 * Implemented as a portal-mounted singleton so any component can call
 * `useConfirm()` without wiring up state of its own.
 */
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { create } from 'zustand';
import { createPortal } from 'react-dom';
import { useEffect, useRef } from 'react';
import { useFocusTrap } from '../hooks/useFocusTrap';

type ConfirmOpts = {
  title: string;
  body?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

type State = {
  opts: ConfirmOpts | null;
  resolver: ((value: boolean) => void) | null;
  ask: (opts: ConfirmOpts) => Promise<boolean>;
  resolve: (v: boolean) => void;
};

const useConfirmStore = create<State>((set, get) => ({
  opts: null,
  resolver: null,
  ask(opts) {
    return new Promise<boolean>((resolve) => {
      set({ opts, resolver: resolve });
    });
  },
  resolve(v) {
    const { resolver } = get();
    if (resolver) resolver(v);
    set({ opts: null, resolver: null });
  },
}));

export function useConfirm() {
  return useConfirmStore((s) => s.ask);
}

export function ConfirmDialogHost() {
  const opts = useConfirmStore((s) => s.opts);
  const resolve = useConfirmStore((s) => s.resolve);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  // Focus Cancel by default for danger prompts — accident-resistant.
  // Focus Confirm for non-destructive prompts so Enter has the natural
  // "OK" semantic.
  useFocusTrap(dialogRef, Boolean(opts), opts?.danger ? cancelRef : confirmRef);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!opts) return;
      if (e.key === 'Escape') resolve(false);
      // Enter only auto-confirms when the user has focused the confirm
      // button explicitly — otherwise it would fire from the cancel-default.
      if (e.key === 'Enter' && document.activeElement === confirmRef.current) resolve(true);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [opts, resolve]);

  if (typeof document === 'undefined') return null;
  return createPortal(
    <AnimatePresence>
      {opts && (
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] grid place-items-center bg-ink/45 backdrop-blur-sm"
          onClick={() => resolve(false)}
        >
          <motion.div
            ref={dialogRef}
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            className="ec-modal w-full max-w-md overflow-hidden rounded-2xl border border-border bg-surface-elevated shadow-floating"
            onClick={(e) => e.stopPropagation()}
            aria-describedby={opts.body ? 'confirm-body' : undefined}
          >
            <div className="flex items-start gap-3 p-5">
              {opts.danger && (
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-900/40 dark:text-rose-300">
                  <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <h2 id="confirm-title" className="text-base font-semibold text-ink">{opts.title}</h2>
                {opts.body && <p id="confirm-body" className="mt-1 text-sm text-ink-muted">{opts.body}</p>}
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-border bg-surface-muted/60 px-5 py-3">
              <button
                ref={cancelRef}
                type="button"
                onClick={() => resolve(false)}
                className="ec-btn-secondary px-3 py-1.5 text-sm"
              >
                {opts.cancelLabel ?? 'Cancel'}
              </button>
              <button
                ref={confirmRef}
                type="button"
                onClick={() => resolve(true)}
                className={`${opts.danger ? 'ec-btn-danger' : 'ec-btn-primary'} px-3 py-1.5 text-sm`}
              >
                {opts.confirmLabel ?? 'Confirm'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
