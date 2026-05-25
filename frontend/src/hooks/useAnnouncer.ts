/**
 * useAnnouncer — global "live region" for screen-reader announcements.
 *
 *   const announce = useAnnouncer();
 *   announce('Saved');                       // polite by default
 *   announce('Form failed validation', 'assertive');
 *
 * The actual live region is rendered once by `<LiveAnnouncer />` mounted
 * inside AppShell. This file just exposes the store and the hook.
 */
import { useCallback } from 'react';
import { create } from 'zustand';

type Politeness = 'polite' | 'assertive';

type AnnouncerState = {
  polite: string;
  assertive: string;
  /** Monotonically-increasing counter so identical messages still re-fire. */
  bump: number;
  announce: (message: string, politeness?: Politeness) => void;
};

export const useAnnouncerStore = create<AnnouncerState>((set) => ({
  polite: '',
  assertive: '',
  bump: 0,
  announce(message, politeness = 'polite') {
    set((s) => ({
      ...(politeness === 'assertive' ? { assertive: message } : { polite: message }),
      bump: s.bump + 1,
    }));
  },
}));

export function useAnnouncer() {
  const announce = useAnnouncerStore((s) => s.announce);
  return useCallback(
    (message: string, politeness: Politeness = 'polite') => announce(message, politeness),
    [announce],
  );
}
