"""Claude provider (Anthropic Python SDK). The ONLY module that imports ``anthropic``.

* Structured output: ``beta.messages.parse(output_format=<pydantic model>)`` -> the SDK
  validates the JSON and returns ``parsed_output``.
* Effort: ``output_config.effort`` controls depth/token spend (Opus 5.5 always thinks;
  effort is the lever). Configured in ``ai.effort``.
* Prompt caching: the stable system prompt carries ``cache_control`` so repeated calls
  of the same assistant reuse it (only applies above the model's minimum prefix size).
* Refusals: with ``ai.server_side_fallback`` a declined request is re-run on a fallback
  model inside the same call; a final refusal raises ``AIRefusalError``.
* Errors are mapped to AIError subclasses - the caller decides, nothing crashes a run.
"""

from __future__ import annotations

import base64
from typing import Any

from framework.ai.errors import AIError, AIRefusalError, AIUnavailableError
from framework.ai.providers.base import LLMRequest, LLMUsage, M
from framework.core.logging_config import get_logger

log = get_logger(__name__)

_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models documented to accept the server-side `fallbacks="default"` parameter.
_FALLBACK_MODELS = ("claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-sonnet-5-5")


class ClaudeProvider:
    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str,
        effort: str = "high",
        max_tokens: int = 16000,
        timeout_s: float = 300,
        max_retries: int = 2,
        server_side_fallback: bool = True,
    ) -> None:
        import anthropic  # lazy: the rest of the framework never needs the SDK

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.use_fallback = server_side_fallback and model.startswith(_FALLBACK_MODELS)

    # ------------------------------------------------------------------ call
    def generate(self, request: LLMRequest, schema: type[M]) -> tuple[M, LLMUsage]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": self._content(request)}],
            "output_format": schema,
            "output_config": {"effort": self.effort},
        }
        if self.use_fallback:
            kwargs["betas"] = [_FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        a = self._anthropic
        try:
            response = self._client.beta.messages.parse(**kwargs)
        except a.AuthenticationError as exc:
            raise AIUnavailableError(
                "Claude rejected the API key (check ANTHROPIC_API_KEY)"
            ) from exc
        except a.PermissionDeniedError as exc:
            raise AIUnavailableError(f"API key lacks permission: {exc.message}") from exc
        except a.RateLimitError as exc:
            raise AIUnavailableError("Claude rate limit reached (after SDK retries)") from exc
        except (a.APITimeoutError, a.APIConnectionError) as exc:
            raise AIUnavailableError(f"Claude not reachable: {exc.__class__.__name__}") from exc
        except a.BadRequestError as exc:
            raise AIError(f"Claude rejected the request: {exc.message}") from exc
        except a.APIStatusError as exc:
            if exc.status_code >= 500:
                raise AIUnavailableError(f"Claude server error {exc.status_code}") from exc
            raise AIError(f"Claude API error {exc.status_code}: {exc.message}") from exc

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise AIRefusalError(f"Claude declined the request (category: {category})")
        if response.stop_reason == "max_tokens":
            raise AIError(f"Answer truncated at max_tokens={self.max_tokens}; raise ai.max_tokens")
        parsed = response.parsed_output
        if parsed is None:
            raise AIError("Claude returned no structured output")

        usage = response.usage
        result_usage = LLMUsage(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            model=response.model,
            extra={"request_id": getattr(response, "_request_id", None)},
        )
        return parsed, result_usage

    @staticmethod
    def _content(request: LLMRequest) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for image in request.images:
            blocks.append({"type": "text", "text": f"[{image.label}]"})
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.standard_b64encode(image.data).decode("ascii"),
                    },
                }
            )
        blocks.append({"type": "text", "text": request.prompt})
        return blocks
