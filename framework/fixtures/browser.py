"""Browser layer: builds on the pytest-playwright plugin instead of replacing it.

pytest-playwright already provides: browser lifecycle, --browser/--headed/--slowmo,
--tracing/--video/--screenshot artifacts for every context created via
``new_context``. This plugin adds:
  * config.yaml defaults for those options (an explicit CLI flag still wins),
  * base_url / viewport / locale / timeouts for every context,
  * pre-authenticated pages (admin_page, user_page, page_for) via storage state,
  * automatic start of the application under test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from config.settings import Settings
from framework.api.auth import TokenProvider
from framework.browser.session import storage_state_for_token
from framework.core.paths import REPORTS_DIR
from framework.fixtures.core import SETTINGS_KEY

PLAYWRIGHT_OUTPUT_DIR = REPORTS_DIR / "playwright"


def _given_on_cli(config: pytest.Config, flag: str) -> bool:
    return any(a == flag or a.startswith(flag + "=") for a in config.invocation_params.args)


@pytest.hookimpl(trylast=True)  # after the core plugin has loaded the settings
def pytest_configure(config: pytest.Config) -> None:
    settings: Settings = config.stash[SETTINGS_KEY]
    b = settings.browser
    opt = config.option
    if not opt.browser:
        opt.browser = [b.name]
    if not _given_on_cli(config, "--headed") and not b.headless:
        opt.headed = True
    if not _given_on_cli(config, "--slowmo"):
        opt.slowmo = b.slow_mo_ms
    for flag, value in (
        ("--tracing", b.trace),
        ("--video", b.video),
        ("--screenshot", b.screenshot),
    ):
        if not _given_on_cli(config, flag):
            setattr(opt, flag.lstrip("-"), value)
    if not _given_on_cli(config, "--output"):
        opt.output = str(PLAYWRIGHT_OUTPUT_DIR)
    if not getattr(opt, "base_url", None):
        opt.base_url = settings.app.base_url
    # Web-first assertions (expect) retry until this timeout.
    expect.set_options(timeout=b.expect_timeout_ms)


@pytest.fixture(scope="session")
def browser_context_args(
    browser_context_args: dict[str, Any], app_server: str, settings: Settings
) -> dict[str, Any]:
    """Options for every browser context. Requesting app_server starts the app if needed."""
    b = settings.browser
    return {
        **browser_context_args,
        "base_url": app_server,
        "viewport": {"width": b.viewport_width, "height": b.viewport_height},
        "locale": "en-US",
        "timezone_id": "UTC",
        "accept_downloads": True,
    }


@pytest.fixture
def new_context(
    new_context: Callable[..., BrowserContext], settings: Settings
) -> Callable[..., BrowserContext]:
    """Wrap pytest-playwright's factory: apply default timeouts to every context
    (and therefore to every page, popup and new tab opened in it)."""

    def factory(**kwargs: Any) -> BrowserContext:
        context = new_context(**kwargs)
        context.set_default_timeout(settings.browser.default_timeout_ms)
        context.set_default_navigation_timeout(settings.browser.navigation_timeout_ms)
        return context

    return factory


# ---------------------------------------------------------------- sessions
@pytest.fixture(scope="session")
def auth_state(
    token_provider: TokenProvider,
    app_server: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str, str], Path]:
    """Return a storage-state file for (email, password), logging in via the HTTPX API
    once per worker. Files live in pytest's temp dir - never in reports (they hold tokens)."""
    cache: dict[str, Path] = {}
    folder = tmp_path_factory.mktemp("auth")

    def get(email: str, password: str) -> Path:
        if email not in cache:
            state = storage_state_for_token(app_server, token_provider.token(email, password))
            path = folder / f"state_{len(cache)}.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            cache[email] = path
        return cache[email]

    return get


@pytest.fixture
def page_for(
    new_context: Callable[..., BrowserContext], auth_state: Callable[[str, str], Path]
) -> Callable[[str, str], Page]:
    """Open a page already logged in as the given account (no login UI involved)."""

    def open_page(email: str, password: str) -> Page:
        return new_context(storage_state=auth_state(email, password)).new_page()

    return open_page


@pytest.fixture
def page_for_token(
    new_context: Callable[..., BrowserContext], app_server: str
) -> Callable[[str], Page]:
    """Open a page whose session is an existing API token (API login -> browser)."""

    def open_page(token: str) -> Page:
        return new_context(storage_state=storage_state_for_token(app_server, token)).new_page()

    return open_page


@pytest.fixture
def admin_page(page_for: Callable[[str, str], Page], settings: Settings) -> Page:
    return page_for(*settings.credentials.require("admin"))


@pytest.fixture
def user_page(page_for: Callable[[str, str], Page], settings: Settings) -> Page:
    return page_for(*settings.credentials.require("user"))
