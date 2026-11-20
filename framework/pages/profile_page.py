from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from framework.components.form import Form
from framework.pages.base_page import BasePage
from framework.reporting.allure_helpers import step_method


class ProfilePage(BasePage):
    PATH = "/profile"
    TITLE = "My profile"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.details_form = Form(page.get_by_test_id("profile-form"))
        self.password_form = Form(page.get_by_test_id("password-form"))
        self.avatar_form = Form(page.get_by_test_id("avatar-form"))
        self.avatar_image = page.get_by_role("img", name="Profile picture")
        self.avatar_error = page.get_by_test_id("avatar-error")

    @step_method("Update profile details")
    def update_details(self, full_name: str, phone: str | None = None) -> None:
        self.details_form.fill("Full name", full_name).fill("Phone", phone).submit("Save profile")

    @step_method("Upload profile picture {file.name}")
    def upload_avatar(self, file: Path) -> None:
        self.page.get_by_label("Choose image (PNG or JPEG, max 1 MB)").set_input_files(file)
        self.avatar_form.submit("Upload picture")
