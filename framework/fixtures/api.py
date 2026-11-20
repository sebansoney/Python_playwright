"""API fixtures: token provider, per-identity API sessions, exchange log in reports."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from config.settings import Settings
from framework.api.auth import BearerAuth, StaticBearerAuth, TokenProvider
from framework.api.clients import ApiSession
from framework.api.http_client import ApiClient, ApiExchangeLog

SessionFactory = Callable[..., ApiSession]


@pytest.fixture(scope="session")
def token_provider(settings: Settings, app_server: str) -> TokenProvider:
    """One login per account per worker; tokens cached until shortly before expiry."""
    return TokenProvider(settings.app.api_base_url, settings.api.timeout_s, settings.api.verify_ssl)


def _new_session(
    settings: Settings, auth: httpx.Auth | None, log: ApiExchangeLog | None
) -> ApiSession:
    client = ApiClient(
        base_url=settings.app.base_url,
        timeout_s=settings.api.timeout_s,
        verify_ssl=settings.api.verify_ssl,
        auth=auth,
        exchange_log=log,
        slow_threshold_ms=settings.api.slow_response_threshold_ms,
        attach_exchanges=log is not None and settings.reporting.attach_api_exchanges == "always",
    )
    return ApiSession(client, settings.app.api_prefix)


@pytest.fixture
def api_log() -> ApiExchangeLog:
    """Every request/response the test made (shown in the report when it fails)."""
    return ApiExchangeLog()


@pytest.fixture
def api_session(
    settings: Settings, token_provider: TokenProvider, api_log: ApiExchangeLog, app_server: str
) -> Iterator[SessionFactory]:
    """Factory: ``api_session(role="admin")``, ``api_session(email=..., password=...)``,
    ``api_session(token="garbage")`` or ``api_session()`` for anonymous."""
    sessions: list[ApiSession] = []

    def create(
        role: str | None = None,
        email: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ) -> ApiSession:
        auth: httpx.Auth | None = None
        if role is not None:
            email, password = settings.credentials.require(role)  # type: ignore[arg-type]
        if email is not None and password is not None:
            auth = BearerAuth(token_provider, email, password)
        elif token is not None:
            auth = StaticBearerAuth(token)
        session = _new_session(settings, auth, api_log)
        sessions.append(session)
        return session

    yield create
    for s in sessions:
        s.client.close()


@pytest.fixture
def api(api_session: SessionFactory) -> ApiSession:
    """API as the seeded admin."""
    return api_session(role="admin")


@pytest.fixture
def user_api(api_session: SessionFactory) -> ApiSession:
    """API as the seeded standard user."""
    return api_session(role="user")


@pytest.fixture
def anon_api(api_session: SessionFactory) -> ApiSession:
    """API without credentials."""
    return api_session()


@pytest.fixture(scope="session")
def admin_backdoor_session(
    settings: Settings, token_provider: TokenProvider
) -> Iterator[ApiSession]:
    """Session-wide admin API for data setup/cleanup (not in per-test exchange logs)."""
    email, password = settings.credentials.require("admin")
    session = _new_session(settings, BearerAuth(token_provider, email, password), log=None)
    yield session
    session.client.close()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    """On failure, add the test's (redacted) API exchanges as a report section."""
    report = yield
    if report.failed and report.when in ("call", "setup"):
        log = getattr(item, "funcargs", {}).get("api_log")
        if isinstance(log, ApiExchangeLog) and log.entries:
            report.sections.append(("API exchanges (redacted)", log.render()))
    return report
