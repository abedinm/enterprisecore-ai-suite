/**
 * PageTransition — fades + softly slides up the routed page each navigation.
 * Honours the reduced-motion preference automatically.
 *
 * Wrap the <Outlet /> in AppShell with this. AnimatePresence keys on the
 * location pathname so React keeps the previous DOM mounted just long
 * enough for the exit animation.
 */
import { AnimatePresence, motion } from 'framer-motion';
import { type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useThemeStore } from '../store/theme';

export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const reduced = useThemeStore((s) => s.reducedMotion);
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={reduced ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduced ? undefined : { opacity: 0, y: -4 }}
        transition={{ duration: reduced ? 0 : 0.28, ease: [0.16, 1, 0.3, 1] }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
