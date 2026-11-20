"""Components present on every authenticated page: navigation bar and flash message."""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from framework.reporting.allure_helpers import step_method


class NavBar:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.root = page.get_by_role("navigation", name="Main")
        self.current_user = page.get_by_test_id("current-user")
        self.current_role = page.get_by_test_id("current-role")

    def link(self, name: str) -> Locator:
        return self.root.get_by_role("link", name=name, exact=True)

    def go_to(self, name: str) -> None:
        self.link(name).click()

    @step_method("Log out")
    def logout(self) -> None:
        self.page.get_by_role("button", name="Log out").click()

    def expect_logged_in_as(self, full_name: str) -> None:
        expect(self.current_user).to_have_text(full_name)


class FlashMessage:
    """Success/info banner shown after create/update/delete/logout (role=status)."""

    def __init__(self, page: Page) -> None:
        self.locator = page.get_by_test_id("flash-message")

    def expect_text(self, text: str) -> None:
        expect(self.locator).to_have_text(text)
