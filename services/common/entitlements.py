import logging
import os
from dataclasses import dataclass
from dataclasses import field
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
    config: dict = field(default_factory=dict)


class EntitlementGuard:
    def __init__(
        self,
        module_name: Optional[str] = None,
        public_paths: Optional[Iterable[str]] = None,
        module_id: Optional[str] = None,
        public_prefixes: Optional[Iterable[str]] = None,
    ):
        from services.common.platform_access import ALIASES
        raw_module = module_name or module_id or os.getenv("MODULE_ID", "")
        self.module_name = ALIASES.get(raw_module, raw_module)
        self.public_paths = {"/health", "/docs", "/openapi.json"}
        if public_paths:
            self.public_paths.update(public_paths)
        # Prefix matches for public subtrees with dynamic segments
        # (exact public_paths can't cover e.g. /api/chat/{identifier}).
        self.public_prefixes = tuple(public_prefixes or ())
        self.enforce_modules = _bool_env("AUTH_ENFORCE_MODULES", True)
        self.license = LicenseVerifier()

    def ensure_startup(self) -> None:
        if self.module_name in {"overview", "admin"}: return
        self.license.ensure_valid()

    async def _check_tenant_module(self, tenant_id: str) -> EntitlementState:
        if self.module_name in {"overview", "admin"}: return EntitlementState(enabled=True)
        if not self.enforce_modules or not self.module_name:
            return EntitlementState(enabled=True)

        # Primary path: the real schema (config/master_schema.sql:47-56)
        # tenant_modules(tenant_id, module_id, status) joined to
        # modules(id, key). Tried first so a correctly-provisioned DB never
        # pays for an exception + retry per request.
        try:
            async with session_scope() as session:
                from services.common.platform_trials import expire
                await expire(session, tenant_id)
                result = await session.execute(
                    text(
                        """
                        select tm.status, tm.config, t.settings, t.billing_status
                        from tenant_modules tm
                        join modules m on m.id = tm.module_id
                        join tenants t on t.id=tm.tenant_id
                        where tm.tenant_id = :tenant_id
                          and m.key = :module_key
                        """
                    ),
                    {"tenant_id": tenant_id, "module_key": self.module_name},
                )
                row = result.fetchone()
                if not row:
                    logger.warning(
                        "entitlements: tenant %s has no row for module '%s' (join path)",
                        tenant_id, self.module_name,
                    )
                    return EntitlementState(enabled=False, reason="module_not_enabled")
                status_value = str(row[0]).upper()
                enabled = status_value in {"ENABLED", "TRIAL"}
                if not enabled:
                    logger.warning(
                        "entitlements: tenant %s module '%s' status=%s",
                        tenant_id, self.module_name, row[0],
                    )
                from services.common.platform_access import payment_access
                if enabled and not payment_access(row[2], row[3]):
                    return EntitlementState(enabled=False, reason="payment_required")
                return EntitlementState(enabled=enabled, config=row[1] or {})
        except SQLAlchemyError:
            logger.info(
                "entitlements: join-path query failed for tenant %s module '%s'; "
                "falling back to legacy direct-column query",
                tenant_id, self.module_name,
            )

        # Legacy fallback: tenant_modules carrying its own module_name/enabled
        # columns (older/alternate schema variant).
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
                    logger.warning(
                        "entitlements: tenant %s has no row for module '%s' (legacy path)",
                        tenant_id, self.module_name,
                    )
                    return EntitlementState(enabled=False, reason="module_not_enabled")
                if "enabled" in row:
                    return EntitlementState(enabled=bool(row["enabled"]))
                if "status" in row and row["status"]:
                    return EntitlementState(enabled=str(row["status"]).upper() in {"ENABLED", "TRIAL"})
        except SQLAlchemyError:
            logger.exception(
                "entitlements: both schema paths failed for tenant %s module '%s'",
                tenant_id, self.module_name,
            )
        return EntitlementState(enabled=False, reason="module_not_enabled")

    def is_licensed(self) -> bool:
        if self.module_name in {"overview", "admin"}: return True
        return self.license.is_module_enabled(self.module_name)

    def dependency(self) -> None:
        if not self.is_licensed():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Module not licensed")

    async def middleware(self, request: Request, call_next) -> Response:
        path = request.url.path
        if (
            path in self.public_paths
            or request.method.upper() == "OPTIONS"
            or any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.public_prefixes)
        ):
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

        if self.module_name not in {"overview", "admin"}:
            from services.common.platform_trials import expire, seat_allowed
            async with session_scope() as session:
                await expire(session, ctx.tenant_id)
                if not await seat_allowed(session, ctx.tenant_id, ctx.user_id):
                    return Response("Your owner must select your Free seat or add paid seats in Admin", status_code=403)

        state = await self._check_tenant_module(str(ctx.tenant_id))
        if not state.enabled:
            return Response("Payment required; open Admin to resolve billing" if state.reason == "payment_required" else "Module not enabled for tenant", status_code=402 if state.reason == "payment_required" else 403)

        from services.common.platform_access import blocked_feature, reserve_write, release_write
        tier = state.config.get("pricing_tier")
        if tier:
            feature = blocked_feature(self.module_name, tier, path)
            if feature:
                return Response(f"{feature['name']} requires {feature['tier']} for this panel", status_code=403)
        period = None
        limit = state.config.get("writes_per_month")
        if limit is not None and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            async with session_scope() as session:
                period = await reserve_write(session, ctx.tenant_id, self.module_name, limit)
            if period is None:
                return Response("Monthly panel write limit reached; open Admin to review your tier", status_code=429)
        try:
            response = await call_next(request)
        except BaseException:
            if period:
                async with session_scope() as session:
                    await release_write(session, ctx.tenant_id, self.module_name, period)
            raise
        if period and response.status_code >= 400:
            async with session_scope() as session:
                await release_write(session, ctx.tenant_id, self.module_name, period)
        return response
