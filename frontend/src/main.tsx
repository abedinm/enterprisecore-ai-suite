import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { initSentry } from './lib/sentry';
import { registerPWA } from './lib/pwa';
import { installA11yShim } from './lib/a11y-shim';
import './i18n';
import './index.css';

// Initialise observability before React mounts so early errors are captured.
// No-op unless VITE_SENTRY_DSN is set at build time.
initSentry();

// Register the service worker (no-op in dev / Electron / unsupported browsers).
registerPWA();

// Runtime accessibility shim — patches systemic gaps in the pre-existing
// surface (label↔input association, th scope, icon-button aria-label,
// table overflow wrapping). New code should still use the principled
// primitives; this is the safety net for legacy markup.
installA11yShim();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
