# ES RERA Explorer - Project Context

This document is the single source of truth for a small learning project that
turns one real Elasticsearch index, `gujrat_rera_data`, into one read-only web
application.

Use it as context: paste this file into an AI assistant or hand it to a
developer, then implement the screens and endpoints in the order given in
"Build checklist". The document contains the exact Elasticsearch Query DSL for
every feature, plus the observed live values of this index, so no guesswork is
needed.

The app is intentionally scoped to one index. Other RERA-related indices exist
on the cluster but are out of scope for version 1.

## Decisions

| Decision | Value |
|---|---|
| Backend | Python, FastAPI, `AsyncElasticsearch` (elasticsearch-py **8.19.x**) |
| Frontend | One HTML page, plain JavaScript and CSS, Chart.js from a CDN |
| Elasticsearch | Remotely hosted at `http://192.168.1.14:9200`; only the URL is required |
| Index | `gujrat_rera_data` (17,271 docs, 279.1 MB, 1 shard + 1 replica) |
| Auth | None (plain HTTP). Optional API key/basic auth is documented but unused |
| Mode | Read-only. No index, document, template, or ILM mutations |
| Scope | Single index, 10 active tabs. Boundary map reads `_source` rings read-only; no indexed geo fields |
| Complexity | Learning project: no build step, no database, no login, no Docker required |

Observed cluster facts (verify live at runtime, never hard-code counts):

| Fact | Observed value |
|---|---|
| Cluster | `elasticsearch`, node `rajiv-omen`, **single node** |
| Status | **yellow** - 36 unassigned shards, 69 active primary shards |
| Version | **8.19.23** (Lucene 9.12.2) |
| Index health | `gujrat_rera_data` is yellow (its one replica cannot be allocated) |
| Docs | 17,271 |
| Store size | 279.1 MB |
| Shards | 1 primary, 1 replica |

## 1. What to build

A single-page explorer with a tab per area:

1. Dashboard
2. Projects
3. Project Detail
4. Analytics
5. Data Quality
6. Pagination and Export
7. Mapping and Indices
8. Ops
9. Console
10. Map / Boundaries

Current release has 10 active tabs. `Map / Boundaries` is a read-only geometry
lab using `Project Profile.Map Location` from `_source`; native ES geo DSL is
not available because the index has no geo fields.

Each tab calls the FastAPI backend, which runs one or more optimized
Elasticsearch queries and returns a consistent JSON envelope. The UI shows a
table or chart, the server-side `took` time, the local wall-clock time, and a
collapsible "Query used" panel so the practical lesson is visible.

The app does not create indices or sample data. It reads `gujrat_rera_data`
only. If the index is missing, or a field needed by a screen is absent, the
feature reports `available: false` instead of failing the whole page.

The three things the user cares about most:

- **Search** by `project_name` (also `promoter_name` and `reg_no`), with
  highlighting and prefix suggestions.
- **Filters** on `district`, `taluka`, `project_type`, `project_status`,
  `price`, dates, and scrape status.
- **Project Detail** showing the five large non-indexed objects, including
  `Project Profile`, as readable section cards.

## 2. Non-negotiable constraints

- Read-only: only `GET`, `_search`, `_count`, `_msearch`, `_field_caps`,
  `_mapping`, `_settings`, `_stats`, `_segments`, `_cat`, `_analyze`,
  `_explain`, `_profile`, `_ilm/explain`, and `_ingest/pipeline/_simulate` are
  allowed.
- `POST /{index}/_pit` and `DELETE /_pit` are allowed as a narrow exception:
  they create and close a search context only, never documents or index state.
  Always close a PIT in a `finally` block.
- Never log or return credentials. The config endpoint exposes only the host.
- Every endpoint validates and caps `size` (maximum 100) and uses a request
  timeout. `from + size > 10000` is rejected with `invalid_request`.
- Use `bool.filter` for exact/range constraints and `must` only for relevance.
- Use `_source` includes. List/search endpoints must never return the five
  disabled objects (about 17 KB per document); only the detail endpoint loads
  them.
- Keep the code small: one FastAPI app, one query module, one HTML page.
- Timings shown in the UI must be labeled as local wall-clock timings; the
  server `took` value is separate.
- `price` is a `keyword`. Never issue numeric `range` queries against it and
  never sort it as a number. Use `term`, `prefix`, and `terms` only.
- Dates in `start_date` and `end_date` use `dd-MM-yyyy`. Convert UI date inputs
  or pass `"format": "dd-MM-yyyy"` in every range query.
- No scripts, `script_fields`, `runtime_mappings`, `regexp`, or leading
  `wildcard` in any interactive path.
- `ALLOW_WRITES=false` at all times. There are no hidden write endpoints.

## 3. Configuration and connection

### Environment variables

```dotenv
ES_URL=http://192.168.1.14:9200
ES_TIMEOUT_SECONDS=15
ES_MAX_CONNECTIONS=20

# Optional, unused in the default no-auth setup
ES_USERNAME=
ES_PASSWORD=
ES_API_KEY=
ES_VERIFY_CERTS=true

# The single index this app reads
INDEX_RERA=gujrat_rera_data

# Optional: only used by the pipeline-simulation panel
PIPELINE_ID=gujrat_normalize_pipeline

# Always false for this project
ALLOW_WRITES=false
```

### Client

Create one `AsyncElasticsearch` instance at startup and close it on shutdown.
Do not create a client per request. The client major version must match the
server major version: server is 8.19.23, so pin `elasticsearch>=8.19,<9`.

```python
from elasticsearch import AsyncElasticsearch

client = AsyncElasticsearch(
    hosts=[settings.es_url],
    request_timeout=settings.es_timeout_seconds,
    max_connections=settings.es_max_connections,
)
```

Use typed keyword arguments on every call (`index=`, `query=`, `aggs=`,
`size=`, `_source=`, ...). The `body=` keyword was removed in elasticsearch-py
9 and should be avoided in 8 as well.

Connection test: `GET /` and `GET /_cluster/health`.

### Startup index discovery

Call:

```text
GET /_cat/indices?format=json&h=index,health,status,docs.count,store.size,pri,rep
GET /gujrat_rera_data/_mapping
GET /gujrat_rera_data/_field_caps?fields=*
```

Cache:

- whether `gujrat_rera_data` exists,
- its live document count, health, store size, and shard counts,
- its mapping and field-caps result.

The mapping is required because five objects are `enabled: false`: their
subsections exist in `_source` but not in `_field_caps`. Capability detection
must read the mapping for display-only sections and field caps for queryable
fields. The frontend disables a feature when its required field is absent.

### Standard response envelope

Success:

```json
{
  "data": {},
  "meta": {
    "index": "gujrat_rera_data",
    "total": 17271,
    "returned": 20,
    "es_took_ms": 12,
    "wall_ms": 18.4,
    "query_used": {}
  }
}
```

Error:

```json
{
  "error": {
    "code": "es_unavailable",
    "message": "Elasticsearch request failed",
    "detail": "Connection refused"
  }
}
```

Error codes: `es_unavailable`, `index_missing`, `field_missing`,
`invalid_request`, `not_found`, `forbidden`, `timeout`, `es_error`,
`pipeline_missing`.

`GET /api/health` is the one documented exception: it returns its own flat
shape, not the envelope, so a dashboard can render before discovery finishes.

### Capability matrix

Computed at startup from `_mapping` and `_field_caps`:

| Capability | Detected via | Enables |
|---|---|---|
| `project_name` text + `.keyword` | field caps | full-text search, exact filter, sort, agg |
| `promoter_name` text + `.keyword` | field caps | search, exact filter, facet |
| `district`, `taluka`, `project_type`, `project_status` keyword | field caps | filters and facets |
| `price` keyword | field caps | term/prefix filter, top-terms facet only |
| `start_date`, `end_date` date | field caps | range filter, date histogram |
| `scrape_status.*` | field caps | scrape filters, stats |
| five `enabled:false` objects | mapping | detail-view section cards only |
| single-node yellow cluster | `_cluster/health` | yellow/replica explanation in Ops |

## 4. Index catalog

Counts below are the values observed on 2026-11-20. The app must display live
counts, not these numbers.

| Index | Docs | Store | Shards | Purpose in the app |
|---|---:|---:|---|---|
| `gujrat_rera_data` | 17,271 | 279.1 MB | 1 primary / 1 replica | Every screen in the app |

### Field reference - indexed and queryable

| Field | Type | Notes |
|---|---|---|
| `projectId` | `long` | Unique ID, also the document `_id` (as a string). Sort key and pagination cursor |
| `project_name` | `text` + `project_name.keyword` | Full-text search, highlight, suggestions, exact match, terms agg, sort |
| `promoter_name` | `text` + `promoter_name.keyword` | Full-text search, exact filter, top-promoter facet |
| `district` | `keyword` | Term filter and terms aggregation |
| `taluka` | `keyword` | Term filter and terms aggregation |
| `project_type` | `keyword` | Term filter and terms aggregation |
| `project_status` | `keyword` | Term filter and terms aggregation |
| `reg_no` | `keyword` | Exact registration-number lookup |
| `price` | `keyword` | Human-readable string, e.g. `"1.67 Crore Onwards"`. Term/prefix only; 6 docs missing |
| `start_date` | `date`, format `dd-MM-yyyy`, `ignore_malformed=true` | Date range and histogram |
| `end_date` | `date`, format `dd-MM-yyyy`, `ignore_malformed=true` | Date range and histogram |
| `page_url` | `keyword` | Exact value, rendered as a source link |
| `scrape_status.complete` | `boolean` | Filter. True for all 17,271 docs |
| `scrape_status.docs_downloaded` | `boolean` | Filter. True for only 5 docs |
| `scrape_status.documents` | `integer` | Range filter, stats/sum aggregation (min 24, max 1,134, avg 77.5) |
| `scrape_status.errors` | `text` | Match query; array of strings in `_source` |
| `scrape_status.scraped_at` | `date`, format `yyyy-MM-dd HH:mm:ss` | Range and histogram |

The mapping has `"dynamic": "false"`. Any field not in the table above is
stored in `_source` but is **not indexed**. Do not search, filter, sort, or
aggregate on unknown fields.

### Boundary ring data (`Project Profile.Map Location`)

The mapping has no `geo_point` or `geo_shape`. The read-only app therefore does
not use ES geo DSL; it renders boundary rings from `_source` and derives
centroids/bboxes in memory. Live source scan results:

| Property | Observed value |
|---|---:|
| Documents with `Map Location` | 17,271 |
| Usable rings (>=3 unique valid points) | 16,955 |
| Degenerate rings (<3 unique points) | 312 |
| Unparseable rings | 4 |
| Total points | 105,750 |
| Average / min / max points per ring | 6.2 / 3 / 149 |
| Explicitly closed rings | 516 |
| Rings with adjacent duplicate points | 439 |
| Ahmedabad usable rings | 5,305 |

The boundary endpoint may request only this path from disabled `Project
Profile`: `Project Profile.Map Location`. All other disabled objects remain
detail-only.

#### Approved follow-up: map search-to-centroid patch (planned)

This follow-up is `APPROVED_WITH_CONCERNS` from the 2026-11-24 office-hours pass.
It is a design contract only; the code is unchanged. The goal is one seamless
search-to-centroid flow: type a misspelled project name, focus the resolved
project boundary, then show nearby projects without losing the indexed filters.

Evidence already collected read-only:

- `shivalik recidency` returns 0 hits with the current strict query;
  `shivalik residency` returns 5 hits.
- Fuzzy `AUTO` alone returns 11 hits but misses the likely target `projectId`
  573 (`Shivalik Residences`).
- `match_phrase_prefix` on analyzed `project_name` with `shivalik resid`
  returns `projectId` 573 first.
- `project_name.keyword` exists and accepts `case_insensitive: true`; the prefix
  `resid` returns 64 hits with `projectId` 573 first.
- Ahmedabad has 5,390 scanned projects; a tight bbox can reduce visible matches
  to 41, which is why the default viewport filter must be removed.

Backend query contract, applied only when `q` is present:

```json
{
  "size": "<size>",
  "_source": ["projectId", "project_name", "district", "taluka", "project_type", "project_status", "reg_no", "page_url", "Project Profile.Map Location"],
  "sort": [{"_score": "desc"}, {"projectId": "asc"}],
  "query": {
    "bool": {
      "minimum_should_match": 1,
      "should": [
        {
          "multi_match": {
            "query": "<original q>",
            "fields": ["project_name^4", "promoter_name^3", "district^3", "taluka^2", "project_type^3", "reg_no^2", "page_url^1"],
            "type": "cross_fields",
            "operator": "or",
            "minimum_should_match": "<current token rule>",
            "lenient": true,
            "boost": 10
          }
        },
        {
          "bool": {
            "boost": 1,
            "minimum_should_match": 1,
            "should": [
              {"match": {"project_name": {"query": "<normalized q>", "operator": "and", "boost": 4}}},
              {"match_phrase_prefix": {"project_name": {"query": "<phrase prefix>", "boost": 3}}},
              {"match": {"project_name": {"query": "<original q>", "fuzziness": "AUTO", "prefix_length": 1, "max_expansions": 25, "operator": "and", "boost": 1}}}
            ]
          }
        }
      ]
    }
  }
}
```

Normalization keeps the original text for fuzzy matching, lowercases and strips
punctuation for exact matching, maps `recidency`, `recidancy`, `recidence`, and
`recidance` to `residency`, and derives the phrase prefix from the normalized
project-name phrase (for example `shivalik recidency` -> `shivalik resid`).
The exact token rule, typo map, and phrase-prefix derivation still need to be
frozen in tests before implementation.

Response and pagination contract:

- `size` and `after` remain per-page scan controls; `MAX_BOUNDARY_SIZE = 10000`.
- Route default is `size = 1000`; UI supplies `2000`; the loader fetches up to
  20 pages.
- With `q`, use `_score` desc then `projectId` asc and a `[score, projectId]`
  cursor; expose `score` on features, markers, and response meta.
- Without `q`, keep the existing `projectId` sort and cursor unchanged.
- `total` means ES total hits; `loaded` means accumulated boundary features plus
  markers before geometry filtering; `returned` means the current response after
  geometry filtering; `complete` is true at the ES end and false if maxPages
  stops early.
- Add `distance_km` with `haversine_km` whenever `lat`, `lon`, and
  `distance_km` are present.
- Show a truncation warning when `complete=false` or visible rows exceed 250.

Frontend contract:

- `Use current view` is unchecked by default. `collectBoundaryParams()` includes
  `bbox` only when `#b-use-view` is checked and `lastBounds` is valid.
- Unchecking clears `#b-bbox` and `lastBounds`; `moveend` no longer triggers a
  load; **Load Boundaries** computes a fresh bbox only when the checkbox is
  checked. If bounds are unavailable, show `Map bounds unavailable. Uncheck
  current view or retry after the map loads.`
- Auto-focus the first `q` result with a usable center with a distinct circle
  marker, highlighted row, `focusBoundary()`, `focusMarker.openPopup()`, and zoom
  14. A row click overrides focus; no usable center shows `Selected project has
  no usable centroid.`
- **Show nearby** is disabled without focus. It pins the focused project, sets
  `nearbyMode = true`, clears `q`, unchecks `#b-use-view`, clears `#b-bbox`, fills
  `lat` / `lon` from the focus center, sets `distance_km = 2`, and keeps
  district / taluka / project type / status / registration number filters.
- The pinned row is first, labelled `Pinned`, with distance `0.0`; other rows are
  sorted by `distance_km` rounded to one decimal; the pinned row remains even
  when no nearby rows are returned.
- Row click re-centers nearby mode; a non-empty `q` submit exits nearby mode and
  clears pinned state plus `lat` / `lon` / `distance_km`; Reset exits nearby
  mode; missing radius inputs show `Radius requires latitude, longitude, and a
  positive distance.`
- Popup action text is `Open project detail`; it calls the existing
  `openDetail(id)` and opens the Project detail tab.
- Bump static asset cache busting from `?v=5` to `?v=6` in `index.html`.

Open implementation contracts to freeze before coding:

- Exact token rule, typo map, and phrase-prefix derivation.
- Exact radius filter contract and pinned-row injection/count behavior.

### Field reference - display-only objects (`enabled: false`)

These are never indexed. They are fetched by the detail endpoint and rendered
as section cards; `Project Profile.Map Location` is additionally fetched by the
boundary endpoint through a strict `_source` allowlist. Requesting a
query/filter on any disabled field must return `field_missing` with a hint that
a mapping change plus reindex would be required.

| Object | Subsections (observed) | Approx. size |
|---|---|---:|
| `Project Profile` | Project Overview, Certificates, Collection Bank Details, About Property, Project Documents, Associated Vendor - Certificate Details, Annual Compliance, Common Amenities, Distance From Project, Map Location, Other Important Documents | 10.6 KB |
| `Project Summary` | Project Details, Common Amenities, Type Details, Promoter Details, Collection Bank Details, Compliance, Construction Booking Status, Status, Draft AFS | 2.1 KB |
| `Promoters` | Promoter Details, Directors, Signatory Details, Group/ Parent Entity, Project Professionals | 2.5 KB |
| `Progress & RERA Actions` | Form-8, Block Progress, Project Progress, Block Booking Status, Blockwise Photos, Block Booking Details, P-E Compliance, Building Use Permission Details/Occupation Certificate Details (BU), Complaint, Penalty(Rs), Progress Status, QPR Compliance, Form5 Compliance, Notifications | 1.3 KB |
| `More Projects by The Same Developer` | Array of `{Project Name, Taluka, District, Reg No., Status}` | 0.6 KB |

`Project Profile.Map Location` is an array of `{lat, lng}` strings forming a
project boundary ring. It is not a `geo_point` and cannot be queried with ES geo
DSL; the detail view may still use its first valid point for a static map link,
while the `Map / Boundaries` tab renders the whole ring as a polygon. Rings are
auto-closed for display, and rings with fewer than three unique valid points are
shown as centroid markers with a warning count. Document URLs elsewhere in
these objects are external URLs and must be rendered as sanitized `https` links
only.

### Observed live facet values

Use these to design labels and demo data, but always read live values from
aggregations.

- **district** (35 buckets, dirty variants included): Ahmedabad 5,389; Vadodara
  2,893; Surat 2,595; Rajkot 1,848; Gandhinagar 1,650; Bhavnagar 727; Valsad
  396; Anand 312; Junagadh 244; Jamnagar 218; plus `RAJKOT` 29, `VADODARA` 4,
  `SURAT` 3, `AHmedabad` 1, `SabarA?Kantha` 18, `Chhota udepur` 2.
- **taluka**: Ahmedabad City 4,270; Vadodara 2,732; Rajkot 1,812; Surat City
  1,768; Gandhinagar 1,423; Daskroi 837; plus `Choryasi` 336 and `Chorasi` 225.
- **project_type**: Residential/Group Housing 7,746; Mixed Development 5,907;
  Commercial 2,495; Plotted Development 1,123.
- **project_status**: New 14,081; Ongoing 3,151; Completed 39.
- **price**: `"10.00 Lakh Onwards"` 419; `"15.00 Lakh Onwards"` 354;
  `"20.00 Lakh Onwards"` 336; `"0 Onwards"` 310; 13,250 other distinct values.
- **scrape_status**: complete=true 17,271; docs_downloaded=true 5;
  documents min 24 / max 1,134 / avg 77.5 / sum 1,338,533.
- **start_date years**: 2005 through 2027, peaking 2019-2024.

Example documents (core fields only, other fields omitted):

```json
{
  "_id": "573",
  "_source": {
    "projectId": 573,
    "page_url": "https://gujrera.gujarat.gov.in/#/project-preview?id=NTcz",
    "project_name": "Shivalik Residences",
    "reg_no": "PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA00645/091117",
    "district": "Ahmedabad",
    "taluka": "Ahmedabad City",
    "promoter_name": "SHIVALIK DEVELOPERS PRIVATE LIMITED",
    "project_type": "Residential/Group Housing",
    "project_status": "Ongoing",
    "start_date": "16-01-2015",
    "end_date": "30-10-2018",
    "price": "1.67 Crore Onwards",
    "scrape_status": {
      "complete": true,
      "docs_downloaded": false,
      "scraped_at": "2026-10-14 13:29:45",
      "documents": 54,
      "errors": []
    }
  }
}
```

```json
{
  "_id": "576",
  "_source": {
    "projectId": 576,
    "project_name": "SHREE RANG PEARL",
    "district": "Gandhinagar",
    "taluka": "Gandhinagar",
    "project_type": "Mixed Development",
    "project_status": "Ongoing",
    "start_date": "21-04-2017",
    "end_date": "20-04-2020",
    "price": "12.30 Lakh Onwards"
  }
}
```

## 5. Read-only task map

Every practical concept must appear somewhere in the product. Tasks that
require writes are documented, not exposed.

| Practical | Task | How the app covers it |
|---|---|---|
| P1 | Docker, cluster, Kibana | Documented; Dashboard/Ops show health and version |
| P2 | Create index, index docs, update, delete, bulk | Documented as reference; UI reads by ID and searches |
| P3 | Explicit/dynamic mapping, text vs keyword, conflicts | Mapping tab, `dynamic:false` explanation, `_analyze` comparison |
| P4 | Query DSL (basic, range, full-text, fuzzy, pagination, highlight) | Projects search presets with highlight on `project_name` |
| P5 | `bool`, `must`/`filter`/`should`, boost | Projects search and rank mode with scrape-status filters |
| P6 | Analyzers, synonyms, autocomplete, fragments, normalizer | Analyzer panel + `match_phrase_prefix` suggestions; true synonyms/ngram require reindex, documented |
| P7 | BM25, explain, boosts, function_score, profile | Rank mode, `_explain` panel, optional `_profile` |
| P8 | Bucket/metric aggregations | Analytics tab with charts and totals |
| P9 | Cleaning, mapping, bulk, failures, reindex, pipeline, CLI | Data Quality tab: missing fields, casing collisions, malformed dates; `_simulate` only if a pipeline exists |
| P10 | from/size, search_after, PIT, scroll, scan, CSV | Pagination tab with cursor paging and streaming export |
| P11 | Templates, aliases, reindex, shards, refresh, ILM, rollover | Mapping/Indices tab: stats, mappings, aliases, single-shard/replica yellow-cluster lesson; changes documented only |
| P12 | geo_point / geo_shape queries | **Partial**: read-only boundary map with bbox/radius/polygon geometry; native ES geo DSL unavailable without index writes |
| P13 | Security, users, roles, API keys, stats, slow logs, snapshot, restore, unassigned shard, indexing failure | Ops tab: health/nodes/shards, unassigned-replica explanation; admin tasks documented as a runbook |

Read-only substitutes:

- P2 CRUD becomes "read by ID + search"; the lifecycle is explained in the UI.
- P9 ingestion becomes aggregation-based quality checks plus optional
  `POST /_ingest/pipeline/{id}/_simulate` (does not index). Missing pipeline
  returns `pipeline_missing` with a hint.
- P11 reindex/rollover/ILM changes are explained; only GET APIs are called.
- P13 user/role/API-key/snapshot actions are documented, not called.

## 6. API specification

All routes are under `/api`. All return the envelope from section 3 unless
noted. Common query parameters: `size` (default 20, maximum 100), `page`
(1-based), `sort` (field or `field:asc|desc`).

### 6.1 Dashboard and discovery

#### `GET /api/health`

```json
{
  "cluster": {"name": "rajiv-omen", "status": "yellow", "nodes": 1},
  "version": "8.19.23",
  "indices": [
    {
      "index": "gujrat_rera_data",
      "configured": true,
      "health": "yellow",
      "docs": 17271,
      "store": "279.1mb",
      "pri": "1",
      "rep": "1"
    }
  ],
  "missing": []
}
```

ES calls:

```text
GET /
GET /_cluster/health
GET /_cat/indices?format=json&h=index,health,status,docs.count,store.size,pri,rep
```

#### `GET /api/indices`

Returns the live `_cat/indices` row for the configured index plus the
configured feature-to-index mapping.

#### `GET /api/indices/{index}/mapping`

```text
GET /{index}/_mapping
```

Returns the mapping and a flattened list of fields with their types. Flags the
five `enabled:false` objects as `indexed: false`.

#### `GET /api/indices/{index}/stats`

```text
GET /{index}/_stats
GET /{index}/_segments
```

Returns docs, store bytes, segment count, and search/indexing totals.

#### `GET /api/indices/{index}/aliases`

```text
GET /_cat/aliases?format=json&h=alias,index
```

Filter client-side to the requested index. This index currently has no
aliases.

### 6.2 Projects

#### `GET /api/projects/search`

Parameters: `q`, `district`, `taluka`, `project_type`, `project_status`,
`promoter`, `reg_no`, `price`, `price_prefix`, `start_from`, `start_to`,
`end_from`, `end_to`, `min_documents`, `max_documents`, `scrape_complete`,
`docs_downloaded`, `sort`, `page`, `size`.

Optimized query (all filters shown for illustration; omit any whose parameter
is empty):

```json
{
  "size": 20,
  "from": 0,
  "track_total_hits": true,
  "_source": [
    "projectId", "project_name", "promoter_name", "district", "taluka",
    "project_type", "project_status", "price", "reg_no",
    "start_date", "end_date", "page_url", "scrape_status"
  ],
  "query": {
    "bool": {
      "filter": [
        {"term": {"district": "Ahmedabad"}},
        {"term": {"taluka": "Ahmedabad City"}},
        {"term": {"project_type": "Residential/Group Housing"}},
        {"term": {"project_status": "Ongoing"}},
        {"term": {"promoter_name.keyword": "SOHAM INFRASTRUCTURE"}},
        {"term": {"reg_no": "PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA00600/EX1/300719"}},
        {"term": {"price": "20.97 Lakh Onwards"}},
        {"prefix": {"price": "20.9"}},
        {"range": {"start_date": {"gte": "01-01-2015", "lte": "31-12-2025", "format": "dd-MM-yyyy"}}},
        {"range": {"end_date": {"gte": "01-01-2018", "format": "dd-MM-yyyy"}}},
        {"range": {"scrape_status.documents": {"gte": 20, "lte": 2000}}},
        {"term": {"scrape_status.complete": true}},
        {"term": {"scrape_status.docs_downloaded": false}}
      ],
      "must": [
        {"multi_match": {"query": "residency", "fields": ["project_name^3", "promoter_name^1"], "type": "best_fields"}}
      ]
    }
  },
  "sort": [{"projectId": "asc"}],
  "highlight": {
        "pre_tags": ["[[HL]]"], "post_tags": ["[[/HL]]"],
    "fields": {"project_name": {}, "promoter_name": {}}
  }
}
```

Rules:

- Omit any filter whose parameter is empty.
- Omit `must` entirely when `q` is empty; this keeps the request a pure cached
  filter.
- `price` supports only `term` (exact dropdown value) and `prefix` (user-typed
  text such as `"10.00"`). Never use `range` or numeric sort on it.
- `promoter` uses `term` on `promoter_name.keyword` for exact matching. Use
  `match` on `promoter_name` only when `q` is intended as full text.
- All UI date inputs are `yyyy-MM-dd`; convert them to `dd-MM-yyyy` in the
  backend, or send `"format": "dd-MM-yyyy"` as shown.
- Highlight values are escaped by the frontend before insertion into the DOM.
  The frontend converts `[[HL]]` / `[[/HL]]` sentinels into safe `<mark>` text
  nodes; never inject raw Elasticsearch highlight HTML.
- Text-field matching is analyzer case-insensitive. Keyword `term` and `prefix`
  clauses use `case_insensitive: true` so `plot` matches `Plot`, `PLOT`, and
  `PLot`, and prefix filters can match `Plotted Development`.
- Always add the unique `projectId` tie-breaker to the sort.
- Allowed sort fields: `projectId`, `project_name.keyword`,
  `promoter_name.keyword`, `district`, `project_status`, `project_type`,
  `start_date`, `end_date`, `scrape_status.documents`. Reject anything else
  with `invalid_request`.
- Observed check: `q=residency`, `district=Ahmedabad`,
  `project_status=Ongoing` returns 96 hits.

#### `GET /api/projects/boundaries`

Read-only boundary-map endpoint; register it before `/projects/{project_id}`.

Parameters: common indexed filters (`q`, `district`, `taluka`,
`project_type`, `project_status`, `promoter`, `reg_no`), `bbox`
(`minLng,minLat,maxLng,maxLat`), radius (`lat`, `lon`, `distance_km`),
`polygon` (`lat,lng;lat,lng;...`), `size` (default 1000, max 10000), and `after`
(the last `projectId` for batching). bbox/radius/polygon filters are applied in
Python after `_source` parsing; they are never inserted into ES DSL.

The ES body uses only indexed filters plus:

```json
{"size": 1000, "_source": ["projectId", "project_name", "district", "taluka", "project_type", "project_status", "reg_no", "page_url", "Project Profile.Map Location"], "sort": [{"projectId": "asc"}]}
```

The standard `{data, meta}` envelope returns compact `features` with `ring`,
`centroid`, and `bbox`, plus `markers` for degenerate rings, `skipped` counts,
and `meta.boundary_filter` / `meta.cache_hit` / `meta.geo_note`. No ES geo DSL,
scripts, runtime fields, or index writes are used.

The approved search-to-centroid patch described in section 2 changes the `q`
branch of this endpoint to typo-tolerant score-ranked matching with a
`[score, projectId]` cursor, adds `score` and optional `distance_km` fields, and
keeps bbox/radius/polygon geometry filtering in Python. Until that patch is
implemented, the body above remains the current contract.

#### `GET /api/projects/{project_id}`

```text
GET /gujrat_rera_data/_doc/{project_id}
```

Because `_id == projectId` as a string, this is the cheapest lookup. If it
returns 404, fall back to:

```json
{"size": 1, "query": {"term": {"projectId": 573}}}
```

Return the full `_source` including the five disabled objects, plus a
`data.sections` object that extracts each object for the section-card UI:

```json
{
  "data": {
    "project": {"projectId": 573, "project_name": "Shivalik Residences"},
    "sections": {
      "Project Profile": {
        "indexed": false,
        "subsections": ["Project Overview", "Certificates", "About Property"]
      },
      "Project Summary": {"indexed": false, "subsections": ["Project Details"]}
    }
  }
}
```

Return 404 with `not_found` when missing.

#### `GET /api/projects/suggest`

Parameters: `q` (minimum 2 characters), `size` (default 8, maximum 20).

No dedicated autocomplete sub-field exists in this mapping, so use
`match_phrase_prefix` on `project_name`:

```json
{
  "size": 8,
  "_source": ["projectId", "project_name", "district", "project_type"],
  "query": {
    "match_phrase_prefix": {
      "project_name": {"query": "shiva", "max_expansions": 20}
    }
  },
  "sort": [{"project_name.keyword": "asc"}]
}
```

Debounce in the frontend at 300 ms. Do not call `_analyze` per keystroke.

#### `GET /api/projects/facets`

```json
{
  "size": 0,
  "track_total_hits": false,
  "aggs": {
    "districts": {"terms": {"field": "district", "size": 100}},
    "talukas": {"terms": {"field": "taluka", "size": 50}},
    "project_types": {"terms": {"field": "project_type", "size": 20}},
    "project_statuses": {"terms": {"field": "project_status", "size": 20}},
    "promoters": {"terms": {"field": "promoter_name.keyword", "size": 20}},
    "prices": {"terms": {"field": "price", "size": 15}},
    "scrape_complete": {"terms": {"field": "scrape_status.complete", "size": 2}},
    "docs_downloaded": {"terms": {"field": "scrape_status.docs_downloaded", "size": 2}},
    "documents_stats": {"stats": {"field": "scrape_status.documents"}}
  }
}
```

`districts` uses size 100 so the Data Quality tab can detect casing variants;
the Projects tab shows only the top 20. `prices` must stay at 15 because there
are 13,250+ distinct values.

### 6.3 Analytics

#### `GET /api/analytics/overview`

```json
{
  "size": 0,
  "track_total_hits": false,
  "aggs": {
    "districts": {"terms": {"field": "district", "size": 20}},
    "talukas": {"terms": {"field": "taluka", "size": 20}},
    "project_types": {"terms": {"field": "project_type", "size": 20}},
    "project_statuses": {"terms": {"field": "project_status", "size": 20}},
    "top_promoters": {"terms": {"field": "promoter_name.keyword", "size": 10}},
    "documents_stats": {"stats": {"field": "scrape_status.documents"}},
    "docs_downloaded": {"terms": {"field": "scrape_status.docs_downloaded", "size": 2}}
  }
}
```

#### `GET /api/analytics/dates`

```json
{
  "size": 0,
  "track_total_hits": false,
  "aggs": {
    "start_years": {
      "date_histogram": {
        "field": "start_date",
        "calendar_interval": "year",
        "format": "yyyy",
        "min_doc_count": 1
      }
    },
    "end_years": {
      "date_histogram": {
        "field": "end_date",
        "calendar_interval": "year",
        "format": "yyyy",
        "min_doc_count": 1
      }
    }
  }
}
```

Observed `start_years` range is 2005-2027. Use `min_doc_count: 1` to avoid
sparse empty buckets.

### 6.4 Data quality

#### `GET /api/quality/scrape`

```json
{
  "size": 0,
  "track_total_hits": true,
  "aggs": {
    "missing_price": {"missing": {"field": "price"}},
    "missing_district": {"missing": {"field": "district"}},
    "missing_taluka": {"missing": {"field": "taluka"}},
    "missing_start_date": {"missing": {"field": "start_date"}},
    "missing_end_date": {"missing": {"field": "end_date"}},
    "missing_promoter": {"missing": {"field": "promoter_name.keyword"}},
    "missing_reg_no": {"missing": {"field": "reg_no"}},
    "with_errors": {"filter": {"exists": {"field": "scrape_status.errors"}}},
    "docs_downloaded": {"terms": {"field": "scrape_status.docs_downloaded", "size": 2}},
    "documents_stats": {"stats": {"field": "scrape_status.documents"}},
    "districts": {"terms": {"field": "district", "size": 100}},
    "talukas": {"terms": {"field": "taluka", "size": 100}}
  }
}
```

The response adds a small "expected vs actual" panel and a **casing collision**
panel computed in Python from the `districts`/`talukas` buckets: group by
`key.strip().lower()` and list groups with more than one distinct raw key.
Expected findings include `Rajkot` vs `RAJKOT`, `Surat` vs `SURAT`, `Vadodara`
vs `VADODARA`, `Ahmedabad` vs `AHmedabad`, `Sabarkantha` vs `SabarA?Kantha`,
`Chhota Udaipur` vs `Chhota udepur`, and `Choryasi` vs `Chorasi`.

Observed: 6 docs missing `price`; 0 missing on all other core fields.

Because `start_date` and `end_date` use `ignore_malformed=true`, malformed
values are stored in `_source` but not indexed. They are therefore invisible
to `exists`/`missing` aggregations. The UI must explain this rather than claim
zero malformed dates. A bounded sample scan may be used as a teaching demo,
but never present it as a complete count.

#### `POST /api/quality/pipeline-simulate`

Body: one raw document. This does not index anything.

```text
POST /_ingest/pipeline/{pipeline_id}/_simulate
```

```json
{
  "docs": [
    {"_source": {"district": " ahmedabad ", "price": "1.67 Crore Onwards"}}
  ]
}
```

Default `pipeline_id` is `gujrat_normalize_pipeline`; allow an override via
`PIPELINE_ID`. If the pipeline is missing, return `pipeline_missing` with a
hint that pipelines are administrative setup and are intentionally not
created by this read-only app.

### 6.5 Pagination and export

#### `GET /api/projects/page`

Parameters: `page` (1-based), `size` (maximum 100).

```json
{
  "from": 20,
  "size": 10,
  "track_total_hits": false,
  "sort": [{"projectId": "asc"}],
  "_source": ["projectId", "project_name", "district", "project_type", "project_status", "price"],
  "query": {"match_all": {}}
}
```

Reject `from + size > 10000` with `invalid_request` and a message explaining
`max_result_window`. This index has 17,271 docs, so the lesson is real.

#### `GET /api/projects/search-after`

Parameters: `cursor` (the `sort` array of the last hit, encoded as JSON in a
query parameter), `size` (maximum 100), `pit` (boolean).

```json
{
  "size": 100,
  "track_total_hits": false,
  "sort": [{"projectId": "asc"}],
  "search_after": [573],
  "_source": ["projectId", "project_name", "district", "project_type", "project_status", "price"]
}
```

For a consistent deep session, support optional PIT mode:

```python
pit = await client.open_point_in_time(index=settings.index_rera, keep_alive="2m")
body = {
    "size": 100,
    "sort": [{"projectId": "asc"}],
    "pit": {"id": pit["id"], "keep_alive": "2m"},
    "search_after": cursor,
}
```

Always close the PIT in a `finally` block.

Return `next_cursor` (the last hit's sort values) and `has_more`.

#### `GET /api/projects/export`

Stream CSV with `elasticsearch.helpers.async_scan`, page size 1,000, bounded
memory, columns:

```text
projectId,project_name,reg_no,district,taluka,promoter_name,project_type,project_status,start_date,end_date,price,page_url
```

```python
from elasticsearch.helpers import async_scan

async def rows():
    async for hit in async_scan(
        client,
        index=settings.index_rera,
        query={"query": {"match_all": {}}},
        size=1000,
        source_includes=[
            "projectId", "project_name", "reg_no", "district", "taluka",
            "promoter_name", "project_type", "project_status",
            "start_date", "end_date", "price", "page_url",
        ],
        preserve_order=False,
    ):
        yield hit["_source"]

return StreamingResponse(rows(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=gujrat_rera_projects.csv"})
```

Add a `limit` parameter, capped at 100,000 (the index has 17,271 docs, so a
full export is possible). If `async_scan` is unavailable in the installed
client, fall back to manual `search_after` paging with `projectId`.

### 6.6 Analyzer tool

#### `POST /api/analyze`

Body: `{"text": "Shivalik Residences", "analyzer": "standard"}` or
`{"text": "...", "field": "project_name"}`.

```text
POST /_analyze
```

Use for the P3/P6 analyzer panels. Compare `standard` on `project_name` with
the `keyword` analyzer on `project_name.keyword`. Never call it per keystroke;
call it when the user presses "Analyze".

### 6.7 Ops

#### `GET /api/ops/health`

```text
GET /_cluster/health
```

#### `GET /api/ops/nodes`

```text
GET /_nodes/stats/os,process,jvm,indices,thread_pool
```

Return a small subset: name, roles, OS CPU/memory, process file descriptors,
JVM heap used/max/percent, GC counts, thread-pool queues, docs/store.

#### `GET /api/ops/shards`

```text
GET /_cat/shards?format=json&h=index,shard,prirep,state,docs,store,node
```

Highlight `UNASSIGNED` rows. Explain the common single-node cause: a replica
cannot be allocated on the only node, so a 1-primary/1-replica index such as
`gujrat_rera_data` is yellow and its replica is unassigned. This is expected,
not an application failure.

P13 tasks that are not exposed (documented in the UI as a runbook):

- create user/role, assign privileges, create API key
- change slow-log settings and read container logs
- create a snapshot repository, snapshot, restore
- reproduce indexing failures

### 6.8 Guarded query console

#### `POST /api/query/{index}`

Purpose: run a hand-written Query DSL body against the one allowed index for
learning. This is still read-only.

Allowed body keys:

```text
query, aggs, size, from, sort, _source, track_total_hits, collapse, highlight, post_filter
```

Reject:

- `script`, `script_fields`, `runtime_mappings`
- `size > 100`
- `from + size > 10000`
- any key not in the allow-list
- any index other than `gujrat_rera_data`

Use a 10-second timeout. Return `query_used` and both timings. Never accept a
target URL or index pattern.

## 7. Frontend specification

One HTML file, one CSS file, one JS file. No framework, no bundler.

### Layout

- Header: app name, `ES_URL` host (no credentials), cluster status pill.
- Top navigation: 10 active tabs; `Map / Boundaries` is the read-only geometry tab.
- Main panel per tab: controls, result table or chart, timing badge, and a
  `<details>` block labeled "Query used" containing the JSON request.
- Footer: "Read-only demo. Timings are local wall-clock."

### Tabs

1. **Dashboard** - cluster status, version, node count, the configured index
   with docs/health/store/shards, and a yellow-cluster explanation.
2. **Projects** - text input for `q`, selects for district/taluka/project_type/
   project_status, exact price select plus price-prefix input, start/end date
   ranges, document-count range, scrape toggles, sort, results table with
   highlighted `project_name`, and a facets sidebar.
3. **Project Detail** - opens from a row; shows core fields plus five section
   cards: Project Profile, Project Summary, Promoters, Progress & RERA Actions,
   More Projects by The Same Developer. Renders nested key/value tables,
   sanitized document links, and a map link from the first `Map Location`
   entry. Add a toggle to view the raw `_source` JSON.
4. **Analytics** - Chart.js bar charts for districts, project types, statuses,
   top promoters, and start-year histogram; cards for document stats and
   docs-downloaded counts.
5. **Data Quality** - cards for total docs, missing price (6), scrape flags,
   document stats; a casing-collision panel; a malformed-date explanation; and
   a pipeline-simulation form with a raw-document textarea.
6. **Pagination** - buttons "Page N (from/size)", "Next 100 (search_after)",
   "Open PIT session", "Export CSV"; show the returned cursor and timing
   comparison.
7. **Mapping and Indices** - mapping tree with indexed/not-indexed markers,
   stats, aliases, field caps, and the single-shard/replica explanation.
8. **Ops** - cluster health, node table, shard table with `UNASSIGNED`
   highlighting, and the static P13 runbook.
9. **Console** - index selector locked to `gujrat_rera_data`, DSL textarea,
   run button, results, and rejection messages for disallowed keys.

### Frontend rules

- Use `fetch` with `AbortController` and a 20-second timeout.
- Disable controls when the required field is unavailable; show the reason
  from `/api/health` and the capability matrix.
- Debounce only the suggest input (300 ms, minimum 2 characters).
- Render tables from JSON; do not hard-code row counts.
- Escape all text before inserting into the DOM. Allow only sanitized
  `http(s)` URLs for links and use `rel="noopener noreferrer"`.
- Keep charts to bar charts and simple cards; no dashboards with many panels.
- Show `es_took_ms` and `wall_ms` separately.

## 8. Backend structure

```text
ElasticSearch_project/
  PROJECT_CONTEXT.md
  README.md
  requirements.txt
  .env.example
  backend/
    __init__.py
    main.py
    config.py
    es_client.py
    schemas.py
    queries.py
    routes.py
  frontend/
    index.html
    app.js
    styles.css
```

- `config.py`: `pydantic-settings` model for the environment variables.
- `es_client.py`: singleton client, startup ping, index/capability discovery,
  shutdown close.
- `schemas.py`: Pydantic models for requests and the response envelope.
- `queries.py`: pure functions returning query bodies; no HTTP calls.
- `routes.py`: one `APIRouter` per feature or a single router with sections.
- `main.py`: app factory, lifespan, error handlers, static file mount,
  `GET /` returns `frontend/index.html`.

Error handling:

```python
from elasticsearch import ApiError, ConnectionError, NotFoundError

@app.exception_handler(ApiError)
async def api_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code if exc.status_code < 500 else 502,
        content={"error": {"code": "es_error", "message": str(exc), "detail": exc.body}},
    )
```

Map `403` to `forbidden`, `404` to `not_found`, connection errors to
`es_unavailable`, timeouts to `timeout`.

Pydantic settings example:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    es_url: str = "http://192.168.1.14:9200"
    es_timeout_seconds: float = 15
    es_max_connections: int = 20
    index_rera: str = "gujrat_rera_data"
    pipeline_id: str = "gujrat_normalize_pipeline"
    allow_writes: bool = False

    class Config:
        env_file = ".env"
```

`requirements.txt`:

```text
fastapi>=0.115
uvicorn[standard]>=0.30
elasticsearch>=8.19,<9
pydantic-settings>=2.4
```

Run:

```powershell
cd ElasticSearch_project
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

## 9. Query optimization checklist

Apply every item that fits the screen.

1. **Filter vs must.** Exact values, booleans, ranges, and dates go in
   `bool.filter` (cacheable, no scoring). Full-text relevance on `project_name`
   and `promoter_name` goes in `must`.
2. **Field types.** Use `term`/`terms`/`prefix` only on `keyword`, never on
   `text`. Use `.keyword` sub-fields for sort and aggregation.
3. **Source filtering.** List endpoints include only the 13 core fields. Never
   return the five disabled objects except in the detail endpoint.
4. **Size caps.** Maximum `size` is 100. Use `size: 0` for aggregation-only
   requests.
5. **Total hits.** Set `track_total_hits: false` for charts, exports, and deep
   scroll; enable it only when the UI shows an exact count.
6. **Pagination.** `from + size <= 10000`; use `search_after` on `projectId`
   for deeper results; use PIT + `search_after` for a stable session.
7. **Expensive clauses.** Avoid `script`, `regexp`, and leading `wildcard`.
   Prefer `prefix` on `price` and `match_phrase_prefix` on `project_name`.
8. **Aggregations.** Cap `terms.size` (price must be 15; promoters 20;
   districts 100 only for the quality panel). Use `min_doc_count: 1` on date
   histograms.
9. **DisplayName collisions.** Do not normalize district/taluka values inside
   queries; show raw buckets and a separate collision panel.
10. **One client.** Reuse the async client; set `max_connections` and a request
    timeout.
11. **Cache metadata.** Fetch mapping/field caps once at startup, not per
    request.
12. **Measure.** Return the server `took` and the local wall time. Never present
    local HTTP latency as Elasticsearch query time.
13. **Stable sorts.** Add the unique `projectId` tie-breaker to every paginated
    sort.
14. **No writes.** Keep `ALLOW_WRITES=false` and reject unknown body keys in
    the query console.

## 10. Build checklist

Do not start with the query console. Build the curated endpoints first.

1. Create `backend/config.py`, `backend/es_client.py`, `backend/main.py`.
2. Implement `GET /api/health` and index discovery; render the Dashboard.
3. Implement `GET /api/projects/search`, `GET /api/projects/{project_id}`,
   `/suggest`, and `/facets`; render the Projects and Detail tabs.
4. Implement analytics endpoints; add Chart.js charts.
5. Implement data quality and pipeline simulation.
6. Implement pagination (`from/size`, `search_after`, PIT) and CSV export.
7. Implement mapping, stats, aliases, and field caps.
8. Implement ops health/nodes/shards and the P13 runbook.
9. Add the guarded query console.
10. Add the read-only `Map / Boundaries` tab and `/api/projects/boundaries`.
11. Add error handling, empty states, and the "field missing" messages.
12. Write `README.md` with setup, `.env` example, endpoints, and a demo script.
13. Apply the approved search-to-centroid patch: typo-aware `q`, score ordering
    and cursor, explicit viewport bbox behavior, focus marker, pinned nearby
    mode, truncation warnings, tests, and static cache bump to `?v=6`.

## 11. Acceptance criteria

- The app starts with only `ES_URL` set and serves the HTML page at `/`.
- `/api/health` reports name `rajiv-omen`, version 8.19.23, yellow status,
  nodes 1, and the live `gujrat_rera_data` row.
- A missing index or field produces a clear message, not a stack trace.
- `q=residency`, `district=Ahmedabad`, `project_status=Ongoing` returns 96 hits
  with highlighted `project_name` and a stable `projectId` sort.
- Detail view for `projectId` 573 returns all five disabled objects as section
  cards, including a map link and document links.
- Exact price filter and price-prefix filter both work; no numeric range query
  is ever sent for `price`.
- Date range filters send `dd-MM-yyyy` values or an explicit `format`.
- Suggest returns results after two characters and debounces requests.
- Analytics values match a direct aggregation call; charts render.
- Data quality reports 6 docs missing `price`, 0 missing on other core fields,
  and lists casing collisions such as `Rajkot`/`RAJKOT`.
- Pipeline simulation returns a normalized document when a pipeline exists and
  `pipeline_missing` otherwise; it never increases the index count.
- Pagination pages are contiguous and unique; the `search_after` cursor on
  `projectId` advances; `from + size > 10000` is rejected with a helpful
  message; CSV export streams 17,271 rows by default.
- Ops shows unassigned shards and explains the single-node replica cause.
- The query console rejects scripts, oversized pages, unknown keys, and any
  index other than `gujrat_rera_data`.
- No endpoint accepts write operations.
- After the planned search-to-centroid patch, `q=shivalik recidency` resolves
  `Shivalik Residences` (`projectId` 573) through the fallback group, with results
  ordered by `score` desc then `projectId` asc and paged by `[score, projectId]`.
- After the planned patch, `Use current view` is unchecked by default, map moves
  do not auto-reload boundaries, and a bbox is sent only when explicitly checked.
- After the planned patch, **Show nearby** pins the focused project, uses a 2 km
  radius from its centroid, retains indexed filters, sorts by `distance_km`, and
  keeps the pinned row visible with no nearby rows.
- After the planned patch, truncation warnings appear when the scan stops early
  or more than 250 visible rows are available.

## 12. Caveats and index-shape drift

- **Single index.** Everything here is about `gujrat_rera_data`. Other state
  RERA indices on the cluster are out of scope.
- **`dynamic: false`.** Unknown fields are in `_source` only, never indexed.
- **`enabled: false` objects.** The five large sections cannot be searched,
  filtered, sorted, or aggregated. Making them queryable requires a mapping
  change plus reindex, which is a write operation and therefore a runbook item.
- **`price` is a keyword.** Values are strings like `"1.67 Crore Onwards"`.
  Numeric ranges and numeric sorting are impossible without a reindex adding a
  numeric field. 13,250+ distinct values and 6 missing values are observed.
- **Custom date format.** `start_date`/`end_date` use `dd-MM-yyyy`; UI inputs
  use `yyyy-MM-dd`. Convert or pass `format`. `ignore_malformed` causes bad
  dates to be stored but not indexed, so `missing` aggregations cannot find
  them.
- **Dirty categorical data.** District and taluka values contain case and
  encoding variants (`RAJKOT`, `AHmedabad`, `SabarA?Kantha`, `Choryasi` vs
  `Chorasi`). Filters are exact; use the collision panel rather than silently
  normalizing.
- **Permissions.** A remote cluster may deny `_cat`, `_nodes`, `_ilm`,
  `_index_template`, or `_analyze`. Catch 403 and mark the panel unavailable.
- **No security features.** The remote cluster is assumed open. If auth is
  added later, use environment variables and never send credentials to the
  browser.
- **Timings.** Wall-clock values include HTTP overhead; server `took` is the
  Elasticsearch measurement. Both are affected by the shared host.
- **Single-node cluster.** A yellow cluster with unallocated replicas is
  expected, not an application failure.
- **Geo is partial and read-only.** Native `geo_point` / `geo_shape` DSL is
  unavailable; `Map / Boundaries` renders `_source` rings and applies
  bbox/radius/polygon filters in backend/frontend geometry code only.
- **P13 admin tasks** cannot be performed by a read-only app. Keep them in the
  runbook text and do not add hidden write endpoints.

## 13. Demo script

1. Open the Dashboard; confirm version 8.19.23, one node, yellow status, and
   the live 17,271-doc `gujrat_rera_data` row. Read the replica explanation.
2. Projects: search `residency`, filter district `Ahmedabad` and status
   `Ongoing`; confirm 96 hits and highlighted names.
3. Projects: add exact price `20.97 Lakh Onwards`, then a price prefix `10.00`;
   open a date range such as 2015-2025 and confirm `dd-MM-yyyy` in "Query used".
4. Open `projectId` 573; show the Project Profile section cards, the map link,
   the promoter details, and the other-developer projects.
5. Analytics: show the district, project-type, status, promoter, and
   start-year charts.
6. Data Quality: show 6 missing prices, the casing-collision panel, the scrape
   flags (5 docs with documents downloaded), and the malformed-date note.
7. Pagination: page through 20 records, then advance 100 with `search_after`,
   then open a PIT session, then export CSV and check the row count.
8. Mapping and Indices: open the mapping, mark the five non-indexed objects,
   show stats and aliases, and explain 1 shard + 1 replica on one node.
9. Ops: show health, node stats, shards, unassigned replicas, and read the P13
   runbook.
10. Console: run a simple `match` query, then confirm scripts, unknown keys,
    oversized pages, and other indices are rejected.
11. Map / Boundaries: filter Ahmedabad, zoom into a boundary cluster, click a
    polygon, then draw a bbox/radius filter and observe cached re-rendering. For
    the planned patch, also search `shivalik recidency`, confirm the focus marker
    on `Shivalik Residences`, click **Show nearby**, verify the pinned row and
    `distance_km` sorting, and leave **Use current view** unchecked until a bbox
    is requested explicitly.

This is the full scope for v1 plus the read-only boundary-map lab and the
approved search-to-centroid follow-up. Native ES geo queries remain out of scope
because they would require index writes. Anything not listed here is out of
scope.
