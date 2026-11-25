"""FastAPI application factory, lifespan, error handlers and static mount."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from elasticsearch import ApiError, AuthorizationException, NotFoundError, TransportError
from elasticsearch import ConnectionError as ESConnectionError
from elastic_transport import ConnectionTimeout

from .config import settings
from .es_client import ESManager
from .routes import _ensure_address_index, router
from .schemas import AppError, error_payload

logger = logging.getLogger("rera")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("elastic_transport.transport").setLevel(logging.WARNING)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


async def _warm_address_cache(es: ESManager) -> None:
    try:
        addresses = await _ensure_address_index(es)
        logger.info("Address cache warm-up finished with %d entries", len(addresses))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - warm-up must never fail startup
        logger.exception("Address cache warm-up failed; continuing without rerank cache")


@asynccontextmanager
async def lifespan(app: FastAPI):
    es = ESManager(settings)
    app.state.es = es
    warm_task: asyncio.Task | None = None
    try:
        await es.discover()
    except Exception:  # noqa: BLE001 - startup must survive a down cluster
        logger.exception("Startup discovery failed; continuing in degraded mode")
    if settings.warm_address_cache_on_startup:
        warm_task = asyncio.create_task(_warm_address_cache(es))
    try:
        yield
    finally:
        if warm_task is not None and not warm_task.done():
            warm_task.cancel()
            with suppress(asyncio.CancelledError):
                await warm_task
        await es.close()


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_payload(code, message))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message, exc.detail))

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error(404, "not_found", "The requested resource was not found.")

    @app.exception_handler(AuthorizationException)
    async def _forbidden(request: Request, exc: AuthorizationException) -> JSONResponse:
        return _error(403, "forbidden", "The cluster denied this operation.")

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        status = exc.status_code or 500
        if status == 404:
            code, out = "not_found", 404
        elif status == 403:
            code, out = "forbidden", 403
        elif 400 <= status < 500:
            code, out = "invalid_request", status
        else:
            code, out = "es_error", 502
        logger.warning("ApiError on %s: status=%s", request.url.path, status)
        return _error(out, code, "Elasticsearch request failed.")

    @app.exception_handler(ESConnectionError)
    async def _connection(request: Request, exc: ESConnectionError) -> JSONResponse:
        logger.warning("ES connection error on %s: %s", request.url.path, type(exc).__name__)
        return _error(503, "es_unavailable", "Elasticsearch is unavailable.")

    @app.exception_handler(ConnectionTimeout)
    async def _conn_timeout(request: Request, exc: ConnectionTimeout) -> JSONResponse:
        return _error(504, "timeout", "Elasticsearch request timed out.")

    @app.exception_handler(TransportError)
    async def _transport(request: Request, exc: TransportError) -> JSONResponse:
        logger.warning("ES transport error on %s: %s", request.url.path, type(exc).__name__)
        return _error(502, "es_error", "Elasticsearch transport error.")

    @app.exception_handler(TimeoutError)
    async def _timeout(request: Request, exc: TimeoutError) -> JSONResponse:
        return _error(504, "timeout", "Request timed out.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Gujrat RERA Explorer",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    register_error_handlers(app)
    app.include_router(router)

    @app.middleware("http")
    async def _no_static_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    if FRONTEND_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False, response_model=None)
    async def index():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse({"message": "Frontend not found."}, status_code=404)

    return app


app = create_app()
