import pytest
import httpx
from backend.main import app, lifespan


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_all_routes_and_root():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Root
            r = await client.get("/")
            assert r.status_code == 200
            assert "<!DOCTYPE html>" in r.text

            # 2. Health
            r = await client.get("/api/health")
            assert r.status_code == 200
            assert "cluster" in r.json()
            assert "version" in r.json()

            # 3. Config
            r = await client.get("/api/config")
            assert r.status_code == 200
            assert r.json()["data"]["index"] == "gujrat_rera_data"

            # 4. Capabilities
            r = await client.get("/api/capabilities")
            assert r.status_code == 200
            features = r.json()["capabilities"]["features"]
            assert features["boundary_map"]["available"] is True
            assert features["native_geo_dsl"]["available"] is False

            # 5. Indices
            r = await client.get("/api/indices")
            assert r.status_code == 200

            # 6. Mapping
            r = await client.get("/api/indices/gujrat_rera_data/mapping")
            assert r.status_code == 200
            assert len(r.json()["data"]["fields"]) > 0

            # 7. Stats
            r = await client.get("/api/indices/gujrat_rera_data/stats")
            assert r.status_code == 200
            assert r.json()["data"]["docs"] == 17271

            # 8. Aliases
            r = await client.get("/api/indices/gujrat_rera_data/aliases")
            assert r.status_code == 200

            # 9. Search (Check route precedence: /projects/search must not be parsed as project_id)
            r = await client.get("/api/projects/search?size=5")
            assert r.status_code == 200
            assert "hits" in r.json()["data"]

            r = await client.get(
                "/api/projects/search",
                params={"q": "shivalik", "size": 5, "rerank_address": "false"},
            )
            assert r.status_code == 200
            rerank = r.json()["meta"]["query_used"]["rerank"]["address"]
            assert rerank["enabled"] is False
            assert "cache_age_seconds" in rerank

            r = await client.get(
                "/api/projects/search",
                params={
                    "q": "shivalik",
                    "size": 5,
                    "query_type": "match",
                    "fuzzy": "true",
                    "rerank_address": "false",
                },
            )
            assert r.status_code == 200
            mode = r.json()["meta"]["query_used"]["mode"]
            assert mode == {"query_type": "match", "fuzzy": True}
            body = r.json()["meta"]["query_used"]["body"]
            match = body["query"]["bool"]["must"][0]["match"]["project_name"]
            assert match["fuzziness"] == "AUTO"

            r = await client.get(
                "/api/projects/search",
                params={"q": "x", "query_type": "wildcard"},
            )
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"

            # 10. Suggest
            r = await client.get("/api/projects/suggest?q=shiva")
            assert r.status_code == 200
            suggestions = r.json()["data"]["suggestions"]
            assert suggestions
            assert all("id" in item and "label" in item and "match_label" in item for item in suggestions)

            # 10b. Case-insensitive exact + prefix matching
            for value in ("plot", "Plot", "PLOT", "PLot"):
                r = await client.get("/api/projects/search", params={"q": value, "size": 5})
                assert r.status_code == 200
                assert r.json()["data"]["hits"]

                r = await client.get(
                    "/api/projects/search", params={"project_type": value, "size": 5}
                )
                assert r.status_code == 200
                hits = r.json()["data"]["hits"]
                assert hits
                assert all("plot" in str(hit.get("project_type", "")).lower() for hit in hits)

                r = await client.get("/api/projects/suggest", params={"q": value})
                assert r.status_code == 200
                assert r.json()["data"]["suggestions"]

            # 11. Facets
            r = await client.get("/api/projects/facets")
            assert r.status_code == 200
            assert "facets" in r.json()["data"]

            # 11b. Boundaries (Check route precedence before /projects/{project_id})
            r = await client.get(
                "/api/projects/boundaries",
                params={"district": "Ahmedabad", "size": 3},
            )
            assert r.status_code == 200
            boundary_data = r.json()["data"]
            assert "features" in boundary_data
            assert "markers" in boundary_data
            assert boundary_data["capabilities"]["native_geo_dsl"] is False

            # 12. Detail
            r = await client.get("/api/projects/573")
            assert r.status_code == 200
            assert "sections" in r.json()["data"]

            # 13. Analytics Overview
            r = await client.get("/api/analytics/overview")
            assert r.status_code == 200

            # 14. Analytics Dates
            r = await client.get("/api/analytics/dates")
            assert r.status_code == 200

            # 15. Quality Scrape
            r = await client.get("/api/quality/scrape")
            assert r.status_code == 200
            assert "casing_collisions" in r.json()["data"]

            # 16. Pipeline Simulate
            r = await client.post("/api/quality/pipeline-simulate", json={"source": {}})
            assert r.status_code == 404
            assert r.json()["error"]["code"] == "pipeline_missing"

            # 17. Page
            r = await client.get("/api/projects/page?page=1&size=10")
            assert r.status_code == 200

            # 18. PIT
            r = await client.post("/api/pit")
            assert r.status_code == 200
            session_id = r.json()["data"]["session_id"]

            # 19. Search-After with PIT
            r = await client.get(f"/api/projects/search-after?size=5&pit=true&session={session_id}")
            assert r.status_code == 200
            assert len(r.json()["data"]["hits"]) == 5

            # 20. Close PIT
            r = await client.delete(f"/api/pit/{session_id}")
            assert r.status_code == 200

            # 21. Export
            r = await client.get("/api/projects/export?limit=3")
            assert r.status_code == 200
            assert "projectId,project_name" in r.text

            # 22. Analyze
            r = await client.post("/api/analyze", json={"text": "Hello Gujarat"})
            assert r.status_code == 200

            # 23. Ops Health
            r = await client.get("/api/ops/health")
            assert r.status_code == 200

            # 24. Ops Nodes
            r = await client.get("/api/ops/nodes")
            assert r.status_code == 200
            node = r.json()["data"]["nodes"][0]
            assert "search_rejected" in node
            assert "query_cache_hit_count" in node
            assert "request_cache_hit_count" in node

            # 25. Ops Shards
            r = await client.get("/api/ops/shards")
            assert r.status_code == 200

            # 26. Ops Slow Log
            r = await client.get("/api/ops/slowlog")
            assert r.status_code == 200
            slowlog = r.json()["data"]
            assert "entries" in slowlog
            assert "es_settings" in slowlog
            assert slowlog["count"] >= 1
            assert any(entry["route"] == "/api/projects/search" for entry in slowlog["entries"])

            # 27. Query Console
            r = await client.post("/api/query/gujrat_rera_data", json={"query": {"match_all": {}}, "size": 1})
            assert r.status_code == 200

            r = await client.post(
                "/api/query/gujrat_rera_data",
                json={"query": {"match_all": {}}, "size": 1, "profile": True},
            )
            assert r.status_code == 200
            assert "profile" in r.json()["data"]


@pytest.mark.asyncio
async def test_route_validation_edge_cases():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Invalid sort field
            r = await client.get("/api/projects/search?sort=invalid_field:asc")
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"

            # Size > 100 limit
            r = await client.get("/api/projects/search?size=101")
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"

            # Suggest q < 2 characters
            r = await client.get("/api/projects/suggest?q=a")
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"

            # Page from + size > 10000 window limit
            r = await client.get("/api/projects/page?page=501&size=20")
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"

            # Search-after missing session
            r = await client.get("/api/projects/search-after?pit=true&session=invalid_session_123")
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "session_expired"

            # Forbidden index access
            r = await client.get("/api/indices/other_index/mapping")
            assert r.status_code == 403
            assert r.json()["error"]["code"] == "forbidden"

            # Forbidden index console query
            r = await client.post("/api/query/other_index", json={"query": {"match_all": {}}})
            assert r.status_code == 403
            assert r.json()["error"]["code"] == "forbidden"

            # Console script query rejection
            r = await client.post(
                "/api/query/gujrat_rera_data",
                json={"query": {"bool": {"filter": [{"script": {"script": "doc['price'].value"}}]}}},
            )
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"
            assert "script" in r.json()["error"]["message"]

            # Invalid boundary bbox
            r = await client.get("/api/projects/boundaries", params={"bbox": "73,23,72,22"})
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"

            # Invalid boundary polygon
            r = await client.get("/api/projects/boundaries", params={"polygon": "22,72;22,72.1"})
            assert r.status_code == 400
            assert r.json()["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_boundary_search_to_centroid_and_nearby():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Typo query resolves projectId 573 (Shivalik Residences)
            r = await client.get("/api/projects/boundaries", params={"q": "shivalik recidency", "size": 10})
            assert r.status_code == 200
            data = r.json()["data"]
            items = data["features"] + data["markers"]
            assert len(items) > 0
            # Target project 573 should be among the top matches
            found_573 = any(item.get("id") == 573 for item in items)
            assert found_573, f"Expected projectId 573 in results: {[it.get('id') for it in items]}"
            # Score must be exposed on items
            assert any(item.get("score") is not None for item in items)

            # 2. Score cursor pagination
            next_after = data.get("next_after")
            if next_after:
                r_paged = await client.get(
                    "/api/projects/boundaries",
                    params={"q": "shivalik recidency", "size": 10, "after_cursor": str(next_after)},
                )
                assert r_paged.status_code == 200

            # 3. Radius filter attaches distance_km and sorts by distance
            r_radius = await client.get(
                "/api/projects/boundaries",
                params={"lat": "23.056223", "lon": "72.591239", "distance_km": "5", "size": 20},
            )
            assert r_radius.status_code == 200
            radius_data = r_radius.json()["data"]
            radius_items = radius_data["features"] + radius_data["markers"]
            assert len(radius_items) > 0
            for item in radius_items:
                assert "distance_km" in item
                assert item["distance_km"] <= 5.0
            # Distances should be in ascending order
            distances = [item["distance_km"] for item in radius_items]
            assert distances == sorted(distances)

            # 4. Incomplete radius filter returns 400
            r_bad_radius = await client.get(
                "/api/projects/boundaries",
                params={"lat": "23.056223", "distance_km": "5"},
            )
            assert r_bad_radius.status_code == 400
            assert r_bad_radius.json()["error"]["code"] == "invalid_request"
