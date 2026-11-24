# Map / Boundaries UI/UX Guide

## 1. Purpose

This guide defines the UI/UX contract for the `Map / Boundaries` page in Gujrat RERA Explorer.

The page is a read-only map laboratory. Its primary job is to let users inspect project boundary rings from `_source`, understand which filters produced the result, and trace a result back to project detail without leaving the map-first workflow.

The current redesign goal is:

- remove the two-column map/results split,
- give the map the full available horizontal space,
- move results and query details into a bottom drawer,
- keep loading, empty, and error states stable and informative.

## 2. Scope

### In scope

- Full-width map stage.
- Bottom drawer for results and query details.
- Compact filter toolbar.
- Stable status/meta strip.
- Loading, empty, error, and success states.
- Focus marker and nearby mode presentation.
- Responsive behavior for desktop, tablet, and phone.
- Accessibility and interaction guardrails.

### Out of scope

- New tab or new route.
- Dark mode or theme toggle.
- Native Elasticsearch geo queries.
- Mapping changes, index writes, or document writes.
- Clustering of overlapping centroids.
- New frontend dependencies.

## 3. Product and audience

| Field | Value |
|---|---|
| Product type | Read-only data exploration / teaching tool |
| Platform | Desktop-first web app, responsive down to 375px |
| Stack | Vanilla HTML, CSS, JavaScript, Leaflet, OpenStreetMap tiles |
| Audience | Developers, students, and demo users learning read-only Elasticsearch patterns |
| Visual direction | Light mode only, dense but readable, white cards, pale blue background, high-contrast blue actions |

## 4. Design principles

1. **Map first**: the map owns the full horizontal content width. Result inspection is secondary and happens in a drawer.
2. **Stable during async work**: loading, filtering, and refreshing must not blank the map or collapse the result area.
3. **Explain every state**: users should always know what is visible, what was scanned, what was skipped, and whether results are truncated.
4. **Query transparency**: keep query-used inspectable, but move it out of the primary visual path.
5. **Read-only clarity**: never imply that the map edits data or uses native geo fields.
6. **Safe rendering**: backend strings are rendered as text nodes; never as HTML.
7. **Keyboard safe**: overlays must not obscure focus, and users must be able to close them with Escape.

## 5. Research basis

Verified UI skill guidance used in this guide:

- **Loading Indicators**: use stable progress/skeleton feedback with `aria-busy`; avoid flicker or frozen UI.
- **Content Jumping**: reserve space and keep async containers stable.
- **No Results**: show suggestions instead of a blank screen or bare `0 results`.
- **Focus Not Obscured**: overlays must not fully cover keyboard focus; support close and focus return.
- **Container Width**: keep long text and query details readable with a bounded measure.

No verified dataset match was found for a map-specific overlay panel. Drawer rules below are general UI guidance applied to this page.

## 6. Page anatomy

### 6.1 Desktop layout

```text
+------------------------------------------------------------------+
| Map / Boundaries                         Zoom  Reset  Load         |
+------------------------------------------------------------------+
| Read-only geometry note                                          |
+------------------------------------------------------------------+
| Search | District | Taluka | Type | Status | Radius | Bbox | ...   |
+------------------------------------------------------------------+
| Status: Rendered 5,388 boundaries | scanned 5,388/5,390 | cache   |
+------------------------------------------------------------------+
|                                                                  |
|                                                                  |
|                       FULL-WIDTH MAP STAGE                        |
|                                                                  |
|                                                    [Results]      |
| +--------------------------------------------------------------+ |
| | Bottom drawer: result table + query details          [Close] | |
| +--------------------------------------------------------------+ |
+------------------------------------------------------------------+
```

### 6.2 Mobile layout

```text
+--------------------------------+
| Map / Boundaries                |
| Zoom  Reset  Load               |
+--------------------------------+
| Read-only note                  |
+--------------------------------+
| Filters stack                   |
+--------------------------------+
| Status/meta                     |
+--------------------------------+
| Map, full width, shorter height |
| [Results]                       |
+--------------------------------+
| Bottom drawer, taller on mobile |
+--------------------------------+
```

## 7. Element contract

### 7.1 Header

- Title: `Map / Boundaries`.
- Supporting text explains that boundaries are read-only and viewport-batched.
- Actions:
  - `Zoom to results`
  - `Reset`
  - `Load Boundaries`
- `Load Boundaries` is the single primary action.

### 7.2 Read-only note

- Keep a compact explanation that geometry comes from `Project Profile.Map Location` in `_source`.
- State that there are no indexed geo fields and no writes.
- Avoid repeating this note inside the map or drawer.

### 7.3 Filter toolbar

- Use a compact responsive grid.
- Keep all existing fields:
  - search query,
  - district,
  - taluka,
  - project type,
  - status,
  - registration number,
  - bbox,
  - radius latitude/longitude/distance,
  - batch size,
  - polygon,
  - current-view checkbox.
- `Use current map view as the bounding box` is unchecked by default.
- Radius is all-or-nothing: latitude, longitude, and distance must all be present.

### 7.4 Status/meta strip

- Place above the map.
- Use `aria-live="polite"`.
- Show:
  - visible count,
  - scanned/loaded count,
  - skipped degenerate/unparseable counts,
  - batch count,
  - cache hit vs ES scan,
  - timings.
- Keep a reserved minimum height so updates do not shift the map.
- Show batch progress during refresh.

### 7.5 Full-width map stage

- The map spans the full panel width.
- Do not place a results column beside it.
- Use a responsive height:
  - desktop: tall enough to dominate the viewport,
  - mobile: shorter but still primary.
- Keep Leaflet canvas rendering enabled.
- Keep attribution visible.
- Keep controls unobscured by the results drawer.

### 7.6 Bottom drawer

- Opens from the bottom of the map stage.
- Contains:
  - result table,
  - truncation note,
  - query-used disclosure.
- Uses `aria-expanded` on the toggle and `aria-controls` pointing to the drawer.
- Has a visible close button.
- Escape closes the drawer and returns focus to the toggle.
- The drawer scrolls internally.
- The drawer does not reduce the map's horizontal width.
- Keep result text and query details bounded for readability.

## 8. Loading, empty, and error states

### 8.1 Initial state

- Map is ready.
- Status says `Map ready.`
- Drawer shows `Choose filters, then load boundaries.`

### 8.2 Loading state

- Keep existing map graphics visible under a subtle refreshing overlay.
- Put the results drawer into `aria-busy="true"`.
- Show a stable skeleton in the drawer, not a one-line spinner.
- Status text progresses by batch, e.g. `Scanning batch 1…`, `Scanning batch 2…`.
- Do not clear the map until the first successful batch is ready to render.
- Aborted or stale loads leave the current map intact.

### 8.3 Success state

- Status says `Rendered N project boundaries.`
- If scan stopped early, say so explicitly.
- Drawer table shows result rows.
- Table shows only the first 250 visible rows and states truncation.

### 8.4 Empty state

Do not show a blank drawer. Show:

- `No project boundaries matched these filters.`
- Suggestions:
  - clear the search text,
  - remove the bbox,
  - widen the radius,
  - reset filters.

### 8.5 Error state

- Keep the map visible.
- Show an error card in the drawer.
- Announce a short message through map status.
- Keep the underlying query-used visible when available.

## 9. Focus marker and nearby mode

- The first usable search result receives a distinct focus marker.
- The matching row is highlighted in the drawer.
- Row click changes focus and re-centers the map.
- Row click must not trigger a reload.
- `Show nearby` is disabled until a focus exists.
- Nearby mode pins the focus row first and sorts remaining rows by distance.
- The pinned row remains visible even when no nearby rows are returned.
- Popup action opens Project detail through the existing `openDetail(id)` behavior.

## 10. Interaction rules

- Map movement updates bounds but does not auto-reload.
- `Load Boundaries` computes bbox only when the current-view checkbox is checked.
- Unchecking current view clears bbox state.
- Drawer open/close must not trigger boundary loading.
- Keyboard focus must remain visible.
- Escape closes the drawer.
- Reduced motion disables drawer and overlay transitions.
- Touch/click targets are at least 44px tall.

## 11. Visual tokens

Use existing CSS variables:

- white card surfaces for map and drawer,
- pale blue page background,
- accent blue for primary actions and focus,
- green for pinned/success,
- amber for warnings,
- red for errors,
- purple for focused rows,
- semantic text colors for primary/secondary/muted text.

Do not add a dark theme. Do not introduce arbitrary per-component hex colors when a token exists.

## 12. Accessibility checklist

- Every input has a real `<label>`.
- Drawer toggle uses `aria-expanded` and `aria-controls`.
- Async regions use `aria-live="polite"`.
- Loading regions use `aria-busy`.
- Focus outlines are visible and not obscured.
- Close button has an accessible name.
- Tables use semantic `<th>` headers.
- Color is never the only state indicator; pinned and focused rows also have text labels or styling supported by DOM structure.
- Drawer can be closed with Escape and focus returns to the toggle.
- Backend strings are inserted with `textContent`, never `innerHTML`.

## 13. Responsive checklist

- Desktop: full-width map, drawer overlays bottom of map stage.
- Tablet: still full-width map; filters wrap; drawer max-height increases.
- Phone `375px`: filters stack; map remains full width with shorter height; drawer nearly fills lower map area but close control remains reachable.
- No horizontal page overflow.
- Tables scroll inside their own container.
- Leaflet is re-sized after tab activation and drawer transitions.

## 14. Guardrails

- No Elasticsearch writes or native geo DSL.
- No new dependencies.
- No inline HTML injection from ES data.
- No new tabs or routes.
- No dark mode.
- No map/results side-by-side split.
- No layout collapse during loading.
- No auto-reload on pan/zoom.
- No silent truncation.
- No commit unless explicitly requested.
- Bump static asset versions whenever `styles.css` or `app.js` changes.

## 15. Verification checklist

- `make check`
- `.venv\Scripts\python.exe -m pytest -q`
- `git diff --check`
- Browser QA:
  - map uses full available horizontal space,
  - results and query details are in bottom drawer,
  - drawer opens/closes by button and Escape,
  - loading keeps prior map visible and shows stable skeleton,
  - empty state gives suggestions,
  - error state keeps map usable,
  - focus marker and nearby mode still work,
  - no horizontal overflow at 1440px, 1024px, and 375px,
  - reduced-motion behavior is respected.
