# Frontend UI/UX Guide — Gujrat RERA Explorer

## 1. Purpose & Design Direction

This document is the visual and interaction source of truth for the **Gujrat RERA Explorer** frontend. It defines the design tokens, layout architecture, component specifications, accessibility standards, and verification checklist required to keep the application bright, scannable, and consistent.

**Design Direction: Bright Clinical Data Explorer** — a single-mode light interface built with crisp white surfaces, pale sky-blue backgrounds, high-contrast sky-blue accents, dense inspectable tables, and strictly separated semantic status colours.

### Core Design Principles

1. **Single Light Mode Only**: Do not add a dark theme or theme toggle. Clinical light surfaces maximize legibility for dense Elasticsearch payloads and tabular data.
2. **Data-Dense, Inspectable UI**: Prioritize information density and scannability over decorative whitespace—this is an Elasticsearch teaching and debugging tool.
3. **Blue for Navigation & Actions**: Reserve sky blue (`--accent` / `--accent-text` / `--accent-gradient`) exclusively for navigation, primary actions, interactive links, focus rings, and selected states.
4. **Semantic Colour Discipline**: Use semantic colours strictly for meaning—green for healthy/success, amber for warnings/caveats, red for errors/failures, and purple for disabled or non-indexed metadata.
5. **Never Rely on Colour Alone**: Always pair status colours with explicit text labels, dots, tags, or icons so colour-vision-deficient users can parse every state.
6. **Tokens Over Hard-Coded Values**: Define and consume CSS custom properties in `:root`; avoid scattered hex values in component rules.
7. **Safe DOM Rendering**: Render all backend-provided strings as DOM text nodes (`textContent`), never `innerHTML`. Build search highlights via safe DOM node creation.
8. **Keyboard-First & Accessible**: Every interactive control must be reachable by keyboard, have a visible `:focus-visible` ring, and meet WCAG 2.1 AA contrast (`≥ 4.5:1` for normal text, `≥ 3:1` for large text and UI components).

---

## 2. Design Tokens (`:root`)

### 2.1 Core Surface & Text Palette

| Token | Value | Contrast / Role |
|---|---:|---|
| `--bg` | `#f0f7ff` | Main page background (pale sky blue) |
| `--bg-elev` | `#ffffff` | Primary card, table, and panel surface |
| `--bg-elev-2` | `#f8fafc` | Secondary surface, alternating table rows, footer |
| `--bg-elev-3` | `#e0f2fe` | Pale blue hover/highlight surface |
| `--border` | `#cbd5e1` | Default borders, inputs, secondary buttons |
| `--border-bright` | `#0284c7` | Active/hover borders |
| `--border-soft` | `#e2e8f0` | Subtle card borders and row dividers |
| `--text` | `#0f172a` | Primary text, headings, table values (`17.8:1` on white) |
| `--text-dim` | `#334155` | Secondary body text (`10.3:1` on white) |
| `--text-faint` | `#64748b` | Labels and metadata on `#ffffff` (`4.76:1` on white) |
| `--text-faint-tinted` | `#475569` | Metadata on `#f0f7ff` or `#e0f2fe` (`≥ 6.4:1` — use instead of `#64748b` on tinted surfaces) |
| `--accent` | `#0284c7` | Primary blue for fills, borders, icons, focus rings, and large/bold text (`≥ 18px` or `≥ 14px` bold) |
| `--accent-text` | `#0369a1` | Accessible blue for small text, links, labels, and badges on light surfaces (`5.9:1` on white) |
| `--accent-soft` | `rgba(2, 132, 199, 0.1)` | Subtle blue tint fill |
| `--accent-gradient` | `linear-gradient(135deg, #0284c7, #2563eb)` | Brand mark, active tab, primary buttons |
| `--focus` | `#0284c7` | Keyboard `:focus-visible` outline |
| `--chart-grid` | `rgba(148, 163, 184, 0.25)` | Chart.js grid lines |

### 2.2 Semantic Colours

| Token | Value | Use |
|---|---:|---|
| `--green` | `#059669` | Healthy status, positive KPI, Chart series 2 |
| `--green-bg` | `#ecfdf5` | Success surface |
| `--green-text` | `#065f46` | High-contrast text inside `--green-bg` |
| `--yellow` | `#d97706` | Warning border/dot, Chart series 3 |
| `--yellow-bg` | `#fffbeb` | Warning / caveat surface |
| `--yellow-text` | `#92400e` | High-contrast warning text (`#78350f` or `#92400e`) inside `--yellow-bg` |
| `--red` | `#dc2626` | Error border/dot, failed state |
| `--red-bg` | `#fef2f2` | Error surface |
| `--red-text` | `#991b1b` | High-contrast error text (`#991b1b` or `#b91c1c`) inside `--red-bg` |
| `--purple` | `#7c3aed` | Non-indexed metadata, muted badge |
| `--purple-bg` | `#f5f3ff` | Non-indexed metadata surface |
| `--cyan` | `#0891b2` | Chart series 4 |
| `--orange` | `#ea580c` | Chart series 5 |
| `--pink` | `#db2777` | Chart series 6 |
| `--lime` | `#65a30d` | Chart series 7 |
| `--indigo` | `#4f46e5` | Chart series 8 |

### 2.3 Supporting Component Tokens

Convert previously hard-coded supporting hex values into `:root` tokens so every surface remains theme-consistent:

| Token | Value | Use |
|---|---:|---|
| `--header-bg` | `#ffffff` | Sticky header background |
| `--header-border` | `#bae6fd` | Sticky header bottom border |
| `--header-sep` | `#e0f2fe` | Header internal separator |
| `--pill-bg` | `#f0f9ff` | Host/info pill background |
| `--pill-border` | `#bae6fd` | Host/info pill border |
| `--pill-text` | `#0369a1` | Host/info pill text |
| `--table-head-bg` | `#f0f7ff` | Table `<th>` background |
| `--table-head-border` | `#bae6fd` | Table `<th>` bottom border |
| `--highlight-bg` | `#fef08a` | Search match `<mark>` background |
| `--highlight-text` | `#854d0e` | Search match `<mark>` text |
| `--highlight-border` | `#facc15` | Search match `<mark>` border |
| `--code-bg` | `#0f172a` | `<pre>` and `.code-input` background |
| `--code-text` | `#7dd3fc` | Read-only `<pre>` JSON/code text |
| `--code-editor-text` | `#38bdf8` | Editable `.code-input` text |
| `--code-border` | `#334155` | Code block / editor border |

### 2.4 Spacing, Radius, Elevation & Z-Index Scales

| Category | Token | Value | Use |
|---|---|---|---|
| **Spacing** | `--space-1` / `--space-2` | `4px` / `8px` | Tight gaps, badge padding, inline icon-to-text spacing |
| | `--space-3` / `--space-4` | `12px` / `16px` | Form field gaps, compact table cell padding |
| | `--space-5` / `--space-6` | `20px` / `24px` | Standard card padding (`20px 22px`), grid gutters |
| **Radius** | `--radius-sm` | `6px` | Tags, badges, inline highlights, small controls |
| | `--radius-md` | `8px` | Inputs, selects, buttons, code blocks |
| | `--radius-lg` | `12px` | Cards, `.table-wrap`, `.facets`, `.suggest-box` |
| | `--radius-pill` | `9999px` | Status pills, `.tag` badges |
| **Shadow** | `--shadow-sm` | `0 1px 2px rgba(15, 23, 42, 0.05)` | Cards, table wrappers |
| | `--shadow-md` | `0 4px 12px rgba(2, 132, 199, 0.12)` | Sticky header, active tabs |
| | `--shadow-lg` | `0 10px 24px rgba(15, 23, 42, 0.12)` | `.suggest-box` dropdown |
| **Z-Index** | `--z-sticky` | `10` | Sticky `.facets` sidebar |
| | `--z-header` | `30` | Sticky `.site-header-wrap` |
| | `--z-dropdown` | `40` | `.suggest-box` autocomplete menu |

### 2.5 Contrast & Accessibility Guardrails

- **Small blue text**: Always use `--accent-text` (`#0369a1`) for small blue labels, table headers, facet headers, and inline links. Do not use `#0284c7` for small text on white (`4.09:1` fails WCAG AA); reserve `#0284c7` for borders, fills, focus rings, and bold/large headings.
- **Tinted-surface metadata**: On `--bg` (`#f0f7ff`) or `--bg-elev-3` (`#e0f2fe`), use `--text-faint-tinted` (`#475569`) instead of `--text-faint` (`#64748b`) to stay above `4.5:1`.
- **Placeholders**: Use `#64748b` (not `#94a3b8`, which fails contrast at `2.56:1`) for input placeholders so hints remain readable.
- **White text**: Permitted only on strong dark/blue fills (`#0284c7`, `#0369a1`, `--accent-gradient`, `#0f172a`).
- **Chart series 2**: Use `--green` (`#059669`) rather than `#4ade80` so green bars/lines remain crisp against white chart canvases.

---

## 3. Typography

| Element | Font / Size / Weight | Notes |
|---|---|---|
| Base font | `Inter`, system UI fallback (`-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`) | `14px`, `line-height: 1.5` |
| Page title | `20px`, weight `800` | Header product title |
| Panel title | `24px`, weight `800` | Tab section heading |
| Card title | `16px`, weight `800` | `.card-head` heading |
| KPI value | `28px`, weight `850`, `-0.02em` tracking | Enable `font-variant-numeric: tabular-nums` |
| Labels & headers | `11.5px`, uppercase, `0.07em`–`0.1em` tracking, weight `750` | Use `--accent-text` or `--text-faint` |
| Metadata | `12px`–`13px`, `--text-faint` / `--text-faint-tinted` | Timestamps, counts, subtitles |
| Monospace | `ui-monospace, SFMono-Regular, "Cascadia Code", Consolas, monospace` | Field names, index names, IDs, JSON, DSL, timings |

### Typography Rules

- Keep headings short and scannable; avoid multi-line card titles.
- Use uppercase **only** for compact labels, table `<th>` headers, tags, and metadata.
- Apply `font-variant-numeric: tabular-nums` to all KPIs, numeric table columns, shard counts, and query `took` timings so digits align vertically.
- Never italicize data values; use `.tag` badges or colour-coded blocks instead.
- Handle long strings gracefully: truncate long project/promoter names in dense tables with `text-overflow: ellipsis` + `title` attribute, and apply `overflow-wrap: anywhere` on long IDs, hashes, and URLs in detail views.

---

## 4. Global Layout & Shell

### 4.1 Page Shell

- **Body**: Full viewport (`min-height: 100vh`), `margin: 0`, flex column, subtle pale blue gradient background (`--bg`).
- **Header (`.site-header-wrap`)**: Sticky (`top: 0`, `z-index: var(--z-header)`), white surface (`--header-bg`), `#bae6fd` bottom border, subtle blue shadow.
- **Main**: `max-width: 1400px`, centred, `padding: 26px 28px 48px`, `flex: 1`.
- **Footer**: `--bg-elev-2` (`#f8fafc`), `1px solid var(--border-soft)` top border, small muted text.

### 4.2 Header & Status Pill

Elements:

- `.brand-mark`: Blue gradient square (`--accent-gradient`) with bold white `GR` monogram.
- `.brand-text h1`: Product title (`Gujrat RERA Explorer`).
- `.brand-sub`: One-line product description.
- `.pill-host`: Elasticsearch host chip (`--pill-bg`, `--pill-border`, `--pill-text`).
- `#cluster-pill`: Live cluster health pill (`aria-live="polite"`) pairing a coloured dot with an explicit text label.

| State | Label Text | Visual Style |
|---|---|---|
| Green | `healthy` / `online` | `--green` dot + `--green-text` on `--green-bg` |
| Yellow | `yellow` | `--yellow` dot + `--yellow-text` on `--yellow-bg` |
| Red | `red` / `offline` | `--red` dot + `--red-text` on `--red-bg` |
| Unknown | `checking…` / `unknown` | `--text-dim` dot + text on `--bg-elev` |

### 4.3 Primary Navigation Tabs

Ten active tabs inside `<nav class="tabs" aria-label="Sections">` with `role="tablist"`:

1. `Dashboard`
2. `Projects`
3. `Project Detail`
4. `Analytics`
5. `Data Quality`
6. `Pagination & Export`
7. `Mapping & Indices`
8. `Ops`
9. `Console`
10. `Map / Boundaries`

Tab states & keyboard behaviour:

- **Default**: `--bg-elev` fill, `--border` border, `--text-dim` text.
- **Hover**: `--bg-elev-3` fill, `--border-bright` border, `--accent-text` text, slight vertical lift (`translateY(-1px)`).
- **Active (`aria-selected="true"`)**: White text on `--accent-gradient`, `--border-bright` border, `--shadow-md`.
- **Accessibility**: Implement `role="tab"`, `aria-selected`, `aria-controls="<panel-id>"`, and roving `tabindex` (`0` on active tab, `-1` on others) with `ArrowLeft` / `ArrowRight` / `Home` / `End` navigation.
- **Overflow**: Wrap cleanly on desktop; allow horizontal scroll with `-webkit-overflow-scrolling: touch` on narrow screens.

---

## 5. Component Library

### 5.1 Buttons

| Class | Appearance | Use |
|---|---|---|
| `.btn` | White fill, `--border` border, `--text` | Secondary actions: `Reset`, `Back to Projects`, `Refresh`, `Close PIT` |
| `.btn-primary` | `--accent-gradient` fill, white text | Primary action (max 1 per panel): `Search`, `Load`, `Run Query`, `Simulate`, `Analyze`, `Go` |
| `.btn-ghost` | `--bg-elev-3` fill, `--accent-text` text, `--pill-border` | Supporting actions: `Copy JSON`, `Reset cursor` |
| `.btn:disabled` | `opacity: 0.55`, `cursor: not-allowed` | Unavailable or in-flight actions |

Interaction rules:

- During async requests, set `disabled` and `aria-busy="true"` on the triggering button (and update label, e.g., `Searching…`) to prevent duplicate submissions.
- Keep button labels concise (1–3 words) and free of emoji.
- Do not add destructive/write buttons; the explorer is strictly read-only.

### 5.2 Cards & Grids

| Class | Use |
|---|---|
| `.card` | Standard white container (`--bg-elev`, `1px solid var(--border-soft)`, `--radius-lg`, `padding: 20px 22px`, `--shadow-sm`) |
| `.card-head` | Flex header row with card title and optional `.tag` or metadata |
| `.card.note` | Caveats and teaching notes (`--yellow` border, `--yellow-bg` fill, `--yellow-text`) |
| `.card.empty` | Explanatory empty state |

Use `.grid-2` for two-column card layouts (`gap: 20px`), collapsing to one column below `900px`.

### 5.3 KPI Cards

Use `.kpi-grid` (`grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`) and `.kpi`:

- **Label**: `11.5px` uppercase (`--text-faint`).
- **Value**: `28px` bold (`850`), `tabular-nums`, default `--text` (reserve `.is-green`, `.is-yellow`, `.is-red`, `.is-warn` strictly for semantic health/error metrics).
- **Subtitle**: `12px`–`13px` muted explanation.

### 5.4 Tags & Badges

| Class | Meaning |
|---|---|
| `.tag` | Neutral metadata pill |
| `.tag-green` | Healthy / complete / supported |
| `.tag-yellow` | Warning / caveat / yellow cluster |
| `.tag-red` | Error / failed / unsupported |
| `.tag-muted` | Non-indexed metadata / index name / read-only marker (`--purple-bg`, `--purple`) |
| `.tag-warn` | Warning count |

Always pair status tags with explicit text (`yellow`, `5 group(s)`, `index: gujrat_rera_data`) and a leading dot when representing health.

### 5.5 Forms, Inputs & Suggest Dropdown

- **Controls**: White background, `1px solid var(--border)`, `--radius-md` (`8px`), `min-height: 38px` (`44px` on touch viewports).
- **Focus**: `--border-bright` (`#0284c7`) + `0 0 0 3px rgba(2, 132, 199, 0.2)`.
- **Labels**: Every input must have a `<label for="…">` styled in small uppercase `--accent-text`.
- **Layout helpers**: `.field` (vertical label/control), `.field-wide` (full-width search), `.inline-input` (compact input + button).
- **Validation**: Show inline error text (`--red-text`) directly beneath invalid inputs (e.g., invalid date range, non-JSON in Console) with `aria-invalid="true"`.

**Suggest Dropdown (`.suggest-wrap` / `.suggest-box`)**:

- Position `.suggest-box` absolutely below the input (`z-index: var(--z-dropdown)`, `--bg-elev`, `1px solid var(--border-bright)`, `--radius-lg`, `--shadow-lg`).
- `.suggest-item`: Flex row with `.suggest-name` (`--accent-text`, bold) and `.suggest-meta` (`--text-faint`, `12px`). Hover/active item uses `--pill-bg` (`#f0f9ff`).
- Wire `role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`, and support `ArrowDown`, `ArrowUp`, `Enter`, and `Escape` to close.

### 5.6 Facets Sidebar (Projects Tab)

- Sticky (`top: 120px`, `z-index: var(--z-sticky)`), internal scroll (`max-height: calc(100vh - 140px)`), `--bg-elev`, `1px solid var(--border-soft)`, `--radius-lg`.
- Section headers in uppercase `--accent-text`.
- `.facet-item`: Full-width button with flex space-between; hover fills `--bg-elev-3`, border `--border-bright`, subtle `translateX(2px)` shift; active/selected facet uses `--accent-soft` fill and `--border-bright` border.
- `.facet-count`: Pill badge with `--pill-bg` and `--pill-text` (`tabular-nums`).
- Collapses to static full-width block below `900px`.

### 5.7 Tables

Wrap every table in `.table-wrap` (`overflow-x: auto`, `--bg-elev`, `1px solid var(--border-soft)`, `--radius-lg`, `--shadow-sm`).

- **Headers (`<th>`)**: `--table-head-bg` (`#f0f7ff`), `--accent-text` (`#0369a1`), `1px solid var(--table-head-border)` bottom border, uppercase `11.5px`.
- **Body**: `--text` (`#0f172a`), zebra-striped even rows (`--bg-elev-2`).
- **Alignment**: Left-align text/IDs; right-align numeric counts, prices, and byte sizes (`tabular-nums`); left-align status tags.
- **Row states**:
  - Clickable rows: `--bg-elev-3` hover with `3px solid var(--accent)` left indicator.
  - `.row-disabled`: Purple tint (`--purple-bg`, `--purple`) for non-indexed/non-queryable mapping fields.
  - `.row-unassigned`: Amber tint (`--yellow-bg`, `--yellow-text`) for unassigned shards.
- **Dense variant**: `.data-table.compact` for technical mapping, token, node, and shard tables.
- **Search highlights**: `<mark>` created via DOM nodes using `--highlight-bg`, `--highlight-text`, and `1px solid var(--highlight-border)`.

### 5.8 Details, Code Blocks & Copy Action

- `<details class="details">`: Pale `--bg-elev-2` summary bar, `--accent-text` label, pointer cursor, CSS disclosure triangle (`▸` closed / `▾` open).
- `<pre>`: `--code-bg` (`#0f172a`), `--code-text` (`#7dd3fc`), `1px solid var(--code-border)`, `--radius-md`, horizontal scroll. Use strictly for machine-readable JSON/DSL, never user-entered HTML.
- `.code-input`: Monospace `<textarea>` with `--code-bg` and `--code-editor-text` (`#38bdf8`).
- **Copy button**: Include a compact `.btn-ghost` `Copy` button on Query DSL disclosures and raw JSON blocks that switches briefly to `Copied` (`aria-live="polite"`).

### 5.9 Charts (Chart.js)

- Height: `270px` fixed container with responsive width.
- Read all colours dynamically from CSS variables via `cssVar()`.
- **Series palette order**:
  1. `--accent` (`#0284c7`)
  2. `--green` (`#059669`)
  3. `--yellow` (`#d97706`)
  4. `--cyan` (`#0891b2`)
  5. `--orange` (`#ea580c`)
  6. `--pink` (`#db2777`)
  7. `--lime` (`#65a30d`)
  8. `--indigo` (`#4f46e5`)
- Grid lines: `--chart-grid`. Axis ticks and legend text: `--text-dim` (`#334155`).
- Always render a sibling `.fallbackTable` if Chart.js fails to load or for keyboard/screen-reader inspection.

### 5.10 Async & Feedback States

| State | Component | Visual & Behaviour |
|---|---|---|
| Loading | `.loading` | White card, dashed `--border`, centred muted text, `aria-busy="true"` |
| Empty (no results) | `.placeholder` | White card, dashed `--border`, clear message + reset/broaden hint |
| Error | `.error-card` | `--red` border, `--red-bg` fill, `--red-text` message + retry action |
| Caveat / Note | `.card.note` | `--yellow` border, `--yellow-bg` fill, `--yellow-text` |
| Success | `.tag-green` / `.pill-status.is-green` | Green dot + text label on `--green-bg` |

Always render the loading state before async work begins and replace it cleanly with results, empty state, or `.error-card` on completion. Announce result-count updates inside an `aria-live="polite"` region.

---

## 6. Tab Specifications

### 6.1 Dashboard
- **Purpose**: Live cluster and index facts with zero hard-coded values.
- **Elements**: Header + `Refresh` button; KPI cards (documents, store size, primary shards, replicas/unassigned shards); `#cluster-pill`; Index card; conditional yellow-health explanation card; capability cards (supported vs. unsupported Elasticsearch features).
- **Visual Priority**: (1) Cluster health → (2) Index size & doc count → (3) Capability badges → (4) Operational caveats.

### 6.2 Projects
- **Purpose**: Full-text search, multi-facet filtering, safe highlighting, and result inspection.
- **Elements**: `Reset` + `Search` buttons; sticky facet sidebar; search input with `.suggest-box`; filter form (district, taluka, project type, status, promoter, price, price prefix, start/end dates, document counts, scrape flags, sort, page size); `aria-live="polite"` result metadata row; results table with safe `<mark>` highlights; query-used `<details>` panel.
- **Visual Priority**: (1) Search input + `Search` button → (2) Filters & facets → (3) Result count & `took` metadata → (4) Results table.

### 6.3 Project Detail
- **Purpose**: Inspect a single project, including its five non-indexed stored sections.
- **Elements**: Project ID input + `Load` button; `Back to Projects` button; core indexed KV cards; five section cards (`Project Profile`, `Project Summary`, `Promoters`, `Progress & RERA Actions`, `More Projects by The Same Developer`); nested `<details>` for complex objects; safe external source/map links (`rel="noopener noreferrer"`).
- **Visual Priority**: (1) Project identity → (2) Core indexed fields → (3) Non-indexed stored sections → (4) Raw source links.

### 6.4 Analytics
- **Purpose**: Visual demonstration of Elasticsearch aggregations.
- **Elements**: `Refresh` button; overview KPI cards; six Chart.js cards (`Projects by district`, `Projects by taluka`, `Projects by status`, `Projects by type`, `Registrations by year`, `Start dates by year`), each with a `.fallbackTable`; date-coverage caveat note.
- **Visual Priority**: (1) Aggregation totals → (2) Charts → (3) Fallback tables → (4) Date coverage caveat.

### 6.5 Data Quality
- **Purpose**: Expose missing fields, scrape coverage, casing collisions, and ingest pipeline dry-run results.
- **Elements**: `Refresh` button; KPI cards (documents, missing price, missing start date, docs downloaded, scrape errors); missing fields table; scrape coverage KV card; district/taluka collision cards; malformed date `.card.note`; pipeline simulator (`.code-input`, `Simulate` button, result disclosure, graceful `pipeline_missing` message).
- **Visual Priority**: (1) Quality KPIs → (2) Missing fields → (3) Collisions → (4) Pipeline simulation.

### 6.6 Pagination & Export
- **Purpose**: Compare paging strategies (`from`/`size`, `search_after` cursor, PIT) and stream a bounded CSV.
- **Elements**: Page N card (`page`, `size`, `Go`, results, query panel); Cursor card (`Next 100`, `Reset cursor`, cursor state text, results, query panel); PIT card (`Open PIT`, `Next (PIT)`, `Close PIT`, active/closed session badge + expiry note, results); CSV export card (limit input + `Export CSV` link).
- **Visual Priority**: (1) Strategy explanation → (2) Controls → (3) Result tables → (4) Cursor/PIT state → (5) Export link.

### 6.7 Mapping & Indices
- **Purpose**: Inspect mapping, index stats, aliases, shard architecture, and analyzer tokenization.
- **Elements**: `Refresh` button; stats KPIs (documents, store, segments, total queries); mapping fields table with `Indexed` / `Enabled` columns (`.row-disabled` for non-indexed fields); aliases card; single-shard/replica architecture note; analyzer tool (text input, field select, `Analyze` button, token table, query-used disclosure).
- **Visual Priority**: (1) Mapping field table → (2) Index stats → (3) Indexed vs. stored-only distinction → (4) Analyzer output.

### 6.8 Ops
- **Purpose**: Show cluster health, node metrics, shard allocation, and the documented P13 admin runbook.
- **Elements**: `Refresh` button; cluster health KV card; nodes table; shards allocation table (`.row-unassigned` for unassigned shards); P13 `.card.note` listing intentionally excluded admin operations.
- **Visual Priority**: (1) Cluster health → (2) Unassigned shards → (3) Node metrics → (4) Admin runbook caveat.

### 6.9 Console
- **Purpose**: Execute guarded read-only Query DSL against `gujrat_rera_data`.
- **Elements**: Guardrail explanation note; `.code-input` Query DSL textarea with client-side JSON validation; `Run Query` button (with `Ctrl + Enter` / `Cmd + Enter` shortcut hint); `aria-live="polite"` result metadata row (`hits`, `took`); raw result disclosure; query-used disclosure.
- **Visual Priority**: (1) Query editor → (2) Run action → (3) Result count & timings → (4) Raw JSON → (5) Guardrail explanation.

### 6.10 Map / Boundaries
- **Purpose**: Show project boundary rings and teach read-only geometry filtering with the same query-visible pattern as other tabs.
- **Data source**: `Project Profile.Map Location` from `_source`; no `geo_point`, no `geo_shape`, no index writes, no API key.
- **Elements**: Read-only note; district/taluka/type/status/`q` filters; `bbox` input; radius (`lat`, `lon`, `distance_km`) input; polygon input; `Load Boundaries` button; Leaflet map container; result table; skipped-ring count; query-used disclosure.
- **Rendering**: Leaflet + OpenStreetMap tiles via CDN, `preferCanvas: true`, auto-closed polygons, centroid markers for degenerate rings, stronger stroke/fill at higher zoom, click popup with project detail link.
- **Interaction**: Filter changes fetch one viewport batch; `moveend` re-renders cached rings without another ES call; stale requests use `AbortController`; `aria-live` reports visible/cached/skipped counts.
- **Visual Priority**: (1) Read-only note + filters → (2) Map → (3) Result counts → (4) Result table → (5) Query used.

---

## 7. Accessibility & Responsive Standards

### 7.1 Accessibility Checklist (WCAG 2.1 AA)

- Maintain `:focus-visible` outline: `2px solid var(--focus); outline-offset: 2px;`.
- Provide a visible text label on every button and a `<label>` for every input/select/textarea.
- Preserve `@media (prefers-reduced-motion: reduce)` to disable transitions and hover transforms.
- Use `role="tablist"`, `role="tab"`, `aria-selected`, `aria-controls`, and arrow-key navigation on tabs.
- Use `aria-live="polite"` on async result counts, status pills, and error banners.
- Keep `<th>` semantic headers in all tables and never block browser zoom (`user-scalable=no` is forbidden).
- Ensure interactive controls on touch devices meet at least `44×44px` hit targets.

### 7.2 Responsive Breakpoints

- **Desktop (`> 900px`)**: Full header with `.brand-sub` and status pills; `260px` sticky `.facets` sidebar + fluid results column; `.grid-2` two-column cards; KPI grid `minmax(200px, 1fr)`; Charts grid `minmax(340px, 1fr)`.
- **Tablet / Mobile (`≤ 900px`)**: Header padding `12px 18px`; hide `.brand-sub`; tabs wrap and scroll horizontally; `main` padding `20px 16px 36px`; Projects layout collapses to single column; `.facets` becomes static (`max-height: none`); `.grid-2` collapses to single column; map container becomes `360px` tall and controls stack full width.

---

## 8. Frontend Change & Verification Checklist

1. Keep `color-scheme: light` on `:root`.
2. Add or update colours in `:root` first; eliminate scattered hex values.
3. Use `--accent-text` (`#0369a1`) for small blue text and `--text-faint-tinted` (`#475569`) on pale-blue surfaces (`≥ 4.5:1` contrast).
4. Replace inline styles with reusable utility/component classes.
5. Keep the sticky header white with `--header-border` and subtle blue shadow.
6. Keep primary actions blue, high-contrast, and limited to one per panel.
7. Pair all semantic status colours with explicit text labels or dots.
8. Keep tables dense, white, blue-headed, and aligned (`tabular-nums` for numbers).
9. Render all backend-provided strings via safe DOM text nodes (`textContent`), never `innerHTML`.
10. Build search highlights via safe DOM node creation.
11. Source all Chart.js colours from CSS variables via `cssVar()` and retain `.fallbackTable`.
12. Ensure loading, empty, and `.error-card` states are wired for every async call, with `aria-live="polite"` updates.
13. Verify `:focus-visible` and keyboard navigation (`Tab`, `Enter`, `Escape`, arrow keys on tabs/suggest) on all new controls.
14. Test layout and horizontal table scroll below `900px` width.
15. If `styles.css` changes, bump the `?v=` asset version in `frontend/index.html` (e.g., `?v=2` → `?v=3`).
16. If `app.js` changes, bump its `?v=` asset version in `frontend/index.html` as well.
17. Run `make check` after changes.
18. Run `pytest` if any backend-facing behaviour changes.
19. Serve with `make frontend` and verify `http://127.0.0.1:8000/`.

---

## 9. Do / Do Not

| Do | Do Not |
|---|---|
| Use white cards (`--bg-elev`) on pale blue pages (`--bg`) | Create a dark mode or theme toggle |
| Use `--accent-text` for small blue text and `--accent` for borders/fills | Use `#0284c7` for small text on white or `#94a3b8` for meaningful placeholders |
| Use amber `.card.note` for caveats and red `.error-card` for errors | Hide errors behind colour-only indicators or use emoji as UI icons |
| Use purple (`.row-disabled`, `.tag-muted`) for non-indexed metadata | Inject backend-provided strings or highlights as raw HTML |
| Use `tabular-nums` and compact tables for technical output | Expose write/admin operations or leading-wildcard console examples |
