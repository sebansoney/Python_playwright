"""Self-tests for the API layer using HTTPX's in-memory MockTransport (no app needed)."""

import json

import httpx
import pytest

from framework.api.http_client import ApiClient, ApiExchangeLog
from framework.assertions import expect_api, json_path, schema_errors
from framework.core.redaction import get_redactor

USER = {
    "id": 7,
    "email": "ann@example.test",
    "full_name": "Ann Example",
    "phone": None,
    "role": "user",
    "is_active": True,
    "has_avatar": False,
    "created_at": "2026-11-18T10:00:00.123456",
    "updated_at": "2026-11-18T10:00:00",
}


def _client(handler, log: ApiExchangeLog | None = None) -> ApiClient:  # type: ignore[no-untyped-def]
    client = ApiClient("http://testserver", exchange_log=log)
    client._http._transport = httpx.MockTransport(handler)
    return client


def test_client_sends_correlation_id_and_records_exchange() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cid"] = request.headers["X-Correlation-ID"]
        return httpx.Response(200, json=USER, headers={"X-Correlation-ID": seen["cid"]})

    log = ApiExchangeLog()
    response = _client(handler, log).get("/users/7", params={"q": None, "page": 1})

    assert response.correlation_id == seen["cid"]
    assert len(seen["cid"]) == 32
    assert response.request.url.query == b"page=1"  # None params are dropped
    assert response.elapsed_ms >= 0
    assert log.entries == [response]
    expect_api(response).has_status(200).echoes_correlation_id().matches_schema("user")


def test_client_does_not_keep_cookies_between_calls() -> None:
    """Regression: a login's Set-Cookie must not silently authenticate later calls."""
    cookie_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cookie_headers.append(request.headers.get("Cookie"))
        return httpx.Response(200, json={}, headers={"Set-Cookie": "access_token=abc; Path=/"})

    client = _client(handler)
    client.post("/auth/login")
    client.get("/users")

    assert cookie_headers == [None, None]


def test_exchange_summary_is_redacted() -> None:
    get_redactor().register_secret("Sup3r-Secret-pw")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl"})

    response = _client(handler).post(
        "/auth/login",
        json={"email": "a@b.test", "password": "Sup3r-Secret-pw"},
        headers={"Authorization": "Bearer abcdefghijklmnop"},
    )
    summary = response.summary()

    assert "Sup3r-Secret-pw" not in summary
    assert "abcdefghijklmnop" not in summary
    assert "eyJhbGciOi" not in summary
    assert "a@b.test" in summary  # non-secret data stays readable


def test_failure_message_contains_the_exchange() -> None:
    response = _client(lambda r: httpx.Response(404, json={"detail": "nope"})).get("/x")

    with pytest.raises(AssertionError) as info:
        expect_api(response).has_status(200)

    assert "Expected HTTP 200, got 404" in str(info.value)
    assert "GET http://testserver/x" in str(info.value)


def test_schema_errors_list_every_problem() -> None:
    bad = {**USER, "role": "root", "id": 0, "surprise": 1}
    del bad["email"]

    problems = schema_errors(bad, "user")

    joined = "\n".join(problems)
    assert len(problems) == 4, joined
    assert "'email' is a required property" in joined
    assert "Additional properties are not allowed ('surprise'" in joined


def test_page_schema_resolves_item_reference() -> None:
    page = {"items": [USER, {**USER, "id": "x"}], "total": 2, "page": 1, "size": 10, "pages": 1}

    assert schema_errors(page, "user_page") == ["items/1/id: 'x' is not of type 'integer'"]


def test_json_path_reads_nested_values() -> None:
    data = json.loads('{"user": {"email": "e"}, "items": [{"sku": "A"}, {"sku": "B"}]}')

    assert json_path(data, "user.email") == "e"
    assert json_path(data, "items.1.sku") == "B"
    assert json_path(data, "items.5.sku") is not None  # sentinel, not an exception
