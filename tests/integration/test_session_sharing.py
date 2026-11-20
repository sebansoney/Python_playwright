"""One login, two channels: API token <-> browser session."""

import re
from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from framework.api.clients import ApiSession
from framework.api.models import Token
from framework.assertions import expect_api
from framework.browser.session import token_from_context
from framework.data.factories import UserData
from framework.pages import DashboardPage, LoginPage, ProfilePage

UserFactory = Callable[..., tuple[UserData, dict[str, Any]]]
SessionFactory = Callable[..., ApiSession]


@pytest.mark.smoke
def test_api_login_session_is_reused_in_browser(
    anon_api: ApiSession, page_for_token: Callable[[str], Page], user_factory: UserFactory
) -> None:
    user, _ = user_factory()

    # Log in through the API only ...
    token = expect_api(anon_api.auth.login(user.email, user.password)).has_status(200).parse(Token)

    # ... and open the app in the browser with that session - no login screen.
    page = page_for_token(token.access_token)
    dashboard = DashboardPage(page).open()
    expect(page).to_have_url(re.compile(r"/dashboard$"))  # not redirected to /login
    expect(dashboard.welcome).to_have_text(f"Welcome, {user.full_name}!")
    dashboard.nav.expect_logged_in_as(user.full_name)


@pytest.mark.regression
def test_browser_login_session_is_reused_for_api(
    page: Page, api_session: SessionFactory, user_factory: UserFactory
) -> None:
    user, created = user_factory()
    LoginPage(page).open().login_as(user.email, user.password)

    token = token_from_context(page.context)
    assert token, "browser has no auth cookie after login"

    me = api_session(token=token).auth.me()
    expect_api(me).has_status(200).json_contains({"id": created["id"], "email": user.email})


@pytest.mark.regression
def test_ui_logout_ends_browser_session_but_issued_token_stays_valid(
    page: Page, api_session: SessionFactory, user_factory: UserFactory
) -> None:
    """Characterises current behaviour (see DEVELOPMENT_STATUS N10): logout only deletes
    the browser cookie; JWTs are stateless and stay valid until they expire."""
    user, _ = user_factory()
    dashboard = LoginPage(page).open().login_as(user.email, user.password)
    token = token_from_context(page.context)
    assert token

    dashboard.nav.logout()

    LoginPage(page).expect_loaded()
    assert token_from_context(page.context) is None
    expect_api(api_session(token=token).auth.me()).has_status(200)


@pytest.mark.regression
def test_profile_change_in_ui_is_visible_via_api(
    page_for: Callable[[str, str], Page], api_session: SessionFactory, user_factory: UserFactory
) -> None:
    user, _ = user_factory()
    profile = ProfilePage(page_for(user.email, user.password)).open()

    profile.update_details("Integration Tester", "+1 202 555 0199")
    profile.flash.expect_text("Profile updated successfully.")

    me = api_session(email=user.email, password=user.password).profile.get()
    expect_api(me).has_status(200).json_contains(
        {"email": user.email, "full_name": "Integration Tester", "phone": "+1 202 555 0199"}
    )
