/**
 * Gamification store — XP, level, login streak, achievements.
 *
 * The store keeps cached server state plus a tiny client-only queue of
 * pending "celebrations" (achievements that need a toast + confetti).
 * Polled lazily; consumers can also call ``refresh()`` after they suspect
 * an action has unlocked something (e.g. invoice creation).
 */
import { create } from 'zustand';
import { api } from '../lib/api';

export type Achievement = {
  key: string;
  label: string;
  description: string;
  icon: string;
  color: string;        // 6-char hex without `#`
  xp: number;
  tier: 'common' | 'rare' | 'epic' | 'legendary';
  unlocked: boolean;
  unlocked_at: string | null;
};

export type Progress = {
  xp: number;
  level: {
    level: number;
    xp: number;
    current_threshold: number;
    next_threshold: number;
    progress: number; // 0..1
  };
  streak: { current: number; best: number; kind: string };
};

type State = {
  progress: Progress | null;
  achievements: Achievement[];
  /** Achievements that have unlocked SINCE the last UI tick — fed to confetti/toast. */
  celebrations: Achievement[];
  loading: boolean;
  fetch: () => Promise<void>;
  refresh: () => Promise<void>;
  track: (event: string) => Promise<void>;
  ack: (key: string) => void;
};

let lastSnapshot: Set<string> = new Set();

export const useGamification = create<State>((set, get) => ({
  progress: null,
  achievements: [],
  celebrations: [],
  loading: false,
  async fetch() {
    if (get().loading) return;
    set({ loading: true });
    try {
      const [p, a] = await Promise.all([
        api.get<Progress>('/gamification/me'),
        api.get<Achievement[]>('/gamification/achievements'),
      ]);
      lastSnapshot = new Set(a.data.filter(x => x.unlocked).map(x => x.key));
      set({ progress: p.data, achievements: a.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },
  async refresh() {
    try {
      const [p, a] = await Promise.all([
        api.get<Progress>('/gamification/me'),
        api.get<Achievement[]>('/gamification/achievements'),
      ]);
      const previously = lastSnapshot;
      const now = new Set(a.data.filter(x => x.unlocked).map(x => x.key));
      const fresh = a.data.filter(x => x.unlocked && !previously.has(x.key));
      lastSnapshot = now;
      set({
        progress: p.data,
        achievements: a.data,
        celebrations: [...get().celebrations, ...fresh],
      });
    } catch {
      /* swallow — gamification must never break the app */
    }
  },
  async track(event: string) {
    try {
      await api.post(`/gamification/track/${event}`);
      get().refresh();
    } catch {
      /* swallow */
    }
  },
  ack(key: string) {
    set({ celebrations: get().celebrations.filter(c => c.key !== key) });
  },
}));
