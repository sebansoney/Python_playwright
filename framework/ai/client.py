"""AIClient - the single, mandatory gate between the framework and any LLM.

Every AI service talks to the model ONLY through ``AIClient.ask``, which:
  1. redacts system prompt and prompt (secrets, tokens, known passwords AND emails),
  2. drops screenshots unless ``ai.send_screenshots`` is true,
  3. enforces the per-run call budget (``ai.max_calls_per_run``),
  4. writes exactly what was sent to ``reports/ai/requests/`` (transparency / audit),
  5. never raises: failures come back as ``AIOutcome(ok=False, message=...)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from framework.ai.errors import AIError
from framework.ai.providers.base import ImageInput, LLMProvider, LLMRequest, LLMUsage
from framework.ai.providers.null import NullProvider
from framework.core.logging_config import get_logger
from framework.core.redaction import Redactor, get_redactor

log = get_logger(__name__)


@dataclass
class AIOutcome[T: BaseModel]:
    ok: bool
    value: T | None = None
    message: str = ""
    usage: LLMUsage | None = None


@dataclass
class AIClient:
    provider: LLMProvider
    max_calls: int = 20
    send_images: bool = False
    audit_dir: Path | None = None
    redactor: Redactor = field(default_factory=get_redactor)
    calls_made: int = 0
    total_usage: LLMUsage = field(default_factory=LLMUsage)

    @property
    def enabled(self) -> bool:
        return not isinstance(self.provider, NullProvider)

    @property
    def disabled_reason(self) -> str:
        return getattr(self.provider, "reason", "") if not self.enabled else ""

    def ask[S: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        schema: type[S],
        purpose: str,
        images: tuple[ImageInput, ...] = (),
    ) -> AIOutcome[S]:
        if not self.enabled:
            return AIOutcome(ok=False, message=self.disabled_reason or "AI is disabled")
        if self.calls_made >= self.max_calls:
            return AIOutcome(
                ok=False, message=f"AI call budget exhausted ({self.max_calls} per run)"
            )

        request = LLMRequest(
            system=self.redactor.redact_text(system, mask_emails=True),
            prompt=self.redactor.redact_text(prompt, mask_emails=True),
            images=images if self.send_images else (),
            purpose=purpose,
        )
        self.calls_made += 1
        self._audit(request, dropped_images=len(images) - len(request.images))
        try:
            value, usage = self.provider.generate(request, schema)
        except AIError as exc:
            log.warning("AI call '%s' failed: %s", purpose, exc)
            return AIOutcome(ok=False, message=str(exc))
        self._add_usage(usage)
        log.info(
            "AI call '%s' ok: %s in / %s out tokens (cache read %s), model %s",
            purpose,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.model,
        )
        return AIOutcome(ok=True, value=value, usage=usage)

    # -------------------------------------------------------------- helpers
    def _add_usage(self, usage: LLMUsage) -> None:
        t = self.total_usage
        t.input_tokens += usage.input_tokens
        t.output_tokens += usage.output_tokens
        t.cache_read_tokens += usage.cache_read_tokens
        t.cache_write_tokens += usage.cache_write_tokens
        t.model = usage.model or t.model

    def _audit(self, request: LLMRequest, dropped_images: int) -> None:
        """Record what leaves the machine (already redacted) for human review."""
        if self.audit_dir is None:
            return
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = self.audit_dir / f"{stamp}-{self.calls_made:02d}-{request.purpose}.md"
        meta = {
            "purpose": request.purpose,
            "provider": getattr(self.provider, "name", "?"),
            "model": getattr(self.provider, "model", "?"),
            "images_sent": [i.label for i in request.images],
            "images_dropped": dropped_images,
        }
        path.write_text(
            f"# AI request (as sent, redacted)\n\n```json\n{json.dumps(meta, indent=2)}\n```\n\n"
            f"## System\n\n{request.system}\n\n## Prompt\n\n{request.prompt}\n",
            encoding="utf-8",
        )
