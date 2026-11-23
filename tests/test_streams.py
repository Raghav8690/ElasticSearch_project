import pytest
import httpx
from backend.main import app, lifespan
from backend.routes import _safe_cell
from backend.queries import EXPORT_COLUMNS


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
