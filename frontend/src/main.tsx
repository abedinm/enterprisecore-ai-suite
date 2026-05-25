import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { initSentry } from './lib/sentry';
import { registerPWA } from './lib/pwa';
import './i18n';
import './index.css';

// Initialise observability before React mounts so early errors are captured.
// No-op unless VITE_SENTRY_DSN is set at build time.
initSentry();

// Register the service worker (no-op in dev / Electron / unsupported browsers).
registerPWA();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
