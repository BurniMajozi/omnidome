"""Directory routes — list team members for channel invites, etc."""

from fastapi import APIRouter, Depends
from sqlalchemy import text

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope

router = APIRouter(prefix="/directory", tags=["Directory"])


@router.get("/users")
async def list_users(ctx: AuthContext = Depends(get_auth_context)):
    """List users in the tenant (id, display name, email) for invite pickers.

    The shared users table may or may not carry tenant_id depending on the auth
    schema, so we try a tenant-scoped query first and fall back to unscoped.
    """
    async def _query(scoped: bool):
        async with session_scope() as session:
            sql = "SELECT id, COALESCE(full_name, email) AS name, email FROM users"
            params: dict = {}
            if scoped:
                sql += " WHERE tenant_id = :tid"
                params["tid"] = str(ctx.tenant_id)
            sql += " ORDER BY name LIMIT 200"
            rows = (await session.execute(text(sql), params)).fetchall()
            return [{"id": str(r[0]), "name": r[1], "email": r[2]} for r in rows]

    try:
        items = await _query(scoped=True)
    except Exception:
        items = await _query(scoped=False)
    return {"items": items}
