import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type Theme = 'light' | 'dark' | 'system';

/**
 * Palettes layer on top of light/dark mode. Each one swaps the `--brand-*`
 * scale + a few accent tokens. The base surface/ink tokens stay constant
 * for legibility; only the brand identity changes. Users can pick their
 * favourite in Settings → Appearance.
 */
export type Palette =
  | 'indigo'   // Default — calm, professional
  | 'aurora'   // Teal-green-cyan, slightly luminous
  | 'sunset'   // Warm orange-rose, energetic
  | 'forest'   // Deep emerald, grounded
  | 'ocean'    // Bright cyan-blue, fresh
  | 'mono';    // Neutral graphite — minimalist

export type Density = 'comfortable' | 'compact';

/** Subtle background animations available globally. None by default. */
export type AmbientFx = 'none' | 'aurora' | 'mesh' | 'grid';

interface ThemeState {
  theme: Theme;
  palette: Palette;
  density: Density;
  ambient: AmbientFx;
  reducedMotion: boolean;       // honour the OS setting OR the user override
  motionPref: 'auto' | 'on' | 'off';
  resolved: 'light' | 'dark';
  setTheme: (t: Theme) => void;
  setPalette: (p: Palette) => void;
  setDensity: (d: Density) => void;
  setAmbient: (a: AmbientFx) => void;
  setMotionPref: (m: 'auto' | 'on' | 'off') => void;
  toggle: () => void;
  apply: () => void;
}

function prefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches;
}

function resolve(t: Theme): 'light' | 'dark' {
  if (t === 'system') return prefersDark() ? 'dark' : 'light';
  return t;
}

function applyClass(resolved: 'light' | 'dark') {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', resolved === 'dark');
  document.documentElement.style.colorScheme = resolved;
}

// Palette swatches — RGB triplets so they slot into the existing
// `<alpha-value>` tailwind tokens.  Tuned for ~4.5:1 contrast on white text
// at the 600 step (matching tailwind's indigo-600 baseline).
const PALETTES: Record<Palette, Record<string, string>> = {
  indigo: {
    50:  '238 242 255', 100: '224 231 255', 200: '199 210 254', 300: '165 180 252',
    400: '129 140 248', 500: '99 102 241',  600: '79 70 229',   700: '67 56 202',
    800: '55 48 163',   900: '49 46 129',
  },
  aurora: {
    50:  '236 254 252', 100: '207 250 244', 200: '153 246 228', 300: '94 234 212',
    400: '45 212 191',  500: '20 184 166',  600: '13 148 136',  700: '15 118 110',
    800: '17 94 89',    900: '19 78 74',
  },
  sunset: {
    // 600 deepened to orange-700 so white text on the primary button keeps
    // WCAG AA contrast (>=4.5:1). Lighter stops untouched.
    50:  '255 247 237', 100: '255 237 213', 200: '254 215 170', 300: '253 186 116',
    400: '251 146 60',  500: '249 115 22',  600: '194 65 12',   700: '154 52 18',
    800: '124 45 18',   900: '85 31 12',
  },
  forest: {
    // 600 deepened to green-700 so white text on the primary button keeps
    // WCAG AA contrast (>=4.5:1).
    50:  '240 253 244', 100: '220 252 231', 200: '187 247 208', 300: '134 239 172',
    400: '74 222 128',  500: '34 197 94',   600: '21 128 61',   700: '22 101 52',
    800: '20 83 45',    900: '14 64 35',
  },
  ocean: {
    50:  '236 254 255', 100: '207 250 254', 200: '165 243 252', 300: '103 232 249',
    400: '34 211 238',  500: '6 182 212',   600: '8 145 178',   700: '14 116 144',
    800: '21 94 117',   900: '22 78 99',
  },
  mono: {
    50:  '249 250 251', 100: '243 244 246', 200: '229 231 235', 300: '209 213 219',
    400: '156 163 175', 500: '107 114 128', 600: '75 85 99',    700: '55 65 81',
    800: '31 41 55',    900: '17 24 39',
  },
};

function applyPalette(p: Palette) {
  if (typeof document === 'undefined') return;
  const swatch = PALETTES[p] ?? PALETTES.indigo;
  const root = document.documentElement;
  for (const [step, rgb] of Object.entries(swatch)) {
    root.style.setProperty(`--brand-${step}`, rgb);
  }
  root.setAttribute('data-palette', p);
}

function applyDensity(d: Density) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-density', d);
}

function applyAmbient(a: AmbientFx) {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-ambient', a);
}

function applyMotionPref(pref: 'auto' | 'on' | 'off'): boolean {
  if (typeof document === 'undefined') return false;
  const osReduced =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const reduced = pref === 'off' ? true : pref === 'on' ? false : osReduced;
  document.documentElement.setAttribute('data-motion', reduced ? 'reduced' : 'full');
  return reduced;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      palette: 'indigo',
      density: 'comfortable',
      ambient: 'aurora',
      reducedMotion: false,
      motionPref: 'auto',
      resolved: prefersDark() ? 'dark' : 'light',
      setTheme: (t) => {
        const resolved = resolve(t);
        applyClass(resolved);
        set({ theme: t, resolved });
        // Fire the "dark_mode" achievement when the user explicitly picks dark.
        if (resolved === 'dark') {
          void import('./gamification').then(m => m.useGamification.getState().track('dark_mode'));
        }
      },
      setPalette: (p) => {
        applyPalette(p);
        set({ palette: p });
        // Fire "palette_picker" the first time they swap.
        void import('./gamification').then(m => m.useGamification.getState().track('palette_picker'));
      },
      setDensity: (d) => {
        applyDensity(d);
        set({ density: d });
      },
      setAmbient: (a) => {
        applyAmbient(a);
        set({ ambient: a });
      },
      setMotionPref: (m) => {
        const reduced = applyMotionPref(m);
        set({ motionPref: m, reducedMotion: reduced });
      },
      toggle: () => {
        const next: Theme = get().resolved === 'dark' ? 'light' : 'dark';
        get().setTheme(next);
      },
      apply: () => {
        const s = get();
        const resolved = resolve(s.theme);
        applyClass(resolved);
        applyPalette(s.palette);
        applyDensity(s.density);
        applyAmbient(s.ambient);
        const reduced = applyMotionPref(s.motionPref);
        set({ resolved, reducedMotion: reduced });
      },
    }),
    {
      name: 'ec.theme',
      storage: createJSONStorage(() => localStorage),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolved = resolve(state.theme);
          applyClass(resolved);
          applyPalette(state.palette ?? 'indigo');
          applyDensity(state.density ?? 'comfortable');
          applyAmbient(state.ambient ?? 'aurora');
          const reduced = applyMotionPref(state.motionPref ?? 'auto');
          state.resolved = resolved;
          state.reducedMotion = reduced;
        }
      },
    },
  ),
);

if (typeof window !== 'undefined' && window.matchMedia) {
  const mql = window.matchMedia('(prefers-color-scheme: dark)');
  mql.addEventListener?.('change', () => {
    const { theme, apply } = useThemeStore.getState();
    if (theme === 'system') apply();
  });
}
