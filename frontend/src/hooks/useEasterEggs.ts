/**
 * useEasterEggs — global keyboard easter eggs.
 *
 * 1. **Konami code** — Up, Up, Down, Down, Left, Right, Left, Right, B, A.
 *    Triggers a one-second confetti shower + unlocks the "konami"
 *    achievement.
 * 2. **Logo seven-clicks** — clicking the sidebar logo 7× within 4s
 *    unlocks "seven_clicks" and pops a small celebration. (Implemented
 *    inside the Sidebar component; this hook just exposes the helper.)
 */
import { useEffect } from 'react';
import { bigCelebrate } from '../lib/celebrate';
import { useGamification } from '../store/gamification';

const KONAMI = [
  'ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown',
  'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight',
  'b', 'a',
];

export function useEasterEggs() {
  const track = useGamification(s => s.track);

  useEffect(() => {
    let seq: string[] = [];
    function onKey(e: KeyboardEvent) {
      // Don't capture keys inside inputs.
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      seq.push(key);
      if (seq.length > KONAMI.length) seq = seq.slice(-KONAMI.length);
      if (seq.length === KONAMI.length && seq.every((k, i) => k === KONAMI[i])) {
        seq = [];
        bigCelebrate(['#d946ef', '#22d3ee', '#f59e0b', '#10b981']);
        track('konami');
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [track]);
}
