/**
 * Tooltip — lightweight, keyboard-accessible tooltip primitive.
 *
 *   <Tooltip label="Save invoice">
 *     <button>...</button>
 *   </Tooltip>
 *
 * Renders into document.body via React portal so it escapes any
 * overflow:hidden parent. Positioned automatically on the side with the
 * most room. Honours reduced motion.
 */
import { AnimatePresence, motion } from 'framer-motion';
import { cloneElement, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type ReactElement, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

type Side = 'top' | 'bottom' | 'left' | 'right';

type Props = {
  label: string;
  /** Preferred side; auto-flips if it would clip. */
  side?: Side;
  /** Render delay in ms (Apple-style 350). */
  delay?: number;
  children: ReactNode;
};

export function Tooltip({ label, side = 'top', delay = 350, children }: Props) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ x: number; y: number; place: Side } | null>(null);
  const targetRef = useRef<HTMLElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | null>(null);
  // Stable id wired into the target via aria-describedby so screen readers
  // announce the tooltip text in addition to the element's own label.
  const tipId = useId();

  function show() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay);
  }
  function hide() {
    if (timer.current) window.clearTimeout(timer.current);
    setOpen(false);
  }

  useLayoutEffect(() => {
    if (!open || !targetRef.current) return;
    const r = targetRef.current.getBoundingClientRect();
    // Decide which side actually fits.
    const tipW = tipRef.current?.offsetWidth ?? 120;
    const tipH = tipRef.current?.offsetHeight ?? 28;
    const margin = 8;
    let place = side;
    if (place === 'top' && r.top < tipH + 8) place = 'bottom';
    else if (place === 'bottom' && r.bottom + tipH + 8 > window.innerHeight) place = 'top';
    else if (place === 'left' && r.left < tipW + 8) place = 'right';
    else if (place === 'right' && r.right + tipW + 8 > window.innerWidth) place = 'left';

    let x = r.left + r.width / 2;
    let y = r.top + r.height / 2;
    if (place === 'top')    y = r.top - margin;
    if (place === 'bottom') y = r.bottom + margin;
    if (place === 'left')   x = r.left - margin;
    if (place === 'right')  x = r.right + margin;
    setCoords({ x, y, place });
  }, [open, side]);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const child = isValidElement(children)
    ? cloneElement(children as ReactElement<any>, {
        ref: (el: HTMLElement) => {
          targetRef.current = el;
          const original = (children as any).ref;
          if (typeof original === 'function') original(el);
          else if (original) original.current = el;
        },
        onMouseEnter: (e: any) => { (children.props as any).onMouseEnter?.(e); show(); },
        onMouseLeave: (e: any) => { (children.props as any).onMouseLeave?.(e); hide(); },
        onFocus:      (e: any) => { (children.props as any).onFocus?.(e); show(); },
        onBlur:       (e: any) => { (children.props as any).onBlur?.(e); hide(); },
        // Always link the tooltip via aria-describedby so screen readers
        // announce the tip text on focus. Keep any existing aria-label (the
        // element may already have a richer label).
        'aria-describedby': [(children.props as any)['aria-describedby'], tipId].filter(Boolean).join(' '),
        'aria-label': (children.props as any)['aria-label'],
      })
    : children;

  const transformByPlace: Record<Side, string> = {
    top:    'translate(-50%, -100%)',
    bottom: 'translate(-50%, 0)',
    left:   'translate(-100%, -50%)',
    right:  'translate(0, -50%)',
  };

  return (
    <>
      {child}
      {typeof document !== 'undefined' && createPortal(
        <AnimatePresence>
          {open && coords && (
            <motion.div
              ref={tipRef}
              id={tipId}
              role="tooltip"
              initial={{ opacity: 0, y: coords.place === 'bottom' ? -4 : 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: coords.place === 'bottom' ? -2 : 2 }}
              transition={{ duration: 0.14, ease: [0.16, 1, 0.3, 1] }}
              style={{
                position: 'fixed',
                left: coords.x,
                top: coords.y,
                transform: transformByPlace[coords.place],
                zIndex: 9999,
                pointerEvents: 'none',
              }}
              className="rounded-md border border-border bg-surface-elevated px-2 py-1 text-[11px] font-medium text-ink shadow-floating"
            >
              {label}
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}
