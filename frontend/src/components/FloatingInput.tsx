/**
 * FloatingInput — Material-style floating label input with animated focus
 * ring, error state with shake animation, and success-check microinteraction.
 *
 *   <FloatingInput
 *     label="Email"
 *     type="email"
 *     value={email}
 *     onChange={(v) => setEmail(v)}
 *     error={errors.email}
 *     valid={touched.email && !errors.email}
 *   />
 */
import { motion } from 'framer-motion';
import { Check } from 'lucide-react';
import { type InputHTMLAttributes, useId, useRef, useState, useEffect } from 'react';

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> & {
  label: string;
  value: string;
  onChange: (v: string) => void;
  error?: string;
  valid?: boolean;
  hint?: string;
};

export function FloatingInput({
  label,
  value,
  onChange,
  error,
  valid,
  hint,
  className = '',
  ...rest
}: Props) {
  const id = useId();
  const [focused, setFocused] = useState(false);
  const filled = value.length > 0;
  const floats = focused || filled;
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Use a CSS class for the shake animation so we don't have to wrap the
  // native <input> with motion.input (which clashes with React's input
  // event types under strict TypeScript).
  useEffect(() => {
    if (!error || !inputRef.current) return;
    const el = inputRef.current;
    el.classList.remove('animate-shake');
    // Force reflow so the animation restarts on every new error.
    void el.offsetWidth;
    el.classList.add('animate-shake');
  }, [error]);

  return (
    <div className={`relative ${className}`}>
      <input
        {...rest}
        ref={inputRef}
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={(e) => { setFocused(true); rest.onFocus?.(e); }}
        onBlur={(e) => { setFocused(false); rest.onBlur?.(e); }}
        className={`peer w-full rounded-lg border bg-surface-elevated px-3 pb-2 pt-5 text-sm placeholder-transparent transition outline-none
          ${error ? 'border-rose-500 focus:ring-2 focus:ring-rose-500/30'
                 : focused ? 'border-brand-500 focus:ring-2 focus:ring-brand-500/30'
                          : 'border-border hover:border-ink-subtle'}`}
        placeholder={label}
        aria-invalid={Boolean(error)}
        aria-describedby={hint || error ? `${id}-hint` : undefined}
      />
      <label
        htmlFor={id}
        className={`pointer-events-none absolute left-3 origin-left transition-all duration-150 ease-out-expo ${
          floats
            ? 'top-1 text-[11px] font-medium uppercase tracking-wider'
            : 'top-3.5 text-sm'
        } ${
          error ? 'text-rose-600' : focused ? 'text-brand-600' : 'text-ink-muted'
        }`}
      >
        {label}
      </label>
      {valid && !error && (
        <motion.span
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 380, damping: 20 }}
          className="pointer-events-none absolute right-3 top-3.5 grid h-5 w-5 place-items-center rounded-full bg-emerald-500 text-white"
          aria-hidden="true"
        >
          <Check className="h-3 w-3" />
        </motion.span>
      )}
      {(hint || error) && (
        <p id={`${id}-hint`} className={`mt-1 text-xs ${error ? 'text-rose-600' : 'text-ink-muted'}`}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}
