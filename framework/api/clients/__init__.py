"""Resource clients bundled into one ``ApiSession`` per identity (admin, user, anonymous)."""

from __future__ import annotations

from dataclasses import dataclass, field

from framework.api.clients.resources import (
    AuthClient,
    ProductsClient,
    ProfileClient,
    SystemClient,
    UsersClient,
)
from framework.api.http_client import ApiClient


@dataclass
class ApiSession:
    """Everything a test needs to talk to the API as one identity::

    api.users.create(...), api.products.list(category="Books"), api.auth.me()
    """

    client: ApiClient
    api_prefix: str
    system: SystemClient = field(init=False)
    auth: AuthClient = field(init=False)
    users: UsersClient = field(init=False)
    products: ProductsClient = field(init=False)
    profile: ProfileClient = field(init=False)

    def __post_init__(self) -> None:
        self.system = SystemClient(self.client, self.api_prefix)
        self.auth = AuthClient(self.client, self.api_prefix)
        self.users = UsersClient(self.client, self.api_prefix)
        self.products = ProductsClient(self.client, self.api_prefix)
        self.profile = ProfileClient(self.client, self.api_prefix)


__all__ = [
    "ApiSession",
    "AuthClient",
    "ProductsClient",
    "ProfileClient",
    "SystemClient",
    "UsersClient",
]
