"""Server-side Supabase Auth Admin client + app_metadata sync.

The admin database is authoritative for tenant / membership / roles / seats. Supabase
`app_metadata` (tenant_id, roles, is_active) is a DERIVED CACHE written only from here,
using SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from the environment (never logged).

Every function that talks to Supabase goes through `get_client()`, which tests replace.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import text

from services.common.db import session_scope

logger = logging.getLogger("admin.sync")

NO_SUPABASE_USER = "no_supabase_user"


class SupabaseError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"supabase {status}: {detail}")
        self.status = status
        self.detail = detail


class SupabaseAdmin:
    def __init__(self, url: str, service_key: str):
        self.url = url.rstrip("/")
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    async def _req(self, method: str, path: str, **kw) -> Any:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.request(method, f"{self.url}/auth/v1{path}", headers=self._headers, **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("msg") or r.json().get("message") or r.text
            except Exception:
                msg = r.text
            raise SupabaseError(r.status_code, str(msg)[:200])
        return r.json() if r.content else {}

    async def get_user(self, user_id: str) -> Dict[str, Any]:
        return await self._req("GET", f"/admin/users/{user_id}")

    async def list_users(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        page = 1
        while True:
            data = await self._req("GET", "/admin/users", params={"page": page, "per_page": 200})
            users = data.get("users", [])
            out.extend(users)
            if len(users) < 200:
                return out
            page += 1

    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        for u in await self.list_users():
            if (u.get("email") or "").lower() == email.lower():
                return u
        return None

    async def set_app_metadata(self, user_id: str, meta: Dict[str, Any], banned: Optional[bool] = None) -> Dict[str, Any]:
        # GoTrue merges app_metadata keys shallowly; a null value removes the key.
        # A deactivated user is also BANNED so they cannot refresh or sign in again (there is no
        # admin "sign out user" endpoint); the admin-DB lookup blocks them immediately regardless.
        body: Dict[str, Any] = {"app_metadata": meta}
        if banned is not None:
            body["ban_duration"] = "876000h" if banned else "none"
        return await self._req("PUT", f"/admin/users/{user_id}", json=body)

    async def set_email(self, user_id: str, email: str) -> Dict[str, Any]:
        """Change a Supabase user's email (admin API; confirmed immediately: platform-admin initiated)."""
        return await self._req("PUT", f"/admin/users/{user_id}", json={"email": email, "email_confirm": True})

    async def revoke_sessions(self, user_id: str) -> bool:
        """GoTrue has NO admin endpoint to revoke a user's sessions (checked against the
        supabase/auth openapi: /admin/users/{id} supports GET/PUT/DELETE and /factors only;
        POST /logout?scope=global needs the USER's own JWT). The earlier DELETE
        /admin/users/{id}/sessions call did not exist, so this is always False and callers report
        sessions_revoked=false.

        What actually ends access: (1) the ban (ban_duration, set by set_app_metadata) blocks
        refresh-token grants and new sign-ins; (2) the web proxy resolves is_active from the admin DB
        on every request (5s cache) and answers 403 at once; (3) an already-issued access JWT stays
        valid until it expires (Supabase default 1h) only for a verifier that checks the JWT alone;
        all /svc and /api traffic passes through the proxy gate in (2)."""
        return False

    async def invite(self, email: str, redirect_to: str) -> Dict[str, Any]:
        return await self._req("POST", "/invite", params={"redirect_to": redirect_to}, json={"email": email})

    async def delete_user(self, user_id: str) -> None:
        await self._req("DELETE", f"/admin/users/{user_id}")

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Resolve a user access token to the Supabase user (id + email)."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.url}/auth/v1/user", headers={"apikey": self._headers["apikey"], "Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            raise SupabaseError(401, "invalid token")
        return r.json()


def get_client() -> Optional[SupabaseAdmin]:
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or ""
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return None
    return SupabaseAdmin(url, key)


def desired_metadata(tenant_id: Optional[str], roles: List[str], is_active: bool) -> Dict[str, Any]:
    if not is_active or not tenant_id:
        # a deactivated / tenant-less user must resolve to nothing on the proxy fallback path
        return {"tenant_id": None, "roles": [], "is_active": False}
    return {"tenant_id": str(tenant_id), "roles": sorted(set(roles)), "is_active": True}


def merge_platform_admin(roles: List[str], existing_meta_roles: Any) -> List[str]:
    """platform_admin lives ONLY in app_metadata (granted via PUT /platform/admins/{id}). Every sync
    is a read-modify-write that keeps it; it is never removed implicitly."""
    out = set(roles)
    if isinstance(existing_meta_roles, list) and "platform_admin" in existing_meta_roles:
        out.add("platform_admin")
    return sorted(out)


async def load_user_state(session, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = (
        await session.execute(
            text("SELECT id, email, tenant_id, is_active, supabase_user_id FROM users WHERE id = :u"),
            {"u": str(user_id)},
        )
    ).mappings().first()
    if not row:
        return None
    roles = (
        await session.execute(
            text(
                """
                SELECT DISTINCT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = :u AND (ur.tenant_id = :t OR r.scope = 'PLATFORM')
                """
            ),
            {"u": str(user_id), "t": str(row["tenant_id"]) if row["tenant_id"] else None},
        )
    ).fetchall()
    return {**dict(row), "roles": sorted(r[0] for r in roles)}


async def _record(user_id: uuid.UUID, ok: bool, error: Optional[str] = None, supabase_user_id: Optional[str] = None) -> None:
    async with session_scope() as s:
        await s.execute(
            text(
                """
                UPDATE users SET supabase_synced = :ok,
                       supabase_synced_at = CASE WHEN :ok THEN now() ELSE supabase_synced_at END,
                       supabase_sync_error = :err,
                       supabase_user_id = COALESCE(:sid, supabase_user_id)
                WHERE id = :u
                """
            ),
            {"ok": ok, "err": error, "u": str(user_id), "sid": supabase_user_id},
        )


async def sync_user(user_id: uuid.UUID, revoke: bool = False) -> Dict[str, Any]:
    """Push DB truth for one user into Supabase app_metadata. Never raises: failures are
    recorded on the user row (supabase_synced=false, supabase_sync_error) and retried."""
    client = get_client()
    if client is None:
        await _record(user_id, False, "supabase_not_configured")
        return {"synced": False, "error": "supabase_not_configured"}
    try:
        async with session_scope() as s:
            state = await load_user_state(s, user_id)
        if not state:
            return {"synced": False, "error": "user_not_found"}
        sid = str(state["supabase_user_id"] or state["id"])
        try:
            existing = await client.get_user(sid)
        except SupabaseError as exc:
            if exc.status not in (404, 422):
                raise
            existing = await client.find_by_email(state["email"])
            if not existing:
                await _record(user_id, False, NO_SUPABASE_USER)
                return {"synced": False, "error": NO_SUPABASE_USER}
            sid = existing["id"]
        meta = desired_metadata(state["tenant_id"], state["roles"], state["is_active"])
        meta["roles"] = merge_platform_admin(meta["roles"], (existing.get("app_metadata") or {}).get("roles"))
        await client.set_app_metadata(sid, meta, banned=not state["is_active"])
        revoked = bool(await client.revoke_sessions(sid)) if revoke else False
        await _record(user_id, True, None, sid)
        # sessions_revoked is False on real GoTrue (no admin API); refresh_blocked says the ban is set.
        return {"synced": True, "sessions_revoked": revoked, "refresh_blocked": not state["is_active"]}
    except Exception as exc:  # noqa: BLE001 - recorded + retried
        msg = str(exc)[:300]
        logger.warning("supabase sync failed for %s: %s", user_id, msg)
        try:
            await _record(user_id, False, msg)
        except Exception:  # noqa: BLE001
            logger.exception("could not record sync failure")
        return {"synced": False, "error": msg}


async def sync_users(user_ids, revoke: bool = False) -> Dict[str, Any]:
    return {str(u): await sync_user(u, revoke=revoke) for u in dict.fromkeys(user_ids)}


async def retry_failed_once(limit: int = 50) -> int:
    async with session_scope() as s:
        rows = (
            await s.execute(
                text(
                    """
                    SELECT id FROM users
                    WHERE supabase_synced = false AND tenant_id IS NOT NULL
                      AND coalesce(supabase_sync_error, '') NOT IN (:nsu, 'supabase_not_configured')
                      AND supabase_sync_error IS NOT NULL
                    ORDER BY created_at LIMIT :n
                    """
                ),
                {"nsu": NO_SUPABASE_USER, "n": limit},
            )
        ).fetchall()
    for (uid,) in rows:
        await sync_user(uid)
    return len(rows)


async def retry_loop(interval: float = 60.0) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            if get_client() is not None:
                await retry_failed_once()
        except Exception:  # noqa: BLE001
            logger.exception("sync retry loop error")


async def reconcile(apply: bool = False, adopt_orphans: bool = False, actor_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    """Compare DB truth with Supabase app_metadata for every user; optionally fix the drift."""
    client = get_client()
    if client is None:
        raise SupabaseError(503, "supabase_not_configured")
    sb_users = await client.list_users()
    by_email = {(u.get("email") or "").lower(): u for u in sb_users}

    async with session_scope() as s:
        db_users = (
            await s.execute(text("SELECT id, email, tenant_id, is_active, supabase_user_id FROM users"))
        ).mappings().all()
        states = {}
        for u in db_users:
            states[str(u["id"])] = await load_user_state(s, u["id"])

    drift: List[Dict[str, Any]] = []
    in_sync = 0
    seen = set()
    for uid, st in states.items():
        sb = by_email.get(st["email"].lower())
        want = desired_metadata(st["tenant_id"], st["roles"], st["is_active"])
        if not sb:
            drift.append({"user_id": uid, "email": st["email"], "issue": NO_SUPABASE_USER, "fixed": False})
            continue
        seen.add(sb["id"])
        am = sb.get("app_metadata") or {}
        want["roles"] = merge_platform_admin(want["roles"], am.get("roles"))
        have = {"tenant_id": am.get("tenant_id"), "roles": sorted(am.get("roles") or []), "is_active": am.get("is_active", True)}
        # a user with no DB roles yet and never synced keeps whatever metadata roles it has
        if have["tenant_id"] == want["tenant_id"] and have["roles"] == want["roles"] and bool(have["is_active"]) == want["is_active"]:
            in_sync += 1
            continue
        item = {"user_id": uid, "email": st["email"], "db": want, "supabase": have, "fixed": False}
        if apply:
            r = await sync_user(uuid.UUID(uid), revoke=False)
            item["fixed"] = bool(r.get("synced"))
        drift.append(item)

    orphans = []
    for sb in sb_users:
        if sb["id"] in seen:
            continue
        am = sb.get("app_metadata") or {}
        if any(str(u["id"]) == sb["id"] for u in db_users):
            continue
        orphans.append({"supabase_id": sb["id"], "email": sb.get("email"), "app_metadata_tenant": am.get("tenant_id"), "app_metadata_roles": am.get("roles") or []})

    adopted: List[str] = []
    adopt_skipped: List[Dict[str, str]] = []
    if apply and adopt_orphans:
        adopted, adopt_skipped = await _adopt(orphans, actor_id)
    return {
        "dry_run": not apply,
        "db_users": len(db_users),
        "supabase_users": len(sb_users),
        "in_sync": in_sync,
        "drift": drift,
        "orphans_in_supabase_only": orphans,
        "adopted": adopted,
        "adopt_skipped": adopt_skipped,
    }


async def _adopt(orphans: List[Dict[str, Any]], actor_id: Optional[uuid.UUID] = None) -> Tuple[List[str], List[Dict[str, str]]]:
    """Create DB users for Supabase-only users that already carry a tenant in app_metadata.

    Each adoption is its own transaction that takes the tenant lock, enforces the seat limit, grants
    ONLY tenant-scope roles of that tenant (never platform_admin / PLATFORM roles from metadata),
    sets is_owner consistently, records the seat event and writes a per-user audit row.
    Returns (adopted emails, [{email, reason}] skipped)."""
    from fastapi import HTTPException

    from services.admin import iam  # lazy: iam imports this module

    adopted: List[str] = []
    skipped: List[Dict[str, str]] = []
    new_ids: List[uuid.UUID] = []
    for o in orphans:
        tid, email = o["app_metadata_tenant"], o["email"]
        if not tid or not email:
            continue
        try:
            tenant_uuid = uuid.UUID(str(tid))
            sid = uuid.UUID(str(o["supabase_id"]))
        except ValueError:
            skipped.append({"email": email, "reason": "invalid_id"})
            continue
        norm = email.strip().lower()
        try:
            async with session_scope() as s:
                if not (await s.execute(text("SELECT 1 FROM tenants WHERE id = :t"), {"t": str(tenant_uuid)})).first():
                    skipped.append({"email": email, "reason": "unknown_tenant"})
                    continue
                tenant = await iam.lock_tenant(s, tenant_uuid)
                if str(tenant["status"]).upper() in {"CLOSED", "SUSPENDED"}:
                    skipped.append({"email": email, "reason": "tenant_not_active"})
                    continue
                if (await s.execute(text("SELECT 1 FROM users WHERE lower(email) = :e OR id = :id"), {"e": norm, "id": str(sid)})).first():
                    skipped.append({"email": email, "reason": "already_in_db"})
                    continue
                other_invite = (
                    await s.execute(
                        text(
                            "SELECT 1 FROM invites WHERE lower(email) = :e AND status = 'pending' "
                            "AND expires_at > now() AND tenant_id <> :t"
                        ),
                        {"e": norm, "t": str(tenant_uuid)},
                    )
                ).first()
                if other_invite:
                    skipped.append({"email": email, "reason": "pending_invite_elsewhere"})
                    continue
                await iam.require_seat(s, tenant_uuid)  # 409 seat_limit_reached
                # tenant-scope roles of THIS tenant only; anything else in metadata is ignored
                wanted = [n for n in (o["app_metadata_roles"] or []) if isinstance(n, str)]
                rows = (
                    await s.execute(
                        text("SELECT id, name FROM roles WHERE tenant_id = :t AND scope = 'TENANT' AND name = ANY(:n)"),
                        {"t": str(tenant_uuid), "n": wanted},
                    )
                ).fetchall()
                if not rows:
                    rows = (
                        await s.execute(
                            text("SELECT id, name FROM roles WHERE tenant_id = :t AND scope = 'TENANT' AND name = 'org_user'"),
                            {"t": str(tenant_uuid)},
                        )
                    ).fetchall()
                names = sorted(r[1] for r in rows)
                is_owner = "owner" in names
                ins = await s.execute(
                    text(
                        """
                        INSERT INTO users (id, tenant_id, email, hashed_password, is_active, supabase_user_id, is_owner)
                        VALUES (:id, :t, :e, 'supabase-managed-no-local-login', true, :id, :o)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"id": str(sid), "t": str(tenant_uuid), "e": norm, "o": is_owner},
                )
                if ins.rowcount == 0:
                    skipped.append({"email": email, "reason": "already_in_db"})
                    continue
                for rid, _ in rows:
                    await s.execute(
                        text("INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t) ON CONFLICT DO NOTHING"),
                        {"u": str(sid), "r": str(rid), "t": str(tenant_uuid)},
                    )
                if is_owner:
                    await s.execute(
                        text("UPDATE tenants SET owner_user_id = :u WHERE id = :t AND owner_user_id IS NULL"),
                        {"u": str(sid), "t": str(tenant_uuid)},
                    )
                await iam.record_seat_event(s, tenant_uuid, sid, 1, "adopted", actor_id)
                await iam.write_audit(s, actor_id, "sync.adopt", "user", sid, tenant_uuid, {"email": norm, "roles": names})
        except HTTPException as exc:
            detail = exc.detail.get("error") if isinstance(exc.detail, dict) else str(exc.detail)
            skipped.append({"email": email, "reason": str(detail)})
            continue
        adopted.append(email)
        new_ids.append(sid)
    for sid in new_ids:
        await sync_user(sid)
    return adopted, skipped


async def set_platform_admin(client: "SupabaseAdmin", supabase_user_id: str, grant: bool) -> Dict[str, Any]:
    """Read-modify-write of app_metadata.roles: adds/removes ONLY platform_admin, keeps every other role."""
    u = await client.get_user(supabase_user_id)
    roles = list((u.get("app_metadata") or {}).get("roles") or [])
    has = "platform_admin" in roles
    if grant and not has:
        roles.append("platform_admin")
    elif not grant and has:
        roles = [r for r in roles if r != "platform_admin"]
    else:
        return {"changed": False, "platform_admin": has}
    await client.set_app_metadata(supabase_user_id, {"roles": sorted(set(roles))})
    return {"changed": True, "platform_admin": grant}


async def count_platform_admins(client: "SupabaseAdmin", exclude: Optional[str] = None) -> int:
    n = 0
    for u in await client.list_users():
        if exclude and u.get("id") == exclude:
            continue
        if "platform_admin" in ((u.get("app_metadata") or {}).get("roles") or []):
            n += 1
    return n
