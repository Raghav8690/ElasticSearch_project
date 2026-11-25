# Optimization Change Plan

Status: batch 1 implemented (#1, #2, #4, #5, #8). Deferred items remain proposals.

Scope comes from `elasticsearch-optimization-guide.md`, limited to changes that can be made from the application side of `Gujrat RERA Explorer`. Hardware/JVM, shard layout, reindexing, mapping rewrites, force-merge, ILM, and index-settings changes are intentionally excluded because the app is read-only against Elasticsearch.

## Current baseline

The app already follows the important search-time rules:

- Exact/range filters use `bool.filter` in `backend/queries.py:383-421`.
- Deep pagination and streaming export use `search_after` + PIT in `backend/queries.py:330-342` and `backend/routes.py:642-695`.
- Aggregation-only requests use `size: 0` in `backend/queries.py:631-647`.
- `_source` is restricted for list, boundary, and export paths in `backend/queries.py:26-53`.
- Autocomplete is debounced by 300 ms in `frontend/app.js:645-686`.
- Detail lookup uses GET by `_id` first in `backend/routes.py:1282-1303`.
- Query console forbids scripts, runtime mappings, regexp, and leading wildcards in `backend/routes.py:1078-1127`.
- ES client uses connection pooling and a 15-second request timeout in `backend/es_client.py:230-242`.

The remaining weak spots are:

- First search with `q` can trigger a full-index address scan.
- Scored queries touch many fields and clauses.
- Some paths request exact `track_total_hits`.
- Diagnostics do not expose Profile API, thread-pool rejections, or cache hit rates.
- Application caching is process-local, not shared.

## Summary table

| # | Change | Priority | Before | After | Functionality change | Estimated code change |
|---|---|---:|---|---|---|---:|
| 1 | Warm and gate address rerank | P0 | First `q` search may run ~35 extra ES scans | Warm-up runs in background; rerank can be disabled | First search gets faster; explicit bypass changes address-based ranking | ~75-130 lines |
| 2 | Cap `track_total_hits` at 10000 | P1 | Exact counts such as `17,271` | Counts show `10,000+` above the cap | Match-count display becomes capped, rows unchanged | ~30-50 lines |
| 3 | Add query timeout / `terminate_after` controls | P1 | Only client-level 15s / 20s timeouts | Search body has optional safety limits | Queries can return partial results with a warning | ~65-105 lines |
| 4 | Allow Profile API in guarded console | P1 | `profile` is rejected | Console can run read-only profiled searches | Larger query metadata; no ranking change | ~55-95 lines |
| 5 | Surface thread-pool and cache metrics in Ops | P1 | `thread_pool` is fetched but dropped | Ops shows search queue/rejections/cache hits | New diagnostic cards/columns only | ~90-135 lines |
| 6 | Narrow scored query / add `rescore` | P2 | All phrase, prefix, fuzzy, and multi-match clauses score every candidate | Expensive scoring runs only on top N | Ranking may change; requires regression examples | ~75-130 lines |
| 7 | Batch dashboard/analytics calls with `_msearch` | P2 | Several parallel HTTP calls | One or two batched ES calls | No visual change; fewer round trips | ~85-150 lines |
| 8 | Wire or remove unused `request_timeout_seconds` | P3 | Config exists but is unused | One clear timeout source | No visible behavior change | ~5-15 lines |
| 9 | Move app caches to Redis | Deferred | Process-local dict caches | Shared TTL cache | Needs Redis service; works across workers | ~120-220 lines + deployment |

## 1. Warm and gate address rerank

### Why

`_ensure_address_index()` scans the entire index with `size: 500` and `search_after` before address-based reranking. With 17,271 documents, a cold cache means about 35 sequential search requests (`ceil(17,271 / 500)`) before the user sees results.

Relevant code:

- `backend/routes.py:46-49` — cache constants/state.
- `backend/routes.py:87-130` — cache freshness and full scan.
- `backend/routes.py:821-872` — rerank decision and merge logic.
- `backend/main.py:28-39` — FastAPI lifespan where warm-up can run.

### Before

- A search with `q` and no explicit sort calls `_ensure_address_index()` at `backend/routes.py:842`.
- Cold cache: the whole index is scanned before ranking is merged.
- Warm cache: searches are fast for one hour.
- If the process restarts, the cold scan happens again.
- With multiple workers, each worker can perform its own scan.

### After

- Add `warm_address_cache_on_startup: bool = True` to `backend/config.py`.
- In `backend/main.py` lifespan, start a non-blocking background task that calls `_ensure_address_index(es)` after discovery.
- Add `rerank_address: bool | None = None` to `/api/projects/search`.
- Default behavior remains `rerank_address=True` when `q` exists and no sort is provided.
- Explicit `rerank_address=false` uses only native ES ranking and skips the full scan completely.
- Add `cache_age_seconds` and `cache_status` to `query_used.rerank`.

### Effect on the app

- Default user-visible ranking stays the same when the cache is warm.
- First search after startup becomes much faster because the cold scan is moved off the request path.
- If warm-up fails, the app stays usable and simply returns normal ES ranking.
- Disabling rerank changes functionality: projects found only by locally extracted address tokens may disappear from top results.
- Ops/query metadata gains one more diagnostic section.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/config.py` | +2-4 lines | Warm-up flag |
| `backend/main.py` | +12-20 lines | Background startup task and cleanup |
| `backend/routes.py` | +25-40 lines | Query param, rerank gate, cache metadata |
| `frontend/app.js` | +5-15 lines | Optional rerank toggle / metadata display |
| `tests/test_routes.py` | +25-40 lines | Warm, bypass, failure tests |
| docs | +10 lines | Describe behavior |

Total: **~75-130 lines**.

### Verification

- Cold-start test: startup completes even if ES is down.
- Search test: first `q` search does not trigger a scan when warm-up succeeded.
- Bypass test: `rerank_address=false` skips `_ensure_address_index()`.
- Browser QA: `q=shivalik residency` still ranks the expected project when rerank is on.

## 2. Cap `track_total_hits` at 10000

### Why

The guide says to leave `track_total_hits` at the default/capped value unless an exact count is required. Current project and boundary searches request exact totals even though the UI mostly needs a count label and pagination progress.

Relevant code:

- `backend/queries.py:435` — project search exact total.
- `backend/queries.py:584` — boundary search exact total.
- `backend/queries.py:729` — quality aggregation exact total.
- `frontend/app.js:579` and `frontend/app.js:1869` — match count display.
- `frontend/app.js:2502` — boundary render count.

### Before

- Project search returns `total: 17271`-style exact counts.
- Boundary search returns exact totals.
- ES must fully count matches before responding.

### After

- Change relevant `track_total_hits` values from `True` to `10000`.
- If `total == 10000`, frontend formats it as `10,000+`.
- Keep exact totals only on an admin-only "exact count" option if needed.

### Effect on the app

- Result rows and ordering do not change.
- Match labels change from an exact number to `10,000+` when the cap is reached.
- Boundary progress text may show `scanned X of 10,000+`.
- Search becomes slightly cheaper on broad queries by allowing early termination.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/queries.py` | 2-4 lines changed | Replace `True` with `10000` |
| `frontend/app.js` | +10-20 lines | Format capped totals |
| tests | +10-20 lines | Assert capped values |
| docs | +5 lines | Explain count display |

Total: **~30-50 lines**.

### Verification

- Assert project and boundary bodies use `track_total_hits: 10000`.
- Browser QA on a broad query confirms `10,000+`.
- Browser QA on a narrow query still shows the exact count.

## 3. Add query timeout and `terminate_after` controls

### Why

The app has client-level timeouts, but no search-body safety net. The guide recommends `timeout` and `terminate_after` for runaway queries.

Current state:

- ES client timeout: 15 seconds in `backend/config.py:20`.
- Frontend abort timeout: 20 seconds in `frontend/app.js:3-33`.
- Guarded console does not allow `timeout` or `terminate_after`.

### Before

- A bad console query can run until the HTTP client gives up.
- No per-query early termination.
- No UI warning when ES returns partial results.

### After

- Add `search_timeout_seconds` and `max_terminate_after` settings.
- Add optional `timeout` and `terminate_after` to generated bodies for console and boundary scans.
- Keep default application search unchanged to avoid surprising partial results.
- Detect `_shards.terminated_early` and show a warning badge in query metadata.

### Effect on the app

- Advanced queries gain a hard safety limit.
- If a limit triggers, results can be incomplete and the UI must say so.
- Normal search behavior remains unchanged unless the user opts in.
- Failed/partial queries become easier to diagnose.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/config.py` | +2 lines | New settings |
| `backend/queries.py` | +10-20 lines | Add optional body keys |
| `backend/routes.py` | +15-25 lines | Apply and report termination |
| console validator | +5 lines | Validate allowed ranges |
| `frontend/app.js` | +15-25 lines | Warning UI |
| tests | +20-30 lines | Validation and partial-result tests |

Total: **~65-105 lines**.

### Verification

- Invalid `terminate_after` values are rejected.
- A forced low `terminate_after` returns `_shards.terminated_early`.
- Frontend shows a clear partial-result warning.

## 4. Allow Profile API in the guarded console

### Why

The guide recommends the Profile API for finding expensive clauses. `profile: true` is read-only and can be safely allowed in the guarded console if strictly validated as a boolean.

Relevant code:

- `ALLOWED_CONSOLE_KEYS` in `backend/routes.py:1079-1082`.
- Validator in `backend/routes.py:1104-1127`.

### Before

- Any body containing `profile` is rejected as an unsupported key.
- Users cannot see per-clause timing from the UI.

### After

- Add `profile` to `ALLOWED_CONSOLE_KEYS`.
- Validate that its value is exactly `true` or `false`.
- Render the returned `profile.shards[].searches[].query` timings in the console result panel.
- Keep a default of `false`.

### Effect on the app

- No data or ranking change.
- Console responses become larger when profiling is enabled.
- Developers can compare before/after clause costs without leaving the app.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/routes.py` | +8-15 lines | Allow and validate `profile` |
| `frontend/app.js` | +25-45 lines | Render profile breakdown |
| `frontend/styles.css` | +10-20 lines | Collapsible profile layout |
| tests | +10-15 lines | Validation tests |

Total: **~55-95 lines**.

### Verification

- `{ "profile": true, "query": ... }` succeeds.
- `{ "profile": "true" }` is rejected.
- Scripts/regexp/runtime mappings remain forbidden.

## 5. Surface thread-pool and cache metrics in Ops

### Why

`ops_nodes()` already requests `thread_pool`, but the projection drops it. The guide specifically says to watch search rejections and cache hit rates.

Relevant code:

- `backend/routes.py:1027-1060` — node stats projection.
- `frontend/app.js:1707-1774` — Ops rendering.

### Before

- Ops shows cluster health, heap, CPU, docs, and store.
- Search queue depth and rejections are invisible.
- Node query cache and request cache hit rates are invisible.

### After

Project these from `_nodes/stats`:

- `thread_pool.search.active`
- `thread_pool.search.queue`
- `thread_pool.search.rejected`
- `thread_pool.search.completed`
- `indices.query_cache.hit_count`
- `indices.query_cache.miss_count`
- `indices.query_cache.evictions`
- `indices.request_cache.hit_count`
- `indices.request_cache.miss_count`

Add them as extra node-table columns or a new diagnostic card.

### Effect on the app

- No search behavior change.
- Ops tab gains operational metrics.
- Cache effectiveness and search saturation become visible.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/routes.py` | +20-30 lines | Project new metrics safely |
| `frontend/app.js` | +40-60 lines | Render columns/cards |
| `frontend/styles.css` | +20-35 lines | Layout for new metrics |
| tests | +10 lines | Projection tests |

Total: **~90-135 lines**.

### Verification

- Missing ES fields render as `—`, not `undefined`.
- Existing Ops tab still loads when metrics are absent.
- Browser QA at desktop and mobile widths shows no overflow.

## 6. Narrow scored query or add `rescore`

### Why

The relevance query currently creates many scored clauses: exact boosts, prefix boosts, two phrase clauses, and a 7-field `cross_fields` query. The guide recommends fewer scored fields and `rescore` for expensive scoring.

Relevant code:

- `backend/queries.py:208-253` — relevance clause.
- `backend/queries.py:504-572` — boundary relevance clause.

### Before

- Every candidate is scored by all exact, prefix, phrase, and multi-match clauses.
- Typo handling and phrase scoring apply broadly.
- Query shape is hard to profile because many clauses contribute.

### After

- Keep exact filters and high-value exact boosts in the main query.
- Move phrase/fuzzy scoring into `rescore` with `window_size: 100` or `200`.
- Keep `multi_match` as the broad recall query.
- Benchmark before and after with `query_used.es_took_ms` and Profile API.

### Effect on the app

- Ranking may change for multi-token and misspelled queries.
- `shivalik recidency` and `shivalik residency` must be regression cases.
- Nearby/boundary flows may rank different projects if boundary relevance is also changed.
- This is the highest functional-risk optimization in this document.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/queries.py` | +35-60 lines | Split main query and rescore |
| tests | +30-60 lines | Ranking regression tests |
| docs | +10 lines | Explain changed ranking behavior |
| frontend | 0 lines | No UI change expected |

Total: **~75-130 lines**.

### Verification

- Run before/after profiling on at least 10 real query strings.
- Confirm exact project IDs still rank first.
- Confirm boundary nearby focus still selects the expected centroid.
- Do not implement unless measured query time justifies the ranking risk.

## 7. Batch dashboard/analytics calls with `_msearch`

### Why

The guide recommends `_msearch` to reduce round trips. The app currently issues several separate requests in parallel.

Relevant call groups:

- `frontend/app.js:1589-1593` — mapping, stats, aliases.
- `frontend/app.js:1714-1718` — health, nodes, shards.
- Analytics facets/quality requests in `frontend/app.js`.

### Before

- Dashboard and analytics fire multiple HTTP requests.
- Each response has separate envelope metadata.
- Latency includes several round trips.

### After

- Add one backend endpoint that builds an `_msearch` body for same-index, read-only search bodies.
- Keep non-search GET APIs as-is.
- Frontend consumes one combined response and renders the same cards.

### Effect on the app

- No visible functionality change.
- Fewer network round trips.
- Query metadata display needs to show multiple bodies in one response.
- Error handling becomes slightly more complex because `_msearch` returns per-response errors.

### Code estimate

| File | Estimate | Work |
|---|---:|---|
| `backend/routes.py` | +40-70 lines | New batch endpoint and envelope |
| `frontend/app.js` | +25-45 lines | Replace `Promise.all` groups |
| tests | +20-35 lines | Success and partial-error tests |

Total: **~85-150 lines**.

### Verification

- Existing dashboard cards render identically.
- One failing sub-search does not hide successful cards.
- No write operations appear in the batch.

## 8. Wire or remove unused `request_timeout_seconds`

### Why

`backend/config.py:32` defines `request_timeout_seconds: float = 20`, but it is not used. The actual ES timeout is `es_timeout_seconds: float = 15`.

### Before

- Two timeout settings exist.
- Only one is effective.
- Future maintainers may change the wrong value.

### After

Either:

- Remove `request_timeout_seconds`, or
- Use it as the middleware/API-level timeout and document the relationship to `es_timeout_seconds`.

### Effect on the app

- No visual functionality change.
- Configuration becomes clearer.

### Code estimate

- **~5-15 lines** across `backend/config.py`, `backend/main.py`, and docs.

### Verification

- `.env` examples match the final settings.
- Timeout error responses remain `504`.

## 9. Move application caches to Redis

### Why

The guide recommends Redis for short-TTL hot-query caching. Current caches are Python dictionaries in `backend/routes.py`.

### Before

- Cache is lost on restart.
- Each worker has a separate cache.
- Address scan can repeat per worker.

### After

- Add an optional Redis-backed cache with TTL.
- Keep in-memory fallback for local development.
- Cache boundary search batches and address index data.

### Effect on the app

- Consistent cache across workers/restarts.
- Requires Redis service, credentials, and deployment changes.
- Adds a failure mode when Redis is unavailable.

### Code estimate

| Area | Estimate |
|---|---:|
| Backend cache abstraction | +50-90 lines |
| Config and dependency wiring | +20-40 lines |
| Route changes | +30-60 lines |
| Tests with fake Redis | +30-50 lines |
| Deployment/docs | +20-40 lines |

Total: **~120-220 lines + deployment**.

Recommendation: **defer**. The dataset is one 17k-document index and the app currently runs as one process. This adds operational complexity without a measured need.

## Explicitly excluded from this plan

These guide items are not proposed because they require index writes, reindexing, hardware changes, or cluster administration outside the read-only app scope:

| Excluded item | Guide section | Reason |
|---|---|---|
| Shard count and replica layout | 1 | Cluster/index administration |
| Dedicated master/coordinating nodes | 1 | Infrastructure |
| SSD/NVMe, heap, swap, filesystem cache | 2 | Hardware/JVM |
| `copy_to`, `index_prefixes`, `edge_ngram`, `search_as_you_type` | 3/4 | Mapping changes and reindex |
| `projectId` as `keyword` instead of `long` | 4 | Mapping change |
| `dynamic: strict`, `index: false`, `doc_values: false`, `norms: false` | 4 | Mapping change |
| `index.sort`, `index_phrases`, eager global ordinals | 4 | Index settings/mapping |
| Force-merge and refresh interval changes | 4/8 | Index writes/settings |
| Search slow log settings | 6 | Index settings |
| Data streams and ILM rollover | 8 | Index lifecycle, not applicable to static data |

## Recommended implementation order

1. Implement #8, #1, #2, #4, and #5 together. They are low-risk, mostly additive, and do not change ranking.
2. Measure baseline and post-change values using `query_used.wall_ms`, `query_used.es_took_ms`, rerank metadata, and Ops metrics.
3. Implement #3 only if runaway or partial-query handling is needed.
4. Implement #6 only if profiling shows scored clauses dominate latency.
5. Treat #7 as a round-trip optimization, not a query-speed fix.
6. Do not implement #9 until the app is deployed with multiple workers or cache consistency becomes a real problem.

## Acceptance checks

- `make check`
- `.venv\Scripts\python.exe -m pytest -q`
- Browser QA for:
  - first search after startup,
  - `q=shivalik residency`,
  - boundary nearby flow,
  - Ops tab,
  - guarded console,
  - mobile layout.
- No app code may perform write operations against Elasticsearch.

## Implementation status

- Implemented #8: removed unused `request_timeout_seconds`; `es_timeout_seconds` remains the ES timeout source.
- Implemented #1: startup background warm-up, `rerank_address` query parameter, cache status/age metadata, and UI selector.
- Implemented #2: project and boundary searches use `track_total_hits: 10000`; UI renders `10,000+`. Quality aggregation keeps exact hits because its percentages need the full denominator.
- Implemented #4: guarded console accepts boolean `profile`; profile timings are shown in the result panel.
- Implemented #5: Ops nodes expose search queue/rejections and query/request cache metrics.
- Deferred: #3, #6, #7, #9.
