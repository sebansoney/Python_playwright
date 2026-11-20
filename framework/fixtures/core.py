"""Core pytest plugin: CLI options, settings bootstrap, logging, auto-markers.

Registered from the root conftest.py via ``pytest_plugins``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config.settings import ENV_VAR_NAME, Settings, available_environments, get_settings
from framework.core.exceptions import ConfigurationError
from framework.core.logging_config import configure_logging, get_logger
from framework.core.paths import LOCAL_BROWSERS_DIR, PROJECT_ROOT, resolve_project_path
from framework.core.redaction import configure_redactor

SETTINGS_KEY = pytest.StashKey[Settings]()

# tests/<folder>/...  ->  marker applied automatically
_FOLDER_MARKERS = {"ui": "ui", "api": "api", "integration": "integration", "unit": "unit"}
_REGRESSION_LAYERS = {"ui", "api", "integration"}

log = get_logger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("framework", "Automation framework options")
    group.addoption(
        "--env",
        action="store",
        default=None,
        help=f"Target environment (config/environments/<env>.yaml). "
        f"Default: ${ENV_VAR_NAME} or 'local'. Available: {', '.join(available_environments())}",
    )


def pytest_configure(config: pytest.Config) -> None:
    bootstrap(config)


def bootstrap(config: pytest.Config) -> Settings:
    """Load settings, configure redaction + logging. Idempotent: other plugins that need
    settings in their own ``pytest_configure`` call this instead of relying on hook order."""
    if SETTINGS_KEY in config.stash:
        return config.stash[SETTINGS_KEY]

    # Browsers installed inside the project (see scripts/setup.*) are used
    # automatically; CI and machines without that folder use Playwright's default.
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and LOCAL_BROWSERS_DIR.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(LOCAL_BROWSERS_DIR)

    # Must run before the first get_settings() call. xdist workers receive the same
    # CLI options, so they resolve the same environment.
    env = config.getoption("--env")
    if env:
        os.environ[ENV_VAR_NAME] = env
    get_settings.cache_clear()

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        raise pytest.UsageError(str(exc)) from exc

    configure_redactor(
        sensitive_keys=settings.redaction.sensitive_keys,
        mask=settings.redaction.mask,
        mask_emails=settings.redaction.mask_emails,
        secrets=settings.secret_values(),
    )
    log_file = configure_logging(
        resolve_project_path(settings.reporting.logs_dir), settings.reporting.log_level
    )
    config.stash[SETTINGS_KEY] = settings
    log.info("Environment '%s' loaded; logging to %s", settings.env, log_file)
    return settings


def pytest_report_header(config: pytest.Config) -> list[str]:
    settings = config.stash.get(SETTINGS_KEY, None)
    if settings is None:
        return []
    return [
        f"framework: env={settings.env}  base_url={settings.app.base_url}  "
        f"ai={'on' if settings.ai.enabled else 'off'}"
    ]


def auto_markers(parts: tuple[str, ...]) -> list[str]:
    """Markers implied by a test's location below tests/ (e.g. ("ui", "test_x.py"))."""
    layer = _FOLDER_MARKERS.get(parts[0]) if parts else None
    if layer is None:
        return []
    return [layer, "regression"] if layer in _REGRESSION_LAYERS else [layer]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply layer markers from the test's folder, and make every functional test part of
    the regression suite (smoke and sanity are subsets of regression, not alternatives)."""
    tests_root = PROJECT_ROOT / "tests"
    for item in items:
        try:
            relative = Path(item.path).resolve().relative_to(tests_root)
        except ValueError:
            continue
        for marker in auto_markers(relative.parts):
            if not item.get_closest_marker(marker):
                item.add_marker(marker)


@pytest.fixture(scope="session")
def settings(pytestconfig: pytest.Config) -> Settings:
    """The validated configuration for this run."""
    return pytestconfig.stash[SETTINGS_KEY]
