"""Logging set-up.

* One log file per run and per xdist worker: logs/run_<worker>.log
* Every log record is redacted at creation time (LogRecord factory), so secrets are
  masked in the file, in pytest's captured output AND in Allure's log attachment -
  no matter which handler emits it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from framework.core.redaction import get_redactor

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(worker)s] %(name)s | %(message)s"
_FRAMEWORK_LOGGER = "framework"
_configured = False


def _worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


def _install_redacting_record_factory() -> None:
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_redacting", False):
        return

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        record.worker = _worker_id()
        try:
            message = record.getMessage()
        except Exception:  # malformed %-args: leave the record untouched
            return record
        record.msg = get_redactor().redact_text(message)
        record.args = None
        return record

    factory._redacting = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def configure_logging(logs_dir: Path, level: str = "INFO") -> Path:
    """Configure framework logging once per process. Returns the log file path."""
    global _configured
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"run_{_worker_id()}.log"
    if _configured:
        return log_file

    _install_redacting_record_factory()

    handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    fw_logger = logging.getLogger(_FRAMEWORK_LOGGER)
    fw_logger.setLevel(level)
    fw_logger.addHandler(handler)
    # Keep propagating so pytest's per-test capture (and Allure) still see records.
    fw_logger.propagate = True

    # Third-party HTTP libs log full URLs/headers at DEBUG - keep them quieter.
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "faker"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the 'framework' namespace, e.g. get_logger(__name__)."""
    if name.startswith(_FRAMEWORK_LOGGER) or name == _FRAMEWORK_LOGGER:
        return logging.getLogger(name)
    return logging.getLogger(f"{_FRAMEWORK_LOGGER}.{name}")
