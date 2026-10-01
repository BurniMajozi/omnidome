"""No-database tests for the independent-review hardening: limiter exemption, platform_admin
preservation, custom-role permission rules, platform admin set/remove, GoTrue session revocation."""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
os.environ["INTERNAL_SERVICE_KEY"] = "test-internal-key"

from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from services.admin import iam, supabase_sync  # noqa: E402


def req(path, headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.9", 1), "method": "GET", "path": path, "query_string": b""})


def test_limiter_exempts_only_internal_paths_with_valid_key():
    from services.common.rate_limiter import internal_key_exempt

    def limiter_exempt(r):
        return internal_key_exempt(r, "/internal/")

    ok = {"x-internal-key": "test-internal-key"}
    assert limiter_exempt(req("/internal/users/by-email", ok)) is True
    assert limiter_exempt(req("/internal/users/by-email")) is False  # no key: still throttled per IP
    assert limiter_exempt(req("/internal/users/by-email", {"x-internal-key": "wrong"})) is False
    assert limiter_exempt(req("/tenants", ok)) is False  # the key does not exempt other routes


def test_merge_platform_admin_is_read_modify_write():
    assert supabase_sync.merge_platform_admin(["org_admin"], ["platform_admin", "x"]) == ["org_admin", "platform_admin"]
    assert supabase_sync.merge_platform_admin(["org_admin"], None) == ["org_admin"]
    assert supabase_sync.merge_platform_admin([], ["platform_admin"]) == ["platform_admin"]


class Fake:
    def __init__(self, users):
        self.users = users

    async def get_user(self, uid):
        return dict(self.users[uid])

    async def list_users(self):
        return [dict(u) for u in self.users.values()]

    async def set_app_metadata(self, uid, meta, banned=None):
        self.users[uid]["app_metadata"] = {**self.users[uid]["app_metadata"], **meta}


def test_set_platform_admin_touches_only_that_role_and_counts_others():
    f = Fake(
        {
            "a": {"id": "a", "app_metadata": {"roles": ["platform_admin", "org_user"], "tenant_id": "t"}},
            "b": {"id": "b", "app_metadata": {"roles": ["org_user"]}},
        }
    )
    assert asyncio.run(supabase_sync.count_platform_admins(f)) == 1
    assert asyncio.run(supabase_sync.count_platform_admins(f, exclude="a")) == 0
    assert asyncio.run(supabase_sync.set_platform_admin(f, "b", True))["changed"] is True
    assert f.users["b"]["app_metadata"]["roles"] == ["org_user", "platform_admin"]
    assert asyncio.run(supabase_sync.set_platform_admin(f, "b", True))["changed"] is False
    asyncio.run(supabase_sync.set_platform_admin(f, "a", False))
    assert f.users["a"]["app_metadata"]["roles"] == ["org_user"] and f.users["a"]["app_metadata"]["tenant_id"] == "t"


def test_revoke_sessions_does_not_call_a_nonexistent_endpoint():
    class Boom(supabase_sync.SupabaseAdmin):
        async def _req(self, *a, **k):
            raise AssertionError("no network call expected")

    assert asyncio.run(Boom("http://x", "k").revoke_sessions("u")) is False


def test_custom_permission_rules():
    check = iam.check_custom_permissions
    check(["crm.read"], ["crm.read", "crm.write"], False)
    for bad in (["org.admin"], ["org.manage"], ["platform.admin"]):
        with pytest.raises(HTTPException) as e:
            check(bad, bad, True)  # forbidden even for a platform actor / even when held
        assert e.value.status_code == 403
    for bad in (["*"], ["crm.*"]):
        with pytest.raises(HTTPException) as e:
            check(bad, bad, True)
        assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        check(["crm.write"], ["crm.read"], False)
    assert e.value.status_code == 403
    check(["crm.write"], [], True)  # a platform actor may grant any non-forbidden permission


def test_custom_role_rank_is_capped_below_actor():
    A = iam.Actor
    assert iam.custom_role_rank(A(rank=80, platform=False, owner=False)) == 40
    assert iam.custom_role_rank(A(rank=100, platform=True, owner=True)) == 40
    assert iam.custom_role_rank(A(rank=30, platform=False, owner=False)) == 20
    with pytest.raises(HTTPException):
        iam.custom_role_rank(A(rank=10, platform=False, owner=False))


def test_system_role_names_cover_seeded_roles():
    for n in ("org_admin", "org_user", "owner", "manager", "hr_manager", "platform_admin"):
        assert n in iam.SYSTEM_ROLE_NAMES
