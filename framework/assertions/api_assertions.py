"""Fluent, reusable assertions for API responses.

    expect_api(response).has_status(201).matches_schema("user").has_json("role", "user")
    expect_api(response).is_error(422, "validation_error").has_field_error("price")

Every failure message ends with the (redacted) request/response, so a failing test
explains itself without re-running it.
"""

from __future__ import annotations

import re
from typing import Any, Self

from pydantic import BaseModel, ValidationError

from framework.api.http_client import ApiResponse
from framework.api.models import Error
from framework.assertions.schema import schema_errors

_MISSING = object()


def json_path(data: Any, path: str) -> Any:
    """Read a dotted path: 'user.email', 'items.0.sku'. Returns _MISSING if absent."""
    current = data
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


class ApiResponseAssert:
    def __init__(self, response: ApiResponse) -> None:
        self.response = response

    # ------------------------------------------------------------ internals
    def _fail(self, message: str) -> None:
        __tracebackhide__ = True
        raise AssertionError(f"{message}\n\n--- exchange ---\n{self.response.summary()}")

    def _json(self) -> Any:
        __tracebackhide__ = True
        try:
            return self.response.json
        except ValueError:
            self._fail("Response body is not valid JSON")

    # --------------------------------------------------------------- status
    def has_status(self, expected: int) -> Self:
        __tracebackhide__ = True
        if self.response.status != expected:
            self._fail(f"Expected HTTP {expected}, got {self.response.status}")
        return self

    def is_success(self) -> Self:
        __tracebackhide__ = True
        if not 200 <= self.response.status < 300:
            self._fail(f"Expected a 2xx status, got {self.response.status}")
        return self

    # -------------------------------------------------------------- headers
    def has_header(self, name: str, value: str | re.Pattern[str] | None = None) -> Self:
        __tracebackhide__ = True
        actual = self.response.headers.get(name)
        if actual is None:
            self._fail(f"Missing response header '{name}'")
        if isinstance(value, re.Pattern) and not value.search(actual or ""):
            self._fail(f"Header '{name}'={actual!r} does not match {value.pattern!r}")
        if isinstance(value, str) and actual != value:
            self._fail(f"Header '{name}'={actual!r}, expected {value!r}")
        return self

    def has_content_type(self, expected: str = "application/json") -> Self:
        __tracebackhide__ = True
        actual = self.response.headers.get("content-type", "")
        if not actual.startswith(expected):
            self._fail(f"Content-Type {actual!r}, expected {expected!r}")
        return self

    def echoes_correlation_id(self) -> Self:
        """The server returned the same X-Correlation-ID the client sent."""
        __tracebackhide__ = True
        return self.has_header("X-Correlation-ID", self.response.correlation_id)

    # ----------------------------------------------------------------- body
    def has_json(self, path: str, expected: Any = _MISSING) -> Self:
        """Path exists (and equals ``expected`` when given)."""
        __tracebackhide__ = True
        actual = json_path(self._json(), path)
        if actual is _MISSING:
            self._fail(f"JSON path '{path}' not found")
        if expected is not _MISSING and actual != expected:
            self._fail(f"JSON '{path}' = {actual!r}, expected {expected!r}")
        return self

    def json_contains(self, subset: dict[str, Any]) -> Self:
        """Every key/value in ``subset`` is present in the top-level JSON object."""
        __tracebackhide__ = True
        body = self._json()
        diffs = {
            k: (body.get(k, "<missing>"), v)
            for k, v in subset.items()
            if body.get(k, _MISSING) != v
        }
        if diffs:
            lines = "\n".join(f"  {k}: actual={a!r} expected={e!r}" for k, (a, e) in diffs.items())
            self._fail(f"JSON body differs:\n{lines}")
        return self

    def has_empty_body(self) -> Self:
        __tracebackhide__ = True
        if self.response.raw.content:
            self._fail("Expected an empty body")
        return self

    # ------------------------------------------------------ contract / types
    def matches_schema(self, name: str) -> Self:
        __tracebackhide__ = True
        problems = schema_errors(self._json(), name)
        if problems:
            self._fail(f"Schema '{name}' violated:\n  - " + "\n  - ".join(problems))
        return self

    def parse[M: BaseModel](self, model: type[M]) -> M:
        """Terminal step: validate against a pydantic model and return the typed object."""
        __tracebackhide__ = True
        try:
            return self.response.parse(model)
        except ValidationError as exc:
            self._fail(f"Body does not fit {model.__name__}:\n{exc}")
            raise  # unreachable; keeps type checkers happy

    # ---------------------------------------------------------- performance
    def responds_within(self, max_ms: float) -> Self:
        __tracebackhide__ = True
        if self.response.elapsed_ms > max_ms:
            self._fail(f"Response took {self.response.elapsed_ms:.0f} ms (limit {max_ms:.0f} ms)")
        return self

    # --------------------------------------------------------------- errors
    def is_error(self, status: int, code: str | None = None) -> Self:
        """Error status + standard error body (schema) + optional machine code."""
        __tracebackhide__ = True
        self.has_status(status).matches_schema("error")
        if code is not None and self._json().get("code") != code:
            self._fail(f"Error code {self._json().get('code')!r}, expected {code!r}")
        return self

    def has_detail(self, detail: str) -> Self:
        __tracebackhide__ = True
        return self.has_json("detail", detail)

    def has_field_error(self, field: str, message: str | None = None) -> Self:
        __tracebackhide__ = True
        error = Error.model_validate(self._json())
        actual = error.message_for(field)
        if actual is None:
            fields = [e.field for e in error.errors or []]
            self._fail(f"No validation error for field '{field}' (errors for: {fields})")
        if message is not None and actual != message:
            self._fail(f"Field '{field}' error {actual!r}, expected {message!r}")
        return self

    def has_field_errors_exactly(self, *fields: str) -> Self:
        __tracebackhide__ = True
        error = Error.model_validate(self._json())
        actual = sorted({e.field for e in error.errors or []})
        if actual != sorted(fields):
            self._fail(f"Validation errors for {actual}, expected exactly {sorted(fields)}")
        return self


def expect_api(response: ApiResponse) -> ApiResponseAssert:
    return ApiResponseAssert(response)
