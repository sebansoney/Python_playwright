"""HTTP client for API tests (HTTPX).

Every request:
  * gets an ``X-Correlation-ID`` (generated unless the caller passes one) so a test
    step can be matched with the application's own log line,
  * is timed (``ApiResponse.elapsed_ms``) and flagged when slower than the configured
    threshold,
  * is logged in one line (method, URL, status, time, correlation id) plus redacted
    bodies at DEBUG level,
  * is recorded into an optional ``ApiExchangeLog`` - shown in the pytest report when
    the test fails (and attached to Allure in Phase 7).

The client never asserts and never retries: deciding what is correct is the job of
the test / assertion layer; retrying infrastructure errors is configured at pytest level.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from functools import cached_property
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from framework.core.logging_config import get_logger
from framework.core.redaction import get_redactor
from framework.reporting.allure_helpers import attach_text, step

log = get_logger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"
_BODY_PREVIEW_CHARS = 2000
M = TypeVar("M", bound=BaseModel)


# --------------------------------------------------------------------------- #
# Response                                                                     #
# --------------------------------------------------------------------------- #
@dataclass
class ApiResponse:
    raw: httpx.Response
    elapsed_ms: float
    correlation_id: str

    @property
    def status(self) -> int:
        return self.raw.status_code

    @property
    def headers(self) -> httpx.Headers:
        return self.raw.headers

    @property
    def text(self) -> str:
        return self.raw.text

    @property
    def request(self) -> httpx.Request:
        return self.raw.request

    @cached_property
    def json(self) -> Any:
        """Parsed JSON body (None for an empty body). Raises ValueError if not JSON."""
        if not self.raw.content:
            return None
        return self.raw.json()

    def parse(self, model: type[M]) -> M:
        """Validate the JSON body against a pydantic model and return the typed object."""
        return model.model_validate(self.json)

    def summary(self) -> str:
        """Redacted, human-readable request/response - used in assertion messages."""
        return render_exchange(self.raw.request, self.raw, self.elapsed_ms, self.correlation_id)


@dataclass
class ApiExchangeLog:
    """Per-test record of every request/response (redacted when rendered)."""

    entries: list[ApiResponse] = field(default_factory=list)

    def add(self, response: ApiResponse) -> None:
        self.entries.append(response)

    def render(self) -> str:
        return "\n\n".join(f"#{i} {r.summary()}" for i, r in enumerate(self.entries, 1))


# --------------------------------------------------------------------------- #
# Client                                                                       #
# --------------------------------------------------------------------------- #
def _no_cookies_jar() -> CookieJar:
    """A cookie jar that refuses to store any cookie."""
    return CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 10,
        verify_ssl: bool = True,
        auth: httpx.Auth | None = None,
        exchange_log: ApiExchangeLog | None = None,
        slow_threshold_ms: float | None = None,
        default_headers: dict[str, str] | None = None,
        persist_cookies: bool = False,
        attach_exchanges: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._attach_exchanges = attach_exchanges  # Allure: attach every exchange to its step
        self._log = exchange_log
        self._slow_ms = slow_threshold_ms
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_s,
            verify=verify_ssl,
            auth=auth,
            headers={"Accept": "application/json", **(default_headers or {})},
            follow_redirects=False,
            # API tests must be explicit about identity. A login response sets an auth
            # cookie (for browsers); storing it would silently authenticate every later
            # call of an "anonymous" session. Opt in with persist_cookies=True.
            cookies=None if persist_cookies else _no_cookies_jar(),
        )

    # ---------------------------------------------------------------- verbs
    def get(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> ApiResponse:
        return self.request("DELETE", path, **kwargs)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | str | None = None,
        files: Any = None,
        auth: httpx.Auth | object | None = httpx.USE_CLIENT_DEFAULT,
        correlation_id: str | None = None,
    ) -> ApiResponse:
        cid = correlation_id or uuid.uuid4().hex
        all_headers = {CORRELATION_HEADER: cid, **(headers or {})}
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        # One Allure step per HTTP call (title only - nothing secret in method + path).
        with step(f"{method} {path}"):
            started = time.perf_counter()
            raw = self._http.request(
                method,
                path,
                json=json,
                params=clean_params or None,
                headers=all_headers,
                content=content,
                files=files,
                auth=auth,  # type: ignore[arg-type]
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            response = ApiResponse(raw=raw, elapsed_ms=elapsed_ms, correlation_id=cid)
            self._record(response)
            if self._attach_exchanges:
                attach_text(f"HTTP {response.status} ({elapsed_ms:.0f} ms)", response.summary())
        return response

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -------------------------------------------------------------- helpers
    def _record(self, response: ApiResponse) -> None:
        req = response.request
        log.info(
            "%s %s -> %s (%.0f ms) cid=%s",
            req.method,
            req.url,
            response.status,
            response.elapsed_ms,
            response.correlation_id,
        )
        log.debug("%s", response.summary())
        if self._slow_ms and response.elapsed_ms > self._slow_ms:
            log.warning(
                "Slow response: %s %s took %.0f ms (threshold %s ms)",
                req.method,
                req.url.path,
                response.elapsed_ms,
                self._slow_ms,
            )
        if self._log is not None:
            self._log.add(response)


# --------------------------------------------------------------------------- #
# Rendering (redacted)                                                         #
# --------------------------------------------------------------------------- #
def _body_text(content: bytes, content_type: str) -> str:
    if not content:
        return "<empty>"
    if "json" in content_type:
        try:
            data = get_redactor().redact(json.loads(content))
            text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except ValueError:
            text = get_redactor().redact_text(content.decode("utf-8", "replace"))
    elif content_type.startswith(("text/", "application/x-www-form-urlencoded")):
        text = get_redactor().redact_text(content.decode("utf-8", "replace"))
    else:
        return f"<{len(content)} bytes {content_type or 'binary'}>"
    if len(text) > _BODY_PREVIEW_CHARS:
        text = text[:_BODY_PREVIEW_CHARS] + f"... <truncated, {len(text)} chars>"
    return text


def render_exchange(
    request: httpx.Request, response: httpx.Response, elapsed_ms: float, correlation_id: str
) -> str:
    redactor = get_redactor()
    req_headers = redactor.redact(dict(request.headers))
    res_headers = redactor.redact(dict(response.headers))
    try:
        req_body = request.content
    except httpx.RequestNotRead:
        req_body = b"<streamed>"
    return (
        f"{request.method} {redactor.redact_text(str(request.url))}  "
        f"[cid={correlation_id}, {elapsed_ms:.0f} ms]\n"
        f"Request headers: {req_headers}\n"
        f"Request body: {_body_text(req_body, request.headers.get('content-type', ''))}\n"
        f"Response: HTTP {response.status_code}\n"
        f"Response headers: {res_headers}\n"
        f"Response body: {_body_text(response.content, response.headers.get('content-type', ''))}"
    )
