"""Clients for the sample application's REST resources."""

from __future__ import annotations

from typing import Any

from framework.api.clients.base import Payload, ResourceClient, as_payload
from framework.api.http_client import ApiResponse


class SystemClient(ResourceClient):
    PATH = ""

    def health(self) -> ApiResponse:
        return self.client.get(self._url("health"))

    def reset_database(self) -> ApiResponse:
        return self.client.post(self._url("test-support", "reset"))


class AuthClient(ResourceClient):
    PATH = "/auth"

    def login(self, email: str | None, password: str | None, **extra: Any) -> ApiResponse:
        body = {
            k: v
            for k, v in {"email": email, "password": password, **extra}.items()
            if v is not None
        }
        return self.client.post(self._url("login"), json=body, auth=None)

    def register(self, payload: Payload) -> ApiResponse:
        return self.client.post(self._url("register"), json=as_payload(payload), auth=None)

    def logout(self) -> ApiResponse:
        return self.client.post(self._url("logout"))

    def me(self) -> ApiResponse:
        return self.client.get(self._url("me"))


class UsersClient(ResourceClient):
    PATH = "/users"

    def list(
        self, q: str | None = None, role: str | None = None, page: Any = None, size: Any = None
    ) -> ApiResponse:
        return self.client.get(self.base, params={"q": q, "role": role, "page": page, "size": size})

    def create(self, payload: Payload) -> ApiResponse:
        return self.client.post(self.base, json=as_payload(payload))

    def get(self, user_id: Any) -> ApiResponse:
        return self.client.get(self._url(user_id))

    def replace(self, user_id: Any, payload: Payload) -> ApiResponse:
        return self.client.put(self._url(user_id), json=as_payload(payload))

    def update(self, user_id: Any, payload: Payload) -> ApiResponse:
        return self.client.patch(self._url(user_id), json=as_payload(payload))

    def delete(self, user_id: Any) -> ApiResponse:
        return self.client.delete(self._url(user_id))


class ProductsClient(ResourceClient):
    PATH = "/products"

    def list(self, **filters: Any) -> ApiResponse:
        """Filters: q, category, min_price, max_price, in_stock, sort, page, size."""
        return self.client.get(self.base, params=filters)

    def categories(self) -> ApiResponse:
        return self.client.get(self._url("categories"))

    def create(self, payload: Payload) -> ApiResponse:
        return self.client.post(self.base, json=as_payload(payload))

    def get(self, product_id: Any) -> ApiResponse:
        return self.client.get(self._url(product_id))

    def replace(self, product_id: Any, payload: Payload) -> ApiResponse:
        return self.client.put(self._url(product_id), json=as_payload(payload))

    def update(self, product_id: Any, payload: Payload) -> ApiResponse:
        return self.client.patch(self._url(product_id), json=as_payload(payload))

    def delete(self, product_id: Any) -> ApiResponse:
        return self.client.delete(self._url(product_id))


class ProfileClient(ResourceClient):
    PATH = "/profile"

    def get(self) -> ApiResponse:
        return self.client.get(self.base)

    def update(self, payload: Payload) -> ApiResponse:
        return self.client.put(self.base, json=as_payload(payload))

    def change_password(self, current_password: str, new_password: str) -> ApiResponse:
        body = {"current_password": current_password, "new_password": new_password}
        return self.client.post(self._url("password"), json=body)

    def upload_avatar(self, filename: str, content: bytes, content_type: str) -> ApiResponse:
        return self.client.post(
            self._url("avatar"), files={"file": (filename, content, content_type)}
        )
