"""Fixture + hooks that make sure the application under test is running."""

from __future__ import annotations

import os
import uuid

import pytest

from config.settings import Settings
from framework.core.app_server import RUN_ID_ENV, AppServer


def _server(settings: Settings) -> AppServer:
    return AppServer(
        base_url=settings.app.base_url,
        health_url=settings.app.health_url,
        startup_timeout_s=settings.app.startup_timeout_s,
    )


def _is_xdist_worker() -> bool:
    return "PYTEST_XDIST_WORKER" in os.environ


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # The run id is created by the controller (or the single process) and inherited
    # by xdist workers through the environment, so all of them agree on "this run".
    if not _is_xdist_worker():
        os.environ[RUN_ID_ENV] = uuid.uuid4().hex


def pytest_unconfigure(config: pytest.Config) -> None:
    if _is_xdist_worker():
        return
    from config.settings import get_settings

    _server(get_settings()).stop_if_started_by(os.environ.get(RUN_ID_ENV))


@pytest.fixture(scope="session")
def app_server(settings: Settings) -> str:
    """Ensure the app is reachable (autostart if configured). Returns the base URL."""
    _server(settings).ensure_running(settings.app.autostart)
    return settings.app.base_url
