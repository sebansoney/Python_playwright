"""Execution policy: infrastructure-only reruns (pytest-rerunfailures).

* Rerun count, delay and the "rerun only these errors" patterns come from
  ``config.yaml -> retry`` (per environment); explicit CLI flags still win.
* ``AssertionError`` (incl. Playwright ``expect`` failures) is ALWAYS excluded - a
  product defect can never be retried away. pytest-rerunfailures checks the exclusion
  against the raised exception itself, so an assertion that happened while handling a
  connection error is not rerun either.
* Reruns stay visible: "R" in the terminal, "rerun" in the summary, Allure retries tab.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from config.settings import Settings
from framework.fixtures.core import bootstrap

NEVER_RERUN: tuple[str, ...] = ("^AssertionError: ",)


@dataclass
class RerunPolicy:
    reruns: int
    delay_s: float
    only_rerun: list[str] = field(default_factory=list)
    rerun_except: list[str] = field(default_factory=list)


def rerun_policy(settings: Settings, cli_args: list[str]) -> RerunPolicy | None:
    """Return the policy to apply, or None when the user set reruns explicitly on the CLI
    (then only the never-rerun safety rule is added, see ``pytest_configure``)."""
    if any(a == "--reruns" or a.startswith("--reruns=") for a in cli_args):
        return None
    retry = settings.retry
    if retry.max_reruns == 0:
        return RerunPolicy(reruns=0, delay_s=0)
    if not retry.only_rerun:
        # Refuse "rerun everything": without patterns every failure would be retried.
        return RerunPolicy(reruns=0, delay_s=0)
    return RerunPolicy(
        reruns=retry.max_reruns,
        delay_s=retry.delay_s,
        only_rerun=list(retry.only_rerun),
        rerun_except=list(NEVER_RERUN),
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    if not hasattr(config.option, "reruns"):
        return  # pytest-rerunfailures not installed / disabled
    settings = bootstrap(config)
    policy = rerun_policy(settings, list(config.invocation_params.args))
    if policy is None:  # user chose --reruns on the CLI: still never rerun assertions
        config.option.rerun_except = [*(config.option.rerun_except or []), *NEVER_RERUN]
        return
    config.option.reruns = policy.reruns
    config.option.reruns_delay = policy.delay_s
    if policy.reruns:
        config.option.only_rerun = [*(config.option.only_rerun or []), *policy.only_rerun]
        config.option.rerun_except = [*(config.option.rerun_except or []), *policy.rerun_except]


def pytest_report_header(config: pytest.Config) -> str | None:
    reruns = getattr(config.option, "reruns", None)
    if not reruns:
        return "reruns: off"
    patterns = ", ".join(config.option.only_rerun or ["<all>"])
    return f"reruns: up to {reruns}x, only for: {patterns}; never for AssertionError"
