# Compaction Context — Gujrat RERA Explorer

## Objective
Build and maintain a read-only FastAPI + vanilla JS/Chart.js app over Elasticsearch index `gujrat_rera_data` (17,271 docs), following `PLAN.md` phase-by-phase with review checkpoints. Phases 0–6 plus the read-only `Map / Boundaries` tab are implemented. The approved search-to-centroid follow-up is documented but not yet implemented in code.

## Important Details
- ES: `http://192.168.1.14:9200`, cluster `elasticsearch`, node `rajiv-omen`, v8.19.23, yellow, 69 primary / 36 unassigned shards.
- Index `gujrat_rera_data`: 17,271 docs, 279.1mb, 1 primary `STARTED` + 1 replica `UNASSIGNED`, `dynamic: false`.
- 5 disabled objects (`enabled:false`, stored but not indexed): `Project Profile`, `Project Summary`, `Promoters`, `Progress & RERA Actions`, `More Projects by The Same Developer`.
- Read-only constraints: no index/document/template/ILM mutations; allowed non-mutating calls include GET APIs, `POST /_pit`, `DELETE /_pit`, `POST /_analyze`, `POST /_ingest/pipeline/{id}/_simulate`; no scripts, `script_fields`, `runtime_mappings`, `regexp`, or leading wildcard.
- `price` is keyword: `term`/`prefix`/`terms` only, NEVER numeric `range`/sort. Dates: `dd-MM-yyyy` with explicit `format`. `from + size <= 10000`.
- Envelope: `{data, meta:{index,total,returned,es_took_ms,wall_ms,query_used}}`; errors: `{error:{code,message,detail:"redacted"}}`.
- Highlighting uses `[[HL]]`/`[[/HL]]`; browser builds `<mark>` DOM nodes, never injects ES text as HTML.
- Exact/prefix keyword clauses use `case_insensitive: true`; `plot`, `Plot`, `PLOT`, `PLot` match the same search/suggest/filter results.
- Geo is partial/read-only: live mapping has no `geo_point`/`geo_shape`. `Project Profile.Map Location` holds boundary rings in `_source` (17,271 docs, 16,955 usable, 312 degenerate, 4 unparseable, 105,750 total points, Ahmedabad 5,305 usable rings). No index writes.
- `Project Profile.Map Location` is a boundary ring, not a point. `parse_ring`, `ring_center`, bbox/radius/polygon filtering, and haversine distance are implemented in Python.
- Boundary API: `GET /api/projects/boundaries`, registered before `/api/projects/{project_id}`; indexed filters go to ES, geometry filters run in Python after `_source` parsing.
- Boundary response includes `features`, `markers`, `skipped`, `capabilities:{native_geo_dsl:false,source_boundaries:true}`, `next_after`, `complete`, `loaded`, and the standard `meta` envelope.
- Boundary cache: `BOUNDARY_CACHE_TTL_SECONDS = 900`, `BOUNDARY_CACHE_MAX_ENTRIES = 24`; `MAX_BOUNDARY_SIZE = 10000`; route default `size = 1000`, UI uses `2000` with multi-page loading up to `20` pages.
- Canvas renderer is enabled with `L.map(..., { preferCanvas: true })`; verify map features with `boundaryState.layersById.size`, not DOM `.leaflet-interactive` counts.
- Python **3.11**, venv `C:\D-Drive\ElasticSearch_project\.venv`, installed deps include fastapi 0.165.0, elasticsearch 8.19.3, uvicorn 0.54.0, pydantic-settings 2.16.3, pytest 9.2.0, httpx 0.28.1, pytest-asyncio 1.5.0, aiohttp.
- Use `.venv\Scripts\python.exe`; set `PYTHONPATH="."` for standalone scripts importing `backend`.
- Docs claim `residency+Ahmedabad+Ongoing=96`; live has returned `97` due to data drift, so assert live values instead of hard-coding.
- Pipeline `gujrat_normalize_pipeline` is missing: `ingest.simulate` raises 400 `illegal_argument_exception` with `pipeline [...] does not exist`; route normalizes to 404 `pipeline_missing`.
- Export follows `PLAN.md` D7/D12: dedicated PIT + `search_after`, batches ≤100, `csv.writer`, formula prefixing, sanitized error row, PIT close in `finally`.
- PIT registry is in `backend/es_client.py`: `pit_keep_alive="2m"`, `pit_ttl_seconds=90`, missing/expired maps to `session_expired`.
- Frontend/backend are served by one Uvicorn process on port `8000`: `/` → `frontend/index.html`, `/static/*` → `frontend/`, `/api/*` → `APIRouter(prefix="/api")`.
- Browse QA needs `$env:BROWSE_SERVER_SCRIPT = "C:\Users\Dell\.config\opencode\skills\gstack\browse\dist\server-node.mjs"` because `browse.exe` otherwise errors: `Cannot find server.ts. Set BROWSE_SERVER_SCRIPT env or run from the browse source tree.`
- Approved search-to-centroid follow-up:
  - Root causes: `q=shivalik recidency` fails because `build_boundary_query()` requires both tokens and has no typo fallback; name → centroid → nearby projects is not implemented; `#b-use-view` defaults checked and viewport bbox is a hard Python filter.
  - Live probe evidence: `shivalik recidency` returns `0`, `shivalik residency` returns `5`; fuzzy `AUTO` returns `11` hits and misses id `573`; `match_phrase_prefix` on `project_name` with `shivalik resid` returns id `573` first; `project_name.keyword` supports `case_insensitive: true`; prefix `resid` returns `64` hits with id `573` first.
  - Likely target: `projectId` / id `573`, `Shivalik Residences`, district `Ahmedabad`, centroid `[23.056223, 72.591239]`.
  - Final frozen-ish top-level `bool.should` probe ranks id `573` at rank `5` with score `333.12268`; exact `Residency` names rank above it.
  - Proposed top-level `bool.should[0]`: exact/current group with `multi_match` on original `q`, fields `["project_name^4", "promoter_name^3", "district^3", "taluka^2", "project_type^3", "reg_no^2", "page_url^1"]`, `type: "cross_fields"`, `operator: "or"`, `minimum_should_match: "<current token rule>"`, `lenient: true`, `boost: 10`.
  - Proposed top-level `bool.should[1]`: fallback `bool`, `minimum_should_match: 1`, `boost: 1`; clauses are normalized exact `match` on `project_name` (`boost: 4`), `match_phrase_prefix` on `project_name` (`boost: 3`), and fuzzy `match` on original `q` (`fuzziness: "AUTO"`, `prefix_length: 1`, `max_expansions: 25`, `operator: "and"`, `boost: 1`).
  - Proposed top-level `minimum_should_match: 1`; normalization lowercases, strips punctuation, keeps original tokens, and maps exact tokens `recidency`, `recidancy`, `recidence`, `recidance` → `residency`; `shivalik recidency` → normalized exact `shivalik residency`, phrase-prefix `shivalik resid`.
  - With `q`, sort ES by `_score` desc then `projectId` asc; expose `score`; use `[score, projectId]` cursor. Without `q`, keep current `projectId` ordering/cursor.
  - With `lat`, `lon`, `distance_km`, add `distance_km = haversine_km(...)`; field meanings: `total` = ES hits, `loaded` = accumulated features/markers before geometry filtering, `returned` = current response after geometry filtering, `complete` = ES end reached, truncation warning when `complete=false` or rows exceed `250`.
  - UI decisions: default `Use current view` unchecked; unchecking clears `#b-bbox` and `lastBounds`; `moveend` does not trigger reload; `Load Boundaries` while checked computes fresh bbox; auto-focus first `q` result with usable center, draw distinct circle marker, highlight row, zoom `14`; row click sets focus and opens popup; popup action calls existing `openDetail(id)`.
  - `Show nearby`: disabled without focus; sets `pinned = focus`, `nearbyMode = true`, clears `q`, unchecks `#b-use-view`, clears `#b-bbox`, fills `lat` / `lon`, sets `distance_km = 2`, keeps district/taluka/project type/status/reg no filters; pinned row first with `Pinned`, distance `0.0`; others sorted by `distance_km` rounded to 1 decimal; pinned row remains if no nearby rows.
  - Nearby exits: row click re-centers nearby; non-empty `q` submit exits nearby and clears pinned/nearby + `lat` / `lon` / `distance_km`; Reset exits nearby; radius error string `Radius requires latitude, longitude, and a positive distance.`
  - Open contracts before coding: freeze exact token rule, typo map, phrase-prefix derivation, radius filter contract, and pinned-row injection/count behavior.

## Work State
### Completed
- **Phase 0**: `requirements.txt`, `.env.example`, `.gitignore`, `.venv`, dependencies installed.
- **Phase 1**: `backend/config.py`, `backend/schemas.py`, `backend/es_client.py` (ESManager, degraded discovery, capabilities, flatten_mapping, PIT registry), `backend/routes.py` (health/config/capabilities/indices/mapping/stats/aliases), `backend/main.py`.
- **Phase 2 backend**: `backend/queries.py` search/suggest/facets/detail builders with `ALLOWED_SORTS`, `parse_sort`, `validate_size`, `validate_page`; routes `/api/projects/search`, `/suggest`, `/facets`, `/{project_id}`.
- **Phase 2 frontend**: Dashboard/Projects/Detail panels, facets, suggest, safe highlights, recursive detail renderer, safe URL check, `.mono`.
- **Phase 3 backend**: analytics overview/dates, scrape quality, casing collisions, and pipeline-simulate routes.
- **Phase 3 frontend**: Analytics KPIs/charts/table fallback, Data Quality KPIs/missing fields/scrape coverage/collision cards/malformed-date caveat/pipeline simulator.
- **Phase 4 backend & frontend**: from/size pages, cursor pagination, PIT lifecycle, streaming CSV export.
- **Phase 5 backend & frontend**: Mapping & Indices, Ops, live analyzer, and Guarded Console with recursive AST allowlist.
- **Phase 6**: pytest suite and `make check`.
- **UI/UX polish**: accessible light-mode styling, safe highlight rendering, cache busting; committed as `ecb1b42 Polish explorer UI accessibility and styling`.
- **Case-insensitive matching**: `_term_clause`, `_prefix_clause`, `_text_filter` plus tests; committed as `b982822 Add case-insensitive exact and prefix matching`.
- **Read-only boundary map**:
  - `backend/geometry.py`: ring parsing, centroids, bbox/radius/polygon filtering, haversine distance.
  - `backend/queries.py`: `build_boundary_query`, `BOUNDARY_SOURCE`, `BOUNDARY_SOURCE_PATH`, `BOUNDARY_SOURCE`.
  - `backend/routes.py`: `/api/projects/boundaries`, cache helpers, scanning/batching, geometry filtering.
  - `backend/es_client.py`: `boundary_map` and `native_geo_dsl:false` capability flags.
  - `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`: 10th tab, Leaflet map, controls, layers/popups/table/query-used, mobile layout.
  - `tests/test_geometry.py`, `tests/test_queries.py`, `tests/test_routes.py`: full boundary coverage.
- **Browser QA verified**: Ahmedabad load `"Rendered 5,388 project boundaries."`, `tableRows: 250`, `boundaryState.layersById.size = 5388`, meta `5,388 visible`, `scanned 5,388 of 5,390`, cache hit; popup + detail link; viewport bbox `331`; radius `185`; polygon `180`; invalid bbox error; GET-only fetch calls; mobile map height `360px`.
- **Documentation updated**: `README.md`, `PROJECT_CONTEXT.md`, `PLAN.md`, `FRONTEND_UI_UX_GUIDE.md`, `compact.md` now describe the 10-tab app, boundary map, and approved search-to-centroid plan.
- **Verification**: `.venv\Scripts\python.exe -m pytest -q` → `53 passed`; `make check` → backend compile + `node --check frontend/app.js` passed; `git diff --check` only reported CRLF warnings.
- **Commits pushed to `origin/main`**:
  - `3293d61 Add read-only boundary map API and tests`
  - `99f8582 Add interactive project boundary map tab`
  - `d47186a Document boundary map and search-to-centroid plan`
- **Current git state**: branch `main` tracks `origin/main` at `d47186a`; working tree is clean.

### Active
- No uncommitted changes; all stage-by-stage commits were pushed.
- Approved search-to-centroid follow-up is documented but not implemented in code.

### Blocked
- Native ES `geo_point` / `geo_shape` queries remain unavailable because the mapping has no geo fields and read-only mode forbids index changes.
- Search-to-centroid implementation should not start until the exact token rule, typo map, phrase-prefix derivation, radius filter contract, and pinned-row injection/count behavior are frozen.
- `rg` is unavailable on this machine; use PowerShell `Select-String` for diff/text scans.

## Next Move
1. Implement the approved search-to-centroid patch after freezing the remaining exact contracts: backend query fallback and scoring/cursor changes, then frontend focus/nearby behavior.
2. Re-run `.venv\Scripts\python.exe -m pytest -q`, `make check`, and targeted browser QA; commit/push only when explicitly requested.
