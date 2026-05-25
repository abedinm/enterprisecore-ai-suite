// Sentry frontend initialisation. No-op when VITE_SENTRY_DSN is unset, which
// is the default for dev and offline / desktop installs.
//
// The @sentry/react SDK is imported dynamically so that builds without a DSN
// don't pull the (~80 KB gzipped) tracing + replay bundles into the initial
// chunk. Tree-shaking on the dynamic-import branch keeps the build clean.

export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return;
  // Dynamic import so unused tree-shakes when no DSN is configured.
  // The @sentry/react types are only resolvable once the package is installed
  // via `npm install` — until then we let TS treat the module as opaque so
  // the build doesn't break in environments that haven't run install yet.
  import(/* @vite-ignore */ '@sentry/react' as string)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .then((Sentry: any) => {
      Sentry.init({
        dsn,
        environment: import.meta.env.MODE,
        tracesSampleRate: 0.1,
        sendDefaultPii: false,
        integrations: [
          Sentry.browserTracingIntegration(),
          Sentry.replayIntegration({ maskAllText: true, blockAllMedia: true }),
        ],
        replaysSessionSampleRate: 0,
        replaysOnErrorSampleRate: 1.0,
      });
    })
    .catch((err: unknown) => {
      // Don't crash the app if Sentry fails to load (offline, CDN error, etc.).
      console.warn('[sentry] failed to load:', err);
    });
}
