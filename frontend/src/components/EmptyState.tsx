/**
 * EmptyState — the answer to "what do I do now?" on every empty list, table,
 * and dashboard. The audit flagged blank grids as a top trust killer for
 * new tenants. This component normalises:
 *
 *   - title  (1-line, sentence case)
 *   - body   (2-line, plain English, no jargon)
 *   - icon OR illustration (one or the other; illustration animates in)
 *   - cta    (primary call-to-action button — magnetic hover)
 *   - secondary (optional learn-more link)
 *
 * Use this in EVERY list view; refactor existing "No rows" placeholders to
 * call it instead of inventing new layouts. Consistency > cleverness.
 */
import type { ComponentType, ReactNode } from 'react';
import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';
import { Magnetic } from './motion';

export type EmptyStateProps = {
  title: string;
  body?: string;
  icon?: LucideIcon | ComponentType<{ className?: string }>;
  /** Drop-in SVG illustration. Takes priority over `icon` when both provided. */
  illustration?: ReactNode;
  cta?: { label: string; onClick: () => void };
  secondary?: { label: string; href?: string; onClick?: () => void };
  children?: ReactNode;
  className?: string;
};

export function EmptyState({
  title,
  body,
  icon: Icon,
  illustration,
  cta,
  secondary,
  children,
  className = '',
}: EmptyStateProps) {
  return (
    <motion.div
      role="status"
      aria-live="polite"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
      className={
        'relative flex flex-col items-center justify-center overflow-hidden rounded-xl border border-dashed ' +
        'border-border bg-surface-muted/40 px-6 py-12 text-center ' +
        className
      }
    >
      {/* Subtle aurora behind the illustration. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 opacity-50"
        style={{
          background:
            'radial-gradient(40% 60% at 50% 30%, rgb(var(--brand-400)/0.18), transparent 60%)',
        }}
      />
      {illustration ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.92, y: 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.42, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
          className="mb-4 text-brand-600"
        >
          {illustration}
        </motion.div>
      ) : Icon ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', stiffness: 380, damping: 18 }}
          className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-brand text-white shadow-md"
        >
          <Icon className="h-7 w-7" aria-hidden="true" />
        </motion.div>
      ) : null}
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      {body && (
        <p className="mt-1 max-w-md text-sm text-ink-muted">{body}</p>
      )}
      {children}
      {(cta || secondary) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          {cta && (
            <Magnetic strength={0.35}>
              <button
                type="button"
                onClick={cta.onClick}
                className="ec-btn-primary px-4 py-2"
              >
                {cta.label}
              </button>
            </Magnetic>
          )}
          {secondary && (
            secondary.href ? (
              <a
                href={secondary.href}
                target={secondary.href.startsWith('http') ? '_blank' : undefined}
                rel={secondary.href.startsWith('http') ? 'noreferrer' : undefined}
                className="text-sm font-medium text-brand-600 hover:underline"
              >
                {secondary.label}
              </a>
            ) : (
              <button
                type="button"
                onClick={secondary.onClick}
                className="text-sm font-medium text-brand-600 hover:underline"
              >
                {secondary.label}
              </button>
            )
          )}
        </div>
      )}
    </motion.div>
  );
}
