"""Fast test-data setup/cleanup through the REST API ("backdoor").

UI and integration tests should not click through five screens just to get a
product to edit: they create preconditions via the API and spend browser time only
on the behaviour under test.

Built on the HTTPX API layer (Phase 5). Setup traffic is not part of a test's
API exchange log; failures raise ``BackdoorError`` (environment problem, not a defect).
"""

from __future__ import annotations

from typing import Any

from framework.api.clients import ApiSession
from framework.api.http_client import ApiResponse
from framework.core.exceptions import FrameworkError
from framework.data.factories import ProductData, UserData


class BackdoorError(FrameworkError):
    """Setup/cleanup API call failed (an environment problem, not a product defect)."""


def _ok(response: ApiResponse, action: str, ok: tuple[int, ...] = (200, 201, 204)) -> Any:
    if response.status not in ok:
        raise BackdoorError(f"{action} failed: HTTP {response.status}\n{response.summary()}")
    return response.json


class Backdoor:
    def __init__(self, api: ApiSession) -> None:
        self._api = api

    # ---------------------------------------------------------------- users
    def create_user(self, user: UserData) -> dict[str, Any]:
        return _ok(self._api.users.create(user), "create user")

    def find_user(self, email: str) -> dict[str, Any] | None:
        page = _ok(self._api.users.list(q=email, size=100), "search users")
        return next((u for u in page["items"] if u["email"] == email.lower()), None)

    def get_user(self, user_id: int) -> dict[str, Any]:
        return _ok(self._api.users.get(user_id), "get user")

    def delete_user(self, user_id: int) -> None:
        _ok(self._api.users.delete(user_id), "delete user", ok=(204, 404))

    def delete_user_by_email(self, email: str) -> None:
        user = self.find_user(email)
        if user:
            self.delete_user(user["id"])

    # ------------------------------------------------------------- products
    def create_product(self, product: ProductData) -> dict[str, Any]:
        return _ok(self._api.products.create(product), "create product")

    def find_product(self, sku: str) -> dict[str, Any] | None:
        page = _ok(self._api.products.list(q=sku, size=100), "search products")
        return next((p for p in page["items"] if p["sku"] == sku.upper()), None)

    def get_product(self, product_id: int) -> dict[str, Any] | None:
        response = self._api.products.get(product_id)
        return None if response.status == 404 else _ok(response, "get product")

    def delete_product(self, product_id: int) -> None:
        _ok(self._api.products.delete(product_id), "delete product", ok=(204, 404))

    def delete_product_by_sku(self, sku: str) -> None:
        product = self.find_product(sku)
        if product:
            self.delete_product(product["id"])
