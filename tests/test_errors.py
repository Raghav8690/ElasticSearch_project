import pytest
import httpx
from backend.main import app, lifespan
from backend.schemas import error_payload, envelope
from backend.config import settings


def test_error_payload_sanitization():
    payload = error_payload("invalid_request", "Custom message", detail="redacted")
    assert payload == {
        "error": {
            "code": "invalid_request",
            "message": "Custom message",
            "detail": "redacted",
        }
    }
    # Sensitive details should not leak
    assert "password" not in str(payload).lower()
    assert "api_key" not in str(payload).lower()


def test_envelope_structure():
    res = envelope({"test": "data"}, index="gujrat_rera_data", total=10, returned=5, es_took_ms=12, wall_ms=18.4)
    assert res["data"] == {"test": "data"}
    meta = res["meta"]
    assert meta["index"] == "gujrat_rera_data"
    assert meta["total"] == 10
    assert meta["returned"] == 5
    assert meta["es_took_ms"] == 12
    assert meta["wall_ms"] == 18.4


@pytest.mark.asyncio
async def test_no_credential_leak_in_config():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/config")
            assert r.status_code == 200
            data = r.json().get("data", {})
            assert "host" in data
            assert "password" not in data
            assert "username" not in data
            assert "api_key" not in data
            if settings.es_password:
                assert settings.es_password not in r.text
            if settings.es_username:
                assert settings.es_username not in r.text
            if settings.es_api_key:
                assert settings.es_api_key not in r.text


@pytest.mark.asyncio
async def test_not_found_error_sanitization():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/projects/999999999")
            assert r.status_code == 404
            err = r.json().get("error", {})
            assert err.get("code") == "not_found"
            assert "detail" in err
            assert err["detail"] == "redacted"


@pytest.mark.asyncio
async def test_session_expired_error():
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.delete("/api/pit/non_existent_session_id")
            assert r.status_code == 400
            err = r.json().get("error", {})
            assert err.get("code") == "session_expired"
