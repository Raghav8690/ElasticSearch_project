import pytest
import httpx
from backend.main import app, lifespan


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_all_25_routes_and_root():
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
            assert "capabilities" in r.json()

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

            # 10. Suggest
            r = await client.get("/api/projects/suggest?q=shiva")
            assert r.status_code == 200
            suggestions = r.json()["data"]["suggestions"]
            assert suggestions
            assert all("id" in item and "label" in item and "match_label" in item for item in suggestions)

            # 11. Facets
            r = await client.get("/api/projects/facets")
            assert r.status_code == 200
            assert "facets" in r.json()["data"]

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

            # 25. Ops Shards
            r = await client.get("/api/ops/shards")
            assert r.status_code == 200

            # 26. Query Console
            r = await client.post("/api/query/gujrat_rera_data", json={"query": {"match_all": {}}, "size": 1})
            assert r.status_code == 200
