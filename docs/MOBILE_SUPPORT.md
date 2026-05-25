# Mobile support

EnterpriseCore's web UI is mobile-first within the tradeoffs of an
enterprise suite — workflows like Construction Gantt or HR org-chart are
viewable on phones but designed-for landscape tablet+ and desktop.

## Supported viewports

| Class         | Range            | Test devices                          |
| ------------- | ---------------- | ------------------------------------- |
| Small phone   | 360 × 800        | Pixel 5 portrait, iPhone SE          |
| Standard phone| 390 × 844        | iPhone 13 portrait                    |
| Large phone   | 414 × 896        | iPhone 11 Pro Max portrait            |
| Tablet portrait| 768 × 1024      | iPad portrait                          |
| Tablet landscape| 1024 × 768     | iPad landscape                        |
| Small desktop | 1280 × 800       | 13" laptop                            |
| Large desktop | 1920 × 1080      | Most workstations                     |

The breakpoint cut-offs (Tailwind defaults):

* `sm` ≥ 640px
* `md` ≥ 768px
* `lg` ≥ 1024px
* `xl` ≥ 1280px

The `useViewport()` hook in `frontend/src/hooks/useViewport.ts` exposes
`isMobile` (<768), `isTablet` (768–1023), `isDesktop` (≥1024) for
components that need different layouts (e.g. split-pane → tabs, table →
cards).

## Layout rules

| Concern                | Mobile (< 768)                                 | Tablet (768-1023)        | Desktop (≥ 1024)       |
| ---------------------- | ---------------------------------------------- | ------------------------ | ---------------------- |
| Sidebar                | Hamburger overlay (off-canvas)                 | Hamburger overlay        | Pinned 288px           |
| Tables                 | Horizontal scroll in `.ec-table-wrap`          | Same                     | Inline                 |
| Wide tables            | `.ec-table-sticky-col` keeps first col sticky  | Same                     | n/a                    |
| Forms                  | `.ec-form-stack` → 1-column                    | 2-column                 | 2-3 column             |
| Modals                 | `.ec-modal` → full-screen at < 480px           | Centered card            | Centered card          |
| Split-pane editors     | Tab strip                                      | Tab strip                | Side-by-side           |
| Touch targets          | 44×44px min via `.ec-tap` / `.touch-target-44` | 44×44                    | n/a (mouse)            |

## Per-page status

| Page                       | Mobile-ready | Notes                                                                 |
| -------------------------- | ------------ | --------------------------------------------------------------------- |
| LoginPage                  | yes          | Single column, fits 360px wide.                                       |
| SignupPage                 | yes          | Same.                                                                 |
| AppShell                   | yes          | Hamburger + bottom-padded main content.                               |
| Dashboard (overview)       | yes          | Tile grid collapses 4→2→1.                                            |
| Marketing public site      | yes          | Mobile-first renderer, themes auto-stack.                             |
| Construction Dashboard     | partial      | Gantt + heatmap scroll horizontally on phones. Tap-and-drag on touch. |
| Knowledge RAG chat         | partial      | Split-pane (chat | sources) collapses to tabs on mobile.              |
| Web Chat ConversationsViewer| partial     | Same pattern — tabs on phones.                                        |
| Org Settings               | yes          | Sub-nav is a pill strip on mobile.                                    |
| BotEditor                  | partial      | Step-by-step wizard works on phones; preview pane stacks below.       |
| HR Org Chart               | desktop only | Inherently 2-D — pinch-to-zoom on tablet+.                            |
| Finance Reports            | tablet+      | Wide multi-column tables; phone users see a scroll-hint banner.       |
| Coding IDE (Monaco)        | desktop only | Monaco itself is desktop-only; route blocks < 1024.                   |

## CSS utilities

`frontend/src/index.css` provides:

```
.ec-table-wrap        — adds horizontal scroll to a table container
.ec-table-sticky-col  — sticks the first column on mobile widths
.ec-modal             — full-screen takeover < 480px, centered above
.ec-form-stack        — forces 1-column at < 480px
.ec-tap               — opts a button into 44×44 min on coarse pointers
```

Always wrap a wide table:

```jsx
<div className="ec-table-wrap ec-table-sticky-col">
  <table className="ec-table">…</table>
</div>
```

## What we don't ship

* **Native mobile apps.** Only PWA + Electron desktop.
* **Offline mobile sync.** The PWA registers a service worker for asset
  caching only; data still requires a connection.
* **Gesture-heavy interactions.** Long-press menus, pinch zoom, or
  3D-Touch — all absent. Standard tap, double-tap, swipe (in
  carousels/sidebar).

## Testing checklist

When you touch a page:

- [ ] Open Chrome DevTools → Device Toolbar → Pixel 5 (393×851).
- [ ] No horizontal scrollbar appears.
- [ ] Every interactive element is ≥ 44×44 px (use the DevTools ruler).
- [ ] Forms stack to one column.
- [ ] Modals are full-screen at < 480px (try iPhone SE 375×667).
- [ ] Sidebar opens via the hamburger and closes on Tab → outside-click.
- [ ] Switch to 414×896 (iPhone 11) — verify the layout still works.
- [ ] Switch to 768×1024 (iPad portrait) — sidebar should still be off-canvas
      since `lg:` is 1024.
- [ ] Switch to 1024×768 (iPad landscape) — sidebar pins to the left.
