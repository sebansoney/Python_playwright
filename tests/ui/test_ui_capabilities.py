"""Browser capabilities: download, upload, iframe, popup, new tab, dynamic content."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from framework.core.paths import TEST_DATA_DIR
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import ProductData, UserData, build_product
from framework.pages import ProductsPage, ProfilePage, ToolsPage
from framework.utilities.files import read_csv, write_csv

CSV_COLUMNS = ("name", "sku", "category", "price", "stock", "description")


@pytest.mark.regression
def test_export_products_downloads_valid_csv(admin_page: Page, tmp_path: Path) -> None:
    tools = ToolsPage(admin_page).open()

    download = tools.export_products()

    assert re.fullmatch(r"products_\d{8}\.csv", download.suggested_filename)
    saved = tmp_path / download.suggested_filename
    download.save_as(saved)
    header, rows = read_csv(saved)
    assert header == list(CSV_COLUMNS)
    skus = {row["sku"] for row in rows}
    assert {"EL-1001", "BK-2001", "TY-6002"} <= skus  # seeded reference products
    mouse = next(row for row in rows if row["sku"] == "EL-1001")
    assert (mouse["name"], mouse["price"]) == ("Wireless Mouse", "24.99")


@pytest.mark.regression
def test_import_products_from_csv_reports_partial_success(
    admin_page: Page, tmp_path: Path, backdoor: Backdoor, cleanup: CleanupRegistry
) -> None:
    good = build_product()
    bad = build_product(category="Cars", price=-5)
    for p in (good, bad):
        cleanup.add(f"delete product {p.sku}", backdoor.delete_product_by_sku, p.sku)
    csv_file = write_csv(tmp_path / "import.csv", CSV_COLUMNS, [good.to_api(), bad.to_api()])
    tools = ToolsPage(admin_page).open()

    tools.import_products(csv_file)

    expect(tools.import_summary).to_have_text("Imported 1 product, 1 row rejected.")
    expect(tools.import_errors_table.get_by_role("row").nth(1)).to_contain_text("3")  # CSV line
    expect(tools.import_errors_table).to_contain_text("Price must be greater than 0")
    assert backdoor.find_product(good.sku) is not None
    assert backdoor.find_product(bad.sku) is None


@pytest.mark.regression
def test_import_rejects_non_csv_file(admin_page: Page) -> None:
    tools = ToolsPage(admin_page).open()

    tools.import_products(TEST_DATA_DIR / "images" / "avatar.png")

    expect(tools.import_error).to_have_text("Only .csv files are supported")


@pytest.mark.regression
def test_avatar_upload_shows_picture(
    page_for: Callable[[str, str], Page], user_factory: Callable[..., tuple[UserData, Any]]
) -> None:
    user, _ = user_factory()  # own user: never modify shared seed accounts
    profile = ProfilePage(page_for(user.email, user.password)).open()
    expect(profile.avatar_image).to_have_count(0)

    profile.upload_avatar(TEST_DATA_DIR / "images" / "avatar.png")

    profile.flash.expect_text("Profile picture updated.")
    expect(profile.avatar_image).to_be_visible()
    # The <img> really loaded (naturalWidth > 0), not just rendered as broken.
    assert profile.avatar_image.evaluate("img => img.naturalWidth") == 16


@pytest.mark.regression
def test_avatar_upload_rejects_non_image(
    page_for: Callable[[str, str], Page], user_factory: Callable[..., tuple[UserData, Any]]
) -> None:
    user, _ = user_factory()
    profile = ProfilePage(page_for(user.email, user.password)).open()

    profile.upload_avatar(TEST_DATA_DIR / "images" / "not_an_image.txt")

    expect(profile.avatar_error).to_have_text("Avatar must be a PNG or JPEG image")


@pytest.mark.regression
def test_help_iframe_contact_form(admin_page: Page) -> None:
    tools = ToolsPage(admin_page).open()
    frame = tools.help_frame

    expect(frame.get_by_role("heading", name="Help center")).to_be_visible()
    tools.help_message_box().fill("I need help with exports")
    frame.get_by_role("button", name="Send message").click()

    expect(frame.get_by_test_id("contact-status")).to_have_text(
        "Thanks! Your message has been sent."
    )


@pytest.mark.regression
def test_help_opens_in_popup_window(admin_page: Page) -> None:
    tools = ToolsPage(admin_page).open()

    popup = tools.open_help_popup()

    expect(popup).to_have_title(re.compile("^Help center"))
    popup.get_by_text("How do I export data?").click()  # expand <details>
    expect(popup.get_by_text("Export products (CSV)")).to_be_visible()
    popup.close()
    expect(tools.heading).to_have_text("Tools")  # original page unaffected


@pytest.mark.regression
def test_view_product_opens_in_new_tab(
    admin_page: Page, product_factory: Callable[..., tuple[ProductData, Any]]
) -> None:
    product, _ = product_factory(price=19.9)
    products = ProductsPage(admin_page).open().search(product.sku)

    detail = products.view_in_new_tab(product.sku)

    expect(detail.heading).to_have_text(product.name)
    expect(detail.sku).to_have_text(product.sku)
    expect(detail.price).to_have_text("19.90")
    assert len(admin_page.context.pages) == 2


@pytest.mark.regression
def test_notifications_load_dynamically(admin_page: Page) -> None:
    tools = ToolsPage(admin_page).open()
    expect(tools.notifications).to_have_count(0)

    tools.load_notifications()

    # No sleep: expect() retries until the delayed (~1.5 s) content arrives.
    expect(tools.notifications_status).to_have_text("3 notifications loaded")
    expect(tools.notifications).to_have_text(
        [
            "Weekly inventory report is available",
            "5 products are running low on stock",
            "Nightly backup completed",
        ]
    )
    expect(tools.load_notifications_button).to_be_enabled()
