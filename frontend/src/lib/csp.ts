/**
 * CSP nonce helpers for the SPA.
 *
 * EnterpriseCore ships a Content-Security-Policy that uses per-request
 * nonces on the `script-src` directive. The SPA itself is delivered as a
 * static bundle and does not normally need to inject inline scripts, but
 * any code that *does* need to (third-party widgets, dynamic feature flags,
 * trusted A/B-test snippets, the Sentry replay bootstrap, etc.) must read
 * the active nonce and stamp it onto the new <script> element.
 *
 * The backend emits the nonce two ways:
 *   1. In the `Content-Security-Policy` response header (read-only from JS).
 *   2. As a `<meta name="csp-nonce" content="...">` tag injected by the
 *      template renderer for HTML responses (the SPA index.html template
 *      should include `<meta name="csp-nonce" content="{{ csp_nonce }}">`).
 *
 * Use {@link getCspNonce} to retrieve the nonce, and {@link createNoncedScript}
 * to build a `<script>` element that will survive the strict CSP.
 */

/**
 * Read the request-scoped CSP nonce from the `<meta name="csp-nonce">` tag.
 *
 * Returns an empty string when no nonce is present (e.g. running under
 * `file://` from the Electron build, where the static index.html does not
 * pass through the backend template).
 */
export function getCspNonce(): string {
  if (typeof document === "undefined") return "";
  const meta = document.querySelector(
    'meta[name="csp-nonce"]'
  ) as HTMLMetaElement | null;
  return meta?.content ?? "";
}

/**
 * Build a `<script>` element that carries the active CSP nonce.
 *
 * Prefer this over `document.createElement("script")` whenever you need to
 * inject runtime JavaScript — without a nonce the browser will refuse to
 * execute the script under our strict CSP.
 */
export function createNoncedScript(
  src?: string,
  inlineCode?: string
): HTMLScriptElement {
  const el = document.createElement("script");
  const nonce = getCspNonce();
  if (nonce) {
    el.setAttribute("nonce", nonce);
  }
  if (src) {
    el.src = src;
  }
  if (inlineCode) {
    el.text = inlineCode;
  }
  return el;
}

/**
 * Inject a nonced inline script into `<head>` and resolve once executed.
 *
 * Resolves immediately for inline code (browser executes synchronously
 * during the `appendChild` call) and on the `load` event for `src` scripts.
 */
export function injectNoncedScript(opts: {
  src?: string;
  inlineCode?: string;
}): Promise<HTMLScriptElement> {
  return new Promise((resolve, reject) => {
    const el = createNoncedScript(opts.src, opts.inlineCode);
    if (opts.src) {
      el.onload = () => resolve(el);
      el.onerror = () =>
        reject(new Error(`failed to load script: ${opts.src}`));
    }
    document.head.appendChild(el);
    if (!opts.src) {
      // Inline scripts run synchronously on append.
      resolve(el);
    }
  });
}
