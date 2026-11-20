"""Cross-cutting API conventions: health, correlation IDs, headers, error format, timing."""

import re
from collections.abc import Callable

import httpx
import pytest

from config.settings import Settings
from framework.api.clients import ApiSession
from framework.api.http_client import ApiResponse
from framework.assertions import expect_api


@pytest.mark.smoke
def test_health_endpoint_is_public(anon_api: ApiSession) -> None:
    response = anon_api.system.health()

    expect_api(response).has_status(200).has_content_type().matches_schema("health").has_json(
        "status", "ok"
    )


@pytest.mark.regression
def test_correlation_id_is_echoed_on_success_and_error(api: ApiSession) -> None:
    ok = api.client.get(api.products.base, correlation_id="qa-trace-0001")
    error = api.client.get(f"{api.products.base}/999999999", correlation_id="qa-trace-0002")

    expect_api(ok).has_status(200).echoes_correlation_id()
    expect_api(error).is_error(404).echoes_correlation_id().has_json(
        "correlation_id", "qa-trace-0002"
    )


@pytest.mark.regression
def test_server_generates_correlation_id_when_missing(settings: Settings, app_server: str) -> None:
    # Plain HTTPX on purpose: our ApiClient always sends an id, here we need none.
    raw = httpx.get(settings.app.health_url, timeout=settings.api.timeout_s)

    assert re.fullmatch(r"[0-9a-f]{32}", raw.headers["X-Correlation-ID"])


@pytest.mark.regression
def test_responses_carry_timing_header(api: ApiSession) -> None:
    response = api.products.list()

    expect_api(response).has_status(200).has_header(
        "X-Response-Time-ms", re.compile(r"^\d+(\.\d+)?$")
    )


@pytest.mark.sanity
def test_core_endpoints_respond_within_threshold(api: ApiSession, settings: Settings) -> None:
    limit = settings.api.slow_response_threshold_ms
    for response in (api.system.health(), api.products.list(), api.users.list(), api.auth.me()):
        expect_api(response).is_success().responds_within(limit)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("call", "status"),
    [
        (lambda anon, user, admin: anon.users.list(), 401),
        (lambda anon, user, admin: user.users.list(), 403),
        (lambda anon, user, admin: admin.users.get(999_999_999), 404),
        (lambda anon, user, admin: admin.users.create({"email": "x"}), 422),
        (lambda anon, user, admin: admin.users.update(1, {}), 400),
    ],
    ids=["401", "403", "404", "422", "400"],
)
def test_every_error_uses_the_standard_error_format(
    anon_api: ApiSession,
    user_api: ApiSession,
    api: ApiSession,
    call: Callable[[ApiSession, ApiSession, ApiSession], ApiResponse],
    status: int,
) -> None:
    response = call(anon_api, user_api, api)

    expect_api(response).is_error(status).has_content_type(
        "application/json"
    ).echoes_correlation_id()
