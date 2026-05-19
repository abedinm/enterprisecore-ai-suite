import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  resolved: 'light' | 'dark';
  setTheme: (t: Theme) => void;
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

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      resolved: prefersDark() ? 'dark' : 'light',
      setTheme: (t) => {
        const resolved = resolve(t);
        applyClass(resolved);
        set({ theme: t, resolved });
      },
      toggle: () => {
        const next: Theme = get().resolved === 'dark' ? 'light' : 'dark';
        get().setTheme(next);
      },
      apply: () => {
        const resolved = resolve(get().theme);
        applyClass(resolved);
        set({ resolved });
      },
    }),
    {
      name: 'ec.theme',
      storage: createJSONStorage(() => localStorage),
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolved = resolve(state.theme);
          applyClass(resolved);
          state.resolved = resolved;
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
