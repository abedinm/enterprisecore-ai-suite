/* EnterpriseCore service worker.
 *
 * Hand-written. Provides the following caching strategies:
 *
 *   App shell (HTML, hashed JS/CSS, fonts, icons)  CacheFirst, versioned.
 *   /assets/* (hashed bundles)                     CacheFirst, 30 day max.
 *   /widget.js                                     StaleWhileRevalidate, 1 day.
 *   /api/v1/* (GET only)                           NetworkFirst, 10s timeout,
 *                                                  5 min stale window.
 *   /site/*                                        NetworkFirst, 1 hour.
 *   /api/health, /metrics                          always passthrough.
 *   POST/PATCH/PUT/DELETE                          always passthrough.
 *
 * Offline fallback:
 *   Navigation requests  ->  /offline.html
 *   API requests         ->  JSON 503 {"error":"offline","code":"offline_no_cache"}
 *
 * Service worker version is hard-coded for now. The build pipeline can later
 * replace __SW_VERSION__ during the prod build to bust caches automatically.
 */

/* global self, caches, fetch, Response, URL */

const SW_VERSION = 'v1';
const SHELL_CACHE = `ec-shell-${SW_VERSION}`;
const ASSET_CACHE = `ec-assets-${SW_VERSION}`;
const API_CACHE = `ec-api-${SW_VERSION}`;
const SITE_CACHE = `ec-site-${SW_VERSION}`;
const WIDGET_CACHE = `ec-widget-${SW_VERSION}`;

const KNOWN_CACHES = [SHELL_CACHE, ASSET_CACHE, API_CACHE, SITE_CACHE, WIDGET_CACHE];

// Files that must always be available offline. Kept minimal because the rest of
// the bundle is hashed and cached on first visit anyway.
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json',
  '/icons/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/logo.svg',
];

const API_TIMEOUT_MS = 10_000;
const API_MAX_AGE_MS = 5 * 60 * 1000;
const SITE_MAX_AGE_MS = 60 * 60 * 1000;
const ASSET_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const WIDGET_MAX_AGE_MS = 24 * 60 * 60 * 1000;

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Best-effort precache. Don't reject the install if a single file 404s,
      // otherwise a stray missing asset breaks the whole SW lifecycle.
      await Promise.all(
        PRECACHE_URLS.map((url) =>
          cache
            .add(new Request(url, { cache: 'reload' }))
            .catch((err) => console.warn('[sw] precache miss', url, err)),
        ),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.map((key) => {
          if (!KNOWN_CACHES.includes(key) && key.startsWith('ec-')) {
            return caches.delete(key);
          }
          return undefined;
        }),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('fetch', (event) => {
  const request = event.request;

  // Only handle same-origin and same-scope traffic. Cross-origin requests
  // (CDNs, analytics, Sentry) bypass the worker entirely.
  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }
  if (url.origin !== self.location.origin) return;

  // Never intercept mutations or non-cacheable telemetry.
  if (request.method !== 'GET') return;
  if (url.pathname === '/api/health' || url.pathname === '/metrics') return;

  if (url.pathname.startsWith('/api/v1/')) {
    event.respondWith(handleApi(request));
    return;
  }
  if (url.pathname.startsWith('/site/')) {
    event.respondWith(handleSite(request));
    return;
  }
  if (url.pathname === '/widget.js') {
    event.respondWith(handleWidget(request));
    return;
  }
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(handleAsset(request));
    return;
  }
  if (request.mode === 'navigate' || (request.destination === 'document')) {
    event.respondWith(handleNavigation(request));
    return;
  }
  // Everything else (root, manifest, icons, logo, etc.) -> shell cache.
  event.respondWith(handleShell(request));
});

// ---------- strategy helpers ----------

function timestamped(response) {
  // Stash a Date header so we can implement max-age on cached responses.
  // Native Cache API doesn't expire entries on its own.
  if (!response || !response.ok) return response;
  const headers = new Headers(response.headers);
  headers.set('x-sw-cached-at', String(Date.now()));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

function isFresh(response, maxAgeMs) {
  if (!response) return false;
  const cachedAt = Number(response.headers.get('x-sw-cached-at') || 0);
  if (!cachedAt) return true;
  return Date.now() - cachedAt < maxAgeMs;
}

async function handleNavigation(request) {
  // NetworkFirst for the SPA shell, falling back to cached / offline.html.
  try {
    const network = await fetch(request);
    if (network && network.ok) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put('/index.html', network.clone()).catch(() => undefined);
    }
    return network;
  } catch {
    const cached = await caches.match('/index.html');
    if (cached) return cached;
    const offline = await caches.match('/offline.html');
    if (offline) return offline;
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

async function handleShell(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) {
    // Refresh in the background.
    fetch(request)
      .then((res) => {
        if (res && res.ok) cache.put(request, timestamped(res.clone())).catch(() => undefined);
      })
      .catch(() => undefined);
    return cached;
  }
  try {
    const network = await fetch(request);
    if (network && network.ok) {
      cache.put(request, timestamped(network.clone())).catch(() => undefined);
    }
    return network;
  } catch {
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

async function handleAsset(request) {
  const cache = await caches.open(ASSET_CACHE);
  const cached = await cache.match(request);
  if (cached && isFresh(cached, ASSET_MAX_AGE_MS)) return cached;
  try {
    const network = await fetch(request);
    if (network && network.ok) {
      cache.put(request, timestamped(network.clone())).catch(() => undefined);
    }
    return network;
  } catch {
    if (cached) return cached;
    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}

async function handleWidget(request) {
  const cache = await caches.open(WIDGET_CACHE);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((res) => {
      if (res && res.ok) cache.put(request, timestamped(res.clone())).catch(() => undefined);
      return res;
    })
    .catch(() => undefined);
  if (cached && isFresh(cached, WIDGET_MAX_AGE_MS)) {
    networkPromise.catch(() => undefined);
    return cached;
  }
  const network = await networkPromise;
  if (network) return network;
  if (cached) return cached;
  return new Response('// offline', {
    status: 503,
    headers: { 'content-type': 'application/javascript' },
  });
}

async function handleSite(request) {
  const cache = await caches.open(SITE_CACHE);
  return networkFirst(request, cache, SITE_MAX_AGE_MS, /* isApi */ false);
}

async function handleApi(request) {
  const cache = await caches.open(API_CACHE);
  return networkFirst(request, cache, API_MAX_AGE_MS, /* isApi */ true);
}

async function networkFirst(request, cache, maxAgeMs, isApi) {
  const cached = await cache.match(request);
  try {
    const network = await fetchWithTimeout(request, API_TIMEOUT_MS);
    if (network && (network.ok || network.status === 304)) {
      cache.put(request, timestamped(network.clone())).catch(() => undefined);
    }
    return network;
  } catch {
    if (cached && isFresh(cached, maxAgeMs)) return cached;
    if (cached) return cached;
    if (isApi) {
      return new Response(
        JSON.stringify({ error: 'offline', code: 'offline_no_cache' }),
        {
          status: 503,
          headers: { 'content-type': 'application/json' },
        },
      );
    }
    const offline = await caches.match('/offline.html');
    if (offline) return offline;
    return new Response('Offline', { status: 503 });
  }
}

function fetchWithTimeout(request, timeoutMs) {
  return new Promise((resolvePromise, rejectPromise) => {
    const timer = setTimeout(() => rejectPromise(new Error('timeout')), timeoutMs);
    fetch(request).then(
      (res) => {
        clearTimeout(timer);
        resolvePromise(res);
      },
      (err) => {
        clearTimeout(timer);
        rejectPromise(err);
      },
    );
  });
}
