# Accessibility

EnterpriseCore targets WCAG 2.1 Level AA conformance. This document records
the conventions our UI follows and the audit baseline.

## What ships in every build

* **Skip-to-content link.** First focusable element in `AppShell`. Lets
  keyboard users jump past the sidebar/topbar straight to `<main>`.
* **`<main>` landmark with `tabIndex={-1}`.** Pairs with the skip link so
  the target is programmatically focusable.
* **`*:focus-visible` ring (3px brand-coloured).** Every interactive
  element shows a clearly visible outline when reached via keyboard. Mouse
  clicks don't trigger it (per WCAG 2.4.7).
* **`prefers-reduced-motion`.** All CSS animations + transitions get
  cut to ~0ms when the OS-level preference is set.
* **`prefers-contrast: more`.** Card borders thicken from 1px → 2px and
  focus rings from 3px → 4px to help low-vision users find structure.
* **`.sr-only` utility.** Visually-hidden text that screen readers still
  announce. Use for icon-only buttons, loading spinners, and any control
  whose visible label would be insufficient.
* **`.touch-target-44`.** Opt-in class that enforces the Apple HIG /
  WCAG 2.5.5 44×44 px tappable surface on coarse pointers. Applied to
  sidebar items + topbar icon buttons on mobile.

See `frontend/src/styles/a11y.css` for the implementation.

## Component checklist

When you build or touch a component, verify each:

- [ ] **Images** carry `alt` (descriptive for content, `alt=""` for decoration).
- [ ] **Form inputs** have an associated `<label htmlFor>` OR `aria-label`.
- [ ] **Icon-only buttons** carry `aria-label`.
- [ ] **Loading spinners** are wrapped in `role="status"` with a `.sr-only`
      label inside (e.g. `<span className="sr-only">Loading…</span>`).
- [ ] **Modal dialogs** carry `role="dialog"` + `aria-modal="true"` and
      trap focus until closed.
- [ ] **Tables** use `<th scope="col">` (or `scope="row"`) and, if the
      table is purely structural, an `aria-label` describing what it
      lists.
- [ ] **Click handlers** belong on `<button>` / `<a>`, not `<div onClick>`.
- [ ] **Color contrast** ≥ 4.5:1 for body text, ≥ 3:1 for large text and
      UI components. Tailwind `text-ink-muted` on `bg-surface-elevated`
      meets 4.5:1 in both light and dark mode.
- [ ] **Keyboard reachable.** Tab through your component — every action
      must be triggerable without a mouse, and `Esc` should dismiss
      modals + dropdowns.

## Lighthouse baseline

| Page                     | Perf | A11y | BP  | SEO |
| ------------------------ | ---- | ---- | --- | --- |
| Marketing public site    | 94   | 90   | 100 | 91  |
| LoginPage                | n/a  | n/a  | n/a | n/a |
| Dashboard (logged-in)    | n/a  | n/a  | n/a | n/a |
| Construction Dashboard   | n/a  | n/a  | n/a | n/a |
| Knowledge Hub            | n/a  | n/a  | n/a | n/a |

(Rows marked `n/a` need a re-audit run after the a11y CSS landed —
script lives at `scripts/lighthouse.mjs`.)

The audit script:

```
npm run build && npm run preview
node scripts/lighthouse.mjs http://127.0.0.1:4173/
```

## Known gaps

* Recharts SVGs don't carry descriptive titles. Wrap each chart in a
  `<figure>` with a sibling `<figcaption>` when the visual is the primary
  signal (not redundant with adjacent tiles).
* Some Marketing site themes use brand colour combos that fall below
  4.5:1 contrast. The renderer flags these in the theme picker UI but
  doesn't block save.

## Reduced motion

We disable transitions globally when the user requests reduced motion.
This includes:

* React-Router page transitions
* Sidebar slide-in on mobile
* Toast slide animations
* Recharts entry animations (set `isAnimationActive={false}` on charts
  that should respect the OS preference — Recharts doesn't read the
  media query itself)

If you add a new animation, gate it the same way:

```css
@media (prefers-reduced-motion: reduce) {
  .your-animation { animation: none !important; transition: none !important; }
}
```

## Screen reader testing

We test against:
* **NVDA** + Firefox on Windows
* **VoiceOver** + Safari on macOS
* **TalkBack** + Chrome on Android (touch + swipe)

When in doubt, run `Ctrl+Alt+Down` (NVDA) or `Ctrl+Opt+Right` (VO) through
the page and listen — anything that announces as "button" without a label,
or skips past important headings, needs a fix.
