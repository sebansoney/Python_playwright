"""Self-tests for the infrastructure-only rerun policy."""

import os
import re

import httpx
import pytest

from config.settings import load_settings
from framework.fixtures.execution import NEVER_RERUN, rerun_policy


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FW_RETRY") or key == "TEST_ENV":
            monkeypatch.delenv(key, raising=False)


def _matches(patterns: list[str], exc: BaseException) -> bool:
    # Exactly the string pytest-rerunfailures builds for each exception.
    text = f"{type(exc).__name__}: {exc}"
    return any(re.search(p, text) for p in patterns)


def test_ci_reruns_infrastructure_errors_only() -> None:
    policy = rerun_policy(load_settings("ci", env_file=None), [])

    assert policy is not None
    assert (policy.reruns, policy.delay_s) == (2, 2)
    assert policy.rerun_except == list(NEVER_RERUN)
    assert _matches(policy.only_rerun, httpx.ConnectError("[Errno 111] Connection refused"))
    assert _matches(policy.only_rerun, httpx.ConnectTimeout("timed out"))


def test_patterns_do_not_match_product_or_test_defects() -> None:
    policy = rerun_policy(load_settings("ci", env_file=None), [])
    assert policy is not None

    for exc in (
        AssertionError("Expected HTTP 200, got 500"),
        AssertionError("Locator expected to have text '11.00'"),
        KeyError("price"),
        httpx.ReadTimeout("read timed out"),  # a slow app is a finding, not noise
    ):
        assert not _matches(policy.only_rerun, exc), exc
    assert _matches(policy.rerun_except, AssertionError("anything"))


def test_regression_module_qualified_patterns_never_matched() -> None:
    """Phase 2 config used 'httpx.ConnectError', which can never match the bare
    class name pytest-rerunfailures compares against."""
    assert not _matches(["httpx.ConnectError"], httpx.ConnectError("refused"))


def test_local_environment_has_no_reruns() -> None:
    policy = rerun_policy(load_settings("local", env_file=None), [])
    assert policy is not None
    assert policy.reruns == 0


def test_cli_reruns_flag_wins() -> None:
    assert rerun_policy(load_settings("ci", env_file=None), ["--reruns", "5"]) is None
    assert rerun_policy(load_settings("ci", env_file=None), ["--reruns=5"]) is None


def test_empty_pattern_list_never_means_rerun_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FW_RETRY__ONLY_RERUN", "[]")
    policy = rerun_policy(load_settings("ci", env_file=None), [])
    assert policy is not None
    assert policy.reruns == 0
