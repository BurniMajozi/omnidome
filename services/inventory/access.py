"""Inventory authorization from authoritative RBAC, with conservative write defaults."""
from fastapi import Depends, HTTPException
from services.common.auth import AuthContext, get_auth_context
from services.common import rbac

ADMIN_ROLES = {"owner", "org_admin", "admin", "tenant_admin", "inventory_admin", "platform_admin"}
WRITE_ROLES = ADMIN_ROLES | {"inventory", "stock_controller", "storekeeper", "inventory_manager"}

async def require_access(auth: AuthContext, tier: str) -> AuthContext:
    if not auth.rbac_loaded:
        try:
            from services.common.db import session_scope
            async with session_scope(auth.tenant_id) as db:
                await rbac._load_rbac(auth, db)
        except Exception:
            if rbac._enforce_rbac():
                raise HTTPException(403, "Inventory access could not be verified")
    roles = {str(r).lower() for r in auth.roles}
    permissions = {str(p).lower() for p in auth.permissions}
    allowed_roles = ADMIN_ROLES if tier == "manager" else WRITE_ROLES
    allowed_permissions = {"inventory.admin"} if tier == "manager" else {"inventory.admin", "inventory.write", "inventory.manage"}
    if not (auth.is_platform_admin or roles & allowed_roles or permissions & allowed_permissions):
        raise HTTPException(403, f"Requires inventory {tier} access")
    return auth

def require_tier(tier: str):
    if tier not in {"manager", "write"}:
        raise ValueError("Unknown inventory access tier")
    async def dependency(auth: AuthContext = Depends(get_auth_context)):
        return await require_access(auth, tier)
    return dependency
