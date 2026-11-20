"""No-op provider used whenever AI is disabled or not configured."""

from __future__ import annotations

from framework.ai.errors import AIUnavailableError
from framework.ai.providers.base import LLMRequest, LLMUsage, M


class NullProvider:
    name = "none"

    def __init__(self, reason: str = "AI is disabled") -> None:
        self.reason = reason

    def generate(self, request: LLMRequest, schema: type[M]) -> tuple[M, LLMUsage]:
        raise AIUnavailableError(self.reason)
