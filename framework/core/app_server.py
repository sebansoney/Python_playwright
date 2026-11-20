"""Start / reuse / stop the sample application for a test run.

Rules (safe for pytest-xdist):
  * If the app already answers its health URL -> reuse it, never stop it.
  * Otherwise, if autostart is enabled, the FIRST worker that needs it starts it,
    guarded by a cross-process file lock; the others wait and reuse it.
  * Only the process that owns the run (the xdist controller, or the single pytest
    process) stops it at the very end, and only if it was started by this run.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from filelock import FileLock

from framework.core.exceptions import AppNotReachableError
from framework.core.logging_config import get_logger
from framework.core.paths import LOGS_DIR, PROJECT_ROOT, REPORTS_DIR
from framework.utilities.waits import wait_until

log = get_logger(__name__)

RUN_ID_ENV = "AUTOMATION_RUN_ID"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _kill_tree(pid: int) -> None:
    """Kill a process AND its children.

    Needed because on Windows `.venv\\Scripts\\python.exe` is a launcher that runs
    the real interpreter as a child: killing only the launcher leaves the server up.
    On POSIX the server is started in its own session, so we kill the whole group.
    """
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass  # already gone


@dataclass
class AppServer:
    base_url: str
    health_url: str
    startup_timeout_s: float
    state_file: Path = REPORTS_DIR / ".app_server.json"
    lock_file: Path = REPORTS_DIR / ".app_server.lock"
    log_file: Path = LOGS_DIR / "app_server.log"

    # ------------------------------------------------------------- queries
    def is_healthy(self) -> bool:
        try:
            return httpx.get(self.health_url, timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    # ------------------------------------------------------------ lifecycle
    def ensure_running(self, autostart: bool) -> None:
        if self.is_healthy():
            return
        if not autostart:
            raise AppNotReachableError(
                f"Application not reachable at {self.health_url} and autostart is disabled. "
                f"Start it with: uv run python -m sample_application --env test"
            )
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_file), timeout=self.startup_timeout_s + 30):
            if self.is_healthy():  # another worker started it while we waited
                return
            self._start()

    def _start(self) -> None:
        url = urlparse(self.base_url)
        if url.hostname not in _LOCAL_HOSTS:
            raise AppNotReachableError(
                f"Refusing to autostart for non-local base_url {self.base_url}; "
                f"start that environment yourself or set app.autostart=false."
            )
        port = url.port or 80
        cmd = [
            sys.executable, "-m", "sample_application",
            "--env", "test", "--reset-db", "--host", url.hostname, "--port", str(port),
        ]  # fmt: skip
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        log.info("Starting sample application: %s", " ".join(cmd))
        log_handle = self.log_file.open("w", encoding="utf-8")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env={**os.environ, "APP_ENV": "test"},
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        self.state_file.write_text(
            json.dumps({"pid": proc.pid, "run_id": os.environ.get(RUN_ID_ENV)}), encoding="utf-8"
        )

        def ready() -> bool:
            if proc.poll() is not None:
                raise AppNotReachableError(
                    f"Sample application exited with code {proc.returncode}.\n{self._log_tail()}"
                )
            return self.is_healthy()

        try:
            wait_until(ready, self.startup_timeout_s, message=f"{self.health_url} healthy")
        except TimeoutError as exc:
            _kill_tree(proc.pid)
            raise AppNotReachableError(f"{exc}\n{self._log_tail()}") from exc
        log.info("Sample application is up (pid %s) at %s", proc.pid, self.base_url)

    def stop_if_started_by(self, run_id: str | None) -> bool:
        """Stop the server only if THIS run started it. Returns True if stopped."""
        if not run_id or not self.state_file.exists():
            return False
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if state.get("run_id") != run_id:
            return False
        _kill_tree(int(state["pid"]))
        log.info("Stopped sample application (pid %s)", state["pid"])
        self.state_file.unlink(missing_ok=True)
        try:
            wait_until(lambda: not self.is_healthy(), 10, message="sample application stopped")
        except TimeoutError:
            log.warning("Sample application still answering after stop: %s", self.health_url)
        return True

    def _log_tail(self, lines: int = 20) -> str:
        try:
            content = self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "--- app_server.log (tail) ---\n" + "\n".join(content[-lines:])
