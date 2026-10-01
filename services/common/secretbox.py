"""Shared Fernet helpers for secrets stored in the database.

Key: env SECRETS_ENCRYPTION_KEY (one Fernet key, or a comma-separated list: the first encrypts,
all decrypt) plus optional SECRETS_ENCRYPTION_KEY_PREVIOUS for rotation. Same semantics as
services/common/agentmail.py. FAILS CLOSED: with no/invalid key nothing is stored or read.

Also provides salted password hashing (PBKDF2-SHA256) for credentials whose cleartext is never needed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets


class SecretsUnavailable(RuntimeError):
    """SECRETS_ENCRYPTION_KEY missing/invalid: refuse to store or read secrets."""


def is_configured() -> bool:
    try:
        _fernet()
        return True
    except SecretsUnavailable:
        return False


def _fernet():
    raw = os.getenv("SECRETS_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise SecretsUnavailable("SECRETS_ENCRYPTION_KEY is not set; refusing to store/read secrets")
    try:
        from cryptography.fernet import Fernet, MultiFernet
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        prev = os.getenv("SECRETS_ENCRYPTION_KEY_PREVIOUS", "").strip()
        if prev and prev not in keys:
            keys.append(prev)
        fernets = [Fernet(k.encode()) for k in keys]
        return MultiFernet(fernets) if len(fernets) > 1 else fernets[0]
    except Exception as exc:  # noqa: BLE001
        raise SecretsUnavailable("SECRETS_ENCRYPTION_KEY is invalid (needs a Fernet key)") from exc


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except SecretsUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SecretsUnavailable("stored secret cannot be decrypted with the configured key") from exc


HASH_PREFIX = "pbkdf2$"
_ITER = 210_000


def hash_password(password: str, *, iterations: int = _ITER) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{HASH_PREFIX}{iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def is_hashed(value: str) -> bool:
    return bool(value) and value.startswith(HASH_PREFIX)


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:  # noqa: BLE001
        return False


def mask(value) -> str | None:
    return "••••" if value else None
