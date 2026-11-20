"""Self-tests for the configuration loader (no app or browser needed)."""

from pathlib import Path

import pytest

from config.settings import load_settings
from framework.core.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from the developer's shell: drop FW_* / TEST_ENV variables."""
    import os

    for key in list(os.environ):
        if key.startswith("FW_") or key in {"TEST_ENV", "ANTHROPIC_API_KEY"}:
            monkeypatch.delenv(key, raising=False)


def test_defaults_load_from_base_yaml() -> None:
    s = load_settings("local", env_file=None)
    assert s.env == "local"
    assert s.app.api_base_url == "http://127.0.0.1:8000/api/v1"
    assert s.browser.name == "chromium"
    assert s.ai.enabled is False


def test_environment_yaml_overrides_base_and_keeps_other_keys() -> None:
    s = load_settings("ci", env_file=None)
    assert s.app.startup_timeout_s == 60  # overridden in ci.yaml (base: 30)
    assert s.retry.max_reruns == 2  # overridden in ci.yaml (local: 0)
    assert s.app.base_url == "http://127.0.0.1:8000"  # inherited from config.yaml (deep merge)
    assert s.retry.only_rerun  # sibling key inherited from config.yaml
    assert s.browser.video == "retain-on-failure"


def test_env_var_overrides_yaml_for_nested_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FW_BROWSER__HEADLESS", "false")
    monkeypatch.setenv("FW_API__TIMEOUT_S", "3.5")
    s = load_settings("local", env_file=None)
    assert s.browser.headless is False
    assert s.api.timeout_s == 3.5
    assert s.browser.name == "chromium"  # sibling key from YAML survives


def test_test_env_variable_selects_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ENV", "ci")
    assert load_settings(env_file=None).env == "ci"


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Unknown environment 'nope'"):
        load_settings("nope", env_file=None)


def test_invalid_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FW_BROWSER__NAME", "netscape")
    with pytest.raises(ConfigurationError, match="Invalid configuration"):
        load_settings("local", env_file=None)


def test_missing_credentials_give_actionable_error() -> None:
    s = load_settings("local", env_file=None)
    with pytest.raises(ConfigurationError, match="FW_CREDENTIALS__ADMIN_PASSWORD"):
        s.credentials.require("admin")


def test_credentials_are_secret_and_not_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FW_CREDENTIALS__ADMIN_USERNAME", "admin@example.test")
    monkeypatch.setenv("FW_CREDENTIALS__ADMIN_PASSWORD", "S3cr3t-value")
    s = load_settings("local", env_file=None)
    assert s.credentials.require("admin") == ("admin@example.test", "S3cr3t-value")
    assert "S3cr3t-value" not in repr(s)
    assert "S3cr3t-value" in s.secret_values()


def test_dotenv_file_is_loaded_and_env_var_beats_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "FW_CREDENTIALS__USER_USERNAME=from-dotenv@example.test\nFW_BROWSER__SLOW_MO_MS=100\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FW_BROWSER__SLOW_MO_MS", "250")
    s = load_settings("local", env_file=dotenv)
    assert s.credentials.user_username == "from-dotenv@example.test"  # .env > YAML
    assert s.browser.slow_mo_ms == 250  # real env var > .env


def test_anthropic_key_uses_standard_variable_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000000000")
    s = load_settings("local", env_file=None)
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value().startswith("sk-ant-")


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (("ui", "test_login.py"), ["ui", "regression"]),
        (("api", "test_users_api.py"), ["api", "regression"]),
        (("integration", "test_x.py"), ["integration", "regression"]),
        (("unit", "test_settings.py"), ["unit"]),  # framework self-tests are not regression
        (("ai_live", "test_claude_live.py"), []),  # opt-in, billed
    ],
)
def test_auto_markers_put_every_functional_test_in_regression(
    parts: tuple[str, ...], expected: list[str]
) -> None:
    """Regression must contain smoke and sanity tests (subsets, not alternatives)."""
    from framework.fixtures.core import auto_markers

    assert auto_markers(parts) == expected
