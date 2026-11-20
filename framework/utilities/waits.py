"""Polling helper for NON-browser conditions (servers, files, background jobs).

For anything in the browser use Playwright's auto-waiting and ``expect`` instead.
``time.sleep`` is banned in this repo; this helper waits on an Event so the
interval is explicit and the overall timeout is always enforced.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


def wait_until[T](
    condition: Callable[[], T],
    timeout_s: float,
    interval_s: float = 0.25,
    message: str = "condition not met",
) -> T:
    """Call ``condition`` until it returns a truthy value or ``timeout_s`` passes."""
    deadline = time.monotonic() + timeout_s
    ticker = threading.Event()
    last_error: Exception | None = None
    while True:
        try:
            result = condition()
            if result:
                return result
        except Exception as exc:  # keep polling; report the last error on timeout
            last_error = exc
        if time.monotonic() >= deadline:
            detail = f" (last error: {last_error!r})" if last_error else ""
            raise TimeoutError(f"Timed out after {timeout_s}s: {message}{detail}")
        ticker.wait(interval_s)
