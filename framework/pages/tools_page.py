"""Tools page: download, upload, iframe, popup window and dynamic content."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Download, FrameLocator, Locator, Page

from framework.pages.base_page import BasePage
from framework.reporting.allure_helpers import step_method


class ToolsPage(BasePage):
    PATH = "/tools"
    TITLE = "Tools"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.export_link = page.get_by_role("link", name="Export products (CSV)")
        self.import_input = page.get_by_label("CSV file")
        self.import_summary = page.get_by_test_id("import-summary")
        self.import_error = page.get_by_test_id("import-error")
        self.import_errors_table = page.get_by_test_id("import-errors")
        self.load_notifications_button = page.get_by_role("button", name="Load notifications")
        self.notifications_status = page.get_by_test_id("notifications-status")
        self.notifications = page.get_by_test_id("notifications-list").get_by_role("listitem")

    # ------------------------------------------------------------ download
    @step_method("Export products as CSV (download)")
    def export_products(self) -> Download:
        with self.page.expect_download() as download_info:
            self.export_link.click()
        return download_info.value

    # -------------------------------------------------------------- upload
    @step_method("Import products from {csv_file.name}")
    def import_products(self, csv_file: Path) -> None:
        self.import_input.set_input_files(csv_file)
        self.page.get_by_role("button", name="Import", exact=True).click()

    # ------------------------------------------------------------- dynamic
    @step_method("Load notifications")
    def load_notifications(self) -> None:
        self.load_notifications_button.click()

    # ----------------------------------------------------- iframe & popup
    @property
    def help_frame(self) -> FrameLocator:
        return self.page.frame_locator("iframe[title='Help center']")

    def help_message_box(self) -> Locator:
        return self.help_frame.get_by_label("Message to support")

    @step_method("Open help in a popup window")
    def open_help_popup(self) -> Page:
        with self.page.expect_popup() as popup_info:
            self.page.get_by_role("button", name="Open help in new window").click()
        popup = popup_info.value
        popup.wait_for_load_state()
        return popup
