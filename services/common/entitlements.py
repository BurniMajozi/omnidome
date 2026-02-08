import logging
import os
from dataclasses import dataclass
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request
from starlette.responses import Response

from services.common.auth import get_auth_context
from services.common.db import session_scope
from services.common.license import LicenseVerifier

logger = logging.getLogger("entitlements")


def _bool_env(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EntitlementState:
    enabled: bool
    reason: Optional[str] = None


class EntitlementGuard:
    def __init__(
        self,
        module_name: Optional[str] = None,
        public_paths: Optional[Iterable[str]] = None,
        module_id: Optional[str] = None,
    ):
        self.module_name = module_name or module_id or os.getenv("MODULE_ID", "")
        self.public_paths = {"/health", "/docs", "/openapi.json"}
        if public_paths:
            self.public_paths.update(public_paths)
        self.enforce_modules = _bool_env("AUTH_ENFORCE_MODULES", True)
        self.license = LicenseVerifier()

    def ensure_startup(self) -> None:
        self.license.ensure_valid()

    async def _check_tenant_module(self, tenant_id: str) -> EntitlementState:
        if not self.enforce_modules or not self.module_name:
            return EntitlementState(enabled=True)

        try:
            async with session_scope() as session:
                result = await session.execute(
                    text(
                        """
                        select enabled, status
                        from tenant_modules
                        where tenant_id = :tenant_id
                          and module_name = :module_name
                        """
                    ),
                    {"tenant_id": tenant_id, "module_name": self.module_name},
                )
                row = result.mappings().one_or_none()
                if row is None:
                    return EntitlementState(enabled=False, reason="module_not_enabled")
                if "enabled" in row:
                    return EntitlementState(enabled=bool(row["enabled"]))
                if "status" in row and row["status"]:
                    return EntitlementState(enabled=str(row["status"]).upper() in {"ENABLED", "TRIAL"})
        except SQLAlchemyError:
            logger.info("module_name column not found; falling back to module join")

        async with session_scope() as session:
            result = await session.execute(
                text(
                    """
                    select tm.status
                    from tenant_modules tm
                    join modules m on m.id = tm.module_id
                    where tm.tenant_id = :tenant_id
                      and m.key = :module_key
                    """
                ),
                {"tenant_id": tenant_id, "module_key": self.module_name},
            )
            row = result.fetchone()
            if not row:
                return EntitlementState(enabled=False, reason="module_not_enabled")
            status_value = str(row[0]).upper()
            return EntitlementState(enabled=status_value in {"ENABLED", "TRIAL"})

    def is_licensed(self) -> bool:
        return self.license.is_module_enabled(self.module_name)

    def dependency(self) -> None:
        if not self.is_licensed():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module not licensed")

    async def middleware(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in self.public_paths or request.method.upper() == "OPTIONS":
            return await call_next(request)

        if not self.is_licensed():
            return Response("Module not licensed", status_code=status.HTTP_403_FORBIDDEN)

        if not self.module_name or not self.enforce_modules:
            return await call_next(request)

        try:
            ctx = await get_auth_context(request)
        except HTTPException as exc:
            return Response(str(exc.detail), status_code=exc.status_code)

        if ctx.is_platform_admin:
            return await call_next(request)

        state = await self._check_tenant_module(str(ctx.tenant_id))
        if not state.enabled:
            return Response("Module not enabled for tenant", status_code=status.HTTP_403_FORBIDDEN)

        return await call_next(request)
