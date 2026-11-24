# Compact Context — Gujrat RERA Explorer

## Objective
Build a read-only FastAPI + vanilla JS/Chart.js app over Elasticsearch index `gujrat_rera_data` (17,271 docs) with 10 active tabs, following `PLAN.md` phase-by-phase with review checkpoints. Phases 0–6 plus a read-only `Map / Boundaries` tab are in scope; native ES geo DSL remains out of scope.

## Important Details
- ES: `http://192.168.1.14:9200`, cluster `elasticsearch`, node `rajiv-omen`, v8.19.23, yellow, 69 primary / 36 unassigned shards.
- Index `gujrat_rera_data`: 17,271 docs, 279.1mb, 1 primary (STARTED) + 1 replica (UNASSIGNED), `dynamic: false`.
- 5 disabled objects (`enabled:false`, stored but not indexed): `Project Profile`, `Project Summary`, `Promoters`, `Progress & RERA Actions`, `More Projects by The Same Developer`.
- Read-only constraints: no index/document/template/ILM mutations; allowed non-mutating calls include GET APIs, `POST /_pit`, `DELETE /_pit`, `POST /_analyze`, `POST /_ingest/pipeline/{id}/_simulate`; no scripts, `script_fields`, `runtime_mappings`, `regexp`, or leading wildcard.
- `price` is keyword: `term`/`prefix`/`terms` only, NEVER numeric `range`/sort. Dates: `dd-MM-yyyy` with explicit `format`. `from + size <= 10000`.
- Envelope: `{data, meta:{index,total,returned,es_took_ms,wall_ms,query_used}}`; errors: `{error:{code,message,detail:"redacted"}}`.
- Highlighting uses `[[HL]]`/`[[/HL]]`; browser builds `<mark>` DOM nodes, never injects ES text as HTML.
- Exact/prefix keyword clauses use `case_insensitive: true`; `plot`, `Plot`, `PLOT`, `PLot` match the same search/suggest/filter results.
- Geo is partial/read-only: live mapping has no `geo_point`/`geo_shape`. `Project Profile.Map Location` holds boundary rings in `_source` (17,271 docs, 16,955 usable, 312 degenerate, 4 unparseable, 105,750 points, Ahmedabad 5,305). No index writes.
- Python **3.11**, venv `C:\D-Drive\ElasticSearch_project\.venv`, no DB/auth/Docker/build step.
- Installed: fastapi 0.165.0, elasticsearch 8.19.3, uvicorn 0.54.0, pydantic-settings 2.16.3, pytest 9.2.0, httpx 0.28.1, pytest-asyncio 1.5.0, aiohttp.
- Docs claim `residency+Ahmedabad+Ongoing=96`; live returns **97** (data drift — assert live, not hard-coded).
- Pipeline `gujrat_normalize_pipeline` is missing: `ingest.simulate` raises 400 `illegal_argument_exception` with `pipeline [...] does not exist`; route normalizes to 404 `pipeline_missing`.
- Export follows `PLAN.md` D7/D12 (dedicated PIT + `search_after`, batches ≤100, `csv.writer`, formula prefixing, sanitized error row, PIT close in `finally`).
- PIT registry is in `backend/es_client.py`: `pit_keep_alive="2m"`, `pit_ttl_seconds=90`, missing/expired maps to `session_expired`.
- Use `.venv\Scripts\python.exe`; set PYTHONPATH for standalone scripts importing `backend`.

## Work State
### Completed
- **Phase 0**: `requirements.txt`, `.env.example`, `.gitignore`, `.venv`, deps installed.
- **Phase 1**: `backend/config.py`, `backend/schemas.py`, `backend/es_client.py` (ESManager, degraded discovery, capabilities, flatten_mapping, PIT registry), `backend/routes.py` (health/config/capabilities/indices/mapping/stats/aliases), `backend/main.py`. Verified: endpoints 200; forbidden mapping 403; 13 features; 5 non-indexed objects; degraded discovery works.
- **Phase 2 backend**: `backend/queries.py` search/suggest/facets/detail builders with `ALLOWED_SORTS`, `parse_sort`, `validate_size`, `validate_page`; routes `/api/projects/search`, `/suggest`, `/facets`, `/{project_id}`. Verified: total=17271, filtered=97, facets 35 districts, detail 573 with all 5 sections, 404/400 guards.
- **Phase 2 frontend**: `frontend/index.html`, `frontend/styles.css`, `frontend/app.js` with Dashboard/Projects/Detail panels, facets, suggest, safe highlights, recursive detail renderer, safe URL check, `.mono`; `node --check` passed.
- **Phase 3 backend**: added `build_analytics_overview`, `build_analytics_dates`, `build_quality_scrape`, `_group_collisions`, `compute_casing_collisions`; routes `/api/analytics/overview`, `/api/analytics/dates`, `/api/quality/scrape`, `POST /api/quality/pipeline-simulate`.
- **Phase 3 frontend**: Analytics KPIs + 6 Chart.js bar charts with table fallback; Data Quality KPIs, missing fields, scrape coverage, collision cards, malformed-date caveat, pipeline simulator; Chart.js CDN in HTML.
- **Phase 3 verified**: overview aggs `districts,talukas,project_types,project_statuses,top_promoters,documents_stats,docs_downloaded`; districts=20, promoters=10, start_year buckets=23, end_year=20; quality total=17271, `missing_price=6`, district collisions=4, taluka collisions=0; simulate → 404 `pipeline_missing`.
- **Phase 4 backend & frontend**:
  - `backend/queries.py`: `build_page`, `parse_cursor`, `build_search_after`. Fixed cursor validation to allow 1–2 integer sort values for PIT mode `[projectId, shard_doc]`.
  - `backend/routes.py`: routes for `/api/projects/page`, `/api/projects/search-after`, `POST /api/pit`, `DELETE /api/pit/{session_id}`, `/api/projects/export` with streaming CSV.
  - `frontend/index.html` & `frontend/app.js`: Pagination & Export tab with from/size, cursor pagination, PIT lifecycle, and memory-safe CSV export.
- **Phase 5 backend & frontend**:
  - `backend/routes.py`: Added `POST /api/analyze`, `GET /api/ops/health`, `GET /api/ops/nodes`, `GET /api/ops/shards`, and `POST /api/query/{index}` with recursive AST allowlist (`_validate_console_body`), blocking scripts, wildcards, and non-whitelisted keys.
  - `frontend/index.html` & `frontend/app.js`: Mapping & Indices tab (with live analyzer), Ops tab (health, node heap/cpu, shard allocator), and Guarded Console tab.
- **All 30 API & contract checks passed**: Verified live against Elasticsearch 8.19.23.
- **Phase 6**: `pytest` suite with 45 passing tests; `make check` and `git diff --check` pass (CRLF warnings only).
- **UI/UX polish**: accessible light-mode styling, safe highlight rendering, cache busting (now `?v=5`); committed/pushed as `ecb1b42 Polish explorer UI accessibility and styling`.
- **Case-insensitive matching**: `_term_clause`, `_prefix_clause`, `_text_filter` in `backend/queries.py` plus tests; verified live for `plot`/`Plot`/`PLOT`/`PLot`; committed/pushed as `b982822 Add case-insensitive exact and prefix matching`.
- **Geo feasibility investigation**: live mapping checked, no geo fields found; `Map Location` holds boundary rings in all 17,271 docs; docs rewritten for read-only map lab.

### Active
- All 10 frontend tabs and 26 API routes are implemented, including the `Map / Boundaries` tab and `/api/projects/boundaries`.
- Docs describe read-only boundary rendering, bbox/radius/polygon geometry filters, viewport batches, and LRU caching.
- Full suite currently passes with `53 passed`; `make check` passes and `git diff --check` reports CRLF warnings only.
- Browser QA verified Ahmedabad load (5,388 visible), viewport bbox (331), radius (185), polygon (180), popup + detail link, GET-only fetch calls, and 360px mobile map height.

### Blocked
- Native ES geo DSL remains unavailable because the mapping has no geo fields and read-only mode forbids index changes; no index writes are required for the map lab.

## Next Move
1. Browser-QA `Map / Boundaries`: Ahmedabad load, zoom clarity, polygon click popup, bbox/radius/polygon filters, cached re-render, and no write calls.
2. Commit the completed read-only boundary-map work only when requested.
