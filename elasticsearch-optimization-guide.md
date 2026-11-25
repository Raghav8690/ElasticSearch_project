# Elasticsearch Optimization Guide

Target setup: ~50 indexes, each with thousands to lakhs of documents.
Core idea: **do less work at search time**: cached filters, fewer fields scored, mappings shaped around access patterns.

Reference: [Elastic Search Speed Guide](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/search-speed)

---

## 1. Shard and Cluster Design (biggest win at this scale)

- **1 primary shard per index** for indexes under ~30-50 GB. Over-sharding (e.g. 50 indexes x 5 shards = 250 tiny shards) wastes heap and slows every search.
- **1 replica** minimum; add more if you need read throughput.
- Merge indexes with the same mapping into one, using a `type` discriminator field plus filtered aliases.
- **3 dedicated master-eligible nodes** in production; add **coordinating nodes** for heavy aggregations.

## 2. Hardware and JVM

- Use **SSD/NVMe**, not HDD.
- Heap = **50% of RAM, max ~31 GB**. Leave the rest for the OS filesystem cache.
- Keep **>= 50% RAM free** for the filesystem cache (hot index data stays in memory).
- Disable swap: `bootstrap.memory_lock: true`.

## 3. Query DSL Optimizations

| Technique | Why |
|---|---|
| Use `bool.filter` / `must_not` for exact checks (`term`, `terms`, `range`, `exists`) | No scoring; results cached as bitsets |
| Use `constant_score` when relevance doesn't matter | Skips scoring |
| Search fewer fields; use `copy_to` to combine text fields at index time | Less per-term work than wide `multi_match` |
| Avoid leading wildcards (`*foo`), unanchored regex, Painless scripts in queries/sorts | Very expensive at runtime |
| Use `index_prefixes` for prefix search; `edge_ngram` / `search_as_you_type` for autocomplete | Replaces wildcards |
| Round dates: `now/m`, `now/h`, `now/d` | Millisecond `now` never hits the query cache |
| Limit `_source` (includes/excludes) or use `fields` | Less data to fetch and send |
| Leave `track_total_hits` at default (10000) unless exact count is needed | Allows early termination (WAND) |
| Use `rescore` | Runs expensive scoring only on top N hits |
| Use `_msearch` | Batches queries, fewer round trips |
| Set `timeout` and `terminate_after` | Safety nets for runaway queries |
| Use `size: 0` for aggregation-only queries | Enables shard request cache |
| Use `composite` aggregation to page through buckets | Avoids huge bucket responses |
| Cap `from + size` via `max_result_window` | Prevents deep-paging abuse |
| Avoid `nested`, `join`, `has_child` | Much slower; denormalize instead |

```json
GET myapp-products/_search
{
  "_source": ["name", "price"],
  "query": {
    "bool": {
      "must":   [{ "match": { "name": "laptop" } }],
      "filter": [
        { "term":  { "status": "active" } },
        { "range": { "created_at": { "gte": "now-7d/d" } } }
      ]
    }
  }
}
```

## 4. Mapping and Index Design

- **IDs, codes, registration numbers -> `keyword`**, not `integer`/`long` (faster exact lookups; numeric is for ranges).
- **Pre-index buckets/flags** (e.g. price tier as keyword) instead of range queries at search time.
- **`index_phrases`** on text fields used with `match_phrase`.
- **`dynamic: strict`** to prevent mapping explosion.
- **`index: false`** on fields never searched.
- **`doc_values: false`** on fields never sorted/aggregated.
- **`norms: false`** on text fields where scoring doesn't matter.
- **Exclude large blobs** from `_source` if never returned.
- **`index.sort`** (e.g. on `start_date`) so searches can stop early once enough top hits are found.
- **Force-merge read-only indexes** to 1 (or few) segments: less per-segment overhead, lower memory.
- **Eager global ordinals** on high-cardinality keyword fields used in aggregations.
- Increase `refresh_interval` (e.g. `30s`) if near-real-time isn't needed; fewer segments, faster indexing.

```json
PUT myapp-products
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "product_id":  { "type": "keyword" },
      "name":        { "type": "text", "index_prefixes": {}, "index_phrases": true },
      "status":      { "type": "keyword" },
      "price":       { "type": "scaled_float", "scaling_factor": 100 },
      "internal":    { "type": "keyword", "index": false, "doc_values": false },
      "created_at":  { "type": "date" }
    }
  }
}
```

## 5. Pagination and Caching

| Technique | When | Why |
|---|---|---|
| `search_after` + PIT (point in time) | Deep pagination | Avoids `from + size` sorting thousands of hits across shards |
| `preference` parameter (e.g. session ID) | Repeated user searches with replicas | Same shard copy -> better node-level cache hits |
| Shard request cache | Repeated aggregation / `size: 0` queries | Caches whole shard-level responses |
| Node query cache (filter context) | Repeated filters | Cached bitsets reused |

## 6. Monitoring and Diagnostics (don't optimize blindly)

- **Search slow log**: catches slow queries in production.
- **Profile API** (`"profile": true`) / Kibana Search Profiler: per-clause timing on slow queries.
- `_cat/thread_pool/search`: watch for **rejections**.
- `_nodes/stats`: cache hit rates, GC pressure.
- `_cat/shards`: check shard balance and sizes.
- **Rally** (or replay of real queries): benchmark before and after each change.

```json
PUT myapp-*/_settings
{
  "index.search.slowlog.threshold.query.warn": "2s",
  "index.search.slowlog.threshold.query.info": "500ms"
}
```

## 7. Application Layer

- Cache hot queries in **Redis** with a short TTL.
- Use **connection pooling** (keep-alive) and client **timeouts**.
- **Debounce** autocomplete on the frontend.
- Use ES **GET by `_id`** (or a DB lookup) when you don't need search.
- Keep queries simple; build them from user input safely (no raw wildcards from users).

## 8. Lifecycle (for time-based data)

- Use **data streams** and **ILM rollover**.
- **Shrink + force-merge** old indexes; move to cheaper nodes or delete.

---

## Starter Index Template

```json
PUT _index_template/search-base
{
  "index_patterns": ["myapp-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1,
      "refresh_interval": "30s",
      "index.search.slowlog.threshold.query.warn": "2s",
      "index.search.slowlog.threshold.query.info": "500ms"
    },
    "mappings": { "dynamic": "strict" }
  }
}
```

> `refresh_interval: 30s` means new docs take up to 30s to become searchable. Lower it if you need near-real-time.

---

## Priority Checklist

1. [ ] Fix shard count (1 primary per index) and mappings
2. [ ] Move exact checks into `bool.filter`; round date ranges
3. [ ] Enable slow log; fix worst queries with Profile API
4. [ ] Add app-level caching (Redis) and connection pooling
5. [ ] Use `search_after` + PIT for deep pagination
6. [ ] Tune JVM heap / filesystem cache / disable swap
7. [ ] Only then: force-merge, `index.sort`, `index_phrases` (trade-offs apply)

At lakhs of docs per index, a well-mapped cluster on ~3 modest nodes is usually already fast. **Measure first, then optimize.**
