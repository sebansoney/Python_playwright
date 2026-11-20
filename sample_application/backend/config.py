"""Sample application configuration (environment variables only).

The app is the *system under test*, so it deliberately does NOT import the test
framework's config. The only shared values are the seeded test accounts
(FW_CREDENTIALS__*), read from the same .env so framework and app always agree.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
FRONTEND_DIR = APP_ROOT / "frontend"
DATABASE_DIR = APP_ROOT / "database"

load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class AppConfig:
    env: str
    database_url: str
    jwt_secret: str
    token_ttl_minutes: int
    cookie_name: str
    admin_email: str
    admin_password: str
    user_email: str
    user_password: str

    @property
    def is_test(self) -> bool:
        """Test-support endpoints (DB reset) exist only when APP_ENV=test."""
        return self.env == "test"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is not set. Copy .env.example to .env "
            f"(project root) or export it before starting the sample application."
        )
    return value


def load_config() -> AppConfig:
    default_db = f"sqlite:///{(DATABASE_DIR / 'app.db').as_posix()}"
    return AppConfig(
        env=os.environ.get("APP_ENV", "dev"),
        database_url=os.environ.get("APP_DATABASE_URL", default_db),
        # Random per process unless set: tokens simply expire on restart.
        jwt_secret=os.environ.get("APP_JWT_SECRET") or secrets.token_urlsafe(32),
        token_ttl_minutes=int(os.environ.get("APP_TOKEN_TTL_MINUTES", "60")),
        cookie_name="access_token",
        admin_email=_required("FW_CREDENTIALS__ADMIN_USERNAME").lower(),
        admin_password=_required("FW_CREDENTIALS__ADMIN_PASSWORD"),
        user_email=_required("FW_CREDENTIALS__USER_USERNAME").lower(),
        user_password=_required("FW_CREDENTIALS__USER_PASSWORD"),
    )


config = load_config()
