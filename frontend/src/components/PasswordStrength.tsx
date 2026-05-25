/**
 * PasswordStrength — animated 5-bar strength meter with a short verdict.
 *
 *   <PasswordStrength value={password} />
 *
 * Scoring is local and deliberately rough: it rewards length, character
 * variety, and penalises common patterns. zxcvbn would be more rigorous
 * but ships ~400 KB; the in-house heuristic is ~40 lines.
 */
import { motion } from 'framer-motion';
import { useMemo } from 'react';

const COMMON = new Set([
  'password', 'qwerty', '12345678', 'iloveyou', 'admin', 'letmein',
  'welcome', 'monkey', 'dragon', 'football', 'baseball', '111111',
]);

const VERDICTS = ['Very weak', 'Weak', 'OK', 'Strong', 'Excellent'] as const;
const COLORS = [
  'from-rose-400 to-rose-600',
  'from-orange-400 to-orange-500',
  'from-amber-400 to-amber-500',
  'from-emerald-400 to-emerald-500',
  'from-emerald-500 to-teal-500',
];

export function score(pw: string): number {
  let s = 0;
  if (!pw) return 0;
  if (pw.length >= 8) s += 1;
  if (pw.length >= 12) s += 1;
  let classes = 0;
  if (/[a-z]/.test(pw)) classes += 1;
  if (/[A-Z]/.test(pw)) classes += 1;
  if (/\d/.test(pw)) classes += 1;
  if (/[^a-zA-Z0-9]/.test(pw)) classes += 1;
  if (classes >= 3) s += 1;
  if (classes === 4) s += 1;
  if (COMMON.has(pw.toLowerCase())) s = 0;
  return Math.min(s, 4);
}

export function PasswordStrength({ value, className = '' }: { value: string; className?: string }) {
  const s = useMemo(() => score(value), [value]);
  const verdict = VERDICTS[s];
  return (
    <div className={className} aria-live="polite">
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map((i) => (
          <motion.span
            key={i}
            initial={false}
            animate={{
              backgroundColor: i <= s ? 'currentColor' : 'rgb(var(--color-border))',
              scaleY: i <= s ? 1 : 0.6,
            }}
            transition={{ duration: 0.2 }}
            className={`h-1.5 flex-1 origin-bottom rounded-full bg-gradient-to-r ${i <= s ? COLORS[s] : 'opacity-40'}`}
          />
        ))}
      </div>
      {value && (
        <p className="mt-1 text-[11px] font-medium text-ink-muted">{verdict}</p>
      )}
    </div>
  );
}
