"""Token management.

``TokenProvider`` logs in once per account and caches the JWT until shortly before
it expires. ``BearerAuth`` plugs it into HTTPX, so clients never handle tokens
themselves. Login traffic is not recorded in the per-test exchange log (it carries
passwords) - and would be redacted anyway.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from dataclasses import dataclass

import httpx

from framework.core.exceptions import FrameworkError
from framework.core.logging_config import get_logger
from framework.core.redaction import get_redactor

log = get_logger(__name__)

_REFRESH_MARGIN_S = 60


class AuthenticationError(FrameworkError):
    """Could not obtain a token for a configured test account (environment problem)."""


@dataclass
class _CachedToken:
    value: str
    expires_at: float


class TokenProvider:
    def __init__(self, api_base_url: str, timeout_s: float = 10, verify_ssl: bool = True) -> None:
        self._base = api_base_url.rstrip("/")
        self._timeout = timeout_s
        self._verify = verify_ssl
        self._cache: dict[str, _CachedToken] = {}

    def token(self, email: str, password: str) -> str:
        cached = self._cache.get(email.lower())
        if cached and cached.expires_at - _REFRESH_MARGIN_S > time.monotonic():
            return cached.value
        get_redactor().register_secret(password)
        response = httpx.post(
            f"{self._base}/auth/login",
            json={"email": email, "password": password},
            timeout=self._timeout,
            verify=self._verify,
        )
        if response.status_code != 200:
            raise AuthenticationError(
                f"Login for {email} failed: HTTP {response.status_code} "
                f"{get_redactor().redact_text(response.text)[:300]}"
            )
        body = response.json()
        token = body["access_token"]
        get_redactor().register_secret(token)
        self._cache[email.lower()] = _CachedToken(token, time.monotonic() + body["expires_in"])
        log.info("Obtained API token for %s (valid %ss)", email, body["expires_in"])
        return token

    def invalidate(self, email: str) -> None:
        self._cache.pop(email.lower(), None)


class BearerAuth(httpx.Auth):
    """HTTPX auth hook: adds ``Authorization: Bearer <token>`` for one account."""

    def __init__(self, provider: TokenProvider, email: str, password: str) -> None:
        self._provider = provider
        self._email = email
        self._password = password

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = (
            f"Bearer {self._provider.token(self._email, self._password)}"
        )
        yield request


class StaticBearerAuth(httpx.Auth):
    """Send a fixed (possibly invalid/expired) token - for negative auth tests."""

    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request
