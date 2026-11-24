"""Elasticsearch client manager: singleton client, degraded discovery,
capability detection and the server-side Point-in-Time session registry.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from elasticsearch import AsyncElasticsearch

from .config import Settings, settings as default_settings
from .schemas import DISABLED_OBJECTS, AppError

logger = logging.getLogger("rera.es")

CAT_INDEX_COLUMNS = ["index", "health", "status", "docs.count", "store.size", "pri", "rep"]


def _safe_reason(exc: BaseException) -> str:
    """A short, credential-free reason for a degraded discovery call."""
    status = getattr(exc, "status_code", None)
    name = exc.__class__.__name__
    return f"{name} (HTTP {status})" if status else name


def field_caps_types(field_caps: dict[str, Any] | None) -> dict[str, str]:
    """Flatten ``_field_caps`` into ``{field: type}``."""
    out: dict[str, str] = {}
    fields = (field_caps or {}).get("fields") or {}
    for name, inner in fields.items():
        if isinstance(inner, dict) and inner:
            out[name] = next(iter(inner.keys()))
    return out


def flatten_mapping(properties: dict[str, Any] | None, prefix: str = "") -> list[dict[str, Any]]:
    """Turn a nested mapping into a flat list, flagging ``enabled: false`` objects."""
    flat: list[dict[str, Any]] = []
    for name, spec in (properties or {}).items():
        field = f"{prefix}{name}"
        if not isinstance(spec, dict):
            continue
        if spec.get("enabled") is False:
            flat.append(
                {"field": field, "type": spec.get("type", "object"), "indexed": False, "enabled": False}
            )
            continue
        if isinstance(spec.get("properties"), dict):
            flat.append({"field": field, "type": spec.get("type", "object"), "indexed": True, "enabled": True})
            flat.extend(flatten_mapping(spec["properties"], field + "."))
        else:
            flat.append(
                {"field": field, "type": spec.get("type", "unknown"), "indexed": True, "enabled": True}
            )
    return flat


def compute_capabilities(
    mapping_properties: dict[str, Any] | None,
    field_caps: dict[str, Any] | None,
    cluster_health: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine ``_mapping`` (display-only objects) and ``_field_caps`` (queryable fields)."""
    types = field_caps_types(field_caps)
    flat = flatten_mapping(mapping_properties)
    map_types = {f["field"]: f["type"] for f in flat if f["indexed"]}

    def ftype(name: str) -> str | None:
        return types.get(name) or map_types.get(name)

    def has(name: str) -> bool:
        return ftype(name) is not None

    def is_type(name: str, *values: str) -> bool:
        return ftype(name) in values

    tracked = [
        "projectId",
        "project_name",
        "project_name.keyword",
        "promoter_name",
        "promoter_name.keyword",
        "district",
        "taluka",
        "project_type",
        "project_status",
        "reg_no",
        "price",
        "start_date",
        "end_date",
        "page_url",
        "scrape_status.complete",
        "scrape_status.docs_downloaded",
        "scrape_status.documents",
        "scrape_status.errors",
        "scrape_status.scraped_at",
    ]
    fields = {
        name: {"present": has(name), "type": ftype(name), "queryable": has(name)} for name in tracked
    }

    disabled_present = {
        name: any(f["field"] == name and not f["indexed"] for f in flat) for name in DISABLED_OBJECTS
    }

    def feature(available: bool, reason: str, requires: list[str]) -> dict[str, Any]:
        return {"available": bool(available), "reason": None if available else reason, "requires": requires}

    features = {
        "full_text_search": feature(
            is_type("project_name", "text"), "project_name (text) is missing.", ["project_name"]
        ),
        "suggest": feature(
            is_type("project_name", "text"), "project_name (text) is missing.", ["project_name"]
        ),
        "promoter_search": feature(
            is_type("promoter_name", "text"), "promoter_name (text) is missing.", ["promoter_name"]
        ),
        "filters": feature(
            all(is_type(f, "keyword") for f in ("district", "taluka", "project_type", "project_status")),
            "One or more keyword facet fields are missing.",
            ["district", "taluka", "project_type", "project_status"],
        ),
        "price_filter": feature(is_type("price", "keyword"), "price (keyword) is missing.", ["price"]),
        "date_filters": feature(
            is_type("start_date", "date") and is_type("end_date", "date"),
            "start_date / end_date (date) are missing.",
            ["start_date", "end_date"],
        ),
        "scrape_filters": feature(
            is_type("scrape_status.complete", "boolean") and is_type("scrape_status.documents", "integer"),
            "scrape_status boolean/integer fields are missing.",
            ["scrape_status.complete", "scrape_status.documents"],
        ),
        "detail_sections": feature(
            all(disabled_present.values()),
            "One or more enabled:false section objects are missing from the mapping.",
            list(DISABLED_OBJECTS),
        ),
        "boundary_map": feature(
            all(is_type(f, "keyword") for f in ("district", "taluka", "project_type", "project_status"))
            and bool(disabled_present.get("Project Profile")),
            "Indexed filters or Project Profile.Map Location source data are missing.",
            ["district", "taluka", "project_type", "project_status", "Project Profile"],
        ),
        "native_geo_dsl": feature(
            False,
            "No geo_point or geo_shape fields are indexed; read-only mode forbids mapping changes.",
            [],
        ),
        "analytics": feature(
            all(is_type(f, "keyword") for f in ("district", "taluka", "project_type", "project_status")),
            "Aggregation keyword fields are missing.",
            ["district", "taluka", "project_type", "project_status"],
        ),
        "data_quality": feature(
            all(is_type(f, "keyword") for f in ("price", "district", "taluka")),
            "Quality-check keyword fields are missing.",
            ["price", "district", "taluka"],
        ),
        "pagination": feature(is_type("projectId", "long"), "projectId (long) sort key is missing.", ["projectId"]),
        "sorting": feature(
            is_type("project_name.keyword", "keyword") and is_type("projectId", "long"),
            "Sortable keyword fields are missing.",
            ["project_name.keyword", "projectId"],
        ),
        "console": feature(True, "", []),
    }

    health = cluster_health or {}
    status = health.get("status")
    single_node = health.get("number_of_nodes") == 1
    unassigned = health.get("unassigned_shards")
    cluster = {
        "status": status,
        "single_node": single_node,
        "unassigned_shards": unassigned,
        "active_primary_shards": health.get("active_primary_shards"),
        "yellow_explanation": (
            "Single-node cluster: a 1-primary/1-replica index cannot allocate its replica on the only "
            "node, so the cluster reports yellow with unassigned replica shards. This is expected."
            if status == "yellow"
            else None
        ),
    }

    return {
        "fields": fields,
        "features": features,
        "disabled_objects": disabled_present,
        "cluster": cluster,
    }


@dataclass
class PitSession:
    """A browser-facing PIT handle mapped to an Elasticsearch PIT id."""

    session_id: str
    pit_id: str
    index: str
    keep_alive: str
    expires_at: float


class ESManager:
    """Owns the single AsyncElasticsearch client, cached discovery and PIT registry."""

    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or default_settings
        self.client = self._build_client()
        self._pits: dict[str, PitSession] = {}
        self.discovery: dict[str, Any] = {
            "ready": False,
            "info": None,
            "health": None,
            "index_row": None,
            "mapping": None,
            "field_caps": None,
            "fields": [],
            "capabilities": {},
            "errors": {},
            "discovered_at": None,
        }

    def _build_client(self) -> AsyncElasticsearch:
        s = self.settings
        kwargs: dict[str, Any] = {
            "hosts": [s.es_url],
            "request_timeout": s.es_timeout_seconds,
            "connections_per_node": s.es_max_connections,
            "verify_certs": s.es_verify_certs,
        }
        if s.es_api_key:
            kwargs["api_key"] = s.es_api_key
        elif s.es_username:
            kwargs["basic_auth"] = (s.es_username, s.es_password)
        return AsyncElasticsearch(**kwargs)

    # -- discovery ---------------------------------------------------------
    async def discover(self) -> dict[str, Any]:
        """Degraded discovery: every call is isolated so ES-down never crashes startup."""
        s = self.settings
        errors: dict[str, str] = {}
        info = health = row = mapping = field_caps = None

        try:
            info = (await self.client.info()).body
        except Exception as exc:  # noqa: BLE001 - intentionally degraded
            errors["info"] = _safe_reason(exc)
        try:
            health = (await self.client.cluster.health()).body
        except Exception as exc:  # noqa: BLE001
            errors["cluster_health"] = _safe_reason(exc)
        try:
            rows = (
                await self.client.cat.indices(format="json", h=CAT_INDEX_COLUMNS, index=s.index_rera)
            ).body
            row = rows[0] if rows else None
        except Exception as exc:  # noqa: BLE001
            errors["cat_indices"] = _safe_reason(exc)
        try:
            body = (await self.client.indices.get_mapping(index=s.index_rera)).body
            mapping = (body.get(s.index_rera) or {}).get("mappings") or {}
        except Exception as exc:  # noqa: BLE001
            errors["mapping"] = _safe_reason(exc)
        try:
            field_caps = (await self.client.field_caps(index=s.index_rera, fields="*")).body
        except Exception as exc:  # noqa: BLE001
            errors["field_caps"] = _safe_reason(exc)

        mapping_properties = (mapping or {}).get("properties") or {}
        capabilities = (
            compute_capabilities(mapping_properties, field_caps, health)
            if (mapping_properties or field_caps)
            else {}
        )

        self.discovery = {
            "ready": health is not None,
            "info": info,
            "health": health,
            "index_row": row,
            "mapping": mapping,
            "field_caps": field_caps,
            "fields": flatten_mapping(mapping_properties),
            "capabilities": capabilities,
            "errors": errors,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.discovery

    @property
    def index_present(self) -> bool:
        return self.discovery.get("index_row") is not None

    # -- PIT registry ------------------------------------------------------
    def _prune_pits(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._pits.items() if v.expires_at <= now]
        for key in expired:
            self._pits.pop(key, None)

    def _touch(self, session: PitSession) -> None:
        session.expires_at = time.monotonic() + self.settings.pit_ttl_seconds

    async def open_pit(self, index: str | None = None, keep_alive: str | None = None) -> PitSession:
        index = index or self.settings.index_rera
        keep_alive = keep_alive or self.settings.pit_keep_alive
        response = await self.client.open_point_in_time(index=index, keep_alive=keep_alive)
        pit_id = response.body["id"]
        session = PitSession(
            session_id=uuid.uuid4().hex,
            pit_id=pit_id,
            index=index,
            keep_alive=keep_alive,
            expires_at=time.monotonic() + self.settings.pit_ttl_seconds,
        )
        self._pits[session.session_id] = session
        return session

    def get_pit(self, session_id: str) -> PitSession:
        self._prune_pits()
        session = self._pits.get(session_id)
        if session is None:
            raise AppError(
                "session_expired",
                "PIT session not found or expired. Open a new session and retry.",
                status_code=400,
            )
        return session

    def update_pit(self, session_id: str, response_body: dict[str, Any] | None) -> PitSession | None:
        session = self._pits.get(session_id)
        if session is None:
            return None
        new_id = (response_body or {}).get("pit_id")
        if new_id:
            session.pit_id = new_id
        self._touch(session)
        return session

    async def delete_pit_id(self, pit_id: str) -> None:
        try:
            await self.client.close_point_in_time(id=pit_id)
        except Exception as exc:  # noqa: BLE001 - closing is best-effort
            logger.debug("PIT close failed: %s", _safe_reason(exc))

    async def close_pit(self, session_id: str) -> bool:
        session = self._pits.pop(session_id, None)
        if session is None:
            return False
        await self.delete_pit_id(session.pit_id)
        return True

    async def close(self) -> None:
        for session in list(self._pits.values()):
            await self.delete_pit_id(session.pit_id)
        self._pits.clear()
        try:
            await self.client.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Client close failed: %s", _safe_reason(exc))
