/**
 * Recommended `vite-plugin-pwa` configuration.
 *
 * This file is NOT imported by the build today. We ship a hand-written
 * `public/sw.js` and a hand-built `public/manifest.json` that work right now
 * without touching `vite.config.ts` (owned by another agent).
 *
 * When you (or that agent) are ready to migrate to vite-plugin-pwa:
 *
 *   1. npm i -D vite-plugin-pwa workbox-window
 *   2. Import `pwaOptions` from this file into `vite.config.ts`:
 *
 *        import { VitePWA } from 'vite-plugin-pwa';
 *        import { pwaOptions } from './vite.pwa.config';
 *        // ...
 *        plugins: [react(), VitePWA(pwaOptions)],
 *
 *   3. Delete `public/sw.js` (the plugin generates one via workbox).
 *   4. Keep `public/manifest.json` OR move it into `pwaOptions.manifest`
 *      (the plugin will emit a fresh one).
 *   5. Update `src/lib/pwa.ts` registration to use `virtual:pwa-register`
 *      from the plugin instead of the hand-rolled register call.
 *
 * The strategies here mirror the hand-written sw.js so behaviour stays
 * consistent across the switchover.
 */

import type { VitePWAOptions } from 'vite-plugin-pwa';

export const pwaOptions: Partial<VitePWAOptions> = {
  strategies: 'generateSW',
  registerType: 'prompt',
  injectRegister: false, // we control registration manually in src/lib/pwa.ts
  includeAssets: [
    'logo.svg',
    'offline.html',
    'icons/icon.svg',
    'icons/icon-192.png',
    'icons/icon-512.png',
    'icons/icon-512-maskable.png',
  ],
  manifest: {
    name: 'EnterpriseCore AI Suite',
    short_name: 'EnterpriseCore',
    description:
      "Offline-first business management suite — Finance, HR, CRM, Projects, Inventory, Marketing, Construction PM, Web Chat, and AI features in a single installable app.",
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'any',
    theme_color: '#4f46e5',
    background_color: '#0c0f16',
    lang: 'en',
    categories: ['business', 'productivity', 'finance'],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
      { src: '/icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
    ],
    shortcuts: [
      { name: 'New invoice', url: '/#/finance/invoices/new' },
      { name: 'New CRM lead', url: '/#/crm/leads/new' },
      { name: 'Construction projects', url: '/#/construction' },
    ],
  },
  workbox: {
    cleanupOutdatedCaches: true,
    clientsClaim: true,
    skipWaiting: false, // user-prompted via UpdateAvailableBanner
    navigateFallback: '/index.html',
    navigateFallbackDenylist: [/^\/api\//, /^\/metrics$/, /^\/site\//],
    globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
    runtimeCaching: [
      {
        // /api/v1/* GETs — NetworkFirst with 10s timeout, 5 min cache window.
        urlPattern: ({ url, request }) =>
          request.method === 'GET' &&
          url.pathname.startsWith('/api/v1/') &&
          url.pathname !== '/api/health' &&
          url.pathname !== '/metrics',
        handler: 'NetworkFirst',
        options: {
          cacheName: 'ec-api',
          networkTimeoutSeconds: 10,
          expiration: { maxAgeSeconds: 5 * 60, maxEntries: 200 },
          cacheableResponse: { statuses: [0, 200] },
        },
      },
      {
        // /site/* marketing renderer — NetworkFirst, 1h cache.
        urlPattern: ({ url }) => url.pathname.startsWith('/site/'),
        handler: 'NetworkFirst',
        options: {
          cacheName: 'ec-site',
          expiration: { maxAgeSeconds: 60 * 60, maxEntries: 100 },
        },
      },
      {
        // Hashed bundles — CacheFirst, 30 days.
        urlPattern: ({ url }) => url.pathname.startsWith('/assets/'),
        handler: 'CacheFirst',
        options: {
          cacheName: 'ec-assets',
          expiration: { maxAgeSeconds: 30 * 24 * 60 * 60, maxEntries: 200 },
        },
      },
      {
        // Embeddable chat widget — StaleWhileRevalidate, 1 day.
        urlPattern: ({ url }) => url.pathname === '/widget.js',
        handler: 'StaleWhileRevalidate',
        options: {
          cacheName: 'ec-widget',
          expiration: { maxAgeSeconds: 24 * 60 * 60 },
        },
      },
    ],
  },
};
