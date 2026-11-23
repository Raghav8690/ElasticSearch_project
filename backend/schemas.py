"""Pydantic request models, response-envelope helpers and shared constants."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# The 13 core queryable fields included by every list/search endpoint.
CORE_FIELDS: list[str] = [
    "projectId",
    "project_name",
    "promoter_name",
    "district",
    "taluka",
    "project_type",
    "project_status",
    "price",
    "reg_no",
    "start_date",
    "end_date",
    "page_url",
    "scrape_status",
]

# The five large mapping objects that are "enabled": false (stored, not indexed).
DISABLED_OBJECTS: list[str] = [
    "Project Profile",
    "Project Summary",
    "Promoters",
    "Progress & RERA Actions",
    "More Projects by The Same Developer",
]


class AppError(Exception):
    """A controlled, browser-safe application error mapped to the error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        detail: str = "redacted",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    analyzer: str | None = "standard"
    field: str | None = None


class PipelineSimulateRequest(BaseModel):
    source: dict[str, Any] = Field(default_factory=dict)
    pipeline_id: str | None = None


def envelope(
    data: Any,
    *,
    index: str,
    total: int | None = None,
    returned: int | None = None,
    es_took_ms: int | None = None,
    wall_ms: float = 0.0,
    query_used: Any = None,
) -> dict[str, Any]:
    """Wrap a payload in the standard success envelope."""
    return {
        "data": data,
        "meta": {
            "index": index,
            "total": total,
            "returned": returned,
            "es_took_ms": es_took_ms,
            "wall_ms": round(wall_ms, 2),
            "query_used": query_used,
        },
    }


def error_payload(code: str, message: str, detail: str = "redacted") -> dict[str, Any]:
    """Build the standard sanitized error envelope."""
    return {"error": {"code": code, "message": message, "detail": detail}}
