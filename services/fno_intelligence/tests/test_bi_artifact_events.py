"""Write-through of BI work product to the knowledge layer: events fire on create/update/publish/delete with the
caller's identity, and a failing or absent memory service never fails or slows the user's save."""

import asyncio

from services.fno_intelligence import bi_artifact_events as ev
from services.fno_intelligence.tests.bi_harness import TENANT_A, USER, env, resp_json, run
from services.fno_intelligence.tests.test_bi_decks import create, put


def capture(monkeypatch, status=200, boom=False):
    sent = []

    async def fake_post(headers, body):
        sent.append((headers, body))
        if boom:
            raise ConnectionError("memory service down")
        return status

    monkeypatch.setenv("TENANT_MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setattr(ev, "_post", fake_post)
    monkeypatch.setattr(ev, "COMMIT_DELAY_S", 0)
    monkeypatch.setattr(ev, "RETRY_DELAY_S", 0)
    return sent


async def drain():
    while ev._tasks:
        await asyncio.gather(*list(ev._tasks), return_exceptions=True)


def test_deck_lifecycle_fires_events_with_caller_identity(tmp_path, monkeypatch):
    sent = capture(monkeypatch)

    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            d = await create(e)
            resp_json(await put(e, d, title="Sales Pipeline Overview"))
            resp_json(await e.req("POST", f"/decks/{d['id']}/publish", roles="admin", json={"published": True}))
            assert (await e.req("DELETE", f"/decks/{d['id']}", roles="admin")).status_code == 204
            await drain()
            return d["id"]

    deck_id = run(scenario())
    bodies = [b for _, b in sent]
    assert [b["deleted"] for b in bodies] == [False, False, False, True]
    assert all(b == {"source_type": "bi_deck", "source_id": deck_id, "deleted": b["deleted"]} for b in bodies)
    h = sent[0][0]
    assert h["X-Tenant-Id"] == str(TENANT_A) and h["X-User-Id"] == str(USER) and "analyst" in h["X-Roles"]


def test_events_never_break_the_save_when_memory_is_down(tmp_path, monkeypatch):
    sent = capture(monkeypatch, boom=True)

    async def scenario():
        async with env(tmp_path, monkeypatch) as e:
            d = await create(e)
            assert resp_json(await put(e, d, title="Still saves"))["title"] == "Still saves"
            await drain()

    run(scenario())
    assert len(sent) == 4          # two events, each retried once, then given up quietly (the sweep catches up)


def test_unconfigured_or_switched_off_is_a_noop(monkeypatch):
    monkeypatch.delenv("TENANT_MEMORY_SERVICE_URL", raising=False)
    assert ev.notify(object(), "bi_deck", "x") is None
    monkeypatch.setenv("TENANT_MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("KNOWLEDGE_WRITE_THROUGH", "false")
    assert ev.notify(object(), "bi_deck", "x") is None
    monkeypatch.delenv("KNOWLEDGE_WRITE_THROUGH")
    assert ev.notify(object(), "customer", "x") is None          # only artifact kinds
    assert ev.notify(None, "bi_deck", "x") is None


def test_rejected_requests_are_not_retried_forever(monkeypatch):
    sent = capture(monkeypatch, status=403)

    async def scenario():
        class A:
            tenant_id, user_id, roles = TENANT_A, USER, ["viewer"]
        ev.notify(A(), "bi_deck", "11111111-2222-3333-4444-555555555555")
        await drain()

    run(scenario())
    assert len(sent) == 1
