# New Feature: Map Search-to-Centroid Resolution

| Field | Value |
|---|---|
| Feature name | Map Search-to-Centroid Resolution |
| Status | `APPROVED_WITH_CONCERNS` |
| Date | 2026-11-24 |
| Type | In-place patch to an existing feature |
| Existing feature | `Map / Boundaries` tab and `GET /api/projects/boundaries` |
| Source of truth | Current chat history, `PLAN.md`, `PROJECT_CONTEXT.md`, `README.md`, `compaction.md` |
| Implementation state | Not implemented |
| Commit scope | Documentation only for this file |

## 1. Purpose

This document defines the next feature in detail before code is changed.

The feature upgrades the read-only `Map / Boundaries` experience from a boundary browser into a seamless name-resolution flow:

1. User types a misspelled project name.
2. Backend resolves likely projects with typo-tolerant fallback matching.
3. Frontend focuses the first usable result on the map.
4. User clicks **Show nearby**.
5. Frontend pins the focused project and loads nearby projects around its centroid.
6. Results preserve the existing indexed filters and are sorted by distance.

This is not a new tab and not a native Elasticsearch geo feature. It is a patch to the current boundary query, API response metadata, and boundary map UI.

## 2. Current state

The existing boundary map is implemented and pushed:

- Backend:
  - `backend/geometry.py`: ring parsing, centroid generation, bbox/radius/polygon geometry checks, haversine distance.
  - `backend/queries.py:405`: `build_boundary_query()` builds strict indexed filters and strict relevance matching.
  - `backend/routes.py:1152`: `GET /api/projects/boundaries` scans boundary documents, applies geometry filters in Python, and caches results.
  - `backend/es_client.py`: exposes `boundary_map` and `native_geo_dsl:false`.
- Frontend:
  - `frontend/index.html:397-425`: boundary form.
  - `frontend/app.js:1884`: `boundaryState` and map rendering logic.
  - `frontend/index.html:450`: static asset cache busting is still `?v=5`.
- Tests:
  - `tests/test_geometry.py`, `tests/test_queries.py`, `tests/test_routes.py`.
- Verification:
  - 53 tests pass.
  - `make check` passes.
  - Browser QA passed for the existing boundary map.
  - Work was pushed as:
    - `3293d61 Add read-only boundary map API and tests`
    - `99f8582 Add interactive project boundary map tab`
    - `d47186a Document boundary map and search-to-centroid plan`

## 3. Problem statement

The current `q` behavior in `build_boundary_query()` is too strict for realistic project-name search.

Observed evidence:

- `q=shivalik recidency` returns `0` hits.
- `q=shivalik residency` returns `5` hits.
- Fuzzy `AUTO` alone returns `11` hits but misses the likely target:
  - `projectId`: `573`
  - Project: `Shivalik Residences`
  - District: `Ahmedabad`
  - Centroid: `[23.056223, 72.591239]`
- `match_phrase_prefix` on analyzed `project_name` with `shivalik resid` returns `projectId 573` first.
- `project_name.keyword` exists and accepts `case_insensitive: true`.
- Prefix `resid` on `project_name.keyword` returns `64` hits with `projectId 573` first.
- Ahmedabad has `5,390` scanned projects, but a tight viewport can reduce visible matches to `41`.

There are two root causes:

1. The current query requires both tokens and has no typo/prefix fallback.
2. `#b-use-view` is checked by default, and `moveend` auto-reloads using the current viewport bbox, which hides results outside the visible map area.

## 4. Goals

- Make typo-tolerant project-name search return the intended project.
- Add a visible map focus for the first usable search result.
- Add **Show nearby** using the focused project centroid.
- Preserve indexed filters during nearby reloads.
- Keep the application fully read-only.
- Keep response metadata explicit enough to explain truncation and result counts.
- Add tests before implementation for the contracts that are still open.

## 5. Non-goals

- No new frontend tab.
- No new Elasticsearch index, mapping, pipeline, ingest processor, or document write.
- No `geo_point` or `geo_shape` field creation.
- No native Elasticsearch geo DSL.
- No clustering of overlapping centroids.
- No dark mode.
- No new dependency.
- No replacement of the existing pagination/export/search tabs.
- No commit unless explicitly requested after implementation.

## 6. Target user flow

### 6.1 Search flow

1. User opens **Map / Boundaries**.
2. **Use current map view as the bounding box** is unchecked by default.
3. User enters `q=shivalik recidency`.
4. Backend matches:
   - original typo text via fuzzy matching,
   - normalized text via exact matching,
   - derived prefix via phrase-prefix matching.
5. Results are ordered by `_score desc`, then `projectId asc`.
6. Frontend finds the first result with a usable centroid.
7. Frontend draws a distinct focus marker, highlights the row, opens the popup, and zooms to at least level 14.

### 6.2 Nearby flow

1. User clicks **Show nearby**.
2. If there is no focused project, the button remains disabled.
3. Frontend:
   - stores the focused project as `pinned`,
   - sets `nearbyMode = true`,
   - clears `q`,
   - unchecks `#b-use-view`,
   - clears `#b-bbox`,
   - fills `#b-lat` and `#b-lon` from the focus centroid,
   - sets `#b-distance` to `2`,
   - keeps district, taluka, project type, status, promoter, and registration-number filters.
4. Backend:
   - applies indexed filters in Elasticsearch,
   - applies radius filtering in Python using the centroid from `Project Profile.Map Location`,
   - returns `distance_km` on features and markers.
5. Frontend:
   - places the pinned row first,
   - labels it `Pinned`,
   - shows its distance as `0.0`,
   - sorts other rows by `distance_km` rounded to one decimal,
   - keeps the pinned row visible even if no nearby rows are returned.

### 6.3 Exit flows

- Clicking a result row while nearby mode is active re-centers the map on that row.
- Submitting a non-empty `q` exits nearby mode and clears `pinned`, `nearbyMode`, `#b-lat`, `#b-lon`, and `#b-distance`.
- Reset exits nearby mode.
- Missing radius inputs show:
  - `Radius requires latitude, longitude, and a positive distance.`
- Missing usable centroid shows:
  - `Selected project has no usable centroid.`
- Missing map bounds show:
  - `Map bounds unavailable. Uncheck current view or retry after the map loads.`

## 7. Backend design

### 7.1 Query builder

Change `build_boundary_query()` in `backend/queries.py:405`.

Current shape:

- Strict `bool.filter` list for indexed filters.
- Optional strict relevance clause from `_build_relevance_clause(q)`.
- Fixed sort: `projectId asc`.
- Fixed cursor: `[after]`.

New shape when `q` is present:

- Keep indexed filters unchanged.
- Add a top-level `bool.should` with two groups:
  1. exact/current group,
  2. fallback group.
- Use `minimum_should_match: 1` at the top level.
- Keep original `q` for fuzzy matching.
- Use normalized `q` for exact and phrase-prefix matching.

Target JSON contract:

```json
{
  "size": "<size>",
  "track_total_hits": true,
  "_source": [
    "projectId",
    "project_name",
    "district",
    "taluka",
    "project_type",
    "project_status",
    "reg_no",
    "page_url",
    "Project Profile.Map Location"
  ],
  "sort": [
    {"_score": "desc"},
    {"projectId": "asc"}
  ],
  "query": {
    "bool": {
      "minimum_should_match": 1,
      "should": [
        {
          "multi_match": {
            "query": "<original q>",
            "fields": [
              "project_name^4",
              "promoter_name^3",
              "district^3",
              "taluka^2",
              "project_type^3",
              "reg_no^2",
              "page_url^1"
            ],
            "type": "cross_fields",
            "operator": "or",
            "minimum_should_match": "<frozen token rule>",
            "lenient": true,
            "boost": 10
          }
        },
        {
          "bool": {
            "boost": 1,
            "minimum_should_match": 1,
            "should": [
              {
                "match": {
                  "project_name": {
                    "query": "<normalized q>",
                    "operator": "and",
                    "boost": 4
                  }
                }
              },
              {
                "match_phrase_prefix": {
                  "project_name": {
                    "query": "<frozen phrase prefix>",
                    "boost": 3
                  }
                }
              },
              {
                "match": {
                  "project_name": {
                    "query": "<original q>",
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                    "max_expansions": 25,
                    "operator": "and",
                    "boost": 1
                  }
                }
              }
            ]
          }
        }
      ]
    }
  }
}
```

When `q` is absent, preserve the current behavior exactly:

- sort by `projectId asc`,
- cursor remains `[after]`,
- no relevance score is introduced.

### 7.2 Normalization

Normalization must be implemented as a pure function so it can be tested directly.

Candidate behavior to freeze before coding:

- Keep the original `q` unchanged for fuzzy matching.
- Lowercase normalized text.
- Strip punctuation.
- Collapse whitespace.
- Preserve original token order.
- Map exact typo tokens:
  - `recidency` → `residency`
  - `recidancy` → `residency`
  - `recidence` → `residency`
  - `recidance` → `residency`
- Derive phrase prefix from the normalized project-name phrase:
  - `shivalik recidency` → normalized exact `shivalik residency`
  - `shivalik recidency` → phrase prefix `shivalik resid`

The exact token rule, typo map, and phrase-prefix derivation are still open contracts and must be frozen in tests before implementation.

### 7.3 Scoring and pagination

With `q`:

- Sort by `_score desc`, then `projectId asc`.
- Expose `score` on features and markers.
- Expose the active sort/cursor mode in response meta.
- Use `[score, projectId]` as `search_after`.
- Parse `after` as a JSON-like cursor rather than a plain integer.
- Preserve compatibility carefully with existing boundary caching.

Without `q`:

- Keep integer `after`.
- Keep `[projectId]` cursor.
- Do not expose score-dependent ordering.

### 7.4 Route changes

Change `project_boundaries()` in `backend/routes.py:1152`:

- Parse query-mode cursors correctly.
- Pass score and sort metadata through response data/meta.
- Add `distance_km` to features/markers when radius inputs are present.
- Sort returned features/markers:
  - by score when `q` is present,
  - by `distance_km` in nearby mode,
  - by `id` otherwise.
- Keep route ordering: `/projects/boundaries` must remain before `/projects/{project_id}`.
- Keep geometry filtering in Python, never in Elasticsearch DSL.

### 7.5 Response metadata

Keep and extend the existing data block:

```json
{
  "features": [],
  "markers": [],
  "skipped": {"degenerate": 0, "unparseable": 0},
  "capabilities": {
    "native_geo_dsl": false,
    "source_boundaries": true
  },
  "next_after": null,
  "complete": true,
  "loaded": 0
}
```

Definitions:

- `total`: Elasticsearch total hits.
- `loaded`: accumulated features plus markers before geometry filtering.
- `returned`: current response after geometry filtering.
- `complete`: `true` when Elasticsearch end is reached; `false` only when max pages stopped early.
- `next_after`: cursor for the next scan page.

Limits remain:

- `MAX_BOUNDARY_SIZE = 10000`
- route default `size = 1000`
- UI supplies `2000`
- frontend loader fetches at most `20` pages
- table shows at most `250` visible rows

## 8. Frontend design

### 8.1 State additions

Extend `boundaryState` in `frontend/app.js:1884` with:

- `focus`: currently focused item.
- `focusMarker`: distinct Leaflet circle marker.
- `pinned`: pinned item for nearby mode.
- `nearbyMode`: boolean.
- Possibly `lastQuery`: helpful for deciding when a new search exits nearby mode.

State rules:

- `focus` is set only from a result with a usable center.
- `pinned` is set only by **Show nearby**.
- `nearbyMode` is true only when `pinned` is set.
- Empty `q` submits do not necessarily exit nearby mode; non-empty `q` submits do.

### 8.2 Form changes

In `frontend/index.html:397-425`:

- Change `#b-use-view` from `checked` to unchecked.
- Add a **Show nearby** button, disabled by default.
- Keep existing fields:
  - `#b-q`
  - `#b-district`
  - `#b-taluka`
  - `#b-type`
  - `#b-status`
  - `#b-reg-no`
  - `#b-bbox`
  - `#b-lat`
  - `#b-lon`
  - `#b-distance`
  - `#b-size`
  - `#b-polygon`
- Bump `/static/app.js?v=5` to `/static/app.js?v=6` at `frontend/index.html:450`.

### 8.3 Bbox behavior

Change `collectBoundaryParams()` and map handlers:

- Include `bbox` only when `#b-use-view` is checked and `lastBounds` is valid.
- Unchecking `#b-use-view` clears `#b-bbox` and `boundaryState.lastBounds`.
- `moveend` updates bounds only; it must not call `loadBoundaries()`.
- **Load Boundaries** computes a fresh bbox only when `#b-use-view` is checked.
- Programmatic focus must not trigger a reload.

### 8.4 Focus marker behavior

When a search returns results:

- Pick the first item with a usable center.
- Draw a distinct circle marker.
- Highlight the matching row.
- Open the popup.
- Call `focusBoundary()`.
- Zoom to at least level 14.
- Use `ignoreBoundaryMove()` so programmatic movement does not create requests.

### 8.5 Nearby behavior

**Show nearby** must:

- remain disabled when `focus` is null,
- set `nearbyMode = true`,
- set `pinned = focus`,
- clear `#b-q`,
- uncheck `#b-use-view`,
- clear `#b-bbox`,
- fill `#b-lat` and `#b-lon` from the focus centroid,
- set `#b-distance` to `2`,
- retain all other indexed filters,
- trigger one boundary load.

Nearby table rendering must:

- place the pinned row first,
- label it `Pinned`,
- show pinned distance as `0.0`,
- sort remaining rows by `distance_km`,
- round displayed distances to one decimal,
- keep the pinned row even if no nearby rows are returned.

### 8.6 Popup behavior

Popup action text:

- `Open project detail`

Action:

- call existing `openDetail(id)`,
- switch to the Project detail tab using the existing tab mechanism.

## 9. Guardrails

### 9.1 Read-only Elasticsearch

Hard rule: this feature must not write to Elasticsearch.

Allowed:

- `GET`-style searches through the existing client.
- `POST /_pit` and `DELETE /_pit` when already part of existing read-only flows.
- Non-mutating `_analyze` and pipeline simulation calls already allowed by the app.

Forbidden:

- index/document/template/ILM writes,
- reindex,
- mapping updates,
- ingest pipeline installation,
- document update/delete,
- `geo_point` or `geo_shape` field creation.

### 9.2 Query safety

Forbidden in the new query path:

- `script`,
- `script_fields`,
- `runtime_mappings`,
- `regexp`,
- leading wildcard queries,
- arbitrary user-controlled query DSL.

Required:

- user text remains a string parameter inside safe query clauses,
- fuzzy matching uses bounded settings:
  - `fuzziness: "AUTO"`
  - `prefix_length: 1`
  - `max_expansions: 25`
- field boosts must stay on known indexed fields.

### 9.3 Source-field safety

- Continue using the strict `BOUNDARY_SOURCE` allowlist.
- Continue reading `Project Profile.Map Location` only from `_source`.
- Never query or filter directly on disabled object fields.
- Missing or invalid geometry must become a marker or a skipped count, not a hard UI failure.

### 9.4 XSS and rendering safety

- Render backend strings with `textContent` or existing safe DOM helpers.
- Never inject Elasticsearch text as `innerHTML`.
- Highlight rendering must continue using safe `<mark>` DOM nodes.
- Popup content must be constructed from safe DOM operations.

### 9.5 Performance and truncation

- Keep `MAX_BOUNDARY_SIZE = 10000`.
- Keep frontend batch size choices and max 20 pages.
- Keep the visible table cap at 250 rows.
- Show truncation status when:
  - `complete=false`,
  - visible rows exceed 250.
- Never silently hide truncated results.

### 9.6 Behavior preservation

- Non-`q` boundary behavior must not change.
- Existing route precedence must not change.
- Existing bbox/radius/polygon filter rules must not change, except bbox becomes explicit-only in the UI.
- Existing export, search, suggest, analytics, console, and detail tabs must not change.
- Existing light-mode visual language must be preserved.

### 9.7 Open contracts are blockers

Implementation must not start until these contracts are frozen in tests:

- exact token rule,
- typo map,
- phrase-prefix derivation,
- exact radius filter contract,
- pinned-row injection/count behavior.

### 9.8 Data-drift guardrail

Do not hard-code live counts such as `96`, `97`, or `5,390` in assertions. Use them as evidence only. Tests and browser QA must assert live behavior.

### 9.9 Git guardrail

- Do not commit unless explicitly requested.
- Do not push unless explicitly requested.
- Stage only intended files.
- Run `git diff --check` before any commit.

## 10. Files likely to change during implementation

| File | Expected change |
|---|---|
| `backend/queries.py` | typo-tolerant fallback query, normalization helpers, score-aware sort/cursor |
| `backend/routes.py` | parse new cursor, add score/distance metadata, nearby-aware sorting |
| `backend/geometry.py` | only if distance helper behavior needs explicit tests; avoid unnecessary changes |
| `frontend/index.html` | unchecked `#b-use-view`, **Show nearby** button, cache bump to `?v=6` |
| `frontend/app.js` | focus state, focus marker, nearby mode, explicit bbox behavior, status warnings |
| `frontend/styles.css` | focus marker/row/button styles if needed |
| `tests/test_queries.py` | query fallback, normalization, score sort/cursor, non-`q` regression |
| `tests/test_routes.py` | boundary route response metadata, route precedence, cache behavior |
| `tests/test_geometry.py` | distance/radius contract if changed |

## 11. Implementation sequence

1. Freeze the five open contracts.
2. Write failing tests for normalization and query fallback.
3. Implement backend query changes.
4. Write/update route tests for score ordering, cursor handling, metadata, and distance.
5. Implement backend route changes.
6. Update frontend form: unchecked bbox, nearby button, cache bump.
7. Implement frontend state transitions and focus/nearby behavior.
8. Add browser QA checks for the full flow.
9. Run verification.
10. Stop for review; commit only if requested.

## 12. Test plan

### 12.1 Backend unit tests

Add or update tests for:

- normalization:
  - lowercase,
  - punctuation stripping,
  - whitespace collapse,
  - typo token mapping,
  - phrase-prefix derivation,
  - original text preserved for fuzzy.
- fallback query:
  - `shivalik recidency` resolves `projectId 573`,
  - exact/current group boost is `10`,
  - fallback group contains exact, phrase-prefix, and fuzzy clauses,
  - top-level `minimum_should_match` is `1`,
  - no scripts/runtime mappings/regexp/leading wildcards.
- ordering:
  - with `q`, sort is `_score desc` then `projectId asc`,
  - without `q`, sort remains `projectId asc`.
- cursors:
  - score-mode cursor `[score, projectId]`,
  - non-query `[projectId]` regression.
- response:
  - `score` is exposed with `q`,
  - `distance_km` is exposed with radius inputs,
  - `complete`, `loaded`, `returned`, and `total` keep their meanings.
- route:
  - `/api/projects/boundaries` still wins over `/api/projects/{project_id}`.
  - cache behavior remains correct for query and non-query filters.

### 12.2 Frontend/browser QA

Manual browser checks at `http://127.0.0.1:8000`:

- `#b-use-view` is unchecked on load.
- Pan/zoom does not trigger a network request.
- `q=shivalik recidency`:
  - resolves a focus marker,
  - highlights `Shivalik Residences`,
  - opens the popup,
  - zooms to at least 14.
- **Show nearby**:
  - is disabled before focus,
  - pins the focus row,
  - clears `q`,
  - sets radius to `2`,
  - keeps indexed filters,
  - sorts by distance,
  - keeps pinned row first with no nearby rows.
- Popup action opens Project detail.
- Non-empty `q` submit exits nearby mode.
- Reset exits nearby mode.
- Missing radius inputs show the exact required error.
- Static asset URL is `?v=6`.

### 12.3 Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
make check
git diff --check
```

## 13. Definition of done

The feature is done when:

- all five open contracts are frozen and covered by tests,
- `shivalik recidency` resolves `Shivalik Residences` / `projectId 573`,
- score ordering and cursor behavior work without breaking non-query mode,
- default bbox behavior no longer hides results,
- focus marker and row highlight work,
- nearby mode pins, sorts, and preserves filters correctly,
- read-only guardrails remain intact,
- all tests pass,
- `make check` passes,
- browser QA confirms the complete flow,
- no commit or push is made unless explicitly requested.

## 14. Current blockers

- Exact token rule is not frozen.
- Typo map is not frozen.
- Phrase-prefix derivation is not frozen.
- Exact radius filter contract is not frozen.
- Pinned-row injection/count behavior is not frozen.
- Native ES geo queries remain impossible without mapping changes, which are forbidden.
