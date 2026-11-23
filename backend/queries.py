"""Pure Elasticsearch Query DSL builders. No HTTP calls happen here.

Every list/search body uses ``bool.filter`` for exact/range/boolean constraints
and ``must`` only for full-text relevance. ``price`` is a keyword, so only
``term``/``prefix`` are ever emitted for it.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .schemas import CORE_FIELDS, DISABLED_OBJECTS, AppError

# Sentinel markers used instead of raw <em> tags. The browser splits on these
# and builds <em> DOM nodes, so no Elasticsearch text is ever injected as HTML.
HIGHLIGHT_PRE = "[[HL]]"
HIGHLIGHT_POST = "[[/HL]]"

MAX_SIZE = 100
MAX_RESULT_WINDOW = 10_000
MAX_EXPORT_LIMIT = 100_000
EXPORT_BATCH = 100
PAGE_SOURCE = ["projectId", "project_name", "district", "project_type", "project_status", "price"]
EXPORT_COLUMNS = [
    "projectId",
    "project_name",
    "reg_no",
    "district",
    "taluka",
    "promoter_name",
    "project_type",
    "project_status",
    "start_date",
    "end_date",
    "price",
    "page_url",
]

# Sortable fields (keyword/date/numeric). Anything else is rejected.
ALLOWED_SORTS = {
    "projectId",
    "project_name.keyword",
    "promoter_name.keyword",
    "district",
    "project_status",
    "project_type",
    "start_date",
    "end_date",
    "scrape_status.documents",
}


def _invalid(message: str) -> AppError:
    return AppError("invalid_request", message, status_code=400)


def validate_size(size: int, *, maximum: int = MAX_SIZE) -> int:
    if not isinstance(size, int) or size < 1 or size > maximum:
        raise _invalid(f"size must be between 1 and {maximum}.")
    return size


def validate_page(page: int, size: int) -> int:
    if not isinstance(page, int) or page < 1:
        raise _invalid("page must be a positive integer.")
    if page * size > MAX_RESULT_WINDOW:
        raise _invalid(
            "from + size must be <= 10000. Use search_after or PIT for deep pagination."
        )
    return (page - 1) * size


def to_indian_date(value: str) -> str:
    """Accept yyyy-MM-dd (UI) or dd-MM-yyyy and return dd-MM-yyyy."""
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    raise _invalid(f"Invalid date '{value}'. Use YYYY-MM-DD.")


def parse_sort(sort: str | None) -> list[dict[str, str]]:
    if not sort:
        return [{"projectId": "asc"}]
    field, _, direction = sort.partition(":")
    field = field.strip()
    direction = (direction or "asc").strip().lower()
    if field not in ALLOWED_SORTS:
        raise _invalid(
            "Unsupported sort field. Allowed: " + ", ".join(sorted(ALLOWED_SORTS)) + "."
        )
    if direction not in ("asc", "desc"):
        raise _invalid("sort direction must be 'asc' or 'desc'.")
    sorts: list[dict[str, str]] = [{field: direction}]
    if field != "projectId":
        sorts.append({"projectId": direction})
    return sorts


def build_page(page: int, size: int) -> dict[str, Any]:
    size = validate_size(size)
    from_ = validate_page(page, size)
    return {
        "from": from_,
        "size": size,
        "track_total_hits": False,
        "sort": [{"projectId": "asc"}],
        "_source": list(PAGE_SOURCE),
        "query": {"match_all": {}},
    }


def parse_cursor(cursor: str | None) -> list[Any]:
    if not cursor:
        return []
    try:
        value = json.loads(cursor)
    except (TypeError, ValueError):
        raise _invalid("cursor must be a JSON array of the last hit's sort values.")
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not isinstance(value[0], int)
        or isinstance(value[0], bool)
    ):
        raise _invalid("cursor must be a JSON array containing one integer projectId.")
    return value


def build_search_after(cursor: str | None, size: int) -> dict[str, Any]:
    size = validate_size(size)
    body: dict[str, Any] = {
        "size": size,
        "track_total_hits": False,
        "sort": [{"projectId": "asc"}],
        "_source": list(PAGE_SOURCE),
        "query": {"match_all": {}},
    }
    parsed = parse_cursor(cursor)
    if parsed:
        body["search_after"] = parsed
    return body


def _date_range(gte: str | None, lte: str | None) -> dict[str, Any] | None:
    if not gte and not lte:
        return None
    bounds: dict[str, Any] = {"format": "dd-MM-yyyy"}
    if gte:
        bounds["gte"] = to_indian_date(gte)
    if lte:
        bounds["lte"] = to_indian_date(lte)
    return bounds


def build_project_search(
    *,
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
) -> dict[str, Any]:
    """Build the optimized project-search body. Empty filters are omitted."""
    validate_size(size)
    offset = validate_page(page, size)

    filters: list[dict[str, Any]] = []
    if district:
        filters.append({"term": {"district": district}})
    if taluka:
        filters.append({"term": {"taluka": taluka}})
    if project_type:
        filters.append({"term": {"project_type": project_type}})
    if project_status:
        filters.append({"term": {"project_status": project_status}})
    if promoter:
        filters.append({"term": {"promoter_name.keyword": promoter}})
    if reg_no:
        filters.append({"term": {"reg_no": reg_no}})
    if price:
        filters.append({"term": {"price": price}})
    if price_prefix:
        filters.append({"prefix": {"price": price_prefix}})

    start_range = _date_range(start_from, start_to)
    if start_range:
        filters.append({"range": {"start_date": start_range}})
    end_range = _date_range(end_from, end_to)
    if end_range:
        filters.append({"range": {"end_date": end_range}})

    if min_documents is not None or max_documents is not None:
        bounds: dict[str, Any] = {}
        if min_documents is not None:
            bounds["gte"] = min_documents
        if max_documents is not None:
            bounds["lte"] = max_documents
        filters.append({"range": {"scrape_status.documents": bounds}})

    if scrape_complete is not None:
        filters.append({"term": {"scrape_status.complete": scrape_complete}})
    if docs_downloaded is not None:
        filters.append({"term": {"scrape_status.docs_downloaded": docs_downloaded}})

    bool_query: dict[str, Any] = {"filter": filters}
    if q and q.strip():
        bool_query["must"] = [
            {
                "multi_match": {
                    "query": q.strip(),
                    "fields": ["project_name^3", "promoter_name^1"],
                    "type": "best_fields",
                }
            }
        ]

    query: dict[str, Any]
    if filters or bool_query.get("must"):
        query = {"bool": bool_query}
    else:
        query = {"match_all": {}}

    return {
        "size": size,
        "from": offset,
        "track_total_hits": True,
        "_source": list(CORE_FIELDS),
        "query": query,
        "sort": parse_sort(sort),
        "highlight": {
            "pre_tags": [HIGHLIGHT_PRE],
            "post_tags": [HIGHLIGHT_POST],
            "fields": {"project_name": {}, "promoter_name": {}},
        },
    }


def build_suggest(q: str, size: int = 8) -> dict[str, Any]:
    """Prefix autocomplete via match_phrase_prefix (no dedicated suggest field)."""
    text = (q or "").strip()
    if len(text) < 2:
        raise _invalid("Suggest requires at least 2 characters.")
    validate_size(size, maximum=20)
    return {
        "size": size,
        "_source": ["projectId", "project_name", "district", "project_type"],
        "query": {"match_phrase_prefix": {"project_name": {"query": text, "max_expansions": 20}}},
        "sort": [{"project_name.keyword": "asc"}],
    }


def build_facets() -> dict[str, Any]:
    """Aggregations for filter dropdowns and the quality panel."""
    return {
        "size": 0,
        "track_total_hits": False,
        "aggs": {
            "districts": {"terms": {"field": "district", "size": 100}},
            "talukas": {"terms": {"field": "taluka", "size": 50}},
            "project_types": {"terms": {"field": "project_type", "size": 20}},
            "project_statuses": {"terms": {"field": "project_status", "size": 20}},
            "promoters": {"terms": {"field": "promoter_name.keyword", "size": 20}},
            "prices": {"terms": {"field": "price", "size": 15}},
            "scrape_complete": {"terms": {"field": "scrape_status.complete", "size": 2}},
            "docs_downloaded": {"terms": {"field": "scrape_status.docs_downloaded", "size": 2}},
            "documents_stats": {"stats": {"field": "scrape_status.documents"}},
        },
    }


def build_project_id_query(project_id: str) -> dict[str, Any]:
    """Fallback lookup when GET _doc/{id} misses."""
    try:
        value: Any = int(project_id)
    except (TypeError, ValueError):
        value = project_id
    return {"size": 1, "track_total_hits": False, "query": {"term": {"projectId": value}}}


def extract_sections(source: dict[str, Any]) -> dict[str, Any]:
    """Extract the five display-only objects for the detail section cards."""
    sections: dict[str, Any] = {}
    for name in DISABLED_OBJECTS:
        if name not in source:
            continue
        value = source[name]
        if isinstance(value, dict):
            subsections = list(value.keys())
        elif isinstance(value, list):
            subsections = []
        else:
            subsections = []
        sections[name] = {
            "indexed": False,
            "present": True,
            "type": "array" if isinstance(value, list) else "object",
            "subsections": subsections,
            "data": value,
        }
    return sections


def build_analytics_overview() -> dict[str, Any]:
    """Categorical + metric aggregations for the Analytics charts."""
    return {
        "size": 0,
        "track_total_hits": False,
        "aggs": {
            "districts": {"terms": {"field": "district", "size": 20}},
            "talukas": {"terms": {"field": "taluka", "size": 20}},
            "project_types": {"terms": {"field": "project_type", "size": 20}},
            "project_statuses": {"terms": {"field": "project_status", "size": 20}},
            "top_promoters": {"terms": {"field": "promoter_name.keyword", "size": 10}},
            "documents_stats": {"stats": {"field": "scrape_status.documents"}},
            "docs_downloaded": {"terms": {"field": "scrape_status.docs_downloaded", "size": 2}},
        },
    }


def build_analytics_dates() -> dict[str, Any]:
    """Yearly date histograms for registration timelines."""
    return {
        "size": 0,
        "track_total_hits": False,
        "aggs": {
            "start_years": {
                "date_histogram": {
                    "field": "start_date",
                    "calendar_interval": "year",
                    "format": "yyyy",
                    "min_doc_count": 1,
                }
            },
            "end_years": {
                "date_histogram": {
                    "field": "end_date",
                    "calendar_interval": "year",
                    "format": "yyyy",
                    "min_doc_count": 1,
                }
            },
        },
    }


def build_quality_scrape() -> dict[str, Any]:
    """Missing-field, scrape-flag and casing-check aggregations."""
    return {
        "size": 0,
        "track_total_hits": True,
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
            "talukas": {"terms": {"field": "taluka", "size": 100}},
        },
    }


def _group_collisions(buckets: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for bucket in buckets or []:
        key = bucket.get("key")
        if not isinstance(key, str):
            continue
        groups.setdefault(key.strip().lower(), []).append(
            {"key": key, "doc_count": bucket.get("doc_count") or 0}
        )
    collisions = []
    for normalized, variants in groups.items():
        if len({v["key"] for v in variants}) > 1:
            collisions.append(
                {
                    "normalized": normalized,
                    "variants": sorted(variants, key=lambda v: v["key"]),
                    "total": sum(v["doc_count"] for v in variants),
                }
            )
    collisions.sort(key=lambda c: c["total"], reverse=True)
    return collisions


def compute_casing_collisions(
    district_buckets: list[dict[str, Any]] | None,
    taluka_buckets: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Group raw buckets by case/space-insensitive key and surface conflicts."""
    return {
        "districts": _group_collisions(district_buckets),
        "talukas": _group_collisions(taluka_buckets),
    }
