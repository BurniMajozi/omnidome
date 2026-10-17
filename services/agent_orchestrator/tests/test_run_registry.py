"""AG-UI runs are backend-owned: they survive client disconnects and can be replayed."""
import asyncio
import json
import uuid

from services.agent_orchestrator import run_registry


def _chunk(kind, **data):
    return "data: " + json.dumps({"type": kind, "data": data}) + "\n\n"


async def _agent(delay=0.0):
    yield _chunk("RUN_STARTED", agent_type="support")
    await asyncio.sleep(delay)
    yield _chunk("TEXT_MESSAGE_CONTENT", delta="hello ")
    yield _chunk("TEXT_MESSAGE_CONTENT", delta="world")
    yield _chunk("RUN_FINISHED")


def _rec():
    return run_registry.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "support", "hi")


def test_run_continues_after_follower_disconnects_and_can_be_replayed(monkeypatch):
    async def scenario():
        notified = []

        async def fake_notify(rec):
            notified.append(rec.status)
        monkeypatch.setattr(run_registry, "_notify_done", fake_notify)

        rec = _rec()
        run_registry.spawn(rec, _agent(delay=0.05))
        first = rec.follow(0)
        got = [await first.__anext__()]          # client reads RUN_STARTED, then disconnects
        await first.aclose()
        await asyncio.wait_for(rec.task, 2)      # the run itself must still complete
        assert rec.status == "finished" and rec.content == "hello world"
        replay = [c async for c in rec.follow(0) if not c.startswith(":")]
        assert len(replay) == 4 and replay[0] == got[0]
        tail = [c async for c in rec.follow(2) if not c.startswith(":")]
        assert len(tail) == 2
        assert notified == ["finished"]

    asyncio.run(scenario())


def test_cancel_marks_cancelled_and_failures_are_reported(monkeypatch):
    async def scenario():
        seen = []

        async def fake_notify(rec):
            seen.append(rec.status)
        monkeypatch.setattr(run_registry, "_notify_done", fake_notify)

        async def slow():
            yield _chunk("RUN_STARTED")
            await asyncio.sleep(30)
            yield _chunk("RUN_FINISHED")

        rec = _rec()
        run_registry.spawn(rec, slow())
        await asyncio.sleep(0.05)
        rec.task.cancel()
        await asyncio.gather(rec.task, return_exceptions=True)
        assert rec.status == "cancelled"

        async def boom():
            yield _chunk("RUN_STARTED")
            yield _chunk("RUN_ERROR", error="model unavailable")

        bad = _rec()
        run_registry.spawn(bad, boom())
        await asyncio.wait_for(bad.task, 2)
        assert bad.status == "error" and bad.error == "model unavailable"
        assert seen == ["cancelled", "error"]

    asyncio.run(scenario())


def test_runs_are_scoped_to_tenant_and_user():
    rec = _rec()
    assert run_registry.get(rec.run_id, rec.tenant_id, rec.user_id) is rec
    assert run_registry.get(rec.run_id, uuid.uuid4(), rec.user_id) is None
    assert run_registry.get(rec.run_id, rec.tenant_id, uuid.uuid4()) is None
    assert run_registry.list_for(rec.tenant_id, rec.user_id) == [rec]
