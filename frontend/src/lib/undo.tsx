/**
 * Undo-toast helper.
 *
 * Standardises the "you just deleted something, here's 5 seconds to undo"
 * UX. Built on top of ``react-hot-toast`` so styling and animation match
 * the rest of the app.
 *
 *   showUndoToast({
 *     message: '3 invoices deleted',
 *     onUndo: () => api.post('/finance/invoices/restore', { ids }),
 *     duration: 6000,
 *   });
 *
 * On undo: dismiss the toast, call the callback. If the user lets it
 * expire, we do nothing — the action is final.
 */
import { toast } from 'react-hot-toast';

type UndoOptions = {
  message: string;
  onUndo: () => Promise<void> | void;
  /** Default 6000 ms (matches Gmail). */
  duration?: number;
};

export function showUndoToast({ message, onUndo, duration = 6000 }: UndoOptions): void {
  const id = toast.custom(
    (t) => (
      <div
        className={[
          'pointer-events-auto flex items-center gap-4 rounded-lg border border-border',
          'bg-surface px-4 py-2.5 text-sm text-ink shadow-lg',
          t.visible ? 'animate-enter' : 'animate-leave',
        ].join(' ')}
        role="status"
        aria-live="polite"
      >
        <span>{message}</span>
        <button
          type="button"
          onClick={async () => {
            toast.dismiss(t.id);
            try {
              await onUndo();
              toast.success('Restored');
            } catch {
              toast.error('Could not undo');
            }
          }}
          className="font-semibold uppercase tracking-wider text-brand-600 hover:underline"
        >
          Undo
        </button>
      </div>
    ),
    { duration },
  );
  return id as unknown as void;
}
