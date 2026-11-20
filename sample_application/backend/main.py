"""FastAPI application factory.

Run:  uv run python -m sample_application          (see sample_application/__main__.py)
Docs: http://127.0.0.1:8000/docs  (OpenAPI / Swagger UI)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from sample_application.backend.api import api_router
from sample_application.backend.api.system import VERSION
from sample_application.backend.config import FRONTEND_DIR, config
from sample_application.backend.errors import register_error_handlers
from sample_application.backend.seed import init_db
from sample_application.backend.web import web_router

log = logging.getLogger("sample_app")

CORRELATION_HEADER = "X-Correlation-ID"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    log.info("Sample app started (env=%s)", config.env)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sample Shop Admin",
        version=VERSION,
        description="System under test for the automation framework.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def correlation_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Echo the caller's X-Correlation-ID (or create one) and time the request."""
        cid = request.headers.get(CORRELATION_HEADER) or uuid.uuid4().hex
        request.state.correlation_id = cid
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[CORRELATION_HEADER] = cid
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        log.info(
            "%s %s -> %s (%.1f ms) cid=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            cid,
        )
        return response

    register_error_handlers(app)
    app.include_router(api_router)
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
    return app


app = create_app()
