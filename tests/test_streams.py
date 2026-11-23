import pytest
import httpx
from types import SimpleNamespace
from backend.main import app, lifespan
from backend.routes import _safe_cell, _export_rows
from backend.queries import EXPORT_COLUMNS, EXPORT_BATCH


def test_safe_cell_formula_injection_defense():
    # Dangerous formula characters must be prefixed with a single quote
    assert _safe_cell("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert _safe_cell("+12345") == "'+12345"
    assert _safe_cell("-12345") == "'-12345"
    assert _safe_cell("@cmd|' /C calc'!A0") == "'@cmd|' /C calc'!A0"
    assert _safe_cell("\tTabbed") == "'\tTabbed"
    assert _safe_cell("\rReturn") == "'\rReturn"

    # Normal strings and numbers remain unmodified
    assert _safe_cell("Shivalik Residences") == "Shivalik Residences"
    assert _safe_cell(573) == 573
    assert _safe_cell(12.34) == 12.34
    assert _safe_cell(None) == ""


@pytest.mark.asyncio
async def test_csv_export_streaming():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            limit = 10
            r = await client.get(f"/api/projects/export?limit={limit}")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/csv")
            assert 'filename="gujrat_rera_projects.csv"' in r.headers["content-disposition"]

            lines = r.text.strip().split("\n")
            header = lines[0].split(",")
            assert header == EXPORT_COLUMNS
            assert len(lines) == limit + 1


@pytest.mark.asyncio
async def test_csv_export_limit_guard():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Over the 100,000 maximum cap
            r = await client.get("/api/projects/export?limit=100001")
            assert r.status_code == 400
            err = r.json().get("error", {})
            assert err.get("code") == "invalid_request"


class FakeSearchClient:
    def __init__(self):
        self.bodies = []

    async def search(self, *, body):
        self.bodies.append(body)
        cursor = body.get("search_after") or [0]
        start = cursor[0] + 1
        hits = [
            {
                "_id": str(project_id),
                "_source": {"projectId": project_id, "project_name": f"Project {project_id}"},
                "sort": [project_id],
            }
            for project_id in range(start, start + body["size"])
        ]
        return SimpleNamespace(body={"hits": {"hits": hits}})


class FakeExportES:
    def __init__(self):
        self.client = FakeSearchClient()
        self.closed_pits = []

    async def delete_pit_id(self, pit_id):
        self.closed_pits.append(pit_id)


@pytest.mark.asyncio
async def test_export_rows_batch_cap_and_pit_close_on_cancel():
    fake_es = FakeExportES()
    generator = _export_rows(fake_es, "pit-123", EXPORT_BATCH + 20)

    header = await generator.__anext__()
    first_batch = await generator.__anext__()
    await generator.aclose()

    assert header.startswith("projectId,project_name")
    assert "Project 1" in first_batch
    assert fake_es.client.bodies
    assert all(body["size"] <= EXPORT_BATCH for body in fake_es.client.bodies)
    assert fake_es.client.bodies[0]["pit"] == {"id": "pit-123", "keep_alive": "2m"}
    assert fake_es.closed_pits == ["pit-123"]


@pytest.mark.asyncio
async def test_export_rows_error_writes_sanitized_row_and_closes_pit():
    class FailingSearchClient:
        async def search(self, *, body):
            raise RuntimeError("secret connection detail")

    class FailingES:
        def __init__(self):
            self.client = FailingSearchClient()
            self.closed_pits = []

        async def delete_pit_id(self, pit_id):
            self.closed_pits.append(pit_id)

    fake_es = FailingES()
    chunks = [chunk async for chunk in _export_rows(fake_es, "pit-fail", 10)]
    output = "".join(chunks)

    assert "#export_error" in output
    assert "secret connection detail" not in output
    assert fake_es.closed_pits == ["pit-fail"]
