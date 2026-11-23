# Compact Context — Gujrat RERA Explorer

## Objective
Build a read-only FastAPI + vanilla JS/Chart.js app over Elasticsearch index `gujrat_rera_data` (17,271 docs) with 9 tabs, following `PLAN.md` phase-by-phase with review checkpoints. Phases 0–3 are complete; Phase 4 backend is mostly implemented; Phase 4 frontend is pending.

## Important Details
- ES: `http://192.168.1.14:9200`, cluster `elasticsearch`, node `rajiv-omen`, v8.19.23, yellow, 69 primary / 36 unassigned shards.
- Index `gujrat_rera_data`: 17,271 docs, 279.1mb, 1 primary (STARTED) + 1 replica (UNASSIGNED), `dynamic: false`.
- 5 disabled objects (`enabled:false`, stored but not indexed): `Project Profile`, `Project Summary`, `Promoters`, `Progress & RERA Actions`, `More Projects by The Same Developer`.
- Read-only constraints: no index/document/template/ILM mutations; allowed non-mutating calls include GET APIs, `POST /_pit`, `DELETE /_pit`, `POST /_analyze`, `POST /_ingest/pipeline/{id}/_simulate`; no scripts, `script_fields`, `runtime_mappings`, `regexp`, or leading wildcard.
- `price` is keyword: `term`/`prefix`/`terms` only, NEVER numeric `range`/sort. Dates: `dd-MM-yyyy` with explicit `format`. `from + size <= 10000`.
- Envelope: `{data, meta:{index,total,returned,es_took_ms,wall_ms,query_used}}`; errors: `{error:{code,message,detail:"redacted"}}`.
- Highlighting uses `[[HL]]`/`[[/HL]]`; browser builds `<em>` DOM nodes, never injects ES text as HTML.
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
- **Phase 3 checks**: `py_compile backend\queries.py backend\routes.py`, `node --check frontend\app.js` passed; all 28 JS DOM ids exist in HTML.
- **Phase 4 backend edits applied**:
  - `backend/queries.py`: `import json`; constants `MAX_EXPORT_LIMIT=100000`, `EXPORT_BATCH=100`, `PAGE_SOURCE`, `EXPORT_COLUMNS`; functions `build_page`, `parse_cursor`, `build_search_after` inserted before `_date_range`.
  - `backend/routes.py`: imports `csv`, `io`, `StreamingResponse`, `_safe_reason`, export constants/builders; helpers `_shape_paged_hit`, `_safe_cell`, async generator `_export_rows`; routes `GET /api/projects/page`, `GET /api/projects/search-after`, `POST /api/pit`, `DELETE /api/pit/{session_id}`, `GET /api/projects/export`.
  - Export opens a dedicated PIT before streaming, batches ≤100, writes formula-safe CSV cells, sanitizes error row, closes PIT in `finally`, sets `Content-Disposition: attachment; filename="gujrat_rera_projects.csv"` and `Cache-Control: no-store`.
  - `py_compile backend\queries.py`, `py_compile backend\routes.py`, and `import backend.routes` all pass.
- **Phase 4 partial live test (port 8013, server stopped in `finally`)**:
  - `/api/projects/page?page=1&size=3` → `page=1 from=0 returned=3 has_more=True ids=12,38,58`.
  - `/api/projects/search-after?size=3` → `mode=search_after returned=3 cursor=58 ids=12,38,58`.
  - Second cursor call failed 400 `invalid_request: cursor must be a JSON array containing one integer projectId` because PowerShell `ConvertTo-Json` serialized the single-element array `[58]` as scalar `58`; this is a test-harness encoding issue, not a confirmed code bug. Rerun with literal `[58]` or `@($cursor) | ConvertTo-Json -Compress -AsArray`.
  - Page overflow and remaining PIT/export checks did not complete because the script aborted at the cursor error; rerun with `curl.exe` for reliable body capture.

### Active
- Phase 4 backend is implemented but only partially verified.
- Phase 4 frontend (Pagination & Export tab) is not started.
- No end-to-end browser UI click-through done; DOM-id checks used instead.

### Blocked
- (none)

## Next Move
1. Rerun Phase 4 live checks with correct cursor encoding: page overflow (`page=501&size=20` → 400), search-after next page with literal `[58]`, `POST /api/pit`, PIT-mode search, `DELETE /api/pit/{session_id}`, expired-session 400, `GET /api/projects/export?limit=5` CSV, `limit=100001` → 400.
2. Implement Phase 4 frontend in `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`: Pagination & Export tab with numeric pager from `/projects/page`, cursor pager from `/projects/search-after`, PIT open/close controls, CSV export link/download, and status/result table.
3. Re-run `node --check frontend\app.js` and DOM-id consistency check after frontend edits.

## Relevant Files
- `C:\D-Drive\ElasticSearch_project\PLAN.md`: phases, D7/D12 export paging, constraints.
- `C:\D-Drive\ElasticSearch_project\PROJECT_CONTEXT.md`: Query DSL and live index values.
- `README.md`: 9-tab overview and API catalog.
- `backend\config.py`: `settings.index_rera`, `pipeline_id`, `pit_keep_alive`, `pit_ttl_seconds`.
- `backend\schemas.py`: `CORE_FIELDS`, `DISABLED_OBJECTS`, `AppError`, `envelope`, request models.
- `backend\es_client.py`: ESManager, capabilities, PITSession registry, `_safe_reason`.
- `backend\queries.py`: Phase 2–4 builders; Phase 4 constants/functions now present.
- `backend\routes.py`: all API routes including new Phase 4 routes; dynamic `/projects/{project_id}` must remain last.
- `backend\main.py`: app factory, lifespan, error handlers, static mount.
- `frontend\index.html`, `frontend\styles.css`, `frontend\app.js`: SPA shell/DOM/API logic; Phase 4 frontend pending.
- Run: `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000` → http://127.0.0.1:8000
