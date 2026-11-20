"""Base class for page objects.

Conventions:
  * PATH is relative; contexts have base_url, so pages work in every environment.
  * Page objects expose *actions* and *locators*; they return other page objects
    when an action navigates. Business assertions stay in tests; small reusable
    ``expect_*`` helpers are fine where they describe page state.
  * No sleeps: every action relies on Playwright's auto-waiting.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Self

from playwright.sync_api import Locator, Page, expect

from framework.components.layout import FlashMessage, NavBar
from framework.reporting.allure_helpers import step_method


class BasePage:
    PATH: str = "/"
    TITLE: str = ""  # heading text; also the start of the <title>

    def __init__(self, page: Page) -> None:
        self.page = page
        self.nav = NavBar(page)
        self.flash = FlashMessage(page)

    @property
    def heading(self) -> Locator:
        return self.page.get_by_role("heading", level=1)

    @step_method("Open page {self.PATH}")
    def open(self) -> Self:
        self.page.goto(self.PATH)
        return self.expect_loaded()

    def submit_and_wait(self, submit: Callable[[], None]) -> None:
        """Run an action that submits a classic (non-JS) form and wait for the
        resulting page load. Needed when the new URL can equal the current one
        (e.g. re-running the same search), where a URL-based wait would pass
        before the new page has arrived."""
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            submit()

    def expect_loaded(self) -> Self:
        path = re.escape(self.PATH.split("?")[0])
        expect(self.page).to_have_url(re.compile(rf"{path}(\?.*)?$"))
        if self.TITLE:
            expect(self.heading).to_have_text(self.TITLE)
        return self
