"""Read-only FastAPI routes. All routes live under /api."""
from __future__ import annotations

import csv
import io
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from elasticsearch import BadRequestError, NotFoundError

from .config import settings
from .es_client import CAT_INDEX_COLUMNS, ESManager, _safe_reason, flatten_mapping
from .queries import (
    EXPORT_BATCH,
    EXPORT_COLUMNS,
    MAX_EXPORT_LIMIT,
    build_analytics_dates,
    build_analytics_overview,
    build_facets,
    build_page,
    build_project_id_query,
    build_project_search,
    build_quality_scrape,
    build_search_after,
    build_suggest,
    compute_casing_collisions,
    extract_sections,
)
from .schemas import DISABLED_OBJECTS, AppError, PipelineSimulateRequest, envelope

router = APIRouter(prefix="/api")


# -- helpers ---------------------------------------------------------------
def get_es(request: Request) -> ESManager:
    es = getattr(request.app.state, "es", None)
    if es is None:
        raise AppError("es_unavailable", "Elasticsearch manager is not initialized.", status_code=503)
    return es


def now_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def require_index(index: str) -> None:
    """Lock every {index} path parameter to the configured index."""
    if index != settings.index_rera:
        raise AppError(
            "forbidden",
            f"Index '{index}' is not allowed. This app is read-only and locked to '{settings.index_rera}'.",
            status_code=403,
        )


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -- discovery -------------------------------------------------------------
@router.get("/health")
async def health(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    """Flat cluster/index summary. Intentionally not wrapped in the envelope."""
    d = es.discovery
    info = d.get("info") or {}
    cluster_health = d.get("health") or {}
    row = d.get("index_row")

    indices: list[dict[str, Any]] = []
    missing: list[str] = []
    if row:
        indices.append(
            {
                "index": row.get("index"),
                "configured": row.get("index") == settings.index_rera,
                "health": row.get("health"),
                "status": row.get("status"),
                "docs": _as_int(row.get("docs.count")),
                "store": row.get("store.size"),
                "pri": row.get("pri"),
                "rep": row.get("rep"),
            }
        )
    else:
        missing.append(settings.index_rera)

    return {
        "cluster": {
            "name": cluster_health.get("cluster_name") or info.get("cluster_name"),
            "status": cluster_health.get("status", "unavailable"),
            "nodes": cluster_health.get("number_of_nodes"),
        },
        "version": (info.get("version") or {}).get("number"),
        "indices": indices,
        "missing": missing,
        "unassigned_shards": cluster_health.get("unassigned_shards"),
        "active_primary_shards": cluster_health.get("active_primary_shards"),
        "errors": d.get("errors") or {},
        "discovered_at": d.get("discovered_at"),
    }


@router.get("/config")
async def get_config(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    start = time.perf_counter()
    data = {
        "host": settings.host,
        "index": settings.index_rera,
        "allow_writes": settings.allow_writes,
        "read_only": not settings.allow_writes,
    }
    return envelope(data, index=settings.index_rera, wall_ms=now_ms(start))


@router.get("/capabilities")
async def get_capabilities(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    """Flat capability flags with available:false reasons."""
    d = es.discovery
    return {
        "index": settings.index_rera,
        "ready": d.get("ready", False),
        "capabilities": d.get("capabilities") or {},
        "errors": d.get("errors") or {},
    }


# -- indices ---------------------------------------------------------------
@router.get("/indices")
async def list_indices(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    start = time.perf_counter()
    rows = (await es.client.cat.indices(format="json", h=CAT_INDEX_COLUMNS, index=settings.index_rera)).body
    wall = now_ms(start)
    data = {"indices": rows, "configured": settings.index_rera}
    return envelope(
        data,
        index=settings.index_rera,
        total=len(rows),
        returned=len(rows),
        wall_ms=wall,
        query_used={"method": "GET", "path": f"/_cat/indices?index={settings.index_rera}"},
    )


@router.get("/indices/{index}/mapping")
async def get_index_mapping(index: str, es: ESManager = Depends(get_es)) -> dict[str, Any]:
    require_index(index)
    start = time.perf_counter()
    body = (await es.client.indices.get_mapping(index=index)).body
    mapping = (body.get(index) or {}).get("mappings") or {}
    properties = mapping.get("properties") or {}
    fields = flatten_mapping(properties)
    wall = now_ms(start)
    data = {
        "index": index,
        "dynamic": mapping.get("dynamic"),
        "mapping": mapping,
        "fields": fields,
        "disabled_objects": [f for f in fields if not f.get("indexed")],
    }
    return envelope(
        data,
        index=index,
        total=len(fields),
        returned=len(fields),
        wall_ms=wall,
        query_used={"method": "GET", "path": f"/{index}/_mapping"},
    )


@router.get("/indices/{index}/stats")
async def get_index_stats(index: str, es: ESManager = Depends(get_es)) -> dict[str, Any]:
    require_index(index)
    start = time.perf_counter()
    stats = (await es.client.indices.stats(index=index)).body
    segments = (await es.client.indices.segments(index=index)).body
    wall = now_ms(start)

    all_stats = stats.get("_all") or {}
    primaries = all_stats.get("primaries") or {}
    docs = (primaries.get("docs") or {}).get("count")
    store_bytes = (primaries.get("store") or {}).get("size_in_bytes")
    search = primaries.get("search") or {}
    indexing = primaries.get("indexing") or {}

    shard_copies = ((segments.get("indices") or {}).get(index) or {}).get("shards") or {}
    segment_count = 0
    for copies in shard_copies.values():
        for copy in copies or []:
            segment_count += copy.get("num_search_segments") or len(copy.get("segments") or {})

    data = {
        "index": index,
        "docs": docs,
        "store_bytes": store_bytes,
        "segments": segment_count,
        "search": {
            "query_total": search.get("query_total"),
            "query_time_in_millis": search.get("query_time_in_millis"),
        },
        "indexing": {
            "index_total": indexing.get("index_total"),
            "index_time_in_millis": indexing.get("index_time_in_millis"),
        },
        "shards": stats.get("_shards"),
    }
    return envelope(
        data,
        index=index,
        total=docs,
        returned=docs,
        wall_ms=wall,
        query_used={"method": "GET", "paths": [f"/{index}/_stats", f"/{index}/_segments"]},
    )


@router.get("/indices/{index}/aliases")
async def get_index_aliases(index: str, es: ESManager = Depends(get_es)) -> dict[str, Any]:
    require_index(index)
    start = time.perf_counter()
    rows = (await es.client.cat.aliases(format="json", h=["alias", "index"])).body
    filtered = [r for r in rows if r.get("index") == index]
    wall = now_ms(start)
    data = {"index": index, "aliases": filtered, "count": len(filtered)}
    return envelope(
        data,
        index=index,
        total=len(filtered),
        returned=len(filtered),
        wall_ms=wall,
        query_used={"method": "GET", "path": "/_cat/aliases"},
    )


# -- analytics -------------------------------------------------------------
async def _agg_search(es: ESManager, body: dict[str, Any], *, track_total_hits: bool = False) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    resp = (
        await es.client.search(
            index=settings.index_rera,
            size=0,
            track_total_hits=track_total_hits,
            aggs=body["aggs"],
        )
    ).body
    return resp, now_ms(start)


@router.get("/analytics/overview")
async def analytics_overview(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    body = build_analytics_overview()
    resp, wall = await _agg_search(es, body)
    aggs = resp.get("aggregations") or {}
    return envelope(
        {"aggregations": aggs, "documents_stats": aggs.get("documents_stats") or {}},
        index=settings.index_rera,
        total=None,
        returned=len(aggs),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


@router.get("/analytics/dates")
async def analytics_dates(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    body = build_analytics_dates()
    resp, wall = await _agg_search(es, body)
    aggs = resp.get("aggregations") or {}
    return envelope(
        {"aggregations": aggs},
        index=settings.index_rera,
        total=None,
        returned=len(aggs),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


# -- data quality ----------------------------------------------------------
@router.get("/quality/scrape")
async def quality_scrape(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    body = build_quality_scrape()
    resp, wall = await _agg_search(es, body, track_total_hits=True)
    aggs = resp.get("aggregations") or {}
    total = ((resp.get("hits") or {}).get("total") or {}).get("value")
    missing = {
        key: (value or {}).get("doc_count")
        for key, value in aggs.items()
        if key.startswith("missing_") and isinstance(value, dict)
    }
    collisions = compute_casing_collisions(
        (aggs.get("districts") or {}).get("buckets"),
        (aggs.get("talukas") or {}).get("buckets"),
    )
    return envelope(
        {
            "total_docs": total,
            "missing": missing,
            "casing_collisions": collisions,
            "aggregations": aggs,
        },
        index=settings.index_rera,
        total=total,
        returned=len(aggs),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


@router.post("/quality/pipeline-simulate")
async def simulate_pipeline(
    payload: PipelineSimulateRequest,
    es: ESManager = Depends(get_es),
) -> dict[str, Any]:
    source = payload.source or {}
    if len(json.dumps(source, ensure_ascii=False)) > 100_000:
        raise AppError("invalid_request", "Document is too large to simulate (max 100 KB).")
    pipeline_id = settings.pipeline_id
    docs = [{"_source": source}]
    start = time.perf_counter()
    try:
        result = (await es.client.ingest.simulate(id=pipeline_id, docs=docs)).body
    except (NotFoundError, BadRequestError) as exc:
        if isinstance(exc, BadRequestError) and "does not exist" not in str(exc):
            raise
        raise AppError(
            "pipeline_missing",
            f"Ingest pipeline '{pipeline_id}' was not found. Pipelines are administrative "
            "setup and are not created by this read-only app.",
            status_code=404,
        )
    wall = now_ms(start)
    return envelope(
        {"pipeline_id": pipeline_id, "result": result},
        index=settings.index_rera,
        total=1,
        returned=1,
        wall_ms=wall,
        query_used={
            "method": "POST",
            "path": f"/_ingest/pipeline/{pipeline_id}/_simulate",
            "body": docs,
        },
    )


# -- pagination, PIT and export -------------------------------------------
def _shape_paged_hit(hit: dict[str, Any]) -> dict[str, Any]:
    shaped = {"_id": hit.get("_id"), "sort": hit.get("sort")}
    shaped.update(hit.get("_source") or {})
    return shaped


def _safe_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


async def _export_rows(es: ESManager, pit_id: str, limit: int):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    def flush() -> str:
        chunk = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return chunk

    writer.writerow(EXPORT_COLUMNS)
    yield flush()
    cursor: list[Any] | None = None
    written = 0
    try:
        while written < limit:
            size = min(EXPORT_BATCH, limit - written)
            body: dict[str, Any] = {
                "size": size,
                "track_total_hits": False,
                "sort": [{"projectId": "asc"}],
                "_source": list(EXPORT_COLUMNS),
                "query": {"match_all": {}},
                "pit": {"id": pit_id, "keep_alive": settings.pit_keep_alive},
            }
            if cursor:
                body["search_after"] = cursor
            resp = (await es.client.search(body=body)).body
            pit_id = resp.get("pit_id") or pit_id
            hits = (resp.get("hits") or {}).get("hits") or []
            if not hits:
                break
            for hit in hits:
                source = hit.get("_source") or {}
                writer.writerow([_safe_cell(source.get(column)) for column in EXPORT_COLUMNS])
                written += 1
            yield flush()
            if len(hits) < size:
                break
            cursor = hits[-1].get("sort")
            if not cursor:
                break
    except Exception as exc:  # noqa: BLE001 - write a sanitized row, never leak details
        yield flush()
        writer.writerow(["#export_error", _safe_reason(exc), "partial export; PIT closed in finally"])
        yield flush()
    finally:
        await es.delete_pit_id(pit_id)


@router.get("/projects/page")
async def page_projects(
    page: int = 1,
    size: int = 20,
    es: ESManager = Depends(get_es),
) -> dict[str, Any]:
    body = build_page(page, size)
    start = time.perf_counter()
    resp = (
        await es.client.search(
            index=settings.index_rera,
            size=body["size"],
            from_=body["from"],
            track_total_hits=False,
            source_includes=body["_source"],
            query=body["query"],
            sort=body["sort"],
        )
    ).body
    wall = now_ms(start)
    hits = (resp.get("hits") or {}).get("hits") or []
    data = {
        "hits": [_shape_paged_hit(hit) for hit in hits],
        "page": page,
        "size": body["size"],
        "from": body["from"],
        "has_more": len(hits) == body["size"],
    }
    return envelope(
        data,
        index=settings.index_rera,
        total=None,
        returned=len(hits),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


@router.get("/projects/search-after")
async def search_after_projects(
    cursor: str | None = None,
    size: int = 100,
    pit: bool = False,
    session: str | None = None,
    es: ESManager = Depends(get_es),
) -> dict[str, Any]:
    body = build_search_after(cursor, size)
    if pit and not session:
        raise AppError(
            "invalid_request",
            "PIT mode needs a session. Open one with POST /api/pit first, or use plain search_after.",
        )
    start = time.perf_counter()
    if session:
        pit_session = es.get_pit(session)
        body["pit"] = {"id": pit_session.pit_id, "keep_alive": pit_session.keep_alive}
        resp = (await es.client.search(body=body)).body
        es.update_pit(session, resp)
        mode = "pit"
    else:
        kwargs: dict[str, Any] = {
            "index": settings.index_rera,
            "size": body["size"],
            "track_total_hits": False,
            "source_includes": body["_source"],
            "query": body["query"],
            "sort": body["sort"],
        }
        if body.get("search_after"):
            kwargs["search_after"] = body["search_after"]
        resp = (await es.client.search(**kwargs)).body
        mode = "search_after"

    wall = now_ms(start)
    hits = (resp.get("hits") or {}).get("hits") or []
    data: dict[str, Any] = {
        "hits": [_shape_paged_hit(hit) for hit in hits],
        "next_cursor": hits[-1].get("sort") if hits else None,
        "has_more": len(hits) == body["size"],
        "mode": mode,
    }
    if session:
        data["session_id"] = session
    return envelope(
        data,
        index=settings.index_rera,
        total=None,
        returned=len(hits),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


@router.post("/pit")
async def open_pit_session(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        pit_session = await es.open_pit()
    except Exception:  # noqa: BLE001 - sanitized failure
        raise AppError("es_unavailable", "Could not open a PIT session.", status_code=502)
    data = {
        "session_id": pit_session.session_id,
        "index": pit_session.index,
        "keep_alive": pit_session.keep_alive,
        "expires_in_seconds": settings.pit_ttl_seconds,
    }
    return envelope(
        data,
        index=settings.index_rera,
        total=1,
        returned=1,
        wall_ms=now_ms(start),
        query_used={
            "method": "POST",
            "path": f"/{settings.index_rera}/_pit?keep_alive={pit_session.keep_alive}",
        },
    )


@router.delete("/pit/{session_id}")
async def close_pit_session(session_id: str, es: ESManager = Depends(get_es)) -> dict[str, Any]:
    start = time.perf_counter()
    closed = await es.close_pit(session_id)
    if not closed:
        raise AppError(
            "session_expired",
            "PIT session not found or expired. Open a new session and retry.",
        )
    return envelope(
        {"session_id": session_id, "closed": True},
        index=settings.index_rera,
        total=1,
        returned=1,
        wall_ms=now_ms(start),
        query_used={"method": "DELETE", "path": "/_pit"},
    )


@router.get("/projects/export")
async def export_projects(
    limit: int = MAX_EXPORT_LIMIT,
    es: ESManager = Depends(get_es),
) -> StreamingResponse:
    if not isinstance(limit, int) or limit < 1 or limit > MAX_EXPORT_LIMIT:
        raise AppError("invalid_request", f"limit must be between 1 and {MAX_EXPORT_LIMIT}.")
    try:
        pit_id = (
            await es.client.open_point_in_time(
                index=settings.index_rera, keep_alive=settings.pit_keep_alive
            )
        ).body["id"]
    except Exception:  # noqa: BLE001
        raise AppError("es_unavailable", "Could not open a PIT for export.", status_code=502)
    headers = {
        "Content-Disposition": 'attachment; filename="gujrat_rera_projects.csv"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(_export_rows(es, pit_id, limit), media_type="text/csv", headers=headers)


# -- projects --------------------------------------------------------------
def _shape_hit(hit: dict[str, Any]) -> dict[str, Any]:
    source = hit.get("_source") or {}
    shaped = {"_id": hit.get("_id"), "_score": hit.get("_score")}
    shaped.update(source)
    shaped["highlight"] = hit.get("highlight") or {}
    return shaped


@router.get("/projects/search")
async def search_projects(
    q: str | None = None,
    district: str | None = None,
    taluka: str | None = None,
    project_type: str | None = None,
    project_status: str | None = None,
    promoter: str | None = None,
    reg_no: str | None = None,
    price: str | None = None,
    price_prefix: str | None = None,
    start_from: str | None = None,
    start_to: str | None = None,
    end_from: str | None = None,
    end_to: str | None = None,
    min_documents: int | None = None,
    max_documents: int | None = None,
    scrape_complete: bool | None = None,
    docs_downloaded: bool | None = None,
    sort: str | None = None,
    page: int = 1,
    size: int = 20,
    es: ESManager = Depends(get_es),
) -> dict[str, Any]:
    body = build_project_search(
        q=q,
        district=district,
        taluka=taluka,
        project_type=project_type,
        project_status=project_status,
        promoter=promoter,
        reg_no=reg_no,
        price=price,
        price_prefix=price_prefix,
        start_from=start_from,
        start_to=start_to,
        end_from=end_from,
        end_to=end_to,
        min_documents=min_documents,
        max_documents=max_documents,
        scrape_complete=scrape_complete,
        docs_downloaded=docs_downloaded,
        sort=sort,
        page=page,
        size=size,
    )
    start = time.perf_counter()
    resp = (
        await es.client.search(
            index=settings.index_rera,
            size=body["size"],
            from_=body["from"],
            track_total_hits=body["track_total_hits"],
            source_includes=body["_source"],
            query=body["query"],
            sort=body["sort"],
            highlight=body["highlight"],
        )
    ).body
    wall = now_ms(start)
    hits = (resp.get("hits") or {}).get("hits") or []
    total = ((resp.get("hits") or {}).get("total") or {}).get("value")
    data = {"hits": [_shape_hit(hit) for hit in hits]}
    return envelope(
        data,
        index=settings.index_rera,
        total=total,
        returned=len(hits),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


@router.get("/projects/suggest")
async def suggest_projects(
    q: str = "",
    size: int = 8,
    es: ESManager = Depends(get_es),
) -> dict[str, Any]:
    body = build_suggest(q, size)
    start = time.perf_counter()
    resp = (
        await es.client.search(
            index=settings.index_rera,
            size=body["size"],
            source_includes=body["_source"],
            query=body["query"],
            sort=body["sort"],
        )
    ).body
    wall = now_ms(start)
    hits = (resp.get("hits") or {}).get("hits") or []
    suggestions = []
    for hit in hits:
        source = hit.get("_source") or {}
        suggestions.append(
            {
                "_id": hit.get("_id"),
                "projectId": source.get("projectId"),
                "project_name": source.get("project_name"),
                "district": source.get("district"),
                "project_type": source.get("project_type"),
            }
        )
    return envelope(
        {"suggestions": suggestions},
        index=settings.index_rera,
        total=len(suggestions),
        returned=len(suggestions),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


@router.get("/projects/facets")
async def project_facets(es: ESManager = Depends(get_es)) -> dict[str, Any]:
    body = build_facets()
    start = time.perf_counter()
    resp = (
        await es.client.search(
            index=settings.index_rera,
            size=0,
            track_total_hits=False,
            aggs=body["aggs"],
        )
    ).body
    wall = now_ms(start)
    aggs = resp.get("aggregations") or {}
    return envelope(
        {"facets": aggs},
        index=settings.index_rera,
        total=None,
        returned=len(aggs),
        es_took_ms=resp.get("took"),
        wall_ms=wall,
        query_used={"method": "POST", "path": f"/{settings.index_rera}/_search", "body": body},
    )


# NOTE: keep this dynamic route LAST among /projects/* so static routes win.
@router.get("/projects/{project_id}")
async def get_project(project_id: str, es: ESManager = Depends(get_es)) -> dict[str, Any]:
    start = time.perf_counter()
    via = "get_doc"
    try:
        resp = (await es.client.get(index=settings.index_rera, id=project_id)).body
        source = resp.get("_source")
    except NotFoundError:
        via = "term_query"
        body = build_project_id_query(project_id)
        fallback = (
            await es.client.search(
                index=settings.index_rera,
                size=1,
                track_total_hits=False,
                query=body["query"],
            )
        ).body
        hits = (fallback.get("hits") or {}).get("hits") or []
        if not hits:
            raise AppError("not_found", f"Project '{project_id}' was not found.", status_code=404)
        source = hits[0].get("_source") or {}

    wall = now_ms(start)
    if not source:
        raise AppError("not_found", f"Project '{project_id}' was not found.", status_code=404)

    core = {key: value for key, value in source.items() if key not in DISABLED_OBJECTS}
    sections = extract_sections(source)
    data = {"project": core, "sections": sections, "raw": source, "lookup": via}
    return envelope(
        data,
        index=settings.index_rera,
        total=1,
        returned=1,
        wall_ms=wall,
        query_used={
            "method": "GET",
            "path": f"/{settings.index_rera}/_doc/{project_id}",
            "fallback": "term projectId" if via == "term_query" else None,
        },
    )
