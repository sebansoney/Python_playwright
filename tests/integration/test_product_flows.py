"""Products across layers: UI <-> API."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from framework.api.clients import ApiSession
from framework.api.models import Page as ApiPage
from framework.api.models import Product
from framework.assertions import expect_api
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import ProductData, build_product
from framework.pages import ProductsPage, ToolsPage
from framework.utilities.files import read_csv

ProductFactory = Callable[..., tuple[ProductData, dict[str, Any]]]


@pytest.mark.smoke
def test_ui_created_product_is_verified_via_api(
    admin_page: Page, api: ApiSession, backdoor: Backdoor, cleanup: CleanupRegistry
) -> None:
    product = build_product(category="Electronics", price=249.99, stock=12)
    cleanup.add(f"delete product {product.sku}", backdoor.delete_product_by_sku, product.sku)

    # Act (UI)
    products = ProductsPage(admin_page).open()
    products.open_add_product().fill(product).save()
    products.flash.expect_text("Product created successfully.")

    # Assert (API): stored exactly as entered, contract-valid, owned by the admin.
    found = (
        expect_api(api.products.list(q=product.sku))
        .has_status(200)
        .matches_schema("product_page")
        .parse(ApiPage[Product])
    )
    assert len(found.items) == 1, f"expected exactly one {product.sku}, got {found.items}"
    stored = found.items[0]
    assert (stored.name, stored.sku, stored.category) == (product.name, product.sku, "Electronics")
    assert (stored.price, stored.stock, stored.in_stock) == (249.99, 12, True)
    assert stored.description == product.description
    assert stored.created_by_id == api.auth.me().json["id"]


@pytest.mark.smoke
def test_api_product_update_is_reflected_in_ui(
    api: ApiSession, admin_page: Page, product_factory: ProductFactory
) -> None:
    product, created = product_factory(price=10.0, stock=5)
    changes = {"name": f"Updated {product.name}", "price": 99.99, "stock": 0}

    expect_api(api.products.update(created["id"], changes)).has_status(200).json_contains(changes)

    products = ProductsPage(admin_page).open().search(product.sku)
    row = products.row(product.sku)
    expect(products.table.cell(row, "Name")).to_have_text(changes["name"])
    expect(products.table.cell(row, "Price")).to_have_text("99.99")
    expect(products.table.cell(row, "Stock")).to_have_text("Out of stock")
    detail = products.view_in_new_tab(product.sku)
    expect(detail.heading).to_have_text(changes["name"])
    expect(detail.price).to_have_text("99.99")
    expect(detail.stock).to_have_text("0")


@pytest.mark.smoke
def test_ui_product_delete_is_verified_via_api(
    api: ApiSession, admin_page: Page, product_factory: ProductFactory
) -> None:
    product, created = product_factory()
    expect_api(api.products.get(created["id"])).has_status(200)

    products = ProductsPage(admin_page).open().search(product.sku)
    products.delete(product.sku, confirm=True)
    products.flash.expect_text("Product deleted successfully.")

    expect_api(api.products.get(created["id"])).is_error(404, "not_found")
    assert api.products.list(q=product.sku).json["total"] == 0


@pytest.mark.regression
def test_csv_export_matches_api_data(
    api: ApiSession, admin_page: Page, product_factory: ProductFactory, tmp_path: Path
) -> None:
    product, created = product_factory(price=12.3, stock=5)

    download = ToolsPage(admin_page).open().export_products()
    file = tmp_path / download.suggested_filename
    download.save_as(file)
    _, rows = read_csv(file)

    exported = next((r for r in rows if r["sku"] == product.sku), None)
    assert exported is not None, f"{product.sku} missing from export"
    stored = expect_api(api.products.get(created["id"])).has_status(200).parse(Product)
    assert exported == {
        "name": stored.name,
        "sku": stored.sku,
        "category": stored.category,
        "price": f"{stored.price:.2f}",  # export uses 2 decimals: 12.3 -> "12.30"
        "stock": str(stored.stock),
        "description": stored.description or "",
    }


@pytest.mark.regression
@pytest.mark.parametrize(
    ("label", "field", "value", "message"),
    [
        ("Name", "name", "X", "Name must be at least 2 characters"),
        ("SKU", "sku", "bad sku!", "SKU must be 3-20 characters: letters, digits or dashes"),
        ("Price", "price", 0, "Price must be greater than 0"),
        ("Price", "price", 100_000.01, "Price must be at most 100000"),
        ("Stock", "stock", -1, "Stock must be at least 0"),
    ],
    ids=["short-name", "bad-sku", "zero-price", "price-above-max", "negative-stock"],
)
def test_validation_rules_are_identical_in_ui_and_api(
    admin_page: Page,
    user_api: ApiSession,
    backdoor: Backdoor,
    cleanup: CleanupRegistry,
    label: str,
    field: str,
    value: Any,
    message: str,
) -> None:
    """The same invalid input is rejected with the same message by the form and the API."""
    invalid = build_product(**{field: value})
    cleanup.add(f"safety: delete {invalid.sku}", backdoor.delete_product_by_sku, invalid.sku)

    form = ProductsPage(admin_page).open().open_add_product()
    form.fill(invalid).save()
    form.form.expect_error(label, message)

    expect_api(user_api.products.create(invalid)).is_error(422, "validation_error").has_field_error(
        field, message
    )
