/**
 * Motion primitives — small, composable, animation-friendly wrappers.
 *
 * Every primitive honours the user's reduced-motion preference. When the
 * theme store reports ``reducedMotion=true`` we render plain DOM with no
 * transforms or opacity transitions.
 *
 * The intent is to compose at the call site:
 *
 *   <Stagger>
 *     <FadeIn delay={0}>...kpi card...</FadeIn>
 *     <FadeIn delay={60}>...kpi card...</FadeIn>
 *     <FadeIn delay={120}>...kpi card...</FadeIn>
 *   </Stagger>
 *
 * For one-off page-level animation, use the bare ``motion.div`` from
 * framer-motion directly. This library only owns the patterns we repeat.
 */
import { motion, useInView, useMotionValue, useSpring, useTransform } from 'framer-motion';
import {
  Children,
  cloneElement,
  isValidElement,
  useEffect,
  useRef,
  type ReactElement,
  type ReactNode,
} from 'react';
import { useThemeStore } from '../../store/theme';

const SPRING_GENTLE = { type: 'spring' as const, stiffness: 180, damping: 22 };
const SPRING_POPPY  = { type: 'spring' as const, stiffness: 380, damping: 18 };
const OUT_EXPO      = [0.16, 1, 0.3, 1] as const;

function useMotion(): boolean {
  return !useThemeStore((s) => s.reducedMotion);
}

// ---------------------------------------------------------------------------
// FadeIn — fades + slides up by 8px. Default building block for hero text,
// tiles, cards.
// ---------------------------------------------------------------------------
export function FadeIn({
  children,
  delay = 0,
  y = 8,
  duration = 0.45,
  className,
  as = 'div',
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  duration?: number;
  className?: string;
  as?: 'div' | 'section' | 'span' | 'li';
}) {
  const animOn = useMotion();
  const initial = animOn ? { opacity: 0, y } : false;
  const Tag = motion[as] as typeof motion.div;
  return (
    <Tag
      initial={initial as any}
      animate={animOn ? { opacity: 1, y: 0 } : { opacity: 1, y: 0 }}
      transition={{ duration, delay, ease: OUT_EXPO }}
      className={className}
    >
      {children}
    </Tag>
  );
}

// ---------------------------------------------------------------------------
// Stagger — wraps a sequence and applies an incremental delay to its children
// (FadeIn/SlideIn etc.). No-op for non-motion children.
// ---------------------------------------------------------------------------
export function Stagger({
  children,
  step = 0.05,
  initialDelay = 0,
  className,
}: {
  children: ReactNode;
  step?: number;
  initialDelay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: { transition: { staggerChildren: step, delayChildren: initialDelay } },
      }}
      className={className}
    >
      {Children.map(children, (child, idx) => {
        if (!isValidElement(child)) return child;
        // If a child already declared a delay prop, respect it; otherwise we
        // let the parent's staggerChildren do the work via variants below.
        return cloneElement(child as ReactElement<{ delay?: number }>, {
          delay: (child.props as any).delay ?? initialDelay + idx * step,
        });
      })}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// SlideIn — from a side, with spring.
// ---------------------------------------------------------------------------
export function SlideIn({
  children,
  from = 'right',
  delay = 0,
  distance = 24,
  className,
}: {
  children: ReactNode;
  from?: 'left' | 'right' | 'top' | 'bottom';
  delay?: number;
  distance?: number;
  className?: string;
}) {
  const animOn = useMotion();
  const axis = from === 'left' || from === 'right' ? 'x' : 'y';
  const sign = from === 'right' || from === 'bottom' ? 1 : -1;
  const initial = animOn ? { opacity: 0, [axis]: sign * distance } : false;
  return (
    <motion.div
      initial={initial as any}
      animate={{ opacity: 1, x: 0, y: 0 }}
      transition={{ ...SPRING_GENTLE, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// ScaleIn — pops into view with overshoot spring. Great for badges.
// ---------------------------------------------------------------------------
export function ScaleIn({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const animOn = useMotion();
  return (
    <motion.div
      initial={animOn ? { opacity: 0, scale: 0.85 } : false}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ ...SPRING_POPPY, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Counter — animated number ticker. ``to`` is the target; we ease from 0
// (or from `from`) over `duration`. Great for KPI cards.
// ---------------------------------------------------------------------------
export function Counter({
  to,
  from = 0,
  duration = 1.2,
  format = (v) => Math.round(v).toLocaleString(),
  className,
}: {
  to: number;
  from?: number;
  duration?: number;
  format?: (v: number) => string;
  className?: string;
}) {
  const animOn = useMotion();
  const ref = useRef<HTMLSpanElement | null>(null);
  const motionValue = useMotionValue(animOn ? from : to);
  const spring = useSpring(motionValue, { duration: duration * 1000, bounce: 0 });
  const display = useTransform(spring, format as (v: number) => any);

  useEffect(() => {
    motionValue.set(to);
    if (!animOn) {
      // Snap to final value with no animation.
      ref.current && (ref.current.textContent = format(to));
    }
  }, [to, motionValue, animOn, format]);

  useEffect(() => {
    return display.on('change', (v: any) => {
      if (ref.current) ref.current.textContent = String(v);
    });
  }, [display]);

  return (
    <span ref={ref} className={className}>
      {format(animOn ? from : to)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// InView — only renders + animates when scrolled into view. Use for tall
// pages so off-screen sections don't all animate at once on mount.
// ---------------------------------------------------------------------------
export function InView({
  children,
  rootMargin = '0px',
  amount = 0.2,
  once = true,
  className,
}: {
  children: ReactNode;
  rootMargin?: string;
  amount?: number;
  once?: boolean;
  className?: string;
}) {
  const animOn = useMotion();
  const ref = useRef<HTMLDivElement | null>(null);
  const inView = useInView(ref, { once, margin: rootMargin as any, amount });
  return (
    <motion.div
      ref={ref}
      initial={animOn ? { opacity: 0, y: 12 } : false}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
      transition={{ duration: 0.45, ease: OUT_EXPO }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Magnetic — gentle attraction toward the cursor on hover. Wrap CTAs.
// ---------------------------------------------------------------------------
export function Magnetic({
  children,
  strength = 0.3,
  className,
}: {
  children: ReactNode;
  strength?: number;
  className?: string;
}) {
  const animOn = useMotion();
  const ref = useRef<HTMLDivElement | null>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const sx = useSpring(x, { stiffness: 200, damping: 18 });
  const sy = useSpring(y, { stiffness: 200, damping: 18 });

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!animOn || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    x.set((e.clientX - r.left - r.width / 2) * strength);
    y.set((e.clientY - r.top - r.height / 2) * strength);
  }
  function onLeave() {
    x.set(0); y.set(0);
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ x: sx, y: sy }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Sparkle — a single twinkling star particle, positioned absolutely.
// Use it inside a wrapped span/div for a "premium" feel on badges + tags.
// ---------------------------------------------------------------------------
export function Sparkle({
  size = 10,
  color,
  style,
}: {
  size?: number;
  color?: string;
  style?: React.CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      style={{ pointerEvents: 'none', ...style }}
      className="animate-sparkle"
      aria-hidden="true"
    >
      <path
        d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z"
        fill={color ?? 'currentColor'}
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Pulse — radiating ring around a child. Great for "new" indicators.
// ---------------------------------------------------------------------------
export function Pulse({
  children,
  className,
  color,
}: {
  children: ReactNode;
  className?: string;
  color?: string;
}) {
  return (
    <span className={`relative inline-flex ${className ?? ''}`}>
      <span
        aria-hidden="true"
        className="absolute inset-0 rounded-full animate-pulse-glow"
        style={{ boxShadow: `0 0 0 0 ${color ?? 'rgb(var(--brand-500))'}` }}
      />
      {children}
    </span>
  );
}
