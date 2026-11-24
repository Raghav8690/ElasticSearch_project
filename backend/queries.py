"""Pure Elasticsearch Query DSL builders. No HTTP calls happen here.

Every list/search body uses ``bool.filter`` for exact/range/boolean constraints
and ``must`` only for full-text relevance. ``price`` is a keyword, so only
``term``/``prefix`` are ever emitted for it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from .schemas import CORE_FIELDS, DISABLED_OBJECTS, AppError

# Sentinel markers used instead of raw HTML tags. The browser splits on these
# and builds <mark> DOM nodes, so no Elasticsearch text is ever injected as HTML.
HIGHLIGHT_PRE = "[[HL]]"
HIGHLIGHT_POST = "[[/HL]]"

MAX_SIZE = 100
MAX_RESULT_WINDOW = 10_000
MAX_EXPORT_LIMIT = 100_000
MAX_BOUNDARY_SIZE = 10_000
EXPORT_BATCH = 100
PAGE_SOURCE = ["projectId", "project_name", "district", "project_type", "project_status", "price"]
BOUNDARY_SOURCE_PATH = "Project Profile.Map Location"
BOUNDARY_SOURCE = [
    "projectId",
    "project_name",
    "promoter_name",
    "district",
    "taluka",
    "project_type",
    "project_status",
    "reg_no",
    "page_url",
    BOUNDARY_SOURCE_PATH,
]
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

ADDRESS_SOURCE_PATH = "Project Profile.Project Overview.Project Address"
SEARCH_TEXT_FIELDS = [
    "project_name^4",
    "promoter_name^3",
    "district^3",
    "taluka^2",
    "project_type^3",
    "reg_no^2",
    "page_url^1",
]
QUERY_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _invalid(message: str) -> AppError:
    return AppError("invalid_request", message, status_code=400)


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def query_tokens(q: str | None) -> list[str]:
    return [token.lower() for token in QUERY_TOKEN_RE.findall(q or "") if len(token) >= 2]


def _term_clause(field: str, value: Any, *, boost: float | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"value": value, "case_insensitive": True}
    if boost is not None:
        spec["boost"] = boost
    return {"term": {field: spec}}


def _prefix_clause(field: str, value: Any, *, boost: float | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"value": value, "case_insensitive": True}
    if boost is not None:
        spec["boost"] = boost
    return {"prefix": {field: spec}}


def _text_filter(field: str, value: Any) -> dict[str, Any]:
    return {
        "bool": {
            "should": [_term_clause(field, value), _prefix_clause(field, value)],
            "minimum_should_match": 1,
        }
    }


def extract_project_address(source: dict[str, Any] | None) -> str:
    profile = (source or {}).get("Project Profile") or {}
    if not isinstance(profile, dict):
        return ""
    overview = profile.get("Project Overview") or {}
    if not isinstance(overview, dict):
        return ""
    return str(overview.get("Project Address") or "")


def address_match_score(address: str | None, q: str | None) -> float:
    address_text = normalize_text(address)
    query_text = normalize_text(q)
    tokens = query_tokens(q)
    if not address_text or not tokens:
        return 0.0
    matched = sum(1 for token in tokens if token in address_text)
    coverage = matched / len(tokens)
    score = matched * 10.0 + coverage * 20.0
    if query_text and query_text in address_text:
        score += 60.0
    return round(score, 2)


def suggest_match_label(q: str | None, source: dict[str, Any] | None) -> str:
    text = normalize_text(q)
    data = source or {}
    checks = [
        ("projectId", "ID"),
        ("reg_no", "Reg no"),
        ("project_name", "Project"),
        ("promoter_name", "Promoter"),
        ("district", "District"),
        ("project_type", "Type"),
    ]
    for field, label in checks:
        value = data.get(field)
        if value is not None and text and text in normalize_text(value):
            return label
    return "Match"


def parse_search_sort(sort: str | None, has_query: bool) -> list[dict[str, Any]]:
    if sort:
        return parse_sort(sort)
    if has_query:
        return [{"_score": {"order": "desc"}}, {"projectId": {"order": "asc"}}]
    return parse_sort(None)


def _build_relevance_clause(q: str) -> dict[str, Any]:
    text = q.strip()
    should: list[dict[str, Any]] = []
    if text.isdigit():
        should.append({"term": {"projectId": {"value": int(text), "boost": 500}}})

    exact_fields = [
        ("project_name.keyword", 140),
        ("promoter_name.keyword", 100),
        ("district", 70),
        ("taluka", 50),
        ("project_type", 140),
        ("reg_no", 100),
    ]
    for field, boost in exact_fields:
        should.append(_term_clause(field, text, boost=boost))

    prefix_fields = [
        ("project_name.keyword", 20),
        ("promoter_name.keyword", 16),
        ("district", 12),
        ("taluka", 10),
        ("project_type", 20),
        ("reg_no", 16),
    ]
    for field, boost in prefix_fields:
        should.append(_prefix_clause(field, text, boost=boost))

    should.append({"match_phrase": {"project_name": {"query": text, "boost": 90}}})
    should.append({"match_phrase": {"promoter_name": {"query": text, "boost": 70}}})

    token_count = len(query_tokens(text))
    minimum_tokens = 1 if token_count <= 1 else max(2, token_count - 1)
    should.append(
        {
            "multi_match": {
                "query": text,
                "fields": SEARCH_TEXT_FIELDS,
                "type": "cross_fields",
                "operator": "or",
                "minimum_should_match": minimum_tokens,
                "lenient": True,
            }
        }
    )
    return {"should": should, "minimum_should_match": 1}


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
        or not (1 <= len(value) <= 2)
        or not all(isinstance(x, int) and not isinstance(x, bool) for x in value)
    ):
        raise _invalid("cursor must be a JSON array containing integer sort values.")
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
        filters.append(_text_filter("district", district))
    if taluka:
        filters.append(_text_filter("taluka", taluka))
    if project_type:
        filters.append(_text_filter("project_type", project_type))
    if project_status:
        filters.append(_text_filter("project_status", project_status))
    if promoter:
        filters.append(_text_filter("promoter_name.keyword", promoter))
    if reg_no:
        filters.append(_text_filter("reg_no", reg_no))
    if price:
        filters.append(_text_filter("price", price))
    if price_prefix:
        filters.append(_prefix_clause("price", price_prefix))

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
    has_query = bool(q and q.strip())
    if has_query:
        bool_query.update(_build_relevance_clause(q or ""))

    query: dict[str, Any]
    if filters or has_query:
        query = {"bool": bool_query}
    else:
        query = {"match_all": {}}

    return {
        "size": size,
        "from": offset,
        "track_total_hits": True,
        "_source": list(CORE_FIELDS),
        "query": query,
        "sort": parse_search_sort(sort, has_query),
        "highlight": {
            "pre_tags": [HIGHLIGHT_PRE],
            "post_tags": [HIGHLIGHT_POST],
            "fields": {"project_name": {}, "promoter_name": {}},
        },
    }


def build_boundary_query(
    *,
    q: str | None = None,
    district: str | None = None,
    taluka: str | None = None,
    project_type: str | None = None,
    project_status: str | None = None,
    promoter: str | None = None,
    reg_no: str | None = None,
    size: int = 1000,
    after: int | None = None,
) -> dict[str, Any]:
    if not isinstance(size, int) or size < 1 or size > MAX_BOUNDARY_SIZE:
        raise _invalid(f"size must be between 1 and {MAX_BOUNDARY_SIZE}.")
    if after is not None and (not isinstance(after, int) or isinstance(after, bool) or after < 0):
        raise _invalid("after must be a non-negative projectId.")

    filters: list[dict[str, Any]] = []
    if district:
        filters.append(_text_filter("district", district))
    if taluka:
        filters.append(_text_filter("taluka", taluka))
    if project_type:
        filters.append(_text_filter("project_type", project_type))
    if project_status:
        filters.append(_text_filter("project_status", project_status))
    if promoter:
        filters.append(_text_filter("promoter_name.keyword", promoter))
    if reg_no:
        filters.append(_text_filter("reg_no", reg_no))

    bool_query: dict[str, Any] = {"filter": filters}
    has_query = bool(q and q.strip())
    if has_query:
        bool_query.update(_build_relevance_clause(q or ""))
    query: dict[str, Any]
    if filters or has_query:
        query = {"bool": bool_query}
    else:
        query = {"match_all": {}}

    body: dict[str, Any] = {
        "size": size,
        "track_total_hits": True,
        "_source": list(BOUNDARY_SOURCE),
        "query": query,
        "sort": [{"projectId": "asc"}],
    }
    if after is not None:
        body["search_after"] = [after]
    return body


def build_suggest(q: str, size: int = 8) -> dict[str, Any]:
    """Multi-field prefix autocomplete with score-first ordering."""
    text = (q or "").strip()
    if len(text) < 2:
        raise _invalid("Suggest requires at least 2 characters.")
    validate_size(size, maximum=20)
    should: list[dict[str, Any]] = []
    if text.isdigit():
        should.append({"term": {"projectId": {"value": int(text), "boost": 100}}})
    should.extend(
        [
            {"match_phrase_prefix": {"project_name": {"query": text, "boost": 8, "max_expansions": 20}}},
            {"match_phrase_prefix": {"promoter_name": {"query": text, "boost": 5, "max_expansions": 20}}},
            _prefix_clause("project_name.keyword", text, boost=6),
            _prefix_clause("promoter_name.keyword", text, boost=4),
            _prefix_clause("district", text, boost=4),
            _prefix_clause("taluka", text, boost=3),
            _prefix_clause("project_type", text, boost=3),
            _prefix_clause("reg_no", text, boost=3),
        ]
    )
    return {
        "size": size,
        "_source": [
            "projectId",
            "project_name",
            "promoter_name",
            "district",
            "taluka",
            "project_type",
            "reg_no",
        ],
        "query": {"bool": {"should": should, "minimum_should_match": 1}},
        "sort": [{"_score": {"order": "desc"}}, {"projectId": {"order": "asc"}}],
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
