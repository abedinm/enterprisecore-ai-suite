/**
 * SaveButton — three-state button (idle → saving → saved) with motion.
 *
 *   <SaveButton onSave={async () => api.post(...)}>Save changes</SaveButton>
 *
 * The component owns its own loading + success state; consumers just hand it
 * an async action. After 1.4s the icon morphs back to the idle label so the
 * button can be pressed again.
 */
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Loader2 } from 'lucide-react';
import { type ReactNode, useState } from 'react';
import { popConfetti, playTickSound } from '../lib/celebrate';

type Props = {
  onSave: () => Promise<void> | void;
  children: ReactNode;
  className?: string;
  celebrate?: boolean;
  disabled?: boolean;
};

type State = 'idle' | 'saving' | 'saved' | 'error';

export function SaveButton({ onSave, children, className = '', celebrate = false, disabled = false }: Props) {
  const [state, setState] = useState<State>('idle');

  async function handle(e: React.MouseEvent<HTMLButtonElement>) {
    if (state === 'saving') return;
    setState('saving');
    try {
      await onSave();
      setState('saved');
      playTickSound();
      if (celebrate) {
        const r = e.currentTarget.getBoundingClientRect();
        popConfetti({
          x: (r.left + r.width / 2) / window.innerWidth,
          y: (r.top + r.height / 2) / window.innerHeight,
        });
      }
      window.setTimeout(() => setState('idle'), 1400);
    } catch {
      setState('error');
      window.setTimeout(() => setState('idle'), 1800);
    }
  }

  const colourClass =
    state === 'error'
      ? 'bg-rose-600 hover:bg-rose-700'
      : state === 'saved'
        ? 'bg-emerald-600 hover:bg-emerald-700'
        : '';

  return (
    <button
      type="button"
      onClick={handle}
      disabled={disabled || state === 'saving'}
      className={`ec-btn-primary relative overflow-hidden ${colourClass} ${className}`}
      aria-live="polite"
    >
      <AnimatePresence mode="wait" initial={false}>
        {state === 'idle' && (
          <motion.span
            key="idle"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
            className="inline-flex items-center gap-2"
          >
            {children}
          </motion.span>
        )}
        {state === 'saving' && (
          <motion.span
            key="saving"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18 }}
            className="inline-flex items-center gap-2"
          >
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Saving…
          </motion.span>
        )}
        {state === 'saved' && (
          <motion.span
            key="saved"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.6 }}
            transition={{ type: 'spring', stiffness: 360, damping: 20 }}
            className="inline-flex items-center gap-2"
          >
            <Check className="h-4 w-4" aria-hidden="true" />
            Saved
          </motion.span>
        )}
        {state === 'error' && (
          <motion.span
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, x: [0, -6, 6, -4, 4, 0] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2"
          >
            Try again
          </motion.span>
        )}
      </AnimatePresence>
    </button>
  );
}
