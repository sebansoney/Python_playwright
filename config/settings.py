"""Typed, validated configuration - the single source of truth for settings.

Precedence (lowest -> highest):
    1. config/config.yaml                    shared defaults
    2. config/environments/<env>.yaml        per-environment overrides
    3. .env file                             local developer values / secrets
    4. real environment variables            CI secrets, ad-hoc overrides
    (5. pytest CLI options such as --browser / --headed are applied by the
        pytest hooks on top of these settings)

Environment variables use the prefix ``FW_`` and ``__`` for nesting, e.g.
``FW_BROWSER__HEADLESS=false``. The Anthropic key uses its standard name
``ANTHROPIC_API_KEY``.

Usage::

    from config.settings import get_settings
    settings = get_settings()
    settings.app.base_url
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from framework.core.exceptions import ConfigurationError
from framework.core.paths import CONFIG_DIR, ENV_FILE, ENVIRONMENTS_DIR

DEFAULT_ENV = "local"
ENV_VAR_NAME = "TEST_ENV"


class _Section(BaseModel):
    """Base for config sections: unknown keys are an error (catches typos)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AppSettings(_Section):
    base_url: str
    api_prefix: str = "/api/v1"
    health_path: str = "/api/v1/health"
    autostart: bool = True
    startup_timeout_s: float = Field(30, gt=0)

    @property
    def api_base_url(self) -> str:
        return self.base_url.rstrip("/") + self.api_prefix

    @property
    def health_url(self) -> str:
        return self.base_url.rstrip("/") + self.health_path


class BrowserSettings(_Section):
    name: Literal["chromium", "firefox", "webkit"] = "chromium"
    headless: bool = True
    slow_mo_ms: int = Field(0, ge=0)
    viewport_width: int = Field(1366, gt=0)
    viewport_height: int = Field(768, gt=0)
    default_timeout_ms: int = Field(10_000, gt=0)
    navigation_timeout_ms: int = Field(30_000, gt=0)
    expect_timeout_ms: int = Field(5_000, gt=0)
    screenshot: Literal["on", "off", "only-on-failure"] = "only-on-failure"
    video: Literal["on", "off", "retain-on-failure"] = "off"
    trace: Literal["on", "off", "retain-on-failure"] = "retain-on-failure"


class ApiSettings(_Section):
    timeout_s: float = Field(10, gt=0)
    verify_ssl: bool = True
    slow_response_threshold_ms: int = Field(2000, gt=0)


class RetrySettings(_Section):
    max_reruns: int = Field(2, ge=0, le=5)
    delay_s: float = Field(1, ge=0)
    only_rerun: list[str] = Field(default_factory=list)


class ReportingSettings(_Section):
    allure_results_dir: Path = Path("reports/allure-results")
    allure_report_dir: Path = Path("reports/allure-report")
    logs_dir: Path = Path("logs")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    allure_enabled: bool = True  # write Allure results even without --alluredir
    clean_results: bool = True  # wipe old results at the start of a run (controller only)
    # Request/response details in Allure: per API step always, only on failure, or never.
    attach_api_exchanges: Literal["always", "on-failure", "off"] = "on-failure"
    # Attach screenshots/traces/videos that pytest-playwright kept for a failed UI test.
    attach_browser_artifacts: bool = True
    # Redacted HTML of the open page(s) when a UI test fails (input for humans + AI locator help).
    attach_dom_snapshot: bool = True


class RedactionSettings(_Section):
    mask: str = "***REDACTED***"
    mask_emails: bool = False
    sensitive_keys: list[str] = Field(default_factory=list)


class AISettings(_Section):
    enabled: bool = False
    provider: Literal["claude", "none"] = "claude"
    model: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    max_tokens: int = Field(16000, gt=0)
    timeout_s: float = Field(300, gt=0)
    max_retries: int = Field(2, ge=0, le=5)
    max_calls_per_run: int = Field(20, ge=0)
    send_screenshots: bool = False
    server_side_fallback: bool = True  # re-run a refused request on a fallback model
    output_dir: Path = Path("reports/ai")
    drafts_dir: Path = Path("ai_drafts")


class CredentialsSettings(_Section):
    """Test accounts. Values come from .env / environment variables only."""

    admin_username: str | None = None
    admin_password: SecretStr | None = None
    user_username: str | None = None
    user_password: SecretStr | None = None

    def require(self, role: Literal["admin", "user"]) -> tuple[str, str]:
        """Return (username, password) for ``role`` or fail with a clear message."""
        username = getattr(self, f"{role}_username")
        password: SecretStr | None = getattr(self, f"{role}_password")
        if not username or password is None:
            prefix = f"FW_CREDENTIALS__{role.upper()}"
            raise ConfigurationError(
                f"Credentials for '{role}' are not configured. Set {prefix}_USERNAME and "
                f"{prefix}_PASSWORD in .env (copy .env.example) or as environment variables."
            )
        return username, password.get_secret_value()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FW_",
        env_nested_delimiter="__",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # .env legitimately contains non-FW_ keys (TEST_ENV, ANTHROPIC_API_KEY ...).
        # Typos inside YAML are still caught: sections forbid extras and
        # top-level YAML keys are checked in load_settings().
        extra="ignore",
        frozen=True,
    )

    env: str = DEFAULT_ENV
    app: AppSettings
    browser: BrowserSettings = BrowserSettings()
    api: ApiSettings = ApiSettings()
    retry: RetrySettings = RetrySettings()
    reporting: ReportingSettings = ReportingSettings()
    redaction: RedactionSettings = RedactionSettings()
    ai: AISettings = AISettings()
    credentials: CredentialsSettings = CredentialsSettings()
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "FW_ANTHROPIC_API_KEY"),
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Earlier sources win. YAML values are passed as init kwargs, so we put
        # init_settings LAST to make YAML the lowest-priority layer.
        return env_settings, dotenv_settings, file_secret_settings, init_settings

    def secret_values(self) -> list[str]:
        """All configured secret values - registered with the redactor at start-up."""
        candidates = [
            self.credentials.admin_password,
            self.credentials.user_password,
            self.anthropic_api_key,
        ]
        return [s.get_secret_value() for s in candidates if s and s.get_secret_value()]


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #
def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path} must contain a mapping at the top level.")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def available_environments() -> list[str]:
    return sorted(p.stem for p in ENVIRONMENTS_DIR.glob("*.yaml"))


def resolve_env_name(env: str | None = None) -> str:
    """Explicit argument > TEST_ENV env var > TEST_ENV in .env > 'local'."""
    if env:
        return env
    if os.environ.get(ENV_VAR_NAME):
        return os.environ[ENV_VAR_NAME]
    if ENV_FILE.exists():
        from_file = dotenv_values(ENV_FILE).get(ENV_VAR_NAME)
        if from_file:
            return from_file
    return DEFAULT_ENV


def load_settings(env: str | None = None, env_file: Path | None = ENV_FILE) -> Settings:
    """Build a fresh Settings object (uncached). Prefer get_settings() in normal code.

    ``env_file=None`` ignores the .env file (used by the framework self-tests).
    """
    env_name = resolve_env_name(env)
    env_yaml = ENVIRONMENTS_DIR / f"{env_name}.yaml"
    if not env_yaml.exists():
        raise ConfigurationError(
            f"Unknown environment '{env_name}'. Available: {', '.join(available_environments())}"
        )

    data = _deep_merge(_read_yaml(CONFIG_DIR / "config.yaml"), _read_yaml(env_yaml))

    allowed = set(Settings.model_fields) - {"env", "credentials", "anthropic_api_key"}
    unknown = set(data) - allowed
    if unknown:
        raise ConfigurationError(
            f"Unknown top-level config keys {sorted(unknown)} "
            f"(allowed: {sorted(allowed)}). Secrets belong in .env, not YAML."
        )

    data["env"] = env_name
    try:
        return Settings(_env_file=env_file, **data)  # type: ignore[call-arg]
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration for env '{env_name}':\n{exc}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings (one load per pytest worker)."""
    return load_settings()
