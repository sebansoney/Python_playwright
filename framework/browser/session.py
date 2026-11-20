"""Share one login between the API and the browser - in both directions.

The sample app accepts the same JWT as ``Authorization: Bearer`` (API) or as the
HTTP-only ``access_token`` cookie (browser). So:
  * API -> browser: put an API token into a context's storage state as that cookie.
  * browser -> API: read the cookie from a logged-in context and use it as a token.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext

AUTH_COOKIE = "access_token"


def storage_state_for_token(
    base_url: str, token: str, cookie_name: str = AUTH_COOKIE
) -> dict[str, Any]:
    """Playwright storage state (usable as ``new_context(storage_state=...)``)."""
    return {
        "cookies": [
            {
                "name": cookie_name,
                "value": token,
                "domain": urlparse(base_url).hostname,
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }


def token_from_context(context: BrowserContext, cookie_name: str = AUTH_COOKIE) -> str | None:
    """The auth token of a logged-in browser context (None when logged out)."""
    return next((c["value"] for c in context.cookies() if c["name"] == cookie_name), None)
