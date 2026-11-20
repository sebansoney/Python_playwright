"""Error types and handlers.

API (/api/...)  -> JSON  {"detail", "code", "correlation_id", "errors"?}
Web (others)    -> 401 redirects to /login, other errors render an HTML error page.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from sample_application.backend.validation import error_list

_DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
}


class AppError(StarletteHTTPException):
    """HTTP error with a stable machine-readable ``code``."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code or _DEFAULT_CODES.get(status_code, "error")


def not_found(what: str) -> AppError:
    return AppError(404, f"{what} not found")


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _correlation_id(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def register_error_handlers(app: FastAPI) -> None:
    # Imported lazily to avoid a circular import (web.common imports errors).
    from sample_application.backend.web.common import render_error

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if _is_api(request):
            code = getattr(exc, "code", None) or _DEFAULT_CODES.get(exc.status_code, "error")
            return JSONResponse(
                {"detail": exc.detail, "code": code, "correlation_id": _correlation_id(request)},
                status_code=exc.status_code,
                headers=exc.headers,
            )
        if exc.status_code == 401:
            target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/login?next={quote(target)}", status_code=303)
        return render_error(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        errors = error_list(exc.errors())
        if not _is_api(request):
            return render_error(request, 400, "; ".join(e["message"] for e in errors))
        return JSONResponse(
            {
                "detail": "Validation failed",
                "code": "validation_error",
                "correlation_id": _correlation_id(request),
                "errors": errors,
            },
            status_code=422,
        )
