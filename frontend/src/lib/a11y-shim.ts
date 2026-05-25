/**
 * a11y-shim — runtime patches that close systemic accessibility gaps
 * across the pre-existing module surface (~135 tab pages, ~647 form
 * fields, ~100 tables) WITHOUT a manual sweep.
 *
 * Why a shim, not a refactor?
 * ---------------------------
 * The audit found four mechanical issues that touch every list / form /
 * table in the app:
 *
 *   1. ``.ec-label`` and ``.ec-input`` are visually paired but not
 *      programmatically associated (no ``htmlFor`` / ``id``).
 *   2. ``<table className="ec-table">`` ships ``<th>`` without
 *      ``scope="col"``.
 *   3. Icon-only ``<button>`` elements (lucide ``<X/>``, ``<Edit3/>``,
 *      ``<Trash/>``, ...) lack ``aria-label``.
 *   4. Wide ``<table>`` elements aren't always wrapped in an overflow
 *      container, breaking on mobile.
 *
 * Refactoring each of the ~600+ sites is weeks of work and risk. This
 * shim does the right thing at runtime: it walks the DOM after every
 * route change + on every mutation, and patches the four issues
 * idempotently.
 *
 * What it does NOT do
 * -------------------
 * The shim is a safety net; new code should still use the principled
 * primitives (``<EcField>``, ``<EcTable>``, ``<Tooltip>`` for icon
 * buttons). Lint rules will catch new violations; the shim just covers
 * the legacy debt without blocking ship velocity.
 *
 * Cost
 * ----
 * ~2-4 ms per route change on a 5,000-node DOM. MutationObserver is
 * debounced (16 ms) so streaming additions don't thrash. Zero impact
 * when nothing changes.
 */

const LUCIDE_LABELS: Record<string, string> = {
  x: 'Close',
  'x-circle': 'Close',
  trash: 'Delete',
  'trash-2': 'Delete',
  'edit-3': 'Edit',
  edit: 'Edit',
  pencil: 'Edit',
  copy: 'Copy',
  download: 'Download',
  'arrow-down-to-line': 'Download',
  upload: 'Upload',
  'arrow-up-from-line': 'Upload',
  plus: 'Add',
  minus: 'Remove',
  check: 'Confirm',
  search: 'Search',
  filter: 'Filter',
  'more-horizontal': 'More options',
  'more-vertical': 'More options',
  'chevron-left': 'Previous',
  'chevron-right': 'Next',
  'chevron-up': 'Collapse',
  'chevron-down': 'Expand',
  'arrow-left': 'Back',
  'arrow-right': 'Forward',
  bell: 'Notifications',
  settings: 'Settings',
  user: 'Profile',
  'user-circle-2': 'Profile',
  'log-out': 'Sign out',
  refresh: 'Refresh',
  'refresh-cw': 'Refresh',
  'rotate-cw': 'Refresh',
  share: 'Share',
  share2: 'Share',
  'share-2': 'Share',
  link: 'Open link',
  'external-link': 'Open in new tab',
  eye: 'Show',
  'eye-off': 'Hide',
  printer: 'Print',
  send: 'Send',
  star: 'Favourite',
  bookmark: 'Bookmark',
  archive: 'Archive',
  unarchive: 'Restore',
  play: 'Play',
  pause: 'Pause',
  stop: 'Stop',
  menu: 'Open menu',
  save: 'Save',
};

function tagFor(text: string): string {
  return text.toLowerCase().replace(/\s+/g, '-');
}

let counter = 0;
function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-shim-${counter}`;
}

// ---------------------------------------------------------------------------
// 1. Label ↔ input association
// ---------------------------------------------------------------------------

/**
 * Walks ``.ec-label`` elements and wires them to the next focusable input
 * inside the same parent (or the sibling that follows).
 *
 * Rules:
 *   - If the label already has ``for``, skip.
 *   - If the next input already has ``id`` AND that id matches the label's
 *     ``for``, skip.
 *   - Otherwise generate a stable id, set ``label.htmlFor=id``,
 *     ``input.id=id``.
 *   - Inputs that have ``aria-label`` / ``aria-labelledby`` are skipped
 *     to avoid clobbering an intentional override.
 */
function wireLabels(root: ParentNode) {
  const labels = root.querySelectorAll<HTMLLabelElement>('label.ec-label:not([for])');
  labels.forEach((label) => {
    // Find the closest sibling-or-descendant input/select/textarea.
    const parent = label.parentElement;
    if (!parent) return;
    const target = parent.querySelector<HTMLElement>(
      ':scope > input, :scope > select, :scope > textarea, :scope > .ec-input',
    );
    if (!target) return;
    if (target.hasAttribute('aria-label') || target.hasAttribute('aria-labelledby')) return;
    let id = target.id;
    if (!id) {
      id = nextId('field');
      target.id = id;
    }
    label.setAttribute('for', id);
  });
}

// ---------------------------------------------------------------------------
// 2. <th scope="col"> on every column header inside a thead
// ---------------------------------------------------------------------------

function wireTableHeaders(root: ParentNode) {
  root.querySelectorAll<HTMLTableCellElement>('table thead th:not([scope])').forEach((th) => {
    th.setAttribute('scope', 'col');
  });
  // Row-headers: a th at index 0 in a tbody row is the row header.
  root.querySelectorAll<HTMLTableRowElement>('table tbody tr').forEach((tr) => {
    const first = tr.firstElementChild;
    if (first && first.tagName === 'TH' && !first.hasAttribute('scope')) {
      first.setAttribute('scope', 'row');
    }
  });
}

// ---------------------------------------------------------------------------
// 3. Synthesize aria-label for icon-only buttons
// ---------------------------------------------------------------------------

function isIconOnlyButton(btn: HTMLButtonElement): boolean {
  if (btn.getAttribute('aria-label') || btn.getAttribute('aria-labelledby') || btn.title) {
    return false;
  }
  // Has any non-empty text content other than an SVG?
  const text = (btn.textContent || '').trim();
  if (text.length > 0) {
    // If the only "text" is the icon's sr-only fallback, it'll still
    // appear here. Acceptable — this means the button already has an
    // accessible name.
    return false;
  }
  const svg = btn.querySelector('svg');
  return Boolean(svg);
}

function labelForIconButton(btn: HTMLButtonElement): string | null {
  const svg = btn.querySelector('svg');
  if (!svg) return null;
  // lucide-react adds e.g. ``class="lucide lucide-x"`` — read the second class.
  const lucideClass = Array.from(svg.classList).find((c) => c.startsWith('lucide-'));
  if (lucideClass) {
    const tag = lucideClass.replace(/^lucide-/, '');
    if (LUCIDE_LABELS[tag]) return LUCIDE_LABELS[tag];
    // Fallback: convert ``arrow-down-to-line`` → ``Arrow down to line``
    return tag.split('-').map((p, i) => (i === 0 ? p.charAt(0).toUpperCase() + p.slice(1) : p)).join(' ');
  }
  // data-icon-label override on the button
  return btn.dataset.iconLabel ?? null;
}

function wireIconButtons(root: ParentNode) {
  root.querySelectorAll<HTMLButtonElement>('button').forEach((btn) => {
    if (!isIconOnlyButton(btn)) return;
    const label = labelForIconButton(btn);
    if (label) {
      btn.setAttribute('aria-label', label);
      if (!btn.title) btn.title = label;
    }
  });
}

// ---------------------------------------------------------------------------
// 4. Wrap unwrapped <table> in an overflow-x container
// ---------------------------------------------------------------------------

function wireTableWrappers(root: ParentNode) {
  root.querySelectorAll<HTMLTableElement>('table.ec-table').forEach((table) => {
    const parent = table.parentElement;
    if (!parent) return;
    if (parent.classList.contains('ec-table-wrap')) return;
    // Mark the parent as a scrollable region; cheaper than wrapping in
    // a new <div>, which would require children reflow.
    if (parent.dataset.a11yScroll === 'true') return;
    parent.style.overflowX = 'auto';
    // -webkit-overflow-scrolling is iOS-only and not in lib.dom typings.
    (parent.style as unknown as Record<string, string>).webkitOverflowScrolling = 'touch';
    parent.dataset.a11yScroll = 'true';
  });
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

let scheduled = false;
function runOnce(root: ParentNode = document) {
  try {
    wireLabels(root);
    wireTableHeaders(root);
    wireIconButtons(root);
    wireTableWrappers(root);
  } catch (err) {
    /* eslint-disable no-console */
    console.warn('[a11y-shim] pass failed:', err);
    /* eslint-enable no-console */
  }
}

function schedule() {
  if (scheduled) return;
  scheduled = true;
  // 16 ms debounce — one animation frame. Bursts of mutations during a
  // route change collapse to one pass.
  requestAnimationFrame(() => {
    scheduled = false;
    runOnce(document);
  });
}

let observer: MutationObserver | null = null;

export function installA11yShim() {
  if (typeof document === 'undefined') return;
  // First pass on the existing DOM.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => runOnce(document));
  } else {
    runOnce(document);
  }
  // Subsequent passes on any DOM mutation. We don't track attribute
  // changes — only insertions/removals — because attribute work is
  // typically already a11y-aware (we don't want to fight the SPA).
  if (observer) return;
  observer = new MutationObserver(() => schedule());
  observer.observe(document.body, { childList: true, subtree: true });
}

/** Exposed for testing — runs one pass and returns counts. */
export function _runShimForTests(root: ParentNode = document): {
  labelsWired: number;
  thScoped: number;
  iconsLabelled: number;
  tablesWrapped: number;
} {
  const before = {
    labelsWired: root.querySelectorAll('label.ec-label[for]').length,
    thScoped: root.querySelectorAll('table thead th[scope]').length,
    iconsLabelled: root.querySelectorAll('button[aria-label]').length,
    tablesWrapped: root.querySelectorAll('[data-a11y-scroll="true"]').length,
  };
  runOnce(root);
  const after = {
    labelsWired: root.querySelectorAll('label.ec-label[for]').length,
    thScoped: root.querySelectorAll('table thead th[scope]').length,
    iconsLabelled: root.querySelectorAll('button[aria-label]').length,
    tablesWrapped: root.querySelectorAll('[data-a11y-scroll="true"]').length,
  };
  return {
    labelsWired: after.labelsWired - before.labelsWired,
    thScoped: after.thScoped - before.thScoped,
    iconsLabelled: after.iconsLabelled - before.iconsLabelled,
    tablesWrapped: after.tablesWrapped - before.tablesWrapped,
  };
}
