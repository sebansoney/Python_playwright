"""Thin, safe wrappers around Allure.

* Everything is redacted before it is written (titles, text, JSON).
* Steps never record function arguments (Allure's ``@allure.step`` decorator would
  store every argument - including passwords - as step parameters).
* All helpers are harmless no-ops when Allure is not active.
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import allure

from framework.core.redaction import get_redactor

P = ParamSpec("P")
R = TypeVar("R")

_FILE_TYPES: dict[str, tuple[Any, str]] = {
    ".png": (allure.attachment_type.PNG, "png"),
    ".jpg": (allure.attachment_type.JPG, "jpg"),
    ".jpeg": (allure.attachment_type.JPG, "jpg"),
    ".webm": (allure.attachment_type.WEBM, "webm"),
    ".txt": (allure.attachment_type.TEXT, "txt"),
    ".log": (allure.attachment_type.TEXT, "log"),
    ".json": (allure.attachment_type.JSON, "json"),
    ".csv": (allure.attachment_type.CSV, "csv"),
    ".zip": ("application/zip", "zip"),
}


@contextmanager
def step(title: str) -> Iterator[None]:
    """``with step("Create product"):`` - redacted title, no parameters recorded."""
    with allure.step(get_redactor().redact_text(title)):
        yield


def step_method(template: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for page-object / client methods.

    The title is ``template.format(**bound_arguments)``, e.g.
    ``@step_method("Search products for '{text}'")``. Only what the template names
    appears in the report (redacted); arguments are NOT stored as step parameters.
    """

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            try:
                title = template.format(**bound.arguments)
            except (KeyError, AttributeError, IndexError):
                title = template
            with step(title):
                return func(*args, **kwargs)

        return wrapper

    return decorate


def attach_text(name: str, text: str) -> None:
    allure.attach(
        get_redactor().redact_text(text), name=name, attachment_type=allure.attachment_type.TEXT
    )


def attach_json(name: str, data: Any) -> None:
    body = json.dumps(get_redactor().redact(data), indent=2, ensure_ascii=False, default=str)
    allure.attach(body, name=name, attachment_type=allure.attachment_type.JSON)


def attach_file(path: Path, name: str | None = None) -> None:
    """Attach a binary/text artifact (screenshot, trace, video ...) by its extension."""
    attachment_type, extension = _FILE_TYPES.get(
        path.suffix.lower(), ("application/octet-stream", path.suffix.lstrip("."))
    )
    allure.attach.file(
        str(path), name=name or path.name, attachment_type=attachment_type, extension=extension
    )
