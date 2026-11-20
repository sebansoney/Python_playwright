from __future__ import annotations

from playwright.sync_api import Locator, Page

from framework.pages.base_page import BasePage


class DashboardPage(BasePage):
    PATH = "/dashboard"
    TITLE = "Dashboard"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.welcome = page.get_by_test_id("welcome-message")

    def stat(self, name: str) -> Locator:
        """Value of a statistics card: 'Users', 'Products', 'Low stock', 'Categories'."""
        card = self.page.get_by_role("article").filter(
            has=self.page.get_by_role("heading", name=name, exact=True)
        )
        return card.locator(".stat-value")
