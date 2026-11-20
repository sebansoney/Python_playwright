"""Per-test cleanup registry.

Register an undo action the moment you create data (before asserting), so it is
removed even when the test fails half-way. Actions run in reverse order (LIFO).
A failing cleanup is logged and reported once at the end; it never hides the
test's own failure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from framework.core.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class _Action:
    description: str
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass
class CleanupRegistry:
    _actions: list[_Action] = field(default_factory=list)

    def add(self, description: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self._actions.append(_Action(description, func, args, kwargs))

    def run(self) -> list[str]:
        """Run all actions LIFO; return descriptions of the ones that failed."""
        failures: list[str] = []
        while self._actions:
            action = self._actions.pop()
            try:
                action.func(*action.args, **action.kwargs)
                log.debug("Cleanup ok: %s", action.description)
            except Exception as exc:
                log.warning("Cleanup failed: %s -> %r", action.description, exc)
                failures.append(f"{action.description}: {exc!r}")
        return failures
