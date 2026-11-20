"""Products: search, filters, add, edit, delete.

Search/filter tests read the seeded reference data but assert *properties*
(every row matches the filter) instead of exact totals, because tests running in
parallel may add products at the same time.
"""

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import ProductData, build_product
from framework.pages import ProductsPage

ProductFactory = Callable[..., tuple[ProductData, dict[str, Any]]]


@pytest.mark.smoke
def test_search_products_by_name(admin_page: Page) -> None:
    products = ProductsPage(admin_page).open()

    products.search("Wireless Mouse")

    expect(products.row("EL-1001")).to_be_visible()
    for name in products.table.column_values("Name"):
        assert "wireless mouse" in name.lower()


@pytest.mark.regression
def test_search_with_no_match_shows_empty_state(admin_page: Page) -> None:
    products = ProductsPage(admin_page).open()

    products.search("no-such-product-zzz")

    products.expect_results_count(0)
    expect(products.empty_state).to_have_text("No products match your filters.")


@pytest.mark.smoke
def test_filter_by_category_and_in_stock(admin_page: Page) -> None:
    products = ProductsPage(admin_page).open()

    products.apply_filters(category="Electronics", in_stock_only=True, sort="price_asc")

    expect(products.row("EL-1001")).to_be_visible()
    expect(products.row("EL-1003")).to_have_count(0)  # seeded Electronics item with stock 0
    assert set(products.table.column_values("Category")) == {"Electronics"}
    assert all(int(stock) > 0 for stock in products.table.column_values("Stock"))
    prices = [float(p) for p in products.table.column_values("Price")]
    assert prices == sorted(prices), f"not sorted by price ascending: {prices}"


@pytest.mark.regression
def test_filter_by_price_range(admin_page: Page) -> None:
    products = ProductsPage(admin_page).open()

    products.apply_filters(min_price=20, max_price=40)

    prices = [float(p) for p in products.table.column_values("Price")]
    assert prices, "expected seeded products between 20 and 40"
    assert all(20 <= p <= 40 for p in prices), prices


@pytest.mark.regression
def test_min_price_greater_than_max_price_is_rejected(admin_page: Page) -> None:
    products = ProductsPage(admin_page).open()

    products.apply_filters(min_price=100, max_price=10)

    expect(products.filter_errors).to_have_text(
        "Minimum price cannot be greater than maximum price"
    )


@pytest.mark.smoke
def test_add_product(admin_page: Page, backdoor: Backdoor, cleanup: CleanupRegistry) -> None:
    product = build_product(category="Sports", price=42.5, stock=7)
    cleanup.add(f"delete product {product.sku}", backdoor.delete_product_by_sku, product.sku)
    products = ProductsPage(admin_page).open()

    products.open_add_product().fill(product).save()

    products.expect_loaded()
    products.flash.expect_text("Product created successfully.")
    products.search(product.sku)
    row = products.row(product.sku)
    expect(products.table.cell(row, "Name")).to_have_text(product.name)
    expect(products.table.cell(row, "Category")).to_have_text("Sports")
    expect(products.table.cell(row, "Price")).to_have_text("42.50")
    expect(products.table.cell(row, "Stock")).to_have_text("7")


@pytest.mark.regression
def test_add_product_shows_validation_errors(admin_page: Page) -> None:
    form = ProductsPage(admin_page).open().open_add_product()

    form.fill(build_product(name="X", sku="bad sku!", price=0, stock=-1)).save()

    form.form.expect_error("Name", "Name must be at least 2 characters")
    form.form.expect_error("SKU", "SKU must be 3-20 characters: letters, digits or dashes")
    form.form.expect_error("Price", "Price must be greater than 0")
    form.form.expect_error("Stock", "Stock must be at least 0")


@pytest.mark.regression
def test_add_product_with_duplicate_sku_is_rejected(
    admin_page: Page, product_factory: ProductFactory
) -> None:
    existing, _ = product_factory()
    form = ProductsPage(admin_page).open().open_add_product()

    form.fill(build_product(sku=existing.sku)).save()

    form.form.expect_error("SKU", "A product with this SKU already exists")


@pytest.mark.smoke
def test_edit_product(
    admin_page: Page, product_factory: ProductFactory, backdoor: Backdoor
) -> None:
    product, created = product_factory(category="Home", price=10.0, stock=5)
    products = ProductsPage(admin_page).open().search(product.sku)

    form = products.open_edit(product.sku)
    form.form.expect_value("Price", "10.00")  # form is pre-filled with stored values
    form.form.fill("Price", "12.99").fill("Stock", "0")
    form.save()

    products.flash.expect_text("Product updated successfully.")
    products.search(product.sku)
    row = products.row(product.sku)
    expect(products.table.cell(row, "Price")).to_have_text("12.99")
    expect(products.table.cell(row, "Stock")).to_have_text("Out of stock")
    stored = backdoor.get_product(created["id"])
    assert stored is not None
    assert (stored["price"], stored["stock"]) == (12.99, 0)


@pytest.mark.smoke
def test_delete_product_after_confirmation(
    admin_page: Page, product_factory: ProductFactory, backdoor: Backdoor
) -> None:
    product, created = product_factory()
    products = ProductsPage(admin_page).open().search(product.sku)

    dialog = products.delete(product.sku, confirm=True)

    products.flash.expect_text("Product deleted successfully.")
    assert dialog.message == f"Delete product {product.name}? This cannot be undone."
    assert backdoor.get_product(created["id"]) is None


@pytest.mark.regression
def test_cancelling_delete_keeps_product(
    admin_page: Page, product_factory: ProductFactory, backdoor: Backdoor
) -> None:
    product, created = product_factory()
    products = ProductsPage(admin_page).open().search(product.sku)

    dialog = products.delete(product.sku, confirm=False)

    expect(products.row(product.sku)).to_be_visible()
    assert dialog.was_shown
    assert backdoor.get_product(created["id"]) is not None
