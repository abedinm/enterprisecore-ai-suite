/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Brand scale reads from CSS variables so the palette can swap at
        // runtime without recompiling. Defaults are seeded in index.css.
        brand: {
          50:  'rgb(var(--brand-50)  / <alpha-value>)',
          100: 'rgb(var(--brand-100) / <alpha-value>)',
          200: 'rgb(var(--brand-200) / <alpha-value>)',
          300: 'rgb(var(--brand-300) / <alpha-value>)',
          400: 'rgb(var(--brand-400) / <alpha-value>)',
          500: 'rgb(var(--brand-500) / <alpha-value>)',
          600: 'rgb(var(--brand-600) / <alpha-value>)',
          700: 'rgb(var(--brand-700) / <alpha-value>)',
          800: 'rgb(var(--brand-800) / <alpha-value>)',
          900: 'rgb(var(--brand-900) / <alpha-value>)',
        },
        surface: {
          DEFAULT: 'rgb(var(--color-surface) / <alpha-value>)',
          muted: 'rgb(var(--color-surface-muted) / <alpha-value>)',
          elevated: 'rgb(var(--color-surface-elevated) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'rgb(var(--color-ink) / <alpha-value>)',
          muted: 'rgb(var(--color-ink-muted) / <alpha-value>)',
          subtle: 'rgb(var(--color-ink-subtle) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--color-border) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgb(0 0 0 / 0.04), 0 1px 3px rgb(0 0 0 / 0.06)',
        // Elevated layers with depth — pair with hover transitions for lift.
        elevated: '0 4px 12px -2px rgb(0 0 0 / 0.06), 0 2px 6px -1px rgb(0 0 0 / 0.04)',
        floating: '0 10px 30px -5px rgb(0 0 0 / 0.12), 0 4px 12px -2px rgb(0 0 0 / 0.08)',
        glow: '0 0 0 1px rgb(var(--brand-500) / 0.4), 0 0 24px -4px rgb(var(--brand-500) / 0.5)',
        'inner-glow': 'inset 0 0 0 1px rgb(var(--brand-500) / 0.3)',
      },
      keyframes: {
        // Cross-cutting motion vocabulary. Names use plain English so
        // `animate-fade-in-up` reads at the call site.
        'fade-in':       { '0%': { opacity: '0' },               '100%': { opacity: '1' } },
        'fade-in-up':    { '0%': { opacity: '0', transform: 'translateY(8px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'fade-in-down':  { '0%': { opacity: '0', transform: 'translateY(-8px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'slide-in-right':{ '0%': { opacity: '0', transform: 'translateX(20px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        'slide-in-left': { '0%': { opacity: '0', transform: 'translateX(-20px)' }, '100%': { opacity: '1', transform: 'translateX(0)' } },
        'scale-in':      { '0%': { opacity: '0', transform: 'scale(0.96)' }, '100%': { opacity: '1', transform: 'scale(1)' } },
        'pop':           { '0%': { transform: 'scale(0.85)' }, '50%': { transform: 'scale(1.05)' }, '100%': { transform: 'scale(1)' } },
        'shake':         { '0%,100%': { transform: 'translateX(0)' }, '20%,60%': { transform: 'translateX(-6px)' }, '40%,80%': { transform: 'translateX(6px)' } },
        'pulse-glow':    { '0%,100%': { boxShadow: '0 0 0 0 rgb(var(--brand-500) / 0.6)' }, '50%': { boxShadow: '0 0 0 12px rgb(var(--brand-500) / 0)' } },
        'shimmer':       { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        'aurora':        { '0%,100%': { transform: 'translate3d(0,0,0) scale(1)' }, '50%': { transform: 'translate3d(40px,-30px,0) scale(1.15)' } },
        'aurora-2':      { '0%,100%': { transform: 'translate3d(0,0,0) scale(1.1)' }, '50%': { transform: 'translate3d(-40px,30px,0) scale(0.95)' } },
        'float':         { '0%,100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-6px)' } },
        'spin-slow':     { 'to': { transform: 'rotate(360deg)' } },
        'gradient-x':    { '0%,100%': { backgroundPosition: '0% 50%' }, '50%': { backgroundPosition: '100% 50%' } },
        'progress':      { '0%': { transform: 'scaleX(0)' }, '100%': { transform: 'scaleX(1)' } },
        'count-up':      { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        'sparkle':       { '0%,100%': { opacity: '0', transform: 'scale(0.4) rotate(0deg)' }, '50%': { opacity: '1', transform: 'scale(1) rotate(180deg)' } },
        'flame':         { '0%,100%': { transform: 'scale(1) rotate(-2deg)' }, '50%': { transform: 'scale(1.08) rotate(2deg)' } },
      },
      animation: {
        'fade-in':        'fade-in 280ms ease-out both',
        'fade-in-up':     'fade-in-up 320ms cubic-bezier(0.16,1,0.3,1) both',
        'fade-in-down':   'fade-in-down 320ms cubic-bezier(0.16,1,0.3,1) both',
        'slide-in-right': 'slide-in-right 320ms cubic-bezier(0.16,1,0.3,1) both',
        'slide-in-left':  'slide-in-left 320ms cubic-bezier(0.16,1,0.3,1) both',
        'scale-in':       'scale-in 220ms cubic-bezier(0.16,1,0.3,1) both',
        'pop':            'pop 360ms cubic-bezier(0.34,1.56,0.64,1) both',
        'shake':          'shake 420ms cubic-bezier(0.36,0.07,0.19,0.97) both',
        'pulse-glow':     'pulse-glow 1.6s ease-out infinite',
        'shimmer':        'shimmer 1.6s linear infinite',
        'aurora':         'aurora 14s ease-in-out infinite',
        'aurora-2':       'aurora-2 18s ease-in-out infinite',
        'float':          'float 3s ease-in-out infinite',
        'spin-slow':      'spin-slow 8s linear infinite',
        'gradient-x':     'gradient-x 6s ease infinite',
        'progress':       'progress 600ms cubic-bezier(0.16,1,0.3,1) both',
        'count-up':       'count-up 420ms cubic-bezier(0.16,1,0.3,1) both',
        'sparkle':        'sparkle 1.4s ease-in-out infinite',
        'flame':          'flame 1.2s ease-in-out infinite',
      },
      backgroundImage: {
        'aurora':   'radial-gradient(at 27% 37%, rgb(var(--brand-400)/0.35) 0px, transparent 50%), radial-gradient(at 97% 21%, rgb(var(--brand-600)/0.30) 0px, transparent 50%), radial-gradient(at 52% 99%, rgb(var(--brand-500)/0.25) 0px, transparent 50%)',
        'mesh':     'linear-gradient(120deg, rgb(var(--brand-500)/0.15), rgb(var(--brand-300)/0.10), rgb(var(--brand-700)/0.12))',
        'grid':     'linear-gradient(rgb(var(--color-border)/0.6) 1px, transparent 1px), linear-gradient(to right, rgb(var(--color-border)/0.6) 1px, transparent 1px)',
        'shimmer':  'linear-gradient(110deg, transparent 0%, rgb(var(--color-ink)/0.06) 35%, rgb(var(--color-ink)/0.10) 50%, rgb(var(--color-ink)/0.06) 65%, transparent 100%)',
        'gradient-brand': 'linear-gradient(135deg, rgb(var(--brand-500)), rgb(var(--brand-700)))',
        'gradient-aurora': 'linear-gradient(135deg, rgb(var(--brand-400)) 0%, rgb(var(--brand-600)) 50%, rgb(var(--brand-800)) 100%)',
      },
      backgroundSize: {
        'shimmer':  '200% 100%',
        'grid-md':  '24px 24px',
      },
      transitionTimingFunction: {
        'out-expo':  'cubic-bezier(0.16, 1, 0.3, 1)',
        'spring':    'cubic-bezier(0.34, 1.56, 0.64, 1)',
        'in-out-expo': 'cubic-bezier(0.87, 0, 0.13, 1)',
      },
    },
  },
  plugins: [],
};
