# Design System

## Theme

Dark. Deep blue-grey base — low chroma, not pure black. Feels like calibrated monitoring equipment in a dim operations room. No light mode.

## Color Strategy

Restrained. Tinted dark neutrals carry 90%+ of surfaces. Status colors (ok / info / warn / err) are the only saturated values, reserved exclusively for system state communication. Never used decoratively.

## Color Tokens

All values OKLCH. Defined in `tailwind.config.js` under `theme.extend.colors`.

### Surface stack (ctrl.*)

| Token | OKLCH | Role |
|---|---|---|
| `ctrl-bg` | `oklch(10% 0.008 245)` | Page background |
| `ctrl-surface` | `oklch(14% 0.010 245)` | Sidebar, topbar |
| `ctrl-panel` | `oklch(18% 0.011 245)` | Cards, stat strips |
| `ctrl-raised` | `oklch(22% 0.012 245)` | Hover states, skeleton loaders |
| `ctrl-border` | `oklch(27% 0.013 245)` | All borders |
| `ctrl-divide` | `oklch(20% 0.010 245)` | Row dividers (lighter than border) |

### Text

| Token | OKLCH | Role |
|---|---|---|
| `ctrl-text` | `oklch(92% 0.004 245)` | Primary text |
| `ctrl-muted` | `oklch(55% 0.009 245)` | Secondary text, labels |
| `ctrl-dim` | `oklch(38% 0.009 245)` | Tertiary, timestamps |

### Status (semantic — never decorative)

| Token | OKLCH | Use |
|---|---|---|
| `status-ok` | `oklch(72% 0.14 164)` | Healthy, success |
| `status-info` | `oklch(75% 0.12 205)` | Neutral informational, CTA |
| `status-warn` | `oklch(79% 0.15 80)` | Warning, needs attention |
| `status-err` | `oklch(66% 0.17 25)` | Error, failure, critical |
| `status-ok-bg` | `oklch(17% 0.04 164)` | Badge background |
| `status-info-bg` | `oklch(17% 0.04 205)` | Badge background |
| `status-warn-bg` | `oklch(18% 0.05 80)` | Badge background |
| `status-err-bg` | `oklch(17% 0.05 25)` | Badge background |

## Typography

| Role | Family | Weight | Class |
|---|---|---|---|
| Display / headings | Syne | 600–800 | `font-display font-semibold` |
| Body / UI | DM Sans | 300–600 | `font-sans` (default) |
| Numbers / code | JetBrains Mono | 400–500 | `font-mono tabnum` |

### Scale

```
2xs: 0.625rem / 0.875rem lh — labels, timestamps, section headers
xs:  0.75rem  / 1rem lh
sm:  0.875rem / 1.375rem lh — body default
base: 1rem    / 1.6rem lh
lg:  1.125rem / 1.75rem lh
xl:  1.25rem  / 1.75rem lh
2xl: 1.5rem   / 2rem lh
```

Section labels: `text-2xs font-display font-semibold uppercase tracking-label text-ctrl-muted`

Numeric values in KPIs: `tabnum text-xl font-semibold` (`.tabnum` applies JetBrains Mono with tabular-nums)

## Spacing

Page padding: `px-7 py-7`. View max-width: `max-w-screen-xl`. Section gaps: `space-y-8`. Grid gaps: `gap-4` (tight) or `gap-8` (sections).

## Components

### StatRow

Horizontal KPI strip. Divided cells with label + value + optional sub-text and status color. Skeleton loading via `stat.loading`. Full width, `bg-ctrl-panel rounded-md`.

### SectionContainer

`<section>` with `.section-rule` title (hairline divider extending to the right). Optional subtitle and action slot. Title: `font-display uppercase tracking-label text-ctrl-text`.

### Badge

Inline status pill: colored dot + text, sized `text-xs`. Variants: `success`, `warning`, `error`, `info`, `pending`, `default`.

### Table

`border-collapse` table. Header: `font-display uppercase tracking-label text-ctrl-muted`. Rows: `hover:bg-ctrl-panel transition-colors duration-100`. Skeleton rows via `animate-pulse` placeholders. Empty state via `EmptyState` inline.

### EmptyState

Centered column: icon (`text-ctrl-dim opacity-40`) + message (`text-ctrl-muted`) + optional subtext (`text-ctrl-dim`).

## Elevation

| Shadow | Use |
|---|---|
| `shadow-panel` | Base cards and surfaces |
| `shadow-float` | Hover/elevated state, tooltips |

## Interactive States

All interactive elements:
- `hover:` — color/bg shift, `transition-all duration-150` or `duration-200`
- `active:scale-[0.97–0.99]` — press feedback proportional to element size
- `focus-visible:` — 2px `oklch(75% 0.12 205)` ring, `outline-offset: 2px`
- `disabled:opacity-40 disabled:cursor-not-allowed`

Sidebar nav active: left `w-0.5` accent (`bg-status-info`) + `bg-ctrl-panel` background.

System cards: `hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]`.

## Motion

Transitions: `duration-100` (micro), `duration-150` (nav, buttons), `duration-200` (cards). All `transition-all` or `transition-colors`. No bounce, no spring. No looping animations except loading spinners (`animate-spin`) and skeletons (`animate-pulse`).

## Scrollbars

Styled: 6px width/height, `ctrl-surface` track, `ctrl-border` thumb, hover to `oklch(34% 0.013 245)`.

## Selection

`oklch(75% 0.12 205 / 0.2)` background, `ctrl-text` color.

## CSS Utilities

| Class | Description |
|---|---|
| `.tabnum` | JetBrains Mono + tabular-nums |
| `.status-dot` | 6px circle, inline-block |
| `.section-rule` | flex + `::after` hairline |
| `.font-display` | Force Syne |
| `.animate-spin` | 1s linear rotate |
