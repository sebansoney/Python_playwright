"""Products: list (search/filters/sort), add/edit form, detail page."""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from framework.components.data_table import DataTable
from framework.components.dialogs import NextDialog
from framework.components.form import Form
from framework.data.factories import ProductData
from framework.pages.base_page import BasePage
from framework.reporting.allure_helpers import step_method

SORT_LABELS = {
    "name_asc": "Name (A-Z)",
    "name_desc": "Name (Z-A)",
    "price_asc": "Price (low to high)",
    "price_desc": "Price (high to low)",
    "newest": "Newest first",
}


class ProductsPage(BasePage):
    PATH = "/products"
    TITLE = "Products"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.filters = Form(page.get_by_test_id("product-filters"))
        self.results_count = page.get_by_test_id("results-count")
        self.table = DataTable(page.get_by_role("table"))
        self.empty_state = page.get_by_test_id("empty-state")
        self.filter_errors = page.get_by_role("alert")

    # ------------------------------------------------------------- filters
    @step_method("Search products for '{text}'")
    def search(self, text: str) -> ProductsPage:
        return self.apply_filters(search=text)

    @step_method("Apply product filters")
    def apply_filters(
        self,
        search: str | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock_only: bool | None = None,
        sort: str | None = None,
    ) -> ProductsPage:
        f = self.filters
        f.fill("Search", search).select("Category", category)
        f.fill("Min price", min_price).fill("Max price", max_price)
        if in_stock_only is not None:
            f.set_checked("In stock only", in_stock_only)
        if sort is not None:
            f.select("Sort by", SORT_LABELS[sort])
        self.submit_and_wait(lambda: f.submit("Apply filters"))
        return self

    def expect_results_count(self, count: int) -> None:
        noun = "product" if count == 1 else "products"
        expect(self.results_count).to_have_text(f"{count} {noun} found")

    # ---------------------------------------------------------------- rows
    def row(self, sku: str) -> Locator:
        return self.table.row_with(sku)

    @step_method("Open 'Add product' form")
    def open_add_product(self) -> ProductFormPage:
        self.page.get_by_role("link", name="Add product").click()
        return ProductFormPage(self.page, editing=False).expect_loaded()

    @step_method("Open edit form of product {sku}")
    def open_edit(self, sku: str) -> ProductFormPage:
        self.row(sku).get_by_role("link", name="Edit").click()
        return ProductFormPage(self.page, editing=True).expect_loaded()

    @step_method("Delete product {sku} (accept dialog: {confirm})")
    def delete(self, sku: str, confirm: bool = True) -> NextDialog:
        dialog = NextDialog(self.page, accept=confirm)
        self.row(sku).get_by_role("button", name="Delete").click()
        return dialog

    @step_method("Open product {sku} in a new tab")
    def view_in_new_tab(self, sku: str) -> ProductDetailPage:
        """'View' opens target=_blank: capture the new tab as a popup."""
        with self.page.expect_popup() as popup_info:
            self.row(sku).get_by_role("link", name="View").click()
        new_tab = popup_info.value
        new_tab.wait_for_load_state()
        return ProductDetailPage(new_tab)


class ProductFormPage(BasePage):
    PATH = "/products"

    def __init__(self, page: Page, editing: bool) -> None:
        super().__init__(page)
        self.editing = editing
        self.TITLE = "Edit product" if editing else "Add product"
        self.form = Form(page.get_by_test_id("product-form"))

    def expect_loaded(self) -> ProductFormPage:
        expect(self.heading).to_have_text(self.TITLE)
        return self

    @step_method("Fill product form ({product.sku})")
    def fill(self, product: ProductData) -> ProductFormPage:
        (
            self.form.fill("Name", product.name)
            .fill("SKU", product.sku)
            .select("Category", product.category)
            .fill("Price", product.price_text)
            .fill("Stock", product.stock)
            .fill("Description", product.description)
        )
        return self

    @step_method("Save product form")
    def save(self) -> None:
        self.form.submit("Save changes" if self.editing else "Create product")


class ProductDetailPage(BasePage):
    PATH = "/products"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.sku = page.get_by_test_id("detail-sku")
        self.category = page.get_by_test_id("detail-category")
        self.price = page.get_by_test_id("detail-price")
        self.stock = page.get_by_test_id("detail-stock")
