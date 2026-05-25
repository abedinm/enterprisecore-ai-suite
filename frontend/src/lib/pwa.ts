/**
 * PWA registration helpers.
 *
 * - Skips service worker registration under Electron (the file:// loader and
 *   service workers don't get along — registration silently does nothing or
 *   conflicts with electron's resource pipeline).
 * - Skips in dev so HMR + Vite's own module graph stay authoritative.
 * - Wires update detection: when a new worker is installed but the old one
 *   is still in control, we emit a `pwa:update-available` window event for
 *   the UpdateAvailableBanner to react to.
 */

const SW_URL = '/sw.js';
const UPDATE_EVENT = 'pwa:update-available';

function isElectron(): boolean {
  if (typeof window === 'undefined') return false;
  const ua = window.navigator.userAgent || '';
  return ua.includes('Electron');
}

export function registerPWA(): void {
  if (typeof window === 'undefined') return;
  if (isElectron()) return;
  if (!('serviceWorker' in navigator)) return;
  // Skip in dev — the worker would cache stale Vite-served modules across HMR.
  if (import.meta.env.MODE !== 'production') return;

  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register(SW_URL, { scope: '/' });

      // If a worker is already waiting at registration time, notify immediately.
      if (reg.waiting && navigator.serviceWorker.controller) {
        window.dispatchEvent(new CustomEvent(UPDATE_EVENT));
      }

      reg.addEventListener('updatefound', () => {
        const newWorker = reg.installing;
        if (!newWorker) return;
        newWorker.addEventListener('statechange', () => {
          if (
            newWorker.state === 'installed' &&
            navigator.serviceWorker.controller
          ) {
            // New SW installed but old one still in control — surface the update.
            window.dispatchEvent(new CustomEvent(UPDATE_EVENT));
          }
        });
      });
    } catch (err) {
      // Registration failures are non-fatal: app still works without the SW.
      console.warn('SW registration failed:', err);
    }
  });
}

export function applyPWAUpdate(): void {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.getRegistration().then((reg) => {
    if (!reg?.waiting) {
      // Nothing waiting — just reload as a fallback.
      window.location.reload();
      return;
    }
    reg.waiting.postMessage({ type: 'SKIP_WAITING' });
    // Reload once the new SW takes over.
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  });
}

export function checkOnline(): boolean {
  if (typeof navigator === 'undefined') return true;
  return navigator.onLine;
}
