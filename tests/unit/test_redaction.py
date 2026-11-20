"""Self-tests for secret redaction - the guard used by logs, reports and AI calls."""

import logging

import pytest

from framework.core.logging_config import get_logger
from framework.core.redaction import Redactor, get_redactor

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJlLXZhbHVl"
MASK = "***REDACTED***"


@pytest.fixture
def redactor() -> Redactor:
    return Redactor()


def test_sensitive_keys_are_masked_at_any_depth(redactor: Redactor) -> None:
    payload = {
        "email": "a@b.test",
        "password": "hunter2",
        "profile": {"access_token": "abc123", "name": "Ann"},
        "items": [{"api_key": "k-1"}, {"id": 7}],
    }
    out = redactor.redact(payload)
    assert out["password"] == MASK
    assert out["profile"] == {"access_token": MASK, "name": "Ann"}
    assert out["items"] == [{"api_key": MASK}, {"id": 7}]
    assert out["email"] == "a@b.test"
    assert payload["password"] == "hunter2", "input must not be mutated"


def test_headers_are_masked_case_insensitively(redactor: Redactor) -> None:
    headers = {"Authorization": f"Bearer {JWT}", "Set-Cookie": "sid=1", "Accept": "json"}
    assert redactor.redact(headers) == {
        "Authorization": MASK,
        "Set-Cookie": MASK,
        "Accept": "json",
    }


@pytest.mark.parametrize(
    ("text", "leaked"),
    [
        (f"token is {JWT}", JWT),
        ("Authorization: Bearer abcdefghijkl123", "abcdefghijkl123"),
        ('{"password": "hunter2", "user": "ann"}', "hunter2"),
        ("login?user=ann&password=hunter2&x=1", "hunter2"),
        ("key sk-ant-api03-AAAAAAAAAAAAAAAAAAAA used", "sk-ant-api03-AAAAAAAAAAAAAAAAAAAA"),
    ],
)
def test_secrets_inside_free_text_are_masked(redactor: Redactor, text: str, leaked: str) -> None:
    out = redactor.redact_text(text)
    assert leaked not in out
    assert MASK in out


@pytest.mark.parametrize(
    "text",
    [
        "GET /api/v1/products?category=books&page=2 -> 200 in 35 ms",
        "api_session::0",  # pytest fixture finalizer name (was over-masked)
        "fixture token_provider set up",
        "token_type == 'bearer'",
    ],
)
def test_non_secret_text_is_unchanged(redactor: Redactor, text: str) -> None:
    assert redactor.redact_text(text) == text


def test_registered_secret_values_are_masked_anywhere(redactor: Redactor) -> None:
    redactor.register_secret("Pa55-word!")
    assert redactor.redact_text("typed Pa55-word! into the field") == f"typed {MASK} into the field"


def test_email_masking_is_opt_in(redactor: Redactor) -> None:
    assert redactor.redact_text("user ann@example.test") == "user ann@example.test"
    assert redactor.redact_text("user ann@example.test", mask_emails=True) == "user <email>"


def test_log_records_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    get_redactor().register_secret("LogSecret-42")
    with caplog.at_level(logging.INFO, logger="framework"):
        get_logger("selftest").info("login with %s and %s", "LogSecret-42", f"Bearer {JWT}")
    assert "LogSecret-42" not in caplog.text
    assert JWT not in caplog.text
    assert MASK in caplog.text
