# Frontend UI/UX Guide

## Purpose

This file is the visual source of truth for the Gujrat RERA Explorer frontend. It defines the UI elements, colour system, component behaviour, and frontend changes needed to keep the application bright, readable, and consistent.

Design direction: **Bright Clinical Data Explorer** — a single light mode using white surfaces, pale blue backgrounds, strong sky-blue accents, dense tables, and clearly separated status colours.

## Design Rules

- Use **one light mode only**. Do not add a dark theme or theme toggle.
- Keep the interface data-dense because this is an Elasticsearch teaching/debugging tool.
- Use white cards and pale blue page backgrounds to make data feel clean and inspectable.
- Use blue for navigation, primary actions, links, and selected states.
- Use semantic colours only for meaning: green = healthy/success, amber = warning, red = error, purple = disabled/non-indexed metadata.
- Never rely on colour alone; pair status colours with text labels, dots, tags, or icons.
- Prefer CSS variables over hard-coded colours.
- Prefer DOM text nodes and safe rendering for all backend data.
- Keep all controls keyboard accessible with visible focus.

## Colour System

### Core Palette

| Token | Value | Use |
|---|---:|---|
| `--bg` | `#f0f7ff` | Main page background |
| `--bg-elev` | `#ffffff` | Primary card/panel surface |
| `--bg-elev-2` | `#f8fafc` | Secondary surface, inactive table rows, tabs strip |
| `--bg-elev-3` | `#e0f2fe` | Pale blue highlight surface |
| `--border` | `#cbd5e1` | Default borders, inputs, secondary buttons |
| `--border-bright` | `#0284c7` | Strong blue border for active/hover states |
| `--border-soft` | `#e2e8f0` | Subtle separators and card borders |
| `--text` | `#0f172a` | Main text, headings, table values |
| `--text-dim` | `#334155` | Secondary body text |
| `--text-faint` | `#64748b` | Labels, metadata, placeholders |
| `--accent` | `#0284c7` | Primary blue, links, selection, focus |
| `--accent-soft` | `rgba(2, 132, 199, 0.1)` | Subtle blue fill |
| `--accent-gradient` | `linear-gradient(135deg, #0284c7, #2563eb)` | Brand mark, active tab, primary buttons |
| `--focus` | `#0284c7` | Keyboard focus ring |
| `--chart-grid` | `rgba(148, 163, 184, 0.25)` | Chart grid lines |

### Semantic Colours

| Token | Value | Use |
|---|---:|---|
| `--green` | `#059669` | Healthy status, positive KPI |
| `--green-bg` | `#ecfdf5` | Success surface |
| `--yellow` | `#d97706` | Warning, malformed/caveat state |
| `--yellow-bg` | `#fffbeb` | Warning surface |
| `--red` | `#dc2626` | Error, failed state |
| `--red-bg` | `#fef2f2` | Error surface |
| `--purple` | `#7c3aed` | Non-indexed metadata, muted badge |
| `--purple-bg` | `#f5f3ff` | Metadata surface |
| `--cyan` | `#0891b2` | Chart series 4 |
| `--orange` | `#ea580c` | Chart series 5 |
| `--pink` | `#db2777` | Chart series 6 |
| `--lime` | `#65a30d` | Chart series 7 |
| `--indigo` | `#4f46e5` | Chart series 8 |

### Supporting Colours

| Use | Value |
|---|---:|
| Sticky header background | `#ffffff` |
| Sticky header bottom border | `#bae6fd` |
| Header separator | `#e0f2fe` |
| Pill border | `#bae6fd` |
| Pill background | `#f0f9ff` |
| Pill text | `#0369a1` |
| Table header background | `#f0f7ff` |
| Table header border | `#bae6fd` |
| Highlight background | `#fef08a` |
| Highlight text | `#854d0e` |
| Highlight border | `#facc15` |
| Code editor background | `#0f172a` |
| Code editor text | `#38bdf8` |
| Code editor border | `#334155` |

### Contrast Guidance

- Body text must stay dark: `#0f172a`, `#334155`, or `#64748b` on white/pale blue.
- Do not use pale blue text on white for small text.
- Use `#0369a1` for small blue labels on light surfaces; use `#0284c7` for larger labels, borders, and fills.
- White text is allowed only on strong blue fills such as `#0284c7`, `#0369a1`, or the primary gradient.
- Error text should use `#991b1b` or `#b91c1c` inside `#fef2f2`.
- Warning text should use `#78350f` or `#b45309` inside `#fffbeb`.

## Typography

| Element | Font / Style |
|---|---|
| Base font | `Inter`, system UI fallback |
| Base size | `14px`, line height `1.5` |
| Page title | `20px`, weight `800` |
| Panel title | `24px`, weight `800` |
| Card title | `16px`, weight `800` |
| KPI value | `28px`, weight `850`, tight letter spacing |
| Labels | `11.5px`, uppercase, letter spacing `0.07em`–`0.1em`, weight `750` |
| Metadata | `12px`–`13px`, `--text-faint` |
| Mono text | `ui-monospace`, `SFMono-Regular`, `Cascadia Code`, `Consolas` |

Rules:

- Keep headings short and scannable.
- Use uppercase only for labels, table headers, and compact metadata.
- Use monospace for field names, index names, IDs, JSON, query text, and code.
- Do not italicise data values; use badges or colour blocks instead.

## Global Layout

### Shell

- Body: full viewport, pale blue gradient background, no margin, flex column.
- Header: sticky at top using `.site-header-wrap`.
- Header surface: white with `#bae6fd` bottom border and subtle blue shadow.
- Main: `max-width: 1400px`, centred, `26px 28px 48px` padding.
- Footer: pale grey-blue `#f8fafc`, top border, small muted text.

### Header

Elements:

- `.brand-mark`: blue gradient square with `GR`.
- `.brand-text h1`: product title.
- `.brand-sub`: one-line product description.
- `.pill-host`: Elasticsearch host chip.
- `#cluster-pill`: status pill with coloured dot and label.

Status pill rules:

| State | Text | Colour |
|---|---|---|
| Green | `healthy` / `online` | `--green` on `--green-bg` |
| Yellow | `yellow` | `--yellow` on `--yellow-bg` |
| Red | `red` / `offline` | `--red` on `--red-bg` |
| Unknown | `checking…` / `unknown` | `--text-dim` on white |

### Tabs

Use the nine existing tabs:

1. Dashboard
2. Projects
3. Project Detail
4. Analytics
5. Data Quality
6. Pagination & Export
7. Mapping & Indices
8. Ops
9. Console

Rules:

- Tabs are buttons inside `<nav class="tabs" aria-label="Sections">`.
- Default tab: white fill, `#cbd5e1` border, `#334155` text.
- Hover: `#e0f2fe` fill, `#0284c7` border/text, slight lift.
- Active: white text on `--accent-gradient`, `#0284c7` border, stronger shadow.
- Tabs may wrap and scroll horizontally on narrow screens.
- For future accessibility updates, add `role="tablist"`, `role="tab"`, `aria-selected`, and `aria-controls`.

## Component Library

### Buttons

| Class | Appearance | Use |
|---|---|---|
| `.btn` | White fill, grey border | Secondary actions: Reset, Back, Refresh |
| `.btn-primary` | Blue gradient, white text | Main action: Search, Run, Load, Go, Analyze |
| `.btn-ghost` | Pale blue fill, blue text/border | Light supporting action |
| `.btn:disabled` | Low opacity, no pointer | Unavailable action |

Rules:

- One primary action per panel where possible.
- Keep labels short: `Search`, `Refresh`, `Load`, `Run Query`, `Simulate`.
- Do not add destructive buttons; this app is read-only.

### Cards

| Class | Use |
|---|---|
| `.card` | Standard content container |
| `.card-head` | Card title row with optional tag/metadata |
| `.card.note` | Caveats and teaching notes |
| `.card.empty` | Empty explanatory state |

Rules:

- White surface, soft border, `12px` radius, subtle shadow.
- Card padding: `20px 22px`.
- Notes use amber border/background and darker amber text.
- Use `.grid-2` for two-column card groups; collapse to one column under `900px`.

### KPI Cards

Use `.kpi-grid` and `.kpi`.

Structure:

- Label: small uppercase.
- Value: large bold number or short text.
- Subtitle: small muted explanation.
- Optional semantic class: `.is-green`, `.is-yellow`, `.is-red`, `.is-warn`.

Rules:

- Use for cluster facts, analytics totals, quality totals, mapping stats.
- Keep values short; long values belong in cards or tables.
- Do not overuse coloured KPI values; default dark text is preferred.

### Tags and Badges

| Class | Meaning |
|---|---|
| `.tag` | Neutral badge |
| `.tag-green` | Healthy / complete |
| `.tag-yellow` | Warning / caveat |
| `.tag-red` | Error / failed |
| `.tag-muted` | Metadata / index name / read-only marker |
| `.tag-warn` | Warning count |

Rules:

- Uppercase, small, pill-shaped.
- Pair with text such as `yellow`, `5 group(s)`, `index: gujrat_rera_data`.
- For health status, combine tag with a dot or explicit label.

### Inputs, Selects, and Fields

Use for search text, filters, dates, numbers, project ID, pagination limits, analyzer text, and console JSON.

Rules:

- White background, `#cbd5e1` border, `8px` radius.
- Placeholder text: `#94a3b8`.
- Focus: `#0284c7` border plus `0 0 0 3px rgba(2, 132, 199, 0.2)`.
- Labels are small blue uppercase text.
- Use `.field` for vertical label/control pairs.
- Use `.field-wide` for full-width search input.
- Use `.inline-input` for compact input+button groups.

### Suggest Dropdown

Structure:

- `.suggest-wrap` around the input.
- `.suggest-box` absolutely positioned below the input.
- `.suggest-item` rows with `.suggest-name` and `.suggest-meta`.

Rules:

- White surface, blue border, strong shadow.
- Hover: `#f0f9ff`.
- Suggested name: `#0284c7`, bold.
- Metadata: `#64748b`, small.

### Facets Sidebar

Use on the Projects tab.

Rules:

- Sticky at `top: 120px`, with internal scrolling.
- White surface, soft border, `12px` radius.
- Header is uppercase `#0284c7`.
- Facet buttons use `.facet-item`.
- Facet hover: pale blue fill, blue border, slight horizontal movement.
- Counts use `.facet-count` with pale blue fill and blue text.
- On screens under `900px`, facets become static and full width.

### Tables

Use `.table-wrap` around `.data-table`.

Rules:

- White surface, soft border, rounded corners, subtle shadow.
- Headers: `#f0f7ff` background, `#0369a1` text, `#bae6fd` bottom border, uppercase labels.
- Body text: `#0f172a`.
- Even rows: `#f8fafc`.
- Hover on clickable rows: `#e0f2fe` with blue left accent.
- Use `.data-table.compact` for dense technical tables.
- Use `.row-disabled` for non-indexed/non-queryable metadata: purple fill/text.
- Use `.row-unassigned` for unassigned shards: amber fill/text.
- Search highlights: yellow fill, dark amber text, yellow border.

### Details and Code Blocks

Use `<details class="details">` for JSON, query bodies, and collapsible raw results.

Rules:

- Summary row: pale background, blue text, pointer cursor.
- Open state uses a downward triangle; closed state uses a right triangle.
- `<pre>` uses dark `#0f172a` background with `#7dd3fc` text to contrast with the light page.
- Use `<pre>` only for machine-readable output, never for user-entered HTML.
- Console and pipeline editors also use `.code-input`.

### Charts

Use Chart.js with colours read from CSS variables through `cssVar()`.

Recommended series order:

1. `#0284c7` blue
2. `#4ade80` green
3. `#d97706` amber
4. `#0891b2` cyan
5. `#ea580c` orange
6. `#db2777` pink
7. `#65a30d` lime
8. `#4f46e5` indigo

Rules:

- Chart height: `270px`.
- Use `--chart-grid` for grid lines.
- Use dark text for labels.
- Always provide `.fallbackTable` if Chart.js cannot load.
- Charts should support tooltips and readable legends.
- Do not use transparent/low-contrast fills for small values.

### States

| State | Component | Visual |
|---|---|---|
| Loading | `.loading` | White card, dashed border, muted text, centred |
| Empty | `.placeholder` | White card, dashed border, muted text |
| Error | `.error-card` | Red border, `#fef2f2` background, dark red text |
| Info | `.card.note` | Amber border, `#fffbeb` background, dark amber text |
| Success | `.tag-green` / `.pill-status.is-green` | Green dot/tag with green-tinted surface |

Always show load state before async work and error state on failure.

## Tab Specifications

### Dashboard

Purpose: show live cluster and index facts without hard-coded values.

Elements:

- Header title and description.
- `Refresh` button.
- KPI cards for documents, store size, primary shards, replicas/unassigned shards.
- Cluster health pill.
- Index card.
- Yellow-health explanation card when applicable.
- Capability cards showing supported/unsupported Elasticsearch features.

Visual priority:

1. Cluster health.
2. Index size and document count.
3. Capability badges.
4. Operational caveats.

### Projects

Purpose: full-text search, filters, facets, safe highlighting, and result inspection.

Elements:

- `Reset` and `Search` buttons.
- Facet sidebar.
- Search input with suggest dropdown.
- Filter form: district, taluka, project type, status, promoter, price, price prefix, start/end dates, document counts, scrape flags, sort, page size.
- Result metadata row.
- Results table with highlight marks.
- Query-used disclosure panel.

Visual priority:

1. Search input and primary Search button.
2. Filters and facets.
3. Result count and query metadata.
4. Results table.

### Project Detail

Purpose: inspect one project including five non-indexed sections.

Elements:

- Project ID input and `Load` button.
- `Back to Projects` button.
- Core KV cards.
- Five section cards:
  - Project Profile
  - Project Summary
  - Promoters
  - Progress & RERA Actions
  - More Projects by The Same Developer
- Nested `<details>` blocks for complex objects.
- Source/map links when safe.

Visual priority:

1. Project identity.
2. Core indexed fields.
3. Non-indexed stored sections.
4. Raw source links.

### Analytics

Purpose: demonstrate Elasticsearch aggregations visually.

Elements:

- `Refresh` button.
- KPI cards for overview values.
- Six Chart.js cards:
  - Projects by district
  - Projects by taluka
  - Projects by status
  - Projects by type
  - Registrations by year
  - Start dates by year
- Table fallback for each chart.

Visual priority:

1. Aggregation totals.
2. Charts.
3. Fallback tables.
4. Date coverage caveat.

### Data Quality

Purpose: expose missing fields, scrape coverage, casing collisions, and pipeline dry-run results.

Elements:

- `Refresh` button.
- KPI cards: documents, missing price, missing start date, docs downloaded, scrape errors.
- Missing fields table.
- Scrape coverage KV card.
- District taluka collision cards.
- Malformed date caveat note.
- Pipeline simulator:
  - `.code-input` textarea.
  - `Simulate` button.
  - Result disclosure.
  - `pipeline_missing` graceful message.

Visual priority:

1. Quality KPIs.
2. Missing fields.
3. Collisions.
4. Pipeline simulation.

### Pagination & Export

Purpose: compare paging strategies and stream a bounded CSV.

Elements:

- Page N card: page number, size, `Go`, result table, query panel.
- Cursor card: `Next 100`, `Reset cursor`, cursor info, result table, query panel.
- PIT card: `Open PIT`, `Next (PIT)`, `Close PIT`, session info, results.
- CSV export card: limit input and `Export CSV` link.

Visual priority:

1. Paging strategy explanation.
2. Controls.
3. Result tables.
4. Cursor/PIT state text.
5. Export link.

### Mapping & Indices

Purpose: inspect mapping, stats, aliases, shard architecture, and analyzer output.

Elements:

- `Refresh` button.
- Stats KPIs: documents, store, segments, total queries.
- Mapping fields table with Indexed/Enabled columns.
- Aliases card.
- Single-shard/replica architecture note.
- Analyzer tool:
  - Text input.
  - Field select.
  - `Analyze` button.
  - Token table.
  - Query-used disclosure.

Visual priority:

1. Mapping field table.
2. Index stats.
3. Indexed vs stored-only distinction.
4. Analyzer output.

### Ops

Purpose: show cluster health, nodes, shards, and the documented P13 admin runbook.

Elements:

- `Refresh` button.
- Cluster health KV card.
- Nodes table.
- Shards allocation table.
- P13 note listing intentionally excluded admin operations.

Visual priority:

1. Cluster health.
2. Unassigned shards.
3. Node metrics.
4. Admin runbook caveat.

### Console

Purpose: run guarded Query DSL against the index.

Elements:

- Query DSL `.code-input` textarea.
- `Run Query` button.
- Result metadata row.
- Raw result disclosure.
- Query-used disclosure.

Keyboard:

- `Ctrl + Enter` runs the query.

Visual priority:

1. Query editor.
2. Run action.
3. Result count and timings.
4. Raw JSON.
5. Guardrail explanation.

## Accessibility Requirements

- Keep `:focus-visible` outline: `2px solid var(--focus)`, `outline-offset: 2px`.
- Every button must have a visible text label.
- Every input must have a `<label>`.
- Preserve the existing `prefers-reduced-motion` override.
- Use colour plus text for all status states.
- Keep table headers in `<th>` elements.
- Keep navigation inside `<nav aria-label="Sections">`.
- Add `aria-live="polite"` to async result/status containers when implementing future changes.
- Add `role="tablist"`, `role="tab"`, `aria-selected`, and `aria-controls` when tabs are next modified.
- Do not block zoom or force fixed-height content that clips text.
- Maintain a minimum `4.5:1` contrast ratio for normal text.

## Responsive Rules

### Desktop

- Full header with brand subtitle and status pills.
- Projects layout: `260px` facet sidebar plus content.
- Card grids use two columns where suitable.
- KPI cards auto-fit with `minmax(200px, 1fr)`.
- Charts auto-fit with `minmax(340px, 1fr)`.

### Tablet / Mobile (`max-width: 900px`)

- Header padding changes to `12px 18px`.
- Brand subtitle hides.
- Tabs remain horizontally scrollable and wrap where possible.
- Main padding changes to `20px 16px 36px`.
- Projects layout becomes one column.
- Facets become static with no max-height.
- `.grid-2` becomes one column.

## Frontend Change Checklist

Use this checklist whenever the frontend is edited.

1. Keep `color-scheme: light`.
2. Add or update colours in `:root` first; do not introduce scattered hex values.
3. Replace inline styles with reusable classes where practical.
4. Keep the sticky header white with pale blue border and shadow.
5. Keep all primary actions blue and high contrast.
6. Keep status colours semantic and labelled.
7. Keep tables dense, white, and blue-headed.
8. Keep all backend-provided strings rendered as text, not HTML.
9. Keep highlight rendering through safe DOM node creation.
10. Keep Chart.js colours sourced from CSS variables.
11. Keep chart fallback tables.
12. Keep loading, empty, and error states consistent.
13. Add visible focus to every new interactive element.
14. Add keyboard behaviour to new controls where appropriate.
15. Test below `900px` width.
16. If `styles.css` changes, bump `frontend/index.html` asset version from `?v=2` to the next version so browsers do not reuse cache.
17. If `app.js` changes, bump its `?v=` version too.
18. Run `make check` after changes.
19. Run `pytest` if any backend-facing behaviour changes.
20. Verify `http://127.0.0.1:8000/` after serving with `make frontend`.

## Do / Do Not

### Do

- Use white cards on pale blue pages.
- Use sky blue for selection, focus, links, and primary actions.
- Use amber notes for caveats.
- Use red only for errors.
- Use purple for non-indexed metadata.
- Use strong dark text for all readable values.
- Use safe text rendering for all Elasticsearch data.
- Use compact tables for technical output.

### Do Not

- Do not create a dark mode.
- Do not use neon or low-contrast colours.
- Do not rely on colour alone.
- Do not use emoji as UI icons.
- Do not inject formatted backend text as HTML.
- Do not hide errors behind colour-only indicators.
- Do not use leading wildcard examples in the console.
- Do not expose write/admin operations in the UI.
