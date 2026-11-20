"""Build the AIClient from settings. Misconfiguration -> NullProvider (AI off), never an error."""

from __future__ import annotations

import os

from config.settings import Settings
from framework.ai.client import AIClient
from framework.ai.providers.base import LLMProvider
from framework.ai.providers.null import NullProvider
from framework.core.logging_config import get_logger
from framework.core.paths import PROJECT_ROOT, resolve_project_path

# The deepest dependency file sits ~140 chars below the project root and its bytecode
# cache ~25 more: keep the root short enough to stay under Windows' 260-char limit.
MAX_SAFE_ROOT_LEN = 90

log = get_logger(__name__)


def build_provider(settings: Settings) -> LLMProvider:
    ai = settings.ai
    if not ai.enabled:
        return NullProvider("AI is disabled (set ai.enabled: true or FW_AI__ENABLED=true)")
    if ai.provider == "none":
        return NullProvider("AI provider is 'none'")
    if ai.provider == "claude":
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        if not key:
            return NullProvider("ANTHROPIC_API_KEY is not set - AI features are skipped")
        try:
            from framework.ai.providers.claude import ClaudeProvider

            return ClaudeProvider(
                api_key=key,
                model=ai.model,
                effort=ai.effort,
                max_tokens=ai.max_tokens,
                timeout_s=ai.timeout_s,
                max_retries=ai.max_retries,
                server_side_fallback=ai.server_side_fallback,
            )
        except ImportError as exc:
            hint = ""
            if os.name == "nt" and len(str(PROJECT_ROOT)) > MAX_SAFE_ROOT_LEN:
                hint = (
                    f" - the project path is {len(str(PROJECT_ROOT))} characters long; parts of"
                    " the SDK exceed the Windows 260-character path limit. Move the project to a"
                    f" shorter path (<= {MAX_SAFE_ROOT_LEN} chars) or enable Windows long paths."
                )
            return NullProvider(f"The 'anthropic' SDK could not be imported ({exc}){hint}")
    return NullProvider(f"Unknown AI provider '{ai.provider}'")


def build_ai_client(settings: Settings, provider: LLMProvider | None = None) -> AIClient:
    provider = provider or build_provider(settings)
    if isinstance(provider, NullProvider):
        log.info("AI assistance off: %s", provider.reason)
    return AIClient(
        provider=provider,
        max_calls=settings.ai.max_calls_per_run,
        send_images=settings.ai.send_screenshots,
        audit_dir=resolve_project_path(settings.ai.output_dir) / "requests",
    )
