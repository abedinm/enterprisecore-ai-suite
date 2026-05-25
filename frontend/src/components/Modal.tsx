/**
 * Modal — accessible dialog primitive used across the suite.
 *
 *   role="dialog" + aria-modal + aria-labelledby
 *   focus trap (uses useFocusTrap)
 *   Escape closes
 *   backdrop click closes (configurable via closeOnBackdrop)
 *   restores focus to the trigger on unmount (via useFocusTrap)
 *
 * Render with a sibling `<ModalClose>` for a pre-labelled "Close" X.
 *
 *   <Modal open={open} onClose={close} title="Edit task" labelledBy="task-modal-title">
 *     <ModalHeader>
 *       <h2 id="task-modal-title">Edit task</h2>
 *       <ModalClose onClose={close} />
 *     </ModalHeader>
 *     <ModalBody>…</ModalBody>
 *     <ModalFooter>…</ModalFooter>
 *   </Modal>
 */
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useEffect, useId, useRef, type ReactNode, type RefObject } from 'react';
import { useFocusTrap } from '../hooks/useFocusTrap';

type Size = 'sm' | 'md' | 'lg' | 'xl';

const SIZE_CLASS: Record<Size, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
};

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  /** Visible heading text. Used to wire aria-labelledby automatically. */
  title?: string;
  /** Override the auto-generated id used by aria-labelledby. */
  labelledBy?: string;
  /** Optional id pointing at descriptive body text. */
  describedBy?: string;
  /** Defaults to 'md'. */
  size?: Size;
  /** Close when the user clicks the backdrop. Defaults to true. */
  closeOnBackdrop?: boolean;
  /** Initial focus target inside the dialog. Defaults to first tabbable. */
  initialFocus?: RefObject<HTMLElement | null>;
  /** Tailwind classes appended to the dialog panel. */
  panelClassName?: string;
  children: ReactNode;
};

export function Modal({
  open,
  onClose,
  title,
  labelledBy,
  describedBy,
  size = 'md',
  closeOnBackdrop = true,
  initialFocus,
  panelClassName = '',
  children,
}: ModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const autoId = useId();
  const titleId = labelledBy ?? (title ? `modal-title-${autoId}` : undefined);

  useFocusTrap(dialogRef, open, initialFocus);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  // Lock background scroll while the dialog is open — prevents a focus-trap
  // overflow situation where the user can scroll the page underneath.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (typeof document === 'undefined') return null;
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] grid place-items-center bg-ink/45 p-4 backdrop-blur-sm"
          onMouseDown={(e) => {
            if (closeOnBackdrop && e.target === e.currentTarget) onClose();
          }}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={describedBy}
            initial={{ opacity: 0, scale: 0.96, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 6 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            className={`ec-modal w-full ${SIZE_CLASS[size]} overflow-hidden rounded-2xl border border-border bg-surface-elevated shadow-floating ${panelClassName}`}
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Hidden title fallback when caller passes `title` but no children
                that already include the heading. Keeps aria-labelledby valid. */}
            {title && !labelledBy && (
              <h2 id={titleId} className="sr-only">
                {title}
              </h2>
            )}
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

export function ModalHeader({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex items-center justify-between border-b border-border px-5 py-3 ${className}`}>
      {children}
    </div>
  );
}

export function ModalBody({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`p-5 ${className}`}>{children}</div>;
}

export function ModalFooter({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex justify-end gap-2 border-t border-border bg-surface-muted/40 px-5 py-3 ${className}`}>
      {children}
    </div>
  );
}

export type ModalCloseProps = {
  onClose: () => void;
  label?: string;
  className?: string;
};

export function ModalClose({ onClose, label = 'Close', className = '' }: ModalCloseProps) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClose}
      className={`ec-btn-ghost !p-2 ${className}`}
    >
      <X size={16} aria-hidden="true" />
    </button>
  );
}
