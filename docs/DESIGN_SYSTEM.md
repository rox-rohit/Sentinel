# SENTINEL Design System

## Principles

1. **Operations first.** Dense, scannable, readable at a glance on a control-room
   display. No oversized empty cards.
2. **Colour carries meaning.** Cyan is structural; amber and red appear only for
   risk, never as decoration.
3. **Numerals are data.** Telemetry uses a mono font with tabular numerals so
   digits line up between rows.
4. **One system.** All pages use the same panel, badge, stat, meter and table
   primitives.

## Tokens (`src/styles.css`)

Colour is semantic and themed. Components never contain a hex value: the
`@theme inline` block maps each `--color-*` utility to a palette variable, and
`:root[data-theme=…]` supplies the values. Default (Sentinel) values:

| Token | Sentinel | Use |
|---|---|---|
| `--color-bg` | `#07090c` | App background |
| `--color-bg-deep` | `#05070a` | Sidebar |
| `--color-surface` | `#0b0f14` | Flat panels |
| `--color-surface-2` | `#10161d` | Inputs, nested surfaces |
| `--color-raised` | `#141c25` | Chips, mini stats |
| `--color-line` | `rgb(148 178 205 / 0.10)` | Separators |
| `--color-line-strong` | `rgb(148 178 205 / 0.18)` | Emphasis borders |
| `--color-fg` | `#e8f0f7` | Primary text |
| `--color-muted` | `#8b9bab` | Secondary text |
| `--color-faint` | `#5d6b7a` | Labels, metadata |
| `--color-accent` | `#35d6f2` | Primary accent, active nav |
| `--color-accent-2` | `#3b82f6` | Secondary data series |
| `--color-good` | `#2dd4a7` | Healthy |
| `--color-warn` | `#f5a524` | Warning / attention |
| `--color-bad` | `#f4495d` | High risk |
| `--color-critical` | `#ff4d6d` | Critical |

The same palettes define supporting tokens: `--overlay-1/2/3` (subtle fills),
`--track` / `--track-strong` (progress rails), `--accent-soft` / `--accent-line`
(chips and emphasis), `--good-soft` / `--good-line`, `--warn-soft` /
`--warn-line`, `--bad-soft` / `--bad-line`, `--critical-soft` /
`--critical-line`, `--chart-1…5`, `--panel-top` / `--panel-bottom`,
`--header-bg`, `--tooltip-bg` / `--tooltip-fg`, `--grid-line`, `--axis`,
`--glow-1` / `--glow-2` and `--selection`.

## Themes

`ThemeProvider` (`src/lib/theme.tsx`) writes `data-theme` on `<html>`, sets
`color-scheme`, persists the choice in `localStorage` and updates the
`theme-color` meta tag. An inline script in `index.html` applies the saved theme
before first paint. Charts take `var(--chart-n)` strings so SVG series follow the
palette.

| Id | Name | Scheme | Intent |
|---|---|---|---|
| `sentinel` | Sentinel | dark | Midnight command centre, cyan telemetry (default) |
| `obsidian` | Obsidian | dark | True black, monochrome steel, no glow |
| `daylight` | Daylight | light | Paper white surfaces, ink-blue accents |
| `graphite` | Graphite | light | Warm stone neutrals, deep teal |
| `aurora` | Aurora | dark | Indigo night, violet and cyan gradients |

The picker lives in the top bar and in System Settings. New UI must use tokens;
a raw hex or `rgb()` in a component is a defect. Amber is reserved for
risk/attention semantics — never for banner styling or decoration.

Typography: Google Sans (interface), IBM Plex Mono (all telemetry numerals).
Base text 11–13 px, page title 19 px, KPI values 26 px — enterprise density,
never editorial scale.

## Surfaces

- `.panel` — gradient surface + 1 px line + 14 px radius. The default container.
- `.panel-flat` — solid surface for nested cards.
- `.raised` — 8 px radius chip for metric tiles.
- `.numeric` — mono, tabular numerals, tightened tracking.
- `.grid-backdrop` — faint 44 px grid, available for empty or hero areas.

No glow, no gradients on text, no rounded 24 px marketing cards.

## Components

| Component | Responsibility |
|---|---|
| `AppShell` | Sidebar navigation, sticky top bar, data-source indicator |
| `PageHeader` + `Note` | Page title, eyebrow, description, caveat callouts |
| `Panel` | Titled surface with optional action and footer |
| `Stat` / `MiniStat` | KPI block with label, value, unit, hint, tone |
| `Badge` / `Label` | Health/severity pill; uppercase micro-label |
| `HealthMeter` / `RiskMeter` / `Ring` | Health bar, risk bar, circular gauge |
| `Table` / `Row` / `Cell` | Dense tables with hover-to-open rows |
| `TelemetryChart` | Multi-series time line chart (Recharts) |
| `AreaTrend` | Filled trend area |
| `BarsChart` | Vertical/horizontal bars |
| `ScatterPlot` | Predicted vs actual, distribution scatter |

## Chart rules

- Grid lines horizontal only, `rgb(148 178 205 / 0.07)`.
- Axis text 10 px, muted, no tick lines.
- Series: cyan primary, blue secondary, amber anomaly, red critical.
- No animation (`isAnimationActive={false}`) — operational charts should not
  re-animate on every refresh.
- Every chart is fed by API/snapshot values; no chart has a hardcoded series.

## Status semantics

| Band | Health | Severity | Colour |
|---|---|---|---|
| Healthy | ≥ 80 | normal | green |
| Attention | 60–79 | low | cyan |
| Warning | 40–59 | medium | amber |
| Critical | < 40 | high/critical | red |

Severity is always shown with its numeric score so colour is never the only cue.

## Layout

- Sidebar: 244 px fixed, grouped nav (Operations / Intelligence / Platform).
- Top bar: 54 px, page breadcrumb, data-source pill, refresh, alert count.
- Content: 16 px gutters on mobile, 24 px on desktop; max 6 KPI columns at XL.
- Breakpoints: single column below `lg`, `xl` two-column analytical layouts.

## Accessibility

- Focus ring on every interactive element (`:focus-visible` cyan outline).
- Status text accompanies colour.
- Tables use real `<table>` semantics; the fleet matrix buttons carry titles.
- Reduced motion honoured globally.
