# Compact Context — Gujrat RERA Explorer

## Objective
Build a read-only FastAPI + vanilla JS/Chart.js app over Elasticsearch index `gujrat_rera_data` (17,271 docs) with 9 tabs, following `PLAN.md` phase-by-phase with review checkpoints. Phases 0–5 (all backend and frontend features) are complete; Phase 6 (unit/integration test suite) is next.

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
- **Phase 4 backend & frontend**:
  - `backend/queries.py`: `build_page`, `parse_cursor`, `build_search_after`. Fixed cursor validation to allow 1–2 integer sort values for PIT mode `[projectId, shard_doc]`.
  - `backend/routes.py`: routes for `/api/projects/page`, `/api/projects/search-after`, `POST /api/pit`, `DELETE /api/pit/{session_id}`, `/api/projects/export` with streaming CSV.
  - `frontend/index.html` & `frontend/app.js`: Pagination & Export tab with from/size, cursor pagination, PIT lifecycle, and memory-safe CSV export.
- **Phase 5 backend & frontend**:
  - `backend/routes.py`: Added `POST /api/analyze`, `GET /api/ops/health`, `GET /api/ops/nodes`, `GET /api/ops/shards`, and `POST /api/query/{index}` with recursive AST allowlist (`_validate_console_body`), blocking scripts, wildcards, and non-whitelisted keys.
  - `frontend/index.html` & `frontend/app.js`: Mapping & Indices tab (with live analyzer), Ops tab (health, node heap/cpu, shard allocator), and Guarded Console tab.
- **All 30 API & contract checks passed**: Verified live against Elasticsearch 8.19.23.

### Active
- All 9 frontend tabs and 25 API routes are fully implemented and running.
- Ready for comprehensive test suite creation and bug hunting (`tests/` directory).

### Blocked
- (none)

## Next Move
1. Build out the formal `pytest` test suite in `tests/` (`test_queries.py`, `test_validators.py`, `test_errors.py`, `test_routes.py`, `test_streams.py`).
2. Run full testing suite to identify any edge-case bugs and verify query optimization.
