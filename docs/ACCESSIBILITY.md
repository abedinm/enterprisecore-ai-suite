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

Re-baselined 2026-05-25 after the WCAG 2.1 AA pass. Logged-in pages
require an authenticated preview server (default admin / `ChangeMe123!`)
and are re-audited from a clean dev build:

```
npm run build && npm run preview
node scripts/lighthouse-audit.mjs   # defaults to http://127.0.0.1:5173/
LH_URL=http://127.0.0.1:4173/dashboard node scripts/lighthouse-audit.mjs
```

| Page                     | Perf | A11y | BP  | SEO |
| ------------------------ | ---- | ---- | --- | --- |
| Marketing public site    | 94   | 95   | 100 | 91  |
| LoginPage                | 96   | 97   | 100 | 92  |
| Dashboard (logged-in)    | 91   | 96   | 100 | 87  |
| Construction Dashboard   | 89   | 96   | 100 | 87  |
| Knowledge Hub            | 90   | 97   | 100 | 87  |

A11y target is ≥95; all five pages clear it. The pre-AA-pass baseline
was 90 for the marketing site and n/a (no skip link, missing roles) for
the logged-in pages.

## Recent fixes (2026-05-25)

* **Marketing theme picker now blocks save** when any text/background
  pair falls below 4.5:1. `src/lib/colorContrast.ts` implements the W3C
  relative-luminance formula; the Settings page surfaces a live ratio
  table and an "Auto-adjust" button that nudges the offending color
  toward black or white until it passes.
* **`<Modal>` primitive** with `role="dialog"`, `aria-modal`,
  `aria-labelledby`, focus trap (via `useFocusTrap`), Escape to close,
  backdrop-click to close, and a labelled `<ModalClose>` X button.
  Adopted by Advising, Deadlines (×2), GroupProjects (×2), LabReports,
  Raci, Risks, Schedule (×2) — 10 inline modals refactored.
* **`<StatusRegion>` + `useAnnouncer()`** for loading / error / success
  announcements. `<LiveAnnouncer>` mounts once in AppShell.
* **Risk heatmap (`ProjectDashboard`)** is now a proper ARIA grid with
  roving tabindex, arrow-key navigation, and per-cell aria-labels
  (`"Probability 3, impact 4, 2 risks"`).
* **Gantt bars (`Schedule`)** are keyboard-reachable: each task row
  carries `role="button"`, `aria-label` describing the date range and
  progress, plus Enter / ArrowUp / ArrowDown handlers.
* **Token bumps:** `--color-ink-subtle` now 100/116/139 in light (4.6:1
  on white) and 156/163/175 in dark (5.0:1 on surface). Button
  `disabled:opacity-50` raised to `disabled:opacity-70` so disabled
  labels still meet contrast.
* **Chart wrapping:** Recharts in `UsageTab` now sits inside
  `<figure>` + sr-only `<figcaption>` with `role="img"` and
  `aria-label` on the chart container.
* **Form errors:** LoginPage error now carries `role="alert"` +
  `aria-live="assertive"` so screen-reader users hear validation
  failures immediately.
* **Table skip link:** Finance Invoices ships a sr-only-until-focused
  "Skip invoices table" anchor; reusable via `<TableSkipLink>`.

## Known gaps

* 19 of the ~30 inline modals across academic, construction, marketing,
  and webchat still use the legacy `fixed inset-0` div pattern. They
  remain visually correct and keyboard-dismissible by clicking the X,
  but lack the focus-trap and `aria-modal` of the new `<Modal>`.
  Migration is mechanical — see `Schedule.tsx` / `Risks.tsx` for the
  pattern.
* Most chart pages outside `UsageTab` (Finance dashboards, CRM
  forecast, HR analytics) still need `<figure>` wrappers and chart
  `aria-label`s.

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
