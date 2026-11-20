"""Well-known project paths. Use these instead of building paths from the CWD,
so code works no matter which folder pytest was started from."""

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

CONFIG_DIR: Path = PROJECT_ROOT / "config"
ENVIRONMENTS_DIR: Path = CONFIG_DIR / "environments"
TEST_DATA_DIR: Path = PROJECT_ROOT / "test_data"
REPORTS_DIR: Path = PROJECT_ROOT / "reports"
LOGS_DIR: Path = PROJECT_ROOT / "logs"
AI_DRAFTS_DIR: Path = PROJECT_ROOT / "ai_drafts"
SCHEMAS_DIR: Path = PROJECT_ROOT / "framework" / "api" / "schemas"
ENV_FILE: Path = PROJECT_ROOT / ".env"
LOCAL_BROWSERS_DIR: Path = PROJECT_ROOT / ".playwright-browsers"


def resolve_project_path(path: str | Path) -> Path:
    """Return ``path`` as absolute; relative paths are resolved from the project root."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p
