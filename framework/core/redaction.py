"""Secret redaction - one implementation used by logs, Allure attachments and the AI layer.

Three complementary techniques:
  1. Key-based:   any dict/header key containing a sensitive word (password, token ...)
                  has its value masked, at any nesting depth.
  2. Pattern-based: JWTs, "Bearer ..." headers, API-key shapes, and "key=value" /
                  '"key": "value"' fragments inside free text are masked.
  3. Value-based: actual secret values known at runtime (configured passwords,
                  the Anthropic key) are masked wherever they appear.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

DEFAULT_MASK = "***REDACTED***"
DEFAULT_SENSITIVE_KEYS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "x-api-key",
    "session",
)

_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_API_KEY_RE = re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


class Redactor:
    def __init__(
        self,
        sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_KEYS,
        mask: str = DEFAULT_MASK,
        mask_emails: bool = False,
    ) -> None:
        self.mask = mask
        self.mask_emails = mask_emails
        self._keys = tuple(k.lower() for k in sensitive_keys)
        self._secrets: set[str] = set()
        key_alt = "|".join(re.escape(k) for k in self._keys) or r"(?!x)x"
        # Matches  password=abc  |  "access_token": "abc"  |  Set-Cookie: abc
        self._kv_re = re.compile(
            rf"""(?ix)
            (["']?[\w-]*(?:{key_alt})[\w-]*["']?\s*[:=](?![:=])\s*)   # key + separator
                                                            # ("::" / "==" are not separators,
                                                            #  e.g. fixture "api_session::0")
            (["']?)                                         # optional opening quote
            ([^"',&;\s}}\]]+)                               # the value
            """
        )

    # ------------------------------------------------------------------ setup
    def register_secret(self, value: str | None) -> None:
        """Mask this exact value anywhere it appears (ignore trivially short values)."""
        if value and len(value) >= 4:
            self._secrets.add(value)

    def register_secrets(self, values: Iterable[str | None]) -> None:
        for v in values:
            self.register_secret(v)

    # ------------------------------------------------------------------- core
    def is_sensitive_key(self, key: str) -> bool:
        k = key.lower()
        return any(s in k for s in self._keys)

    def redact_text(self, text: str, *, mask_emails: bool | None = None) -> str:
        if not text:
            return text
        # Longest first so a secret that contains another is fully masked.
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, self.mask)
        text = _JWT_RE.sub(self.mask, text)
        text = _BEARER_RE.sub(lambda m: f"{m.group(1)} {self.mask}", text)
        text = _API_KEY_RE.sub(self.mask, text)
        text = self._kv_re.sub(lambda m: f"{m.group(1)}{m.group(2)}{self.mask}", text)
        if self.mask_emails if mask_emails is None else mask_emails:
            text = _EMAIL_RE.sub("<email>", text)
        return text

    def redact(self, data: Any, *, mask_emails: bool | None = None) -> Any:
        """Recursively redact dicts, lists, tuples and strings. Returns a copy."""
        if isinstance(data, str):
            return self.redact_text(data, mask_emails=mask_emails)
        if isinstance(data, Mapping):
            return {
                k: (
                    self.mask
                    if isinstance(k, str) and self.is_sensitive_key(k) and v not in (None, "")
                    else self.redact(v, mask_emails=mask_emails)
                )
                for k, v in data.items()
            }
        if isinstance(data, list | tuple):
            return type(data)(self.redact(v, mask_emails=mask_emails) for v in data)
        return data


# A single process-wide instance, configured at start-up from settings.
_redactor = Redactor()


def get_redactor() -> Redactor:
    return _redactor


def configure_redactor(
    sensitive_keys: Iterable[str] | None = None,
    mask: str = DEFAULT_MASK,
    mask_emails: bool = False,
    secrets: Iterable[str | None] = (),
) -> Redactor:
    """Replace the global redactor (called once from the pytest bootstrap)."""
    global _redactor
    _redactor = Redactor(sensitive_keys or DEFAULT_SENSITIVE_KEYS, mask, mask_emails)
    _redactor.register_secrets(secrets)
    return _redactor
