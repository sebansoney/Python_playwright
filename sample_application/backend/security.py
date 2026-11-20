"""Password hashing (bcrypt) and JWT tokens (HS256)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from sample_application.backend.config import config

_ALGORITHM = "HS256"
_BCRYPT_ROUNDS = 10  # demo app: fast enough for many test logins, still a real hash


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > 72:  # bcrypt limit; such a password can never match
        return False
    return bcrypt.checkpw(raw, password_hash.encode())


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    ttl_s = config.token_ttl_minutes * 60
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(seconds=ttl_s)}
    return jwt.encode(payload, config.jwt_secret, algorithm=_ALGORITHM), ttl_s


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, config.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
