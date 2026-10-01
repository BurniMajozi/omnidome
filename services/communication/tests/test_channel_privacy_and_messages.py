"""Private-channel visibility, tenant scoping, history order/cursor, idempotent post, reactions, pin,
approvals/escalations state machines, reference validation and schedule validation.
SQLite in memory, no containers. Run: PYTHONPATH=. python -m pytest services/communication/tests -q
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from services.communication.tests.conftest_db import (
    ADMIN, ALICE, BOB, CAROL, EVE, OTHER_TENANT, TENANT, Env,
)
from services.communication.models import Message
from services.communication.routes import messages as messages_mod


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("MESSAGE_RATE_PER_MIN", "100000")
    e = Env(monkeypatch)
    yield e
    e.close()


def mk_channel(env, user, private=True, name="c"):
    c = env.as_user(user)
    r = c.post("/api/v1/channels", json={"name": name, "is_private": private})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── H1: privacy ────────────────────────────────────────────────────────────

def test_private_channel_visible_to_owner_member_admin_only(env):
    cid = mk_channel(env, ALICE)
    c = env.as_user(ALICE)
    assert c.post(f"/api/v1/channels/{cid}/members", json={"user_ids": [str(BOB)]}).status_code == 201

    assert env.as_user(ALICE).get(f"/api/v1/channels/{cid}").status_code == 200
    assert env.as_user(BOB).get(f"/api/v1/channels/{cid}").status_code == 200
    assert env.as_user(ADMIN, roles=["admin"]).get(f"/api/v1/channels/{cid}").status_code == 200
    # non-member in the same tenant: 404 on every route
    carol = env.as_user(CAROL)
    assert carol.get(f"/api/v1/channels/{cid}").status_code == 404
    assert carol.get(f"/api/v1/channels/{cid}/messages").status_code == 404
    assert carol.post(f"/api/v1/channels/{cid}/messages", json={"content": "hi"}).status_code == 404
    assert carol.get(f"/api/v1/channels/{cid}/members").status_code == 404
    assert carol.put(f"/api/v1/channels/{cid}", json={"name": "x"}).status_code == 404
    assert carol.delete(f"/api/v1/channels/{cid}").status_code == 404
    assert carol.get(f"/api/v1/channels/{cid}/preferences").status_code == 404


def test_list_and_summary_only_visible(env):
    private = mk_channel(env, ALICE, True, "secret")
    public = mk_channel(env, ALICE, False, "open")
    env.as_user(ALICE).post(f"/api/v1/channels/{private}/messages", json={"content": "x"})
    env.as_user(ALICE).post(f"/api/v1/channels/{public}/messages", json={"content": "y"})

    ids = {i["id"] for i in env.as_user(CAROL).get("/api/v1/channels").json()["items"]}
    assert ids == {public}
    assert env.as_user(CAROL).get("/api/v1/channels").json()["total"] == 1
    summ = {i["channel_id"] for i in env.as_user(CAROL).get("/api/v1/channels/summary").json()["items"]}
    assert summ == {public}
    ids = {i["id"] for i in env.as_user(ADMIN, roles=["tenant_admin"]).get("/api/v1/channels").json()["items"]}
    assert ids == {public, private}


def test_manage_needs_owner_or_admin_and_members_must_be_tenant_users(env):
    cid = mk_channel(env, ALICE, False)
    env.as_user(ALICE).post(f"/api/v1/channels/{cid}/members", json={"user_ids": [str(BOB)]})
    bob = env.as_user(BOB)  # plain member
    assert bob.put(f"/api/v1/channels/{cid}", json={"name": "x"}).status_code == 403
    assert bob.post(f"/api/v1/channels/{cid}/members", json={"user_ids": [str(CAROL)]}).status_code == 403
    assert bob.delete(f"/api/v1/channels/{cid}").status_code == 403
    alice = env.as_user(ALICE)
    assert alice.post(f"/api/v1/channels/{cid}/members", json={"user_ids": [str(EVE)]}).status_code == 422
    assert alice.put(f"/api/v1/channels/{cid}", json={"name": "renamed"}).status_code == 200
    assert env.as_user(ADMIN, roles=["admin"]).put(f"/api/v1/channels/{cid}", json={"name": "r2"}).status_code == 200
    assert alice.delete(f"/api/v1/channels/{cid}/members/{BOB}").status_code == 204
    assert env.as_user(ALICE).delete(f"/api/v1/channels/{cid}/members/{ALICE}").status_code == 409


def test_other_tenant_cannot_see_channel(env):
    cid = mk_channel(env, ALICE, False)
    assert env.as_user(EVE, tenant=OTHER_TENANT).get(f"/api/v1/channels/{cid}").status_code == 404


def test_delete_channel_removes_dependents(env):
    cid = mk_channel(env, ALICE, False)
    c = env.as_user(ALICE)
    c.post(f"/api/v1/channels/{cid}/messages", json={"content": "m"})
    assert c.post("/api/v1/tasks", json={"channel_id": cid, "title": "t"}).status_code == 201
    assert c.post("/api/v1/approvals", json={"channel_id": cid, "title": "a"}).status_code == 201
    assert c.post("/api/v1/escalations", json={"channel_id": cid, "reason": "r"}).status_code == 201
    assert c.delete(f"/api/v1/channels/{cid}").status_code == 204

    from sqlalchemy import func, select
    from services.communication.models import Approval, Escalation, Task

    async def counts():
        async with env.maker() as s:
            return [(await s.execute(select(func.count()).select_from(m))).scalar() for m in (Task, Approval, Escalation, Message)]

    assert env.run(counts()) == [0, 0, 0, 0]


# ── H2: pin ────────────────────────────────────────────────────────────────

def test_pin_and_unpin(env):
    cid = mk_channel(env, ALICE, False)
    mid = env.as_user(ALICE).post(f"/api/v1/channels/{cid}/messages", json={"content": "p"}).json()["id"]
    r = env.as_user(BOB).patch(f"/api/v1/messages/{mid}/pin", json={"is_pinned": True})
    assert r.status_code == 200 and r.json()["is_pinned"] is True
    r = env.as_user(BOB).patch(f"/api/v1/messages/{mid}/pin", json={"is_pinned": False})
    assert r.json()["is_pinned"] is False


def test_pin_hidden_for_private_and_other_tenant(env):
    cid = mk_channel(env, ALICE, True)
    mid = env.as_user(ALICE).post(f"/api/v1/channels/{cid}/messages", json={"content": "p"}).json()["id"]
    assert env.as_user(CAROL).patch(f"/api/v1/messages/{mid}/pin", json={"is_pinned": True}).status_code == 404
    assert env.as_user(EVE, tenant=OTHER_TENANT).patch(f"/api/v1/messages/{mid}/pin", json={"is_pinned": True}).status_code == 404


# ── H3: message ids are tenant + channel scoped ────────────────────────────

def test_cross_tenant_and_cross_channel_message_ids_404(env):
    cid = mk_channel(env, ALICE, False)
    other = mk_channel(env, ALICE, False, "other")
    mid = env.as_user(ALICE).post(f"/api/v1/channels/{cid}/messages", json={"content": "m"}).json()["id"]
    eve = env.as_user(EVE, tenant=OTHER_TENANT)
    for call in (
        lambda: eve.get(f"/api/v1/channels/{cid}/messages/{mid}"),
        lambda: eve.put(f"/api/v1/channels/{cid}/messages/{mid}", json={"content": "x"}),
        lambda: eve.delete(f"/api/v1/channels/{cid}/messages/{mid}"),
        lambda: eve.post(f"/api/v1/channels/{cid}/messages/{mid}/react?emoji=%2B1"),
    ):
        assert call().status_code == 404
    # right tenant, wrong channel
    assert env.as_user(ALICE).get(f"/api/v1/channels/{other}/messages/{mid}").status_code == 404
    # right tenant, author only
    assert env.as_user(BOB).put(f"/api/v1/channels/{cid}/messages/{mid}", json={"content": "x"}).status_code == 403


def test_reactions_validated_idempotent_and_author_deletable(env):
    cid = mk_channel(env, ALICE, False)
    mid = env.as_user(ALICE).post(f"/api/v1/channels/{cid}/messages", json={"content": "m"}).json()["id"]
    bob = env.as_user(BOB)
    base = f"/api/v1/channels/{cid}/messages/{mid}/react"
    assert bob.post(base, params={"emoji": "\U0001F44D"}).status_code == 201
    assert bob.post(base, params={"emoji": "\U0001F44D"}).status_code == 201  # idempotent, no duplicate row
    assert bob.post(base, params={"emoji": "thumbs_up"}).status_code == 201
    for bad in ("x" * 33, "<script>", "a b", ""):
        assert bob.post(base, params={"emoji": bad}).status_code == 422, bad
    # only the author removes their reaction
    assert env.as_user(CAROL).delete(base, params={"emoji": "thumbs_up"}).status_code == 404
    assert env.as_user(BOB).delete(base, params={"emoji": "thumbs_up"}).status_code == 204


def test_valid_emoji_function():
    v = messages_mod.valid_emoji
    assert v("+1") and v(":tada:") and v("\U0001F468‍\U0001F469")
    assert not v("") and not v("y" * 40) and not v("a>b") and not v("\n")


# ── H4: history newest-first + cursor ──────────────────────────────────────

def _seed(env, cid, n):
    async def go():
        async with env.maker() as s:
            base = datetime(2026, 1, 1, tzinfo=timezone.utc)
            for i in range(n):
                s.add(Message(tenant_id=TENANT, channel_id=uuid.UUID(cid), user_id=ALICE, content=f"m{i:03d}",
                              created_at=base + timedelta(seconds=i)))
            await s.commit()
    env.run(go())


def test_history_returns_newest_page_ascending(env):
    cid = mk_channel(env, ALICE, False)
    _seed(env, cid, 120)
    r = env.as_user(BOB).get(f"/api/v1/channels/{cid}/messages").json()
    texts = [m["content"] for m in r["items"]]
    assert len(texts) == 50 and texts[0] == "m070" and texts[-1] == "m119"  # newest 50, oldest-first
    assert r["has_more"] is True and r["total"] == 120 and r["next_before"]


def test_keyset_cursor_walks_back_without_gaps_or_dupes(env):
    cid = mk_channel(env, ALICE, False)
    _seed(env, cid, 120)
    c = env.as_user(BOB)
    seen, before = [], None
    for _ in range(10):
        url = f"/api/v1/channels/{cid}/messages?limit=50" + (f"&before={before}" if before else "")
        r = c.get(url).json()
        seen = [m["content"] for m in r["items"]] + seen
        before = r["next_before"]
        if not r["has_more"]:
            break
    assert seen == [f"m{i:03d}" for i in range(120)]
    assert before is None
    assert c.get(f"/api/v1/channels/{cid}/messages?before=not-a-cursor").status_code == 422
    ts = "2026-01-01T00:00:10Z"
    r = c.get(f"/api/v1/channels/{cid}/messages?before={ts}&limit=5").json()
    assert [m["content"] for m in r["items"]] == ["m005", "m006", "m007", "m008", "m009"]


def test_legacy_page_param_walks_older(env):
    cid = mk_channel(env, ALICE, False)
    _seed(env, cid, 120)
    r = env.as_user(BOB).get(f"/api/v1/channels/{cid}/messages?page=2&page_size=50").json()
    assert r["items"][0]["content"] == "m020" and r["items"][-1]["content"] == "m069"


# ── M8: idempotent post, limits ────────────────────────────────────────────

def test_client_msg_id_makes_retry_idempotent_and_broadcasts_once(env):
    cid = mk_channel(env, ALICE, False)
    c = env.as_user(ALICE)
    a = c.post(f"/api/v1/channels/{cid}/messages", json={"content": "once", "client_msg_id": "k-1"})
    b = c.post(f"/api/v1/channels/{cid}/messages", json={"content": "once", "client_msg_id": "k-1"})
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
    assert len(env.broadcasts) == 1  # broadcast only for the created row, after commit
    n = c.get(f"/api/v1/channels/{cid}/messages").json()["total"]
    assert n == 1
    assert c.post(f"/api/v1/channels/{cid}/messages", json={"content": "x", "client_msg_id": "bad id!"}).status_code == 422


def test_message_length_and_rate_limit(env, monkeypatch):
    cid = mk_channel(env, ALICE, False)
    monkeypatch.setenv("MESSAGE_MAX_CHARS", "10")
    c = env.as_user(ALICE)
    assert c.post(f"/api/v1/channels/{cid}/messages", json={"content": "x" * 11}).status_code == 422
    assert c.post(f"/api/v1/channels/{cid}/messages", json={"content": "x" * 10}).status_code == 201
    monkeypatch.setenv("MESSAGE_RATE_PER_MIN", "2")
    messages_mod._limiters.clear()
    codes = [c.post(f"/api/v1/channels/{cid}/messages", json={"content": "r"}).status_code for _ in range(3)]
    assert codes == [201, 201, 429]


# ── M9: approvals / escalations ────────────────────────────────────────────

def test_approval_state_machine(env):
    cid = mk_channel(env, ALICE, False)
    aid = env.as_user(ALICE).post("/api/v1/approvals", json={"channel_id": cid, "title": "t"}).json()["id"]
    url = f"/api/v1/approvals/{aid}/decide"
    assert env.as_user(ALICE, roles=["admin"]).post(url, json={"status": "approved"}).status_code == 403  # self
    assert env.as_user(BOB).post(url, json={"status": "approved"}).status_code == 403  # no manager tier
    assert env.as_user(ADMIN, roles=["manager"]).post(url, json={"status": "maybe"}).status_code == 422
    r = env.as_user(ADMIN, roles=["manager"]).post(url, json={"status": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["decided_by"] == str(ADMIN)
    assert env.as_user(ADMIN, roles=["admin"]).post(url, json={"status": "rejected"}).status_code == 409
    assert env.as_user(ADMIN).get("/api/v1/approvals?status=bogus").status_code == 422


def test_approval_requester_can_cancel_others_cannot(env):
    cid = mk_channel(env, ALICE, False)
    aid = env.as_user(ALICE).post("/api/v1/approvals", json={"channel_id": cid, "title": "t"}).json()["id"]
    url = f"/api/v1/approvals/{aid}/decide"
    assert env.as_user(BOB, roles=["admin"]).post(url, json={"status": "cancelled"}).status_code == 403
    assert env.as_user(ALICE).post(url, json={"status": "cancelled"}).json()["status"] == "cancelled"


def test_escalation_enums_and_transitions(env):
    cid = mk_channel(env, ALICE, False)
    eid = env.as_user(ALICE).post("/api/v1/escalations", json={"channel_id": cid, "reason": "r"}).json()["id"]
    url = f"/api/v1/escalations/{eid}"
    assert env.as_user(ALICE).patch(f"{url}/status", params={"status": "weird"}).status_code == 422
    assert env.as_user(BOB).patch(f"{url}/status", params={"status": "resolved"}).status_code == 403
    assert env.as_user(ALICE).patch(f"{url}/status", params={"status": "resolved"}).status_code == 200
    assert env.as_user(ALICE).patch(f"{url}/status", params={"status": "closed"}).status_code == 200
    assert env.as_user(ALICE).patch(f"{url}/status", params={"status": "open"}).status_code == 409
    assert env.as_user(ALICE).patch(f"{url}/assign", params={"assigned_to": str(BOB)}).status_code == 403
    assert env.as_user(ADMIN, roles=["manager"]).patch(f"{url}/assign", params={"assigned_to": str(EVE)}).status_code == 422
    assert env.as_user(ADMIN, roles=["manager"]).patch(f"{url}/assign", params={"assigned_to": str(BOB)}).status_code == 200


# ── M10: reference validation, schedule ────────────────────────────────────

def test_reference_validation_for_task_approval_escalation(env):
    private = mk_channel(env, ALICE, True)
    public = mk_channel(env, ALICE, False)
    mid = env.as_user(ALICE).post(f"/api/v1/channels/{private}/messages", json={"content": "m"}).json()["id"]
    carol = env.as_user(CAROL)
    assert carol.post("/api/v1/tasks", json={"channel_id": private, "title": "t"}).status_code == 404
    assert carol.post("/api/v1/approvals", json={"channel_id": private, "title": "t"}).status_code == 404
    assert carol.post("/api/v1/escalations", json={"channel_id": private, "reason": "r"}).status_code == 404
    assert carol.post("/api/v1/tasks", json={"channel_id": public, "title": "t", "message_id": mid}).status_code == 404
    assert carol.post("/api/v1/tasks", json={"channel_id": str(uuid.uuid4()), "title": "t"}).status_code == 404
    assert env.as_user(EVE, tenant=OTHER_TENANT).post("/api/v1/tasks", json={"channel_id": public, "title": "t"}).status_code == 404
    assert env.as_user(ALICE).post("/api/v1/tasks", json={"channel_id": public, "title": "t", "assignee_id": str(EVE)}).status_code == 422
    ok = env.as_user(ALICE).post("/api/v1/tasks", json={"channel_id": private, "title": "t", "message_id": mid})
    assert ok.status_code == 201
    # lists hide private-channel items from non-members
    assert env.as_user(CAROL).get("/api/v1/tasks").json()["total"] == 0
    assert env.as_user(ALICE).get("/api/v1/tasks").json()["total"] == 1


def _ev(cid, **kw):
    start = datetime(2026, 5, 1, 9, tzinfo=timezone.utc)
    body = {"channel_id": cid, "title": "mtg", "type": "meeting",
            "start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat()}
    body.update(kw)
    return body


def test_schedule_validation_and_user_from_ctx(env):
    cid = mk_channel(env, ALICE, False)
    c = env.as_user(BOB)
    ok = c.post("/api/v1/schedule", json=_ev(cid, user_id=str(ALICE)))
    # a client-supplied user_id is not honoured for non-admins
    assert ok.status_code == 403
    r = c.post("/api/v1/schedule", json=_ev(cid))
    assert r.status_code == 201 and r.json()["user_id"] == str(BOB)
    bad = _ev(cid, end_time="2026-05-01T08:00:00+00:00")
    assert c.post("/api/v1/schedule", json=bad).status_code == 422
    assert c.post("/api/v1/schedule", json=_ev(cid, start_time="2026-05-01T09:00:00", end_time="2026-05-01T10:00:00")).status_code == 422
    adm = env.as_user(ADMIN, roles=["admin"]).post("/api/v1/schedule", json=_ev(cid, user_id=str(CAROL)))
    assert adm.status_code == 201 and adm.json()["user_id"] == str(CAROL)
    assert env.as_user(ADMIN, roles=["admin"]).post("/api/v1/schedule", json=_ev(cid, user_id=str(EVE))).status_code == 422
    private = mk_channel(env, ALICE, True, "p")
    assert env.as_user(CAROL).post("/api/v1/schedule", json=_ev(private)).status_code == 404
