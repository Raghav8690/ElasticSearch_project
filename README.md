# Gujrat RERA Explorer

[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-8.19.23-005571?logo=elasticsearch)](https://www.elastic.co/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/Mode-Read--Only-green)](#non-negotiable-constraints)

A high-performance, read-only educational web application that turns a real-world Elasticsearch index (`gujrat_rera_data` &mdash; 17,271 projects, 279.1 MB) into an interactive 10-tab exploration tool.

Designed to demonstrate real-world Elasticsearch concepts covering **12 of 13 practical exercises fully plus a partial P12 map lab**. The live index has no `geo_point` / `geo_shape` fields, so native ES geo DSL is out of scope; instead, all 17,271 documents contain boundary rings under `Project Profile.Map Location`, rendered from `_source` with no index writes. Instead of clean, synthetic mock datasets, this application works directly with real-world Indian real estate regulatory data containing dirty categorical values, custom date formats, casing inconsistencies, and large display-only non-indexed objects.

---

## Table of Contents

- [Key Features](#key-features)
- [Observed Cluster & Index Facts](#observed-cluster--index-facts)
- [System Architecture](#system-architecture)
  - [Request Flow](#request-flow)
  - [PIT (Point-in-Time) Lifecycle](#pit-point-in-time-lifecycle)
  - [Standard API Envelopes](#standard-api-envelopes)
- [Repository Layout](#repository-layout)
- [Quickstart & Installation](#quickstart--installation)
  - [Prerequisites](#prerequisites)
  - [Configuration (`.env`)](#configuration-env)
  - [Running the Application](#running-the-application)
- [Application Feature Tour (10 Active Tabs)](#application-feature-tour-10-active-tabs)
- [API Surface Catalog](#api-surface-catalog)
- [Elasticsearch Practicals Coverage Matrix](#elasticsearch-practicals-coverage-matrix)
- [Non-Negotiable Constraints & Guardrails](#non-negotiable-constraints--guardrails)
- [Interactive Demo Script](#interactive-demo-script)
- [Testing & Quality Assurance](#testing--quality-assurance)

---

## Key Features

- **Real-World Gujarat RERA Substrate**: 17,271 authentic project registrations with live text search, dynamic aggregations, and edge cases.
- **Teaching Tool First**: Every single tab and request displays the exact Elasticsearch Query DSL executed, the server-side `es_took_ms`, and the client-measured `wall_ms`.
- **5 Non-Indexed Object Section Cards**: Demonstrates Elasticsearch's `enabled: false` mapping directive. Subsections like `Project Profile` (10.6 KB) and `Promoters` (2.5 KB) are preserved in `_source` but excluded from indices, displayed seamlessly as rich frontend section cards.
- **Data Quality & Casing Collision Detection**: Detects un-normalized categorical entries (e.g., `Ahmedabad` vs. `AHmedabad`, `Rajkot` vs. `RAJKOT`, `Choryasi` vs. `Chorasi`) using aggregation buckets.
- **Safe Deep Pagination & Streaming CSV Export**: Supports cursor pagination via `search_after` and Point-in-Time (PIT) search contexts, including a streaming CSV export capable of serving all 17,271 records without running out of memory.
- **Built-in Ops Learning**: Uses a single-node cluster with unassigned replicas as an educational feature rather than an error condition.
- **Guarded Query Console**: Allows interactive Query DSL testing against `gujrat_rera_data` with a recursive allowlist that rejects dangerous operations (scripts, wildcards, oversized windows).
- **Read-Only Boundary Map**: 10th tab renders project boundary rings from `_source` with Leaflet + OpenStreetMap; district/bbox/radius/polygon filters are computed without indexing or data mutation.

---

## Observed Cluster & Index Facts

*Note: All counts are verified dynamically at runtime; the app never hardcodes counts.*

| Property | Observed Value | Description / Note |
|---|---|---|
| **Cluster / Node** | `elasticsearch` / `rajiv-omen` | Single-node deployment |
| **Cluster Status** | **yellow** | 36 unassigned replica shards; 69 active primary shards |
| **ES Version** | **8.19.23** | Lucene 9.12.2 |
| **Index Name** | `gujrat_rera_data` | Single index target for v1 |
| **Index Health** | **yellow** | 1 primary shard assigned, 1 replica unassigned |
| **Documents** | **17,271** | Complete Gujarat RERA scraped archive |
| **Store Size** | **279.1 MB** | Total index size on disk |
| **Dynamic Mapping** | `dynamic: false` | Unknown fields in `_source` are not indexed |

---

## System Architecture

### Request Flow

```text
Browser (Vanilla JS / Chart.js)
  │  fetch() with AbortController (20s timeout)
  ▼
FastAPI Backend (routes.py)
  │  Parameter validation, route ordering, recursive console allowlist
  ▼
Query Builders (queries.py)            ES Client Manager (es_client.py)
  │  Pure Query DSL builders             │  AsyncElasticsearch singleton
  │  Source filtering (_source)          │  Degraded discovery & capabilities
  │  Highlight sentinels & format guards │  PIT session registry (UUID -> pit_id)
  ▼                                      ▼
Elasticsearch Cluster (8.19.23 at http://192.168.1.14:9200)
```

### PIT (Point-in-Time) Lifecycle

```text
Browser                 FastAPI (routes.py)          es_client.py            Elasticsearch
   │                            │                         │                        │
   ├─── Open PIT Session ──────>│                         │                        │
   │                            ├─── open_point_in_time ─>│                        │
   │                            │                         ├─── POST /{index}/_pit ─>│
   │                            │<── session_id (UUID) ───│<── pit_id ────────────┤
   │<── session_id ─────────────┤                         │                        │
   │                            │                         │                        │
   ├─── Next (session_id) ─────>│                         │                        │
   │                            ├─── Resolve pit_id ─────>│                        │
   │                            ├─── search_after ────────────────────────────────>│
   │<── Hits + next_cursor ─────│<── Update pit_id ───────│<── hits + new pit_id ──┤
   │                            │                         │                        │
   ├─── Close Session ─────────>│                         │                        │
   │                            ├─── delete_pit ─────────>│                        │
   │                            │                         ├─── DELETE /_pit ──────>│
   │<── 204 No Content ─────────┤                         │                        │
```

### Standard API Envelopes

Every API endpoint (with the intentional flat-shape exception of `GET /api/health`) uses a strict, uniform JSON response envelope:

#### Success Response
```json
{
  "data": { ... },
  "meta": {
    "index": "gujrat_rera_data",
    "total": 17271,
    "returned": 20,
    "es_took_ms": 12,
    "wall_ms": 18.4,
    "query_used": { ... }
  }
}
```

#### Sanitized Error Response
```json
{
  "error": {
    "code": "invalid_request",
    "message": "from + size must be <= 10000. Use search_after for deep pagination.",
    "detail": "redacted"
  }
}
```

*Standard Error Codes*: `es_unavailable`, `index_missing`, `field_missing`, `invalid_request`, `not_found`, `forbidden`, `timeout`, `es_error`, `pipeline_missing`, `session_expired`.

---

## Repository Layout

```text
ElasticSearch_project/
├── PLAN.md                 # Approved engineering implementation plan & decisions
├── PROJECT_CONTEXT.md      # Ground-truth technical specification & ES DSL queries
├── README.md               # Project documentation (this file)
├── requirements.txt        # Python dependency specifications
├── .env.example            # Sample environment configuration
├── backend/
│   ├── __init__.py
│   ├── main.py             # FastAPI app factory, lifespan, static file mount, exceptions
│   ├── config.py           # Pydantic Settings model for environment variables
│   ├── es_client.py        # AsyncElasticsearch singleton, PIT registry, discovery
│   ├── schemas.py          # Request models and standard response envelopes
│   ├── queries.py          # Pure functions generating Elasticsearch Query DSL
│   └── routes.py           # 26 read-only API endpoints + static route definitions
├── frontend/
│   ├── index.html          # Single-page HTML interface (10 active tabs)
│   ├── app.js              # Vanilla JavaScript (fetch, Chart.js bindings, DOM renderer)
│   └── styles.css          # Modern dashboard styling and responsive grid layout
└── tests/
    ├── test_queries.py     # Unit tests for pure query builders
    ├── test_validators.py  # Validation & AST allowlist tests for Query Console
    ├── test_errors.py      # Error handler and credential sanitization tests
    ├── test_routes.py      # Route precedence and contract tests
    └── test_streams.py     # Streaming CSV export and PIT cancellation tests
```

---

## Quickstart & Installation

### Prerequisites

- **Python**: 3.10 or 3.11+
- **Elasticsearch**: 8.19.23 reachable over HTTP (default: `http://192.168.1.14:9200`)
- **Virtual Environment**: Recommended (`venv`)

### Configuration (`.env`)

Create a `.env` file in the project root (or copy `.env.example`):

```dotenv
# Elasticsearch cluster endpoint
ES_URL=http://192.168.1.14:9200
ES_TIMEOUT_SECONDS=15
ES_MAX_CONNECTIONS=20

# Optional Authentication (leave empty for unauthenticated local clusters)
ES_USERNAME=
ES_PASSWORD=
ES_API_KEY=
ES_VERIFY_CERTS=true

# Index configuration
INDEX_RERA=gujrat_rera_data
PIPELINE_ID=gujrat_normalize_pipeline

# Security safety lock
ALLOW_WRITES=false
```

### Running the Application

1. **Create and activate a virtual environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Start the FastAPI application**:
   ```powershell
   uvicorn backend.main:app --reload --port 8000
   ```

4. **Access the Web Interface**:
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

---

## Application Feature Tour (10 Active Tabs)

The 10 tabs below are active today. The `Map / Boundaries` tab is a read-only
geometry lab; it does not imply native Elasticsearch geo fields.

### 1. Dashboard
- Live cluster status pill (`yellow`, `green`, `red`), version (`8.19.23`), and node count.
- Configured index overview with live document count (17,271), storage size, and shard allocation.
- In-depth ops explanation for why single-node clusters remain yellow with unassigned replica shards.
- Capability badges displaying detected feature availability.

### 2. Projects
- **Full-Text Search**: Search by `project_name` (boost ^3) and `promoter_name` (boost ^1) with safe DOM highlight rendering (`[[HL]]` sentinels converted to `<mark>` nodes).
- **Prefix Auto-Suggest**: Case-insensitive prefix matching for `plot`, `Plot`, `PLOT`, and `PLot`, with debounced (300 ms, min 2 chars) suggest results.
- **Filters**: Case-insensitive exact and prefix terms for District, Taluka, Project Type, Project Status, Promoter, Registration Number, and Scrape Status.
- **Price Constraints**: Exact price selection and prefix search (`prefix` on `price` keyword); strictly prohibits illegal numeric range queries.
- **Date Ranges**: `start_date` and `end_date` date pickers formatted to `dd-MM-yyyy`.
- **Facets Sidebar**: Live terms aggregations showing breakdown counts.

### 3. Project Detail
- Accessible by clicking any project from the search results or via ID search.
- Dual-lookup strategy: Direct `GET _doc/{id}` with a `term` query fallback on `projectId`.
- Core metadata: Registration number, Promoter, Status, Dates, Pricing, and Source URL.
- **Five Rich Section Cards** rendering `enabled: false` display objects:
  1. *Project Profile* (Overview, Certificates, Amenities, Map Location coords)
  2. *Project Summary* (Booking status, Compliance, Financial Details)
  3. *Promoters* (Directors, Signatories, Parent Entities)
  4. *Progress & RERA Actions* (Block Progress, Form Compliance, Complaints, Penalties)
  5. *More Projects by The Same Developer*
- Static map link generated from `Project Profile.Map Location` lat/lng.
- Raw `_source` JSON inspection toggle.

### 4. Analytics
- Interactive charts powered by Chart.js:
  - **Districts Bar Chart**: Distribution across top districts (Ahmedabad, Vadodara, Surat, Rajkot, etc.).
  - **Project Types**: Residential/Group Housing vs. Mixed Development vs. Commercial vs. Plotted.
  - **Project Status**: Breakdown of New vs. Ongoing vs. Completed.
  - **Top Promoters**: Highest-volume developers in the state.
  - **Start Year Histogram**: Date histogram from 2005 through 2027.
- Scraped document metric cards (min 24, max 1,134, average 77.5 documents per project).

### 5. Data Quality
- Identifies missing data: 6 documents missing `price`; 0 missing on all other core fields.
- **Casing Collision Detector**: Python-evaluated grouping of Elasticsearch aggregation buckets identifying variations like `Rajkot` vs `RAJKOT` or `Choryasi` vs `Chorasi`.
- **Malformed Dates Explanation**: Highlights how Elasticsearch's `ignore_malformed=true` preserves corrupt dates in `_source` while skipping indexation.
- **Ingest Pipeline Simulation**: Form to test `_simulate` on `gujrat_normalize_pipeline` without altering data.

### 6. Pagination & Export
- Side-by-side comparison of paging techniques:
  - **Page N (`from + size`)**: Standard offset paging; enforces strict 10,000 window cap with an educational alert when exceeded.
  - **Next 100 (`search_after`)**: High-performance cursor pagination using `[projectId]`.
  - **PIT Sessions**: Point-in-Time session creation and destruction with server-side TTL tracking.
- **Streaming CSV Export**: Memory-bounded streaming export using `search_after` batches (up to 17,271 records) with formula-injection sanitization.

### 7. Mapping & Indices
- Interactive mapping inspector marking indexed queryable fields vs. non-indexed (`enabled: false`) objects.
- Live `_stats` and segment breakdown.
- Cat aliases inspector (demonstrating zero configured aliases).
- Field capabilities matrix (`_field_caps`).

### 8. Ops
- Cluster health and OS / JVM node metrics.
- Shards breakdown highlighting the unassigned replica shard on single-node setups.
- Search slow log: recent API searches with wall/ES timings, slow-query flags, and current Elasticsearch slow-log thresholds.
- **P13 Operational Runbook**: Administrative procedures (users, roles, API keys, snapshot/restore, slow logs) documented as a safe reference guide.

### 9. Guarded Query Console
- Educational playground locked specifically to `gujrat_rera_data`.
- JSON Query DSL editor with execution time metrics and hit counts.
- **Security AST Validator**: Rejects write operations, `script`, `regexp`, leading wildcards, unauthorized indices, and query bodies exceeding allowed boundaries.

### 10. Map / Boundaries
- Interactive Leaflet + OpenStreetMap view of project boundary rings from `Project Profile.Map Location`; no API key or index writes.
- Indexed filters first (`district`, `taluka`, `project_type`, `q`), then read-only bbox / radius / polygon geometry filtering in the backend.
- Viewport-batched loading with an in-memory cache; zooming re-renders cached polygons without another Elasticsearch request.
- Degenerate rings are shown as centroid markers and counted in the result meta instead of failing the map.

#### Approved follow-up: map search-to-centroid patch (planned)

- The approved next patch upgrades the boundary map from a viewport-batched ring browser into a name-resolution flow; it is **planned, not yet implemented**.
  - `q` changes from a strict both-token match into an exact/current group plus a fallback group: normalized exact `project_name`, `match_phrase_prefix` on `project_name`, and fuzzy `match` with `fuzziness: AUTO`.
  - Original typo text is preserved for fuzzy matching; normalized text strips punctuation and maps variants such as `recidency` / `recidence` to `residency`.
  - With `q`, ES results are ordered by `_score` descending then `projectId` ascending; boundaries, markers, and response meta expose `score`, and pagination uses a `[score, projectId]` cursor. Without `q`, the existing `projectId` ordering and cursor remain unchanged.
  - The map gains a distinct focus marker for the first usable search result, row-click focus, and a **Show nearby** action that pins that project and reloads with a 2 km radius centred on its centroid.
  - Nearby results keep district / taluka / project type / status / registration number filters, drop `q`, sort by `distance_km`, and keep the pinned row visible at the top even when no nearby rows are returned.
  - `Use current view` is unchecked by default; unchecking it clears `#b-bbox`, map moves no longer trigger auto-reloads, and **Load Boundaries** computes a fresh bbox only when the checkbox is checked.
  - Table and map show truncation status when the scan stops early or more than 250 visible rows are available.
  - The two contracts still to freeze before coding are the exact token / typo-map / phrase-prefix derivation rules and the exact radius-filter / pinned-row count behavior.

---

## API Surface Catalog

All endpoints are hosted under `/api` and return standardized envelopes:

| Area | HTTP Method & Route | Purpose |
|---|---|---|
| **Discovery** | `GET /api/health` | Flat cluster/index health summary (survives degraded startup) |
| | `GET /api/config` | Safe configuration (host and index name only; no credentials) |
| | `GET /api/capabilities` | Dynamic feature availability flags with failure reasons |
| **Indices** | `GET /api/indices` | Cat indices information for configured index |
| | `GET /api/indices/{index}/mapping` | Index mapping with indexed vs. unindexed flags |
| | `GET /api/indices/{index}/stats` | Document counts, store bytes, segment statistics |
| | `GET /api/indices/{index}/aliases` | Cat aliases filtered to current index |
| **Projects** | `GET /api/projects/search` | Multi-filter search with highlighting & sorting |
| | `GET /api/projects/suggest` | Debounced prefix autocomplete via `match_phrase_prefix` |
| | `GET /api/projects/boundaries` | Read-only boundary rings with bbox/radius/polygon filters and cached viewport batches |
| | `GET /api/projects/facets` | Aggregations for dropdown filters and stats |
| | `GET /api/projects/{project_id}` | Full detail with section extraction and fallback |
| **Analytics** | `GET /api/analytics/overview` | Categorical aggregations for charts |
| | `GET /api/analytics/dates` | Date histograms for project registration timelines |
| **Quality** | `GET /api/quality/scrape` | Missing field aggregations & casing collision detector |
| | `POST /api/quality/pipeline-simulate` | Dry-run ingest pipeline simulation |
| **Pagination** | `GET /api/projects/page` | Offset pagination (`from` / `size` with 10k cap) |
| | `POST /api/pit` | Create a Point-in-Time search context |
| | `DELETE /api/pit/{session_id}` | Explicitly close a Point-in-Time context |
| | `GET /api/projects/search-after` | Cursor-based search with optional PIT integration |
| | `GET /api/projects/export` | Streaming CSV download of project records |
| **Analyzer** | `POST /api/analyze` | Tokenizer and analyzer test tool for text fields |
| **Ops** | `GET /api/ops/health` | Raw cluster health status |
| | `GET /api/ops/nodes` | JVM heap, CPU, memory, and thread-pool metrics |
| | `GET /api/ops/shards` | Cat shards showing primary/replica allocation status |
| | `GET /api/ops/slowlog` | Recent search requests and ES slow-log threshold settings |
| **Console** | `POST /api/query/{index}` | Guarded Query DSL runner with recursive allowlist |

---

## Elasticsearch Practicals Coverage Matrix

This application covers **12 of the 13 Elasticsearch curriculum practicals fully**, with **P12 partial** as a read-only geometry/map lab:

| Practical | Subject | Coverage in Gujrat RERA Explorer |
|---|---|---|
| **P1** | Cluster, Nodes & Health | Dashboard & Ops tabs; version 8.19.23, node metrics, yellow status |
| **P2** | Index Lifecycle & CRUD | Read-only architecture; document retrieval by `_id`, query explanations |
| **P3** | Mappings & Analyzers | Mapping tab (`dynamic: false`), Analyze panel, text vs keyword comparison |
| **P4** | Query DSL & Highlights | Projects tab search filters with safe sentinel `[[HL]]` rendering into `<mark>` nodes |
| **P5** | Bool Queries & Filtering | Strict separation of cached `bool.filter` vs scored `must` multi-match |
| **P6** | Suggestions & Analyzers | Case-insensitive prefix suggest with `case_insensitive: true` and `match_phrase_prefix` |
| **P7** | Relevance & Scoring | Multi-match field boosting (`project_name^3`, `promoter_name^1`) |
| **P8** | Aggregations & Metrics | Analytics tab charts; terms aggregations, date histograms, stats |
| **P9** | Data Quality & Ingestion | Missing field detection, casing collisions, pipeline `_simulate` |
| **P10** | Pagination & Export | `from/size` vs `search_after` vs PIT; streaming CSV export |
| **P11** | Aliases, Stats & Shards | Mapping & Indices tab; segment stats, aliases, shard replica lesson |
| **P12** | Geo-spatial Queries | **Partial**: 16,955 usable boundary rings rendered from `_source`; bbox/radius/polygon filtering is client/server geometry, not native ES geo DSL |
| **P13** | Operations & Administration | Ops tab: node heap, unassigned shards, and administrative runbooks |

> **Geo boundary note**: native ES `geo_point` / `geo_shape` queries are not
> available because the mapping has no indexed geo fields and the app never
> writes to the index. The `Map / Boundaries` tab reads boundary rings from
> `_source`, computes centroids/bbox/geometry filters in the backend, and caches
> normalized features in memory only.

---

## Non-Negotiable Constraints & Guardrails

1. **Read-Only Operation**: `ALLOW_WRITES=false` is enforced at all times. The only HTTP POST methods allowed are non-mutating search/analysis APIs (`/_search`, `/_pit`, `/_analyze`, `/_simulate`).
2. **Field Type Safety (`price`)**: `price` is indexed as a `keyword` string (e.g., `"1.67 Crore Onwards"`). Numeric range queries and numeric sorting on `price` are strictly prohibited; only `term` and `prefix` queries are permitted.
3. **Date Formatting**: `start_date` and `end_date` utilize the custom Indian format `dd-MM-yyyy`. All range queries must explicitly include `"format": "dd-MM-yyyy"`.
4. **Source Filtering**: Search and list endpoints must include only the 13 core queryable fields and explicitly exclude the five disabled objects to avoid payload bloat (~17 KB per document). Disabled objects are loaded only on the detail view; the boundary endpoint is the sole exception, with a strict `_source` allowlist for `Project Profile.Map Location` only.
5. **Result Window Limit**: `from + size > 10000` is rejected with an `invalid_request` error, instructing the client to use `search_after`.
6. **Console AST Whitelist**: The guarded console verifies queries through a recursive allowlist, barring `script`, `regexp`, leading wildcards, and requests to any index other than `gujrat_rera_data`.

---

## Interactive Demo Script

Follow this 11-step script to evaluate or demonstrate the system:

1. **Open Dashboard**: Verify cluster name `rajiv-omen`, version `8.19.23`, yellow status, and live `17,271` document count. Read the single-node replica explanation card.
2. **Search with Filters**: Go to **Projects**, enter `q=residency`, filter District `Ahmedabad`, and Status `Ongoing`. Confirm exactly 96 hits and inspect the highlighted project names.
3. **Inspect Query DSL**: Expand the collapsible "Query used" panel below the search results to observe the generated `bool.filter` and `must` blocks.
4. **Test Price & Date Filters**: In **Projects**, filter price prefix `10.00` and date range `01-01-2015` to `31-12-2025`. Observe `"format": "dd-MM-yyyy"` in the query.
5. **View Project Detail**: Click `projectId 573` (Shivalik Residences). Review the five rich section cards (`Project Profile`, `Promoters`, etc.), open the Google Maps link, and toggle raw JSON.
6. **Examine Analytics**: Go to **Analytics**; review the Chart.js visual breakdown across Districts, Types, Statuses, and the Start Year histogram.
7. **Inspect Data Quality**: Go to **Data Quality**; observe the 6 missing price documents, the casing collision list (`Rajkot` / `RAJKOT`), and test an address normalization in the Ingest Pipeline simulator.
8. **Test Pagination**: Go to **Pagination**; test `Page N (from/size)`. Advance beyond 10,000 hits to trigger the `max_result_window` educational notice. Switch to `Next 100 (search_after)` and watch the cursor update.
9. **Export CSV**: Click **Export CSV** to stream project records with memory safety and formula sanitization.
10. **Test Guarded Console**: In **Console**, run a valid `match` query, then attempt a disallowed `script` or `wildcard` to observe the AST rejection rule.
11. **Explore Boundaries**: In **Map / Boundaries**, filter district `Ahmedabad`, zoom into a cluster, click a project polygon, then draw a bbox or radius filter and confirm cached re-rendering on zoom. For the planned patch, also try `q=shivalik recidency`, confirm `Shivalik Residences` is the focus marker, click **Show nearby**, verify the pinned row and `distance_km` sorting, and leave **Use current view** unchecked until a bbox is requested explicitly.

---

## Testing & Quality Assurance

The test suite utilizes `pytest`, `pytest-asyncio`, and `httpx.ASGITransport` to validate backend logic without requiring a browser:

```powershell
# Run the full test suite
pytest -v

# Run query builder validation tests
pytest tests/test_queries.py

# Run console AST security tests
pytest tests/test_validators.py

# Run error sanitization tests
pytest tests/test_errors.py
```

### Coverage Highlights
- **Query Builder Branching**: Validates that empty filters are omitted from DSL, date formats are added, and price queries never use numeric ranges.
- **AST Validator**: Confirms rejection of scripts, nested wildcards, oversized pages, and forbidden indices.
- **Security & Sanitization**: Asserts that Elasticsearch exceptions, passwords, and sensitive credentials are never leaked to client responses.
- **Route Precedence**: Ensures static API routes (`/api/projects/search`, `/api/projects/boundaries`) take precedence over dynamic route variables (`/api/projects/{project_id}`).
- **Boundary Geometry**: Validates ring parsing, bbox/radius/polygon filters, invalid-ring fallback, `_source` allowlisting, and cache-safe compact responses.
- **Map Search-to-Centroid Patch (planned)**: Add tests for typo fallback, `_score` ordering and `[score, projectId]` cursors, explicit-bbox-only loading, focus marker / pinned nearby mode, `distance_km` sorting, truncation warnings, and static cache bump to `?v=6`.
- **Streaming Export**: Verifies formula injection prevention and guaranteed Point-in-Time closure upon stream completion or client disconnection.
