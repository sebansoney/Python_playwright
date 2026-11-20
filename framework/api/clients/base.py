"""Base for resource clients: one class per API resource, one method per endpoint.

Resource clients only build requests and return ``ApiResponse`` - no assertions,
so the same method serves positive and negative tests alike. Payloads are plain
dicts (or anything with ``to_api()``), so tests can send deliberately invalid data.
"""

from __future__ import annotations

from typing import Any, Protocol

from framework.api.http_client import ApiClient


class SupportsToApi(Protocol):
    def to_api(self) -> dict[str, Any]: ...


Payload = dict[str, Any] | SupportsToApi | None


def as_payload(payload: Payload) -> Any:
    if payload is None or isinstance(payload, dict):
        return payload
    return payload.to_api()


class ResourceClient:
    PATH = ""

    def __init__(self, client: ApiClient, api_prefix: str) -> None:
        self.client = client
        self.base = f"{api_prefix.rstrip('/')}{self.PATH}"

    def _url(self, *parts: object) -> str:
        return "/".join([self.base, *(str(p) for p in parts)])
