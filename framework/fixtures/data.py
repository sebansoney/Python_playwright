"""Test-data fixtures: API backdoor, factories that auto-register cleanup."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from framework.api.clients import ApiSession
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import ProductData, UserData, build_product, build_user


@pytest.fixture(scope="session")
def backdoor(admin_backdoor_session: ApiSession) -> Backdoor:
    return Backdoor(admin_backdoor_session)


@pytest.fixture
def cleanup() -> Iterator[CleanupRegistry]:
    registry = CleanupRegistry()
    yield registry
    failures = registry.run()
    if failures:
        warnings.warn(
            pytest.PytestWarning("Test data cleanup failed: " + "; ".join(failures)), stacklevel=1
        )


@pytest.fixture
def product_factory(
    backdoor: Backdoor, cleanup: CleanupRegistry
) -> Callable[..., tuple[ProductData, dict[str, Any]]]:
    """Create a product via API (deleted after the test). Returns (input, API response)."""

    def create(**overrides: Any) -> tuple[ProductData, dict[str, Any]]:
        data = build_product(**overrides)
        created = backdoor.create_product(data)
        cleanup.add(f"delete product {data.sku}", backdoor.delete_product, created["id"])
        return data, created

    return create


@pytest.fixture
def user_factory(
    backdoor: Backdoor, cleanup: CleanupRegistry
) -> Callable[..., tuple[UserData, dict[str, Any]]]:
    """Create a user via API (deleted after the test). Returns (input, API response)."""

    def create(**overrides: Any) -> tuple[UserData, dict[str, Any]]:
        data = build_user(**overrides)
        created = backdoor.create_user(data)
        cleanup.add(f"delete user {data.email}", backdoor.delete_user, created["id"])
        return data, created

    return create
