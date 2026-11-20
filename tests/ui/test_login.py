"""Login / logout behaviour.

Credentials come from settings (.env); expected texts are the app's documented
messages (docs/sample_application.md).
"""

import re

import pytest
from playwright.sync_api import Page, expect

from config.settings import Settings
from framework.pages import DashboardPage, LoginPage


@pytest.mark.smoke
def test_valid_login_opens_dashboard(page: Page, settings: Settings) -> None:
    email, password = settings.credentials.require("admin")

    dashboard = LoginPage(page).open().login_as(email, password)

    expect(dashboard.welcome).to_have_text("Welcome, Admin User!")
    dashboard.nav.expect_logged_in_as("Admin User")
    expect(dashboard.nav.current_role).to_have_text("admin")


@pytest.mark.smoke
def test_invalid_password_shows_error_and_stays_on_login(page: Page, settings: Settings) -> None:
    email, _ = settings.credentials.require("admin")
    login = LoginPage(page).open()

    login.login(email, "Wrong-Password-1")

    expect(login.error_alert).to_have_text("Invalid email or password")
    expect(page).to_have_url(re.compile(r"/login$"))
    login.form.expect_value("Email", email)  # email is kept, password is not
    login.form.expect_value("Password", "")


@pytest.mark.regression
def test_empty_fields_show_required_messages(page: Page) -> None:
    login = LoginPage(page).open()

    login.form.submit("Log in")

    login.form.expect_error("Email", "Email is required")
    login.form.expect_error("Password", "Password is required")
    expect(login.error_alert).to_have_count(0)


@pytest.mark.regression
def test_disabled_account_cannot_log_in(page: Page, settings: Settings) -> None:
    _, password = settings.credentials.require("user")  # seeded with the user password
    login = LoginPage(page).open()

    login.login("disabled.user@example.test", password)

    expect(login.error_alert).to_have_text("Account is disabled")


@pytest.mark.sanity
def test_logout_returns_to_login_with_message(admin_page: Page) -> None:
    dashboard = DashboardPage(admin_page).open()

    dashboard.nav.logout()

    login = LoginPage(admin_page).expect_loaded()
    login.flash.expect_text("You have been logged out.")
    # Session is gone: protected pages redirect to login again.
    admin_page.goto(DashboardPage.PATH)
    LoginPage(admin_page).expect_loaded()


@pytest.mark.regression
def test_protected_page_redirects_to_login_and_back(page: Page, settings: Settings) -> None:
    page.goto("/products?category=Books")

    login = LoginPage(page).expect_loaded()
    login.login(*settings.credentials.require("user"))

    expect(page).to_have_url(re.compile(r"/products\?category=Books$"))
