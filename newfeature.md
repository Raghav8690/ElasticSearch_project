# New Feature: Project Query Comparison Lab

| Field | Value |
|---|---|
| Feature name | Project Query Comparison Lab |
| Status | `PROPOSED` |
| Date | 2026-11-25 |
| Type | In-place patch to an existing feature |
| Existing feature | `Projects` tab and `GET /api/projects/search` |
| Source of truth | Current chat decisions, `frontend/index.html`, `frontend/app.js`, `backend/queries.py`, `backend/routes.py`, `tests/` |
| Implementation state | Not started |
| Commit scope | Documentation only for this file |

## 1. Purpose

This document defines the next feature before code is changed.

The `Projects` tab currently exposes a large filter form, a facet sidebar, and a single result set. This makes it difficult to see how different Elasticsearch query types behave against the same user input.

This feature turns the tab into a focused query-comparison lab:

1. The user enters one search phrase.
2. The user chooses an `A` query type and a `B` query type.
3. The user toggles fuzzy matching on or off.
4. The frontend runs both searches in parallel with the same input.
5. Two result panels show totals, timings, rows, and the generated query body side by side.

The feature is read-only and does not add a new tab, route, index, or mapping.

## 2. Decisions

These decisions are frozen for this feature.

| Decision | Value |
|---|---|
| Comparison layout | Side-by-side A/B result panels |
| Query types | `multi_match`, `match`, `phrase`, `term` |
| Filter controls | Remove all Project filter fields |
| Facet sidebar | Remove from the Projects tab |
| Controls to keep | Query, address rerank, fuzzy, sort, page size |
| Fuzzy behavior | Applies to `multi_match` and `match` only |
| `phrase` behavior | Exact `match_phrase`; no fuzziness |
| `term` behavior | Exact keyword term; no fuzziness |
| Default A type | `multi_match` |
| Default B type | `match` |
| Default fuzzy | `on` in the UI; API default is `false` |
| Default rerank | `on`, preserving current behavior |
| Default sort | Relevance when `q` is present |
| Default page size | `20` |
| New API endpoint | None; run two existing searches |

### 2.1 Technical correction

Elasticsearch does not support `fuzziness` on every query form:

- `match_phrase` does not support `fuzziness`.
- `multi_match` with `type: cross_fields` does not support `fuzziness`.

Therefore:

- Fuzzy is applied directly to `match`.
- For `multi_match`, the existing `cross_fields` clause stays exact, and fuzzy adds a separate bounded `multi_match` fallback clause (`type: best_fields` over `project_name^2` and `promoter_name^1`).
- `phrase` remains an exact phrase query.
- `term` remains an exact keyword query.
- The UI must explain that fuzzy is not applicable to `phrase` or `term`.

If phrase typo tolerance is needed later, it must be added as a separate fuzzy fallback clause, not by passing `fuzziness` to `match_phrase`.

## 3. Current state

### 3.1 Frontend

- `frontend/index.html:69-132` contains the Project facet sidebar and full filter form.
- `frontend/index.html:75-124` contains the filters that must be removed.
- `frontend/index.html:84-86` contains the existing address rerank control.
- `frontend/index.html:10` and `frontend/index.html:470` load static assets at `?v=10`.
- `frontend/app.js:431-493` contains project facets rendering and loading.
- `frontend/app.js:495-528` `collectSearchParams()` maps every current filter to an API parameter.
- `frontend/app.js:530-564` `resultsTable()` renders a hit table.
- `frontend/app.js:566-591` `runSearch()` runs one search and renders one result set.
- `frontend/app.js:593-606` contains reset and first-load behavior.
- `frontend/app.js:2723-2751` wires the Project search and reset buttons.
- `frontend/app.js:393-403` provides `queryDetails()` for the generated query body.
- `frontend/app.js:1080-1085` formats capped totals as `10,000+`.

### 3.2 Backend

- `backend/routes.py:792-909` implements `search_projects()` and currently accepts all Project filters plus `rerank_address`.
- `backend/queries.py:356-444` implements `build_project_search()` with all Project filters.
- `backend/queries.py:208-253` implements the current relevance clause used by `q`.
- `backend/queries.py:200-205` implements default relevance sorting.
- Address rerank is applied in `backend/routes.py:839-892` after the Elasticsearch search.
- `backend/queries.py` already uses safe indexed-field clauses and does not use scripts, runtime mappings, regexp, or leading wildcards.

### 3.3 Tests

- `tests/test_queries.py` covers the current Project search DSL, filters, relevance, highlighting, sort, and boundary query behavior.
- `tests/test_routes.py` covers route precedence, live project search, rerank metadata, facets, boundaries, and detail lookup.
- There are currently no tests for selectable Project query types or a Project fuzzy toggle.

### 3.4 Worktree note

At the time this document is written, the worktree contains pre-existing changes outside this feature:

- Deleted documentation files.
- A modified `frontend/logo.png`.

Those changes must not be modified, staged, or committed as part of this feature.

## 4. Goals

- Make the Projects tab a clear A/B query-type comparison tool.
- Remove filter clutter from the Projects tab.
- Keep the address-rerank toggle and explain its effect.
- Add a fuzzy on/off control with correct per-query-type behavior.
- Show both result sets without losing the existing safe rendering and metadata.
- Keep the application fully read-only.
- Preserve existing API compatibility for callers that still send filters.
- Add tests for the new query types and fuzzy contracts.

## 5. Non-goals

- No new frontend tab or route.
- No new Elasticsearch index, mapping, analyzer, pipeline, or document write.
- No new backend comparison endpoint.
- No field selector for each query type.
- No JSON diff between the two generated query bodies.
- No row-level diff highlighting between the A and B result sets.
- No pagination changes beyond the existing sort and page size controls.
- No removal of the backend filter parameters in this change.
- No removal of the existing facets endpoint.
- No change to the Map / Boundaries feature.
- No dark mode or theme toggle.
- No new dependency.

## 6. Target user flow

### 6.1 Search and compare

1. User opens the `Projects` tab.
2. The form shows only query, A type, B type, fuzzy, address rerank, sort, and page size.
3. User enters a phrase such as `shivalik recidency`.
4. User selects `A = multi_match` and `B = term`.
5. User selects fuzzy `on`.
6. User clicks **Search**.
7. The frontend sends two requests to `/api/projects/search` in parallel:
   - one with `query_type=multi_match`,
   - one with `query_type=term`.
8. Both requests use the same `q`, `fuzzy`, `sort`, `size`, and `rerank_address`.
9. The frontend renders:
   - an A panel with totals, returned count, timings, table, and query details,
   - a B panel with the same structure.
10. If one request fails, the other panel still renders.

### 6.2 Fuzzy comparison

1. User keeps `A = match` and `B = match`.
2. User runs once with fuzzy `off` and once with fuzzy `on`.
3. Fuzzy-off results reflect exact analyzed matching.
4. Fuzzy-on results add typo tolerance to `match`.
5. `phrase` and `term` show a visible note that fuzzy does not apply.

### 6.3 Address rerank

1. Address rerank remains enabled by default.
2. Both panels use the same rerank setting.
3. Because reranking can reduce visible differences between query types, the UI shows:
   `Turn address rerank off to compare raw query behavior.`

### 6.4 Reset

1. User clicks **Reset**.
2. The form returns to:
   - empty query,
   - A = `multi_match`,
   - B = `match`,
   - fuzzy = `on`,
   - rerank = `on`,
   - sort = default relevance option,
   - size = `20`.
3. A fresh comparison runs.

### 6.5 Empty query

1. User leaves the query empty.
2. Both panels return the same `match_all` result set.
3. Query type and fuzzy are ignored for matching.
4. The panel metadata still shows the selected type so the user can see that it was ignored.

## 7. Frontend design

### 7.1 Form contract

Replace the current filter form with these controls.

| ID | Control | Values | Default |
|---|---|---|---|
| `q` | Search input | free text | empty |
| `f-query-a` | A query type | see Section 7.2 | `multi_match` |
| `f-query-b` | B query type | see Section 7.2 | `match` |
| `f-fuzzy` | Fuzzy | `on`, `off` | `on` |
| `f-rerank` | Address rerank | `on`, `off` | `on` |
| `f-sort` | Sort | existing sort options | relevance/default |
| `f-size` | Page size | `20`, `50`, `100` | `20` |

Keep the existing `#q` autocomplete behavior and `#suggest-box`.

Add helper text under the fuzzy control:

`Fuzzy applies to multi_match and match. Phrase and term stay exact.`

Add helper text under the rerank control:

`Turn address rerank off to compare raw query behavior.`

### 7.2 Query type options

Use these labels and values in both dropdowns.

| Value | Label |
|---|---|
| `multi_match` | Relevance (multi_match) |
| `match` | Analyzed match |
| `phrase` | Exact phrase |
| `term` | Exact term (keyword) |

### 7.3 Removal contract

Remove from the Projects tab:

- The `aside.facets` sidebar.
- `#facets-body`.
- `#f-district`.
- `#f-taluka`.
- `#f-type`.
- `#f-status`.
- `#f-promoter`.
- `#f-price`.
- `#f-price-prefix`.
- `#f-start-from`.
- `#f-start-to`.
- `#f-end-from`.
- `#f-end-to`.
- `#f-min-docs`.
- `#f-max-docs`.
- `#f-complete`.
- `#f-downloaded`.

Remove the corresponding entries from the Project search parameter map.

Do not remove the backend filter parameters or their tests in this feature.

### 7.4 Comparison markup

Replace the single result area with two static panels.

Suggested structure:

```html
<div class="compare-grid" id="projects-compare">
  <section class="compare-panel" aria-labelledby="compare-a-title">
    <div class="compare-head">
      <h3 id="compare-a-title">A: Relevance (multi_match)</h3>
    </div>
    <div class="result-meta" id="compare-a-meta" aria-live="polite"></div>
    <div id="compare-a-results" class="stack" aria-live="polite"></div>
    <div id="compare-a-query"></div>
  </section>

  <section class="compare-panel" aria-labelledby="compare-b-title">
    <div class="compare-head">
      <h3 id="compare-b-title">B: Analyzed match</h3>
    </div>
    <div class="result-meta" id="compare-b-meta" aria-live="polite"></div>
    <div id="compare-b-results" class="stack" aria-live="polite"></div>
    <div id="compare-b-query"></div>
  </section>
</div>
```

Each panel must update its title when its selected query type changes.

### 7.5 JavaScript contract

Refactor the Project search path as follows.

#### `collectBaseSearchParams()`

Collects the shared parameters:

- `q`
- `fuzzy`
- `rerank_address`
- `sort`
- `size`

#### `collectSearchParams(queryType)`

Returns the shared parameters plus `query_type`.

#### `runComparison()`

- Read both query types.
- Send both requests in parallel.
- Use `Promise.allSettled`.
- Render each panel independently.
- Keep the Search button busy until both promises settle.
- Clear both panels before starting.

#### `renderComparePanel(side, res)`

- Update the panel title with the selected query type label.
- Render total, returned count, `es_took_ms`, and `wall_ms`.
- Render the hit table with the existing `resultsTable()`.
- Render the query body with `queryDetails()`.

#### `renderCompareError(side, err)`

- Render the existing `errorCard()` in that panel only.

#### `resetProjects()`

- Reset the form.
- Restore defaults from the markup.
- Run `runComparison()`.

#### `ensureProjects()`

- Remove the Project facet load.
- Run `runComparison()` on first open.

#### `initProjects()`

- Wire **Search** and form submit to `runComparison()`.
- Keep the reset wiring.
- Keep the existing suggest-selection behavior; when a suggestion has no ID, run `runComparison()`.

### 7.6 Facet cleanup

Remove Project-specific facet behavior:

- `renderFacets()`.
- `loadFacets()`.
- The `loadFacets()` call in `ensureProjects()`.

Keep `fillSelect()` because the Map / Boundaries tab still uses it.

Keep `/api/projects/facets` unchanged because the API and boundary tab still use it.

### 7.7 Styling

Update `frontend/styles.css`:

- Change `.projects-layout` to a single-column layout.
- Remove project facet-specific styles that become unused.
- Add `.compare-grid` with two equal columns and a gap.
- Add `.compare-panel` with the existing card surface, border, radius, and shadow.
- Add `.compare-head` spacing and title styling.
- Stack `.compare-grid` into one column at `max-width: 1100px`.
- Keep the existing mobile breakpoint behavior for filters and tables.

At narrow widths, each panel's table must scroll inside its own `.table-wrap`; the page itself must not overflow horizontally.

### 7.8 Static asset version

Bump both Project static assets from `?v=10` to `?v=11`:

- `frontend/index.html` stylesheet link.
- `frontend/index.html` app script link.

Leave the logo and favicon versions unchanged unless their files change.

## 8. Backend design

### 8.1 Route parameters

Extend `search_projects()` in `backend/routes.py` with:

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `query_type` | string | `multi_match` | Selected query mode |
| `fuzzy` | boolean | `false` | Apply fuzziness where supported |

Keep all existing parameters for API compatibility.

Pass `query_type` and `fuzzy` into `build_project_search()`.

Add both values to `query_used` so the UI and tests can verify what ran.

Suggested metadata shape:

```json
{
  "query_used": {
    "method": "POST",
    "path": "/gujrat_rera_data/_search",
    "body": {},
    "mode": {
      "query_type": "multi_match",
      "fuzzy": true
    },
    "rerank": {}
  }
}
```

### 8.2 Builder parameters

Extend `build_project_search()` with:

```python
query_type: str = "multi_match"
fuzzy: bool = False
```

Validate `query_type` against the allowed set:

- `multi_match`
- `match`
- `phrase`
- `term`

Raise the existing invalid-parameter error for any other value.

### 8.3 Query construction

When `q` is empty:

- Ignore `query_type` and `fuzzy`.
- Preserve the current `match_all` behavior.
- Preserve the current sort behavior: `projectId asc` unless an explicit sort is supplied.

When `q` is present:

- Apply the selected query type.
- Keep existing filters inside `bool.filter` when callers still send them.
- Keep the existing highlight configuration.

#### `multi_match`

Keep the current `cross_fields` relevance clause from `_build_relevance_clause()` unchanged.

Do not add `fuzziness` to the `cross_fields` clause: Elasticsearch rejects that combination.

When `fuzzy=true` and `q` is not purely numeric, append a separate bounded fuzzy fallback clause:

```json
{
  "multi_match": {
    "query": "<q>",
    "fields": ["project_name^2", "promoter_name^1"],
    "type": "best_fields",
    "operator": "or",
    "minimum_should_match": "<minimum token rule>",
    "lenient": true,
    "boost": 2,
    "fuzziness": "AUTO",
    "prefix_length": 1,
    "max_expansions": 25
  }
}
```

Do not add fuzziness to the exact, prefix, or phrase clauses inside the relevance block.

#### `match`

Produce:

```json
{
  "match": {
    "project_name": {
      "query": "<q>",
      "operator": "and",
      "lenient": true,
      "boost": 100
    }
  }
}
```

When `fuzzy=true`, add:

```json
{
  "fuzziness": "AUTO",
  "prefix_length": 1,
  "max_expansions": 25
}
```

#### `phrase`

Produce:

```json
{
  "match_phrase": {
    "project_name": {
      "query": "<q>",
      "slop": 0,
      "boost": 100
    }
  }
}
```

Never add `fuzziness` to this clause.

#### `term`

For non-numeric `q`, produce:

```json
{
  "term": {
    "project_name.keyword": {
      "value": "<q>",
      "case_insensitive": true,
      "boost": 100
    }
  }
}
```

For an all-digit `q`, use `projectId` instead:

```json
{
  "term": {
    "projectId": {
      "value": 573,
      "boost": 100
    }
  }
}
```

Never add `fuzziness` to this clause.

### 8.4 Structure

For `match`, `phrase`, and `term`, the query should be:

```json
{
  "bool": {
    "filter": [],
    "must": []
  }
}
```

Omit `filter` when it is empty, matching the existing style.

For `multi_match`, preserve the existing `bool` relevance-clause structure so current ranking behavior is not rewritten unnecessarily.

### 8.5 Sorting

Keep the existing rule:

- If `sort` is supplied, `parse_sort()` wins.
- Otherwise, a query search uses `_score desc`, then `projectId asc`.
- Otherwise, no query uses `projectId asc`.

### 8.6 Rerank

Address rerank remains in `backend/routes.py` and applies after the selected query type produces candidates.

Both A and B requests use the same rerank setting.

No rerank logic changes are required for this feature.

## 9. API examples

### 9.1 A side

```http
GET /api/projects/search?q=shivalik%20recidency&query_type=multi_match&fuzzy=true&rerank_address=false&size=20
```

### 9.2 B side

```http
GET /api/projects/search?q=shivalik%20recidency&query_type=term&fuzzy=true&rerank_address=false&size=20
```

### 9.3 Exact phrase

```http
GET /api/projects/search?q=shivalik%20residences&query_type=phrase&fuzzy=false&size=20
```

### 9.4 Exact term

```http
GET /api/projects/search?q=Shivalik%20Residences&query_type=term&fuzzy=false&size=20
```

## 10. Safety and guardrails

### 10.1 Elasticsearch read-only

Allowed:

- Existing search requests.
- Existing address-cache reads.
- Existing `_pit` flows in other features.

Forbidden:

- Index writes.
- Document writes.
- Mapping updates.
- Template or ILM updates.
- Reindex operations.
- Ingest pipeline installation.
- `geo_point` or `geo_shape` creation.

### 10.2 Query safety

Forbidden in the new query path:

- `script`.
- `script_fields`.
- `runtime_mappings`.
- `regexp`.
- Leading wildcard queries.
- Arbitrary user-controlled query DSL.

Required:

- User text remains a string value inside a known clause.
- Fuzzy settings remain bounded:
  - `fuzziness: "AUTO"`
  - `prefix_length: 1`
  - `max_expansions: 25`
- No new fields are queried unless they are already indexed and approved.

### 10.3 Rendering safety

- Continue rendering backend strings with safe DOM text nodes.
- Do not use `innerHTML` for search content.
- Reuse `resultsTable()` and `queryDetails()` so existing highlight and copy behavior is preserved.

### 10.4 Behavior preservation

- Do not change Map / Boundaries behavior.
- Do not change the Projects API response envelope.
- Do not change the facets endpoint.
- Do not remove backend filter parameters.
- Do not change non-query sort behavior.
- Do not change address rerank behavior.

### 10.5 Git guardrail

- Do not commit unless explicitly requested.
- Do not push unless explicitly requested.
- Leave pre-existing worktree changes untouched.
- Run `git diff --check` before any commit.

## 11. Files likely to change during implementation

| File | Expected change |
|---|---|
| `frontend/index.html` | Remove facets and filters; add A/B controls and panels; bump `?v=11` |
| `frontend/app.js` | Add comparison params and rendering; remove project facet code; update reset/init |
| `frontend/styles.css` | Single-column Projects layout; comparison panel styles; responsive stacking |
| `backend/routes.py` | Add `query_type` and `fuzzy`; pass through and expose in metadata |
| `backend/queries.py` | Add query-type validation and per-mode DSL; add fuzzy to supported modes |
| `tests/test_queries.py` | Add query-type, fuzzy, empty-query, numeric-term, invalid-type tests |
| `tests/test_routes.py` | Add route metadata and parameter pass-through tests |

## 12. Implementation sequence

1. Add failing backend tests for query types and fuzzy behavior.
2. Implement backend query-type validation and DSL generation.
3. Add route parameters and `query_used.mode` metadata.
4. Update frontend markup: remove filters/facets, add A/B controls and panels.
5. Update frontend JavaScript: base params, comparison requests, panel rendering, reset/init.
6. Update CSS for comparison layout and responsive behavior.
7. Bump static asset versions to `?v=11`.
8. Run backend tests and `make check`.
9. Run browser QA for desktop and mobile.
10. Stop for review; do not commit unless asked.

## 13. Test plan

### 13.1 Backend unit tests

Add or update tests for:

- Default `query_type` is `multi_match`.
- `match` produces a `match` clause on `project_name`.
- `phrase` produces a `match_phrase` clause on `project_name`.
- `term` produces a `term` clause on `project_name.keyword` with `case_insensitive: true`.
- Numeric `term` uses `projectId`.
- `fuzzy=true` keeps the `multi_match` `cross_fields` clause exact and adds a separate bounded fuzzy `best_fields` fallback clause.
- `fuzzy=true` does not add a fuzzy fallback for numeric `multi_match` queries.
- `fuzzy=true` adds bounded fuzzy parameters to `match`.
- `fuzzy=true` does not add fuzziness to `phrase`.
- `fuzzy=true` does not add fuzziness to `term`.
- Empty `q` ignores `query_type` and returns `match_all`.
- Invalid `query_type` raises the existing invalid-parameter error.
- Explicit sort still overrides relevance sort.
- No generated body contains scripts, runtime mappings, regexp, or leading wildcards.

### 13.2 Backend route tests

- `/api/projects/search` accepts `query_type` and `fuzzy`.
- `query_used.mode.query_type` matches the request.
- `query_used.mode.fuzzy` matches the request.
- Two requests with different query types produce different query bodies.
- Existing filter parameters still work.
- Existing rerank metadata still works.
- Route precedence for `/api/projects/search` remains intact.

### 13.3 Frontend browser QA

At `http://127.0.0.1:8000`:

- The Projects tab shows only query, A, B, fuzzy, rerank, sort, and size controls.
- The facet sidebar and all old filter fields are absent.
- Defaults are A=`multi_match`, B=`match`, fuzzy=`on`, rerank=`on`, size=`20`.
- Search renders two panels with independent metadata.
- Changing A/B labels updates the panel titles.
- Fuzzy on/off changes `match` and `multi_match` results where applicable.
- Phrase and term remain exact.
- Term with an exact project name returns the expected project.
- Term with a numeric project ID returns the expected project.
- Query details are present in both panels.
- Turning rerank off produces `enabled: false` in both panels.
- One failed request does not prevent the other panel from rendering.
- Reset restores defaults and reruns.
- Desktop layout shows two columns.
- Mobile layout stacks panels and does not overflow horizontally.
- No browser console errors.
- Static asset URLs contain `?v=11`.

### 13.4 Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
make check
git diff --check
```

## 14. Acceptance criteria

The feature is complete when:

- The Projects tab has no facet sidebar and no old filter fields.
- The only Project controls are query, A type, B type, fuzzy, address rerank, sort, and page size.
- Two searches run in parallel against the same input.
- Each panel shows its own totals, timings, rows, and query details.
- `multi_match`, `match`, `phrase`, and `term` produce the documented DSL.
- Fuzzy applies to `multi_match` and `match` only.
- Phrase and term are documented and rendered as exact queries.
- Empty query returns `match_all` for both panels.
- Existing backend filters remain API-compatible.
- Existing boundary and facet endpoints are unchanged.
- Read-only guardrails remain intact.
- Backend tests pass.
- `make check` passes.
- Browser QA passes on desktop and mobile.
- No commit or push is made unless explicitly requested.

## 15. Open questions

None. The query types, comparison layout, filter removal scope, and fuzzy behavior are frozen for implementation.
