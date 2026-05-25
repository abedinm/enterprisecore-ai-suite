/**
 * useFocusTrap — keep keyboard focus inside a container while it's mounted.
 *
 * On mount:
 *   - remembers the previously-focused element
 *   - focuses ``initialFocus`` (or the first tabbable descendant)
 *   - intercepts Tab / Shift-Tab to cycle through descendants only
 * On unmount:
 *   - restores focus to the previously-focused element
 *
 * Skip the trap by passing ``active=false`` (e.g. when the container is
 * hidden but mounted). Reference-counts so nested traps don't fight.
 */
import { useEffect, type RefObject } from 'react';

const TABBABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function useFocusTrap(
  ref: RefObject<HTMLElement | null>,
  active: boolean,
  initialFocus?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!active) return;
    const root = ref.current;
    if (!root) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    // Focus an initial target if provided, else first tabbable, else the
    // container itself (so Esc still works even if the dialog has no
    // tabbable children).
    const focusInitial = () => {
      const target =
        initialFocus?.current ??
        (root.querySelector(TABBABLE_SELECTOR) as HTMLElement | null) ??
        root;
      target?.focus({ preventScroll: true });
    };
    // Defer one frame so any AnimatePresence enter completes first.
    const raf = requestAnimationFrame(focusInitial);

    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      const trapRoot = ref.current;
      if (!trapRoot) return;
      const focusables = Array.from(
        trapRoot.querySelectorAll<HTMLElement>(TABBABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute('data-focus-trap-ignore'));
      if (focusables.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const activeEl = document.activeElement as HTMLElement | null;
      if (e.shiftKey) {
        if (activeEl === first || !trapRoot.contains(activeEl)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (activeEl === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKey);
      // Restore focus to whatever had it before. If it's gone (e.g. the
      // route changed under us) we leave focus on the body — the next
      // interactive element gets focused on the next Tab.
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus({ preventScroll: true });
      }
    };
  }, [active, ref, initialFocus]);
}
