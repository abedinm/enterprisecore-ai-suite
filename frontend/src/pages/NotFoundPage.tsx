/**
 * 404 — Lost in space.
 *
 * A friendly, animated dead-end: floating astronaut, twinkling stars,
 * gradient nebula. Magnetic "Take me home" CTA + a search shortcut.
 *
 * Beats the typical "Page not found." text by an order of magnitude.
 */
import { motion } from 'framer-motion';
import { Home, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Magnetic } from '../components/motion';

const STARS = Array.from({ length: 40 }, (_, i) => ({
  id: i,
  left: Math.random() * 100,
  top: Math.random() * 100,
  delay: Math.random() * 2,
  duration: 1.4 + Math.random() * 1.6,
  size: 1 + Math.random() * 2,
}));

export function NotFoundPage() {
  const nav = useNavigate();
  return (
    <div className="relative grid min-h-[80vh] place-items-center overflow-hidden rounded-2xl border border-border bg-surface-elevated">
      {/* Nebula gradient */}
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 animate-aurora"
        style={{
          background:
            'radial-gradient(40% 60% at 30% 30%, rgb(var(--brand-400)/0.25), transparent 60%),' +
            'radial-gradient(50% 60% at 80% 70%, rgb(var(--brand-700)/0.25), transparent 60%)',
        }}
      />
      {/* Stars */}
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
        {STARS.map((s) => (
          <motion.span
            key={s.id}
            className="absolute rounded-full bg-white"
            style={{ left: `${s.left}%`, top: `${s.top}%`, width: s.size, height: s.size }}
            animate={{ opacity: [0.2, 1, 0.2] }}
            transition={{ duration: s.duration, repeat: Infinity, delay: s.delay }}
          />
        ))}
      </div>

      <div className="relative z-10 max-w-md rounded-2xl bg-surface-elevated/75 px-6 py-8 text-center shadow-elevated backdrop-blur-sm">
        {/* Floating astronaut */}
        <motion.div
          animate={{ y: [0, -10, 0], rotate: [-2, 2, -2] }}
          transition={{ duration: 4.2, repeat: Infinity, ease: 'easeInOut' }}
          className="mx-auto mb-6 h-28 w-28"
          aria-hidden="true"
        >
          <svg viewBox="0 0 120 120" className="h-full w-full drop-shadow-lg">
            <defs>
              <radialGradient id="helmet" cx="50%" cy="40%" r="55%">
                <stop offset="0%" stopColor="rgb(var(--brand-300))" stopOpacity="0.95" />
                <stop offset="100%" stopColor="rgb(var(--brand-700))" stopOpacity="0.95" />
              </radialGradient>
              <linearGradient id="suit" x1="0%" x2="0%" y1="0%" y2="100%">
                <stop offset="0%" stopColor="#f5f7fb" />
                <stop offset="100%" stopColor="#d1d5db" />
              </linearGradient>
            </defs>
            {/* Suit */}
            <ellipse cx="60" cy="98" rx="32" ry="14" fill="url(#suit)" />
            <rect x="40" y="60" width="40" height="32" rx="14" fill="url(#suit)" />
            {/* Backpack */}
            <rect x="44" y="62" width="32" height="22" rx="6" fill="#9ca3af" />
            {/* Helmet */}
            <circle cx="60" cy="48" r="22" fill="url(#helmet)" />
            <ellipse cx="54" cy="42" rx="6" ry="3" fill="white" opacity="0.7" />
            {/* Arm waving */}
            <motion.g
              animate={{ rotate: [-10, 20, -10] }}
              transition={{ duration: 2.4, repeat: Infinity }}
              style={{ originX: '38px', originY: '70px' }}
            >
              <rect x="20" y="60" width="22" height="10" rx="5" fill="url(#suit)" />
              <circle cx="20" cy="65" r="6" fill="url(#suit)" />
            </motion.g>
          </svg>
        </motion.div>

        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-brand-600">404</p>
        <h1 className="mt-1 text-3xl font-semibold text-ink">Lost in space</h1>
        <p className="mt-2 text-sm text-ink-muted">
          That page floated off into the nebula. We can&apos;t find it from here.
        </p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Magnetic strength={0.35}>
            <button
              type="button"
              onClick={() => nav('/')}
              className="ec-btn-primary px-4 py-2"
            >
              <Home className="h-4 w-4" />
              Take me home
            </button>
          </Magnetic>
          <button
            type="button"
            onClick={() => nav('/search')}
            className="ec-btn-secondary px-4 py-2"
          >
            <Search className="h-4 w-4" />
            Search instead
          </button>
        </div>
      </div>
    </div>
  );
}
