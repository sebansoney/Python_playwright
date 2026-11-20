"""Provider-neutral interface. Services depend on this, never on a vendor SDK.

Adding another LLM = one new module implementing ``LLMProvider`` + one line in
``framework/ai/factory.py``. Nothing else in the framework changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True)
class ImageInput:
    media_type: str  # "image/png" | "image/jpeg"
    data: bytes
    label: str = "screenshot"


@dataclass(frozen=True)
class LLMRequest:
    """One self-contained question. ``system`` should be stable (cacheable);
    ``prompt`` carries the variable, already-redacted context."""

    system: str
    prompt: str
    images: tuple[ImageInput, ...] = ()
    purpose: str = "general"  # for logs / budget accounting


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""
    extra: dict[str, object] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def generate(self, request: LLMRequest, schema: type[M]) -> tuple[M, LLMUsage]:
        """Return a validated instance of ``schema``. Raise AIError subclasses on failure."""
        ...
