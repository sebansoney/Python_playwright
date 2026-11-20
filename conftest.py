"""Root conftest - intentionally tiny.

All hooks and fixtures live in framework/fixtures/ and are registered here as
plugins, grouped by concern. Hooks that depend on each other use tryfirst/trylast.
"""

pytest_plugins = [
    "framework.fixtures.core",  # --env, settings, logging, auto-markers
    "framework.fixtures.app",  # start/reuse/stop the application under test
    "framework.fixtures.execution",  # infrastructure-only reruns
    "framework.fixtures.api",  # HTTPX API sessions, token provider, exchange log
    "framework.fixtures.browser",  # Playwright defaults, authenticated pages
    "framework.fixtures.data",  # backdoor, factories, cleanup
    "framework.fixtures.reporting",  # Allure results, labels, failure attachments
    "framework.fixtures.ai",  # optional AI analysis (--ai-analysis), `ai` fixture
]
