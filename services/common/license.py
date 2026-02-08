from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger("license")


def _load_public_key(raw: str) -> Ed25519PublicKey:
    if raw.startswith("-----BEGIN"):
        return serialization.load_pem_public_key(raw.encode("utf-8"))
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw))


def _canonical_payload(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _parse_datetime(value: Optional[Any]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass
class LicenseInfo:
    payloads: list[Dict[str, Any]] = field(default_factory=list)
    valid: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def modules(self) -> list[str]:
        modules: set[str] = set()
        for payload in self.payloads:
            raw = payload.get("modules", [])
            if isinstance(raw, list):
                modules.update(str(item).strip() for item in raw if str(item).strip())
        return sorted(modules)

    @property
    def expires_at(self) -> Optional[datetime]:
        dates = [_parse_datetime(payload.get("expires_at") or payload.get("expiry") or payload.get("exp")) for payload in self.payloads]
        dates = [dt for dt in dates if dt]
        return max(dates) if dates else None


class LicenseVerifier:
    def __init__(self, licenses_dir: Optional[Path] = None) -> None:
        self.licenses_dir = licenses_dir or self._default_license_dir()
        self.public_key = os.getenv("LICENSE_PUBLIC_KEY")
        self.enforcement = os.getenv("LICENSE_ENFORCEMENT", "warn").lower()
        self._state: Optional[LicenseInfo] = None

    def _default_license_dir(self) -> Path:
        root = Path(__file__).resolve().parents[2]
        return root / "licenses"

    def _load_license_blobs(self) -> list[Dict[str, Any]]:
        blobs: list[Dict[str, Any]] = []
        explicit_path = os.getenv("LICENSE_PATH")
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                blobs.append(json.loads(path.read_text(encoding="utf-8")))
            return blobs

        if not self.licenses_dir.exists():
            return blobs
        for path in sorted(self.licenses_dir.glob("*.json")):
            try:
                blobs.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("Failed to read license file %s: %s", path, exc)
        return blobs

    def verify(self) -> LicenseInfo:
        if self._state is not None:
            return self._state

        state = LicenseInfo()
        blobs = self._load_license_blobs()
        if not blobs:
            state.errors.append("license_missing")
            self._state = state
            return state

        if not self.public_key:
            state.errors.append("public_key_missing")
            self._state = state
            return state

        try:
            public_key = _load_public_key(self.public_key)
        except Exception as exc:
            state.errors.append(f"public_key_invalid:{exc}")
            self._state = state
            return state

        for blob in blobs:
            payload = blob.get("payload", blob)
            signature = blob.get("signature") or os.getenv("LICENSE_SIGNATURE")
            if not signature:
                state.errors.append("signature_missing")
                continue
            expires_at = _parse_datetime(payload.get("expires_at") or payload.get("expiry") or payload.get("exp"))
            if expires_at and expires_at < datetime.now(tz=timezone.utc):
                state.errors.append("license_expired")
                continue
            try:
                public_key.verify(base64.b64decode(signature), _canonical_payload(payload))
                state.payloads.append(payload)
            except Exception as exc:
                state.errors.append(f"verify_failed:{exc}")

        state.valid = bool(state.payloads)
        self._state = state
        return state

    def ensure_valid(self) -> None:
        state = self.verify()
        if state.valid:
            return
        if self.enforcement == "warn":
            logger.warning("License invalid: %s", ",".join(state.errors) or "unknown")
            return
        raise RuntimeError("License invalid: " + ",".join(state.errors))

    def is_module_enabled(self, module_name: str) -> bool:
        state = self.verify()
        if not state.valid:
            return self.enforcement == "warn"
        if not module_name:
            return True
        return module_name in state.modules
