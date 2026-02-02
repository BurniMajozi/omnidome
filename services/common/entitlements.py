import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException, status
from starlette.requests import Request
from starlette.responses import Response


def _load_public_key(raw: str) -> Ed25519PublicKey:
    if raw.startswith("-----BEGIN"):
        key_bytes = raw.encode("utf-8")
        return serialization.load_pem_public_key(key_bytes)
    key_bytes = base64.b64decode(raw)
    return Ed25519PublicKey.from_public_bytes(key_bytes)


def _canonical_payload(payload: Dict[str, Any]) -> bytes:
    # Canonical JSON for signature verification
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _load_license_blob(path: Optional[str]) -> Dict[str, Any]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    raw = os.getenv("LICENSE_JSON")
    if not raw:
        return {}
    return json.loads(raw)


@dataclass
class LicenseState:
    payload: Dict[str, Any]
    valid: bool
    error: Optional[str] = None

    @property
    def modules(self) -> Iterable[str]:
        return self.payload.get("modules", []) if self.payload else []


class EntitlementGuard:
    def __init__(self, module_id: Optional[str] = None):
        self.module_id = module_id or os.getenv("MODULE_ID", "")
        self.enforcement = os.getenv("LICENSE_ENFORCEMENT", "strict").lower()
        self.license_path = os.getenv("LICENSE_PATH")
        self.public_key = os.getenv("LICENSE_PUBLIC_KEY")
        self._state: Optional[LicenseState] = None

    def _verify(self) -> LicenseState:
        blob = _load_license_blob(self.license_path)
        if not blob:
            return LicenseState(payload={}, valid=False, error="license_missing")

        payload = blob.get("payload", blob)
        signature = blob.get("signature") or os.getenv("LICENSE_SIGNATURE")
        if not signature:
            return LicenseState(payload=payload, valid=False, error="signature_missing")

        if not self.public_key:
            return LicenseState(payload=payload, valid=False, error="public_key_missing")

        try:
            pub = _load_public_key(self.public_key)
            pub.verify(base64.b64decode(signature), _canonical_payload(payload))
            return LicenseState(payload=payload, valid=True)
        except Exception as exc:
            return LicenseState(payload=payload, valid=False, error=f"verify_failed:{exc}")

    def _ensure_state(self) -> LicenseState:
        if self._state is None:
            self._state = self._verify()
        return self._state

    def state(self) -> LicenseState:
        return self._ensure_state()

    def ensure_startup(self) -> None:
        state = self._ensure_state()
        if state.valid:
            return
        if self.enforcement == "warn":
            return
        raise RuntimeError(f"License verification failed: {state.error}")

    def is_entitled(self) -> bool:
        state = self._ensure_state()
        if not state.valid and self.enforcement != "warn":
            return False
        if not self.module_id:
            return True
        return self.module_id in state.modules

    def dependency(self) -> None:
        if not self.is_entitled():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Module not licensed",
            )

    async def middleware(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in {"/health", "/docs", "/openapi.json"}:
            return await call_next(request)
        if not self.is_entitled():
            return Response("Module not licensed", status_code=status.HTTP_403_FORBIDDEN)
        return await call_next(request)
