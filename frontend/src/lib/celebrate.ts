/**
 * Celebration helpers — confetti bursts, optional sound, haptic vibration.
 *
 * Lazy-loads canvas-confetti so the main bundle stays light. Respects the
 * user's reduced-motion preference (no confetti when the OS says no).
 */
import { useThemeStore } from '../store/theme';

type ConfettiFn = (opts?: Record<string, unknown>) => void;
let confettiLib: ConfettiFn | null = null;

async function getConfetti(): Promise<ConfettiFn> {
  if (!confettiLib) {
    const mod = await import('canvas-confetti');
    confettiLib = (mod as any).default ?? (mod as any);
  }
  return confettiLib as ConfettiFn;
}

function reducedMotion(): boolean {
  // Read the reduced-motion flag without subscribing to the store.
  return useThemeStore.getState().reducedMotion;
}

/** Single small burst — great for "thing saved" feedback. */
export async function popConfetti(opts?: { x?: number; y?: number; colors?: string[] }) {
  if (reducedMotion()) return;
  const c = await getConfetti();
  c({
    particleCount: 60,
    spread: 65,
    startVelocity: 35,
    origin: { x: opts?.x ?? 0.5, y: opts?.y ?? 0.5 },
    colors: opts?.colors,
    scalar: 0.9,
    zIndex: 9999,
  });
}

/** Big celebration — three offset bursts, for achievements. */
export async function bigCelebrate(colors?: string[]) {
  if (reducedMotion()) return;
  const c = await getConfetti();
  const palette = colors ?? ['#6366f1', '#22d3ee', '#f59e0b', '#ec4899', '#10b981'];
  const burst = (x: number, delay: number) =>
    setTimeout(() => {
      c({
        particleCount: 90,
        spread: 80,
        startVelocity: 45,
        origin: { x, y: 0.7 },
        colors: palette,
        scalar: 1.1,
        zIndex: 9999,
      });
    }, delay);
  burst(0.2, 0);
  burst(0.5, 140);
  burst(0.8, 280);
  // Final cannon from the top.
  setTimeout(() => {
    c({
      particleCount: 120,
      spread: 360,
      startVelocity: 25,
      origin: { x: 0.5, y: 0.2 },
      colors: palette,
      ticks: 220,
      gravity: 0.6,
      zIndex: 9999,
    });
  }, 420);
}

// ---------------------------------------------------------------------------
// Sound — opt-in via the user's settings store. Generates short tones via the
// Web Audio API so we don't ship any audio files.
// ---------------------------------------------------------------------------

let audioCtx: AudioContext | null = null;
function ctx(): AudioContext {
  if (!audioCtx) {
    const Ctor = (window.AudioContext || (window as any).webkitAudioContext);
    audioCtx = new Ctor();
  }
  return audioCtx;
}

function isSoundEnabled(): boolean {
  try {
    return localStorage.getItem('ec.sound') === 'on';
  } catch {
    return false;
  }
}

export function setSoundEnabled(on: boolean) {
  try {
    localStorage.setItem('ec.sound', on ? 'on' : 'off');
  } catch {
    /* localStorage may be blocked */
  }
}

/**
 * Play a short rising "ding" — used for achievement unlocks. Sound off by
 * default; users opt in from Settings → Appearance.
 */
export function playWinSound() {
  if (!isSoundEnabled() || reducedMotion()) return;
  try {
    const ac = ctx();
    const now = ac.currentTime;
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(523.25, now);            // C5
    osc.frequency.linearRampToValueAtTime(659.25, now + 0.10); // E5
    osc.frequency.linearRampToValueAtTime(783.99, now + 0.20); // G5
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.6);
    osc.connect(gain).connect(ac.destination);
    osc.start(now);
    osc.stop(now + 0.6);
  } catch {
    /* audio blocked; silent fallback */
  }
}

/** Soft tick — for non-achievement feedback like saving a draft. */
export function playTickSound() {
  if (!isSoundEnabled() || reducedMotion()) return;
  try {
    const ac = ctx();
    const now = ac.currentTime;
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(880, now);
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.08, now + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.10);
    osc.connect(gain).connect(ac.destination);
    osc.start(now);
    osc.stop(now + 0.12);
  } catch {
    /* audio blocked */
  }
}

/** Best-effort tactile feedback on mobile. */
export function buzz(pattern: number | number[] = 25) {
  if (reducedMotion()) return;
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* not supported */
  }
}
