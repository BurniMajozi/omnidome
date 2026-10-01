"""WebSocket access, typing scope, Redis fan-out (fake Redis), and connection hardening helpers.
No containers, no real sockets. Run: PYTHONPATH=. python -m pytest services/communication/tests -q
"""

import asyncio
import json
import uuid

import pytest

from services.communication import realtime
from services.communication.routes import ws as ws_mod
from services.communication.tests.conftest_db import ALICE, BOB, CAROL, ADMIN, TENANT, Env


def run(coro):
    return asyncio.run(coro)


class FakeWS:
    def __init__(self, user="u", slow=False, fail=False):
        self.user, self.sent, self.slow, self.fail, self.closed = user, [], slow, fail, None

    async def send_text(self, text):
        if self.slow:
            await asyncio.sleep(30)
        if self.fail:
            raise RuntimeError("gone")
        self.sent.append(json.loads(text))

    async def close(self, code=1000, reason=None):
        self.closed = code


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    realtime._connections.clear()
    realtime._subscribed_topics.clear()
    monkeypatch.setattr(realtime, "REDIS_URL", None)
    yield
    realtime._connections.clear()


def register(tenant, channel, user, ws=None):
    ws = ws or FakeWS(user)
    realtime._connections[tenant][channel].add((user, ws))
    return ws


# ── ws.py access (members allowed, strangers denied, admin allowed) ─────────

def test_ws_channel_access_function(monkeypatch):
    env = Env(monkeypatch)
    try:
        cid = env.as_user(ALICE).post("/api/v1/channels", json={"name": "p", "is_private": True}).json()["id"]
        env.as_user(ALICE).post(f"/api/v1/channels/{cid}/members", json={"user_ids": [str(BOB)]})
        chk = ws_mod._check_channel_access
        cid_u = uuid.UUID(cid)
        assert env.run(chk(TENANT, cid_u, ALICE)) is True      # creator
        assert env.run(chk(TENANT, cid_u, BOB)) is True        # member
        assert env.run(chk(TENANT, cid_u, CAROL)) is False     # same tenant, not a member
        assert env.run(chk(uuid.UUID("a0000000-0000-0000-0000-000000000002"), cid_u, ALICE)) is False  # other tenant
        assert env.run(chk(TENANT, uuid.uuid4(), ALICE)) is False
        public = env.as_user(ALICE).post("/api/v1/channels", json={"name": "o", "is_private": False}).json()["id"]
        assert env.run(chk(TENANT, uuid.UUID(public), CAROL)) is True
    finally:
        env.close()


# ── M5: typing uses the connection's channel ───────────────────────────────

class InboundWS(FakeWS):
    def __init__(self, user, frames):
        super().__init__(user)
        self.frames = list(frames)

    async def receive_text(self):
        if not self.frames:
            raise RuntimeError("disconnect")
        return self.frames.pop(0)


def test_typing_ignores_client_channel_id():
    t, mine, other = "t1", "chan-mine", "chan-other"
    peer_mine = register(t, mine, "peer")
    peer_other = register(t, other, "peer2")
    sender = InboundWS("me", [json.dumps({"type": "typing", "channel_id": other})])
    register(t, mine, "me", sender)
    run(realtime.handle_connection(sender, t, mine, "me"))
    assert any(e["type"] == "typing" for e in peer_mine.sent)
    assert not [e for e in peer_other.sent if e["type"] == "typing"]
    assert not [e for e in sender.sent if e["type"] == "typing"]  # not echoed to sender


# ── M6: Redis fan-out ──────────────────────────────────────────────────────

class FakePubSub:
    def __init__(self, redis):
        self.redis, self.topics, self.queue = redis, set(), asyncio.Queue()

    async def subscribe(self, topic):
        self.topics.add(topic)
        self.redis.subs.append(self)

    async def unsubscribe(self, topic):
        self.topics.discard(topic)

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        try:
            return await asyncio.wait_for(self.queue.get(), timeout)
        except asyncio.TimeoutError:
            return None


class FakeRedis:
    def __init__(self):
        self.published, self.subs, self.fail = [], [], False

    def pubsub(self):
        return FakePubSub(self)

    async def publish(self, topic, msg):
        if self.fail:
            raise RuntimeError("redis down")
        self.published.append((topic, msg))
        for p in self.subs:
            if topic in p.topics:
                p.queue.put_nowait({"type": "message", "channel": topic, "data": msg})


def use_fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(realtime, "REDIS_URL", "redis://fake")
    monkeypatch.setattr(realtime, "_redis_client", fake)
    monkeypatch.setattr(realtime, "_redis_pubsub", None)
    monkeypatch.setattr(realtime, "_redis_listener_task", None)
    return fake


def test_publish_delivers_locally_once_and_own_echo_is_dropped(monkeypatch):
    async def go():
        fake = use_fake_redis(monkeypatch)
        ws = register("t1", "c1", "u1")
        await realtime._ensure_redis_sub("t1", "c1")
        await realtime.broadcast_message("t1", "c1", {"id": "m1"})
        await asyncio.sleep(0.2)  # let the listener run: the echo of our own publish must be ignored
        assert len(fake.published) == 1
        assert [e["data"]["id"] for e in ws.sent] == ["m1"]
        realtime._redis_listener_task.cancel()
    run(go())


def test_foreign_replica_payload_is_delivered_once(monkeypatch):
    async def go():
        fake = use_fake_redis(monkeypatch)
        ws = register("t1", "c1", "u1")
        await realtime._ensure_redis_sub("t1", "c1")
        foreign = json.dumps({"origin": "other-replica", "tenant_id": "t1", "channel_id": "c1",
                              "type": "message", "data": {"id": "m9"}})
        await fake.publish("comm:ws:t1:c1", foreign)
        await asyncio.sleep(0.2)
        assert [e["data"]["id"] for e in ws.sent] == ["m9"]
        realtime._redis_listener_task.cancel()
    run(go())


def test_redis_payload_validation_and_tenant_recheck():
    async def go():
        a = register("tA", "c1", "u1")
        b = register("tB", "c1", "u2")
        good = {"origin": "x", "tenant_id": "tA", "channel_id": "c1", "type": "message", "data": {"id": 1}}
        assert await realtime.deliver_redis_payload(json.dumps(good), "comm:ws:tA:c1")
        assert len(a.sent) == 1 and len(b.sent) == 0                       # only the payload's own tenant
        assert not await realtime.deliver_redis_payload(json.dumps(good), "comm:ws:tB:c1")  # topic mismatch
        for bad in ({"tenant_id": "tA"}, {**good, "data": "x"}, {**good, "channel_id": 5}, [1], "nope"):
            assert not await realtime.deliver_redis_payload(json.dumps(bad) if not isinstance(bad, str) else bad)
        assert not await realtime.deliver_redis_payload(json.dumps({**good, "origin": realtime.ORIGIN_ID}))
    run(go())


def test_redis_down_falls_back_to_local_only(monkeypatch):
    async def go():
        fake = use_fake_redis(monkeypatch)
        fake.fail = True
        ws = register("t1", "c1", "u1")
        await realtime.broadcast_message("t1", "c1", {"id": "m1"})
        assert [e["data"]["id"] for e in ws.sent] == ["m1"]
    run(go())


def test_unsubscribes_when_last_socket_leaves(monkeypatch):
    async def go():
        use_fake_redis(monkeypatch)
        ws = register("t1", "c1", "u1")
        await realtime._ensure_redis_sub("t1", "c1")
        assert "comm:ws:t1:c1" in realtime._subscribed_topics
        realtime.disconnect(ws, "t1", "c1", "u1")
        await realtime._maybe_unsubscribe("t1", "c1")
        assert "comm:ws:t1:c1" not in realtime._subscribed_topics
        assert "comm:ws:t1:c1" not in realtime._redis_pubsub.topics
        realtime._redis_listener_task.cancel()
    run(go())


def test_listener_restarts_with_backoff(monkeypatch):
    async def go():
        fake = use_fake_redis(monkeypatch)
        realtime._subscribed_topics.add("comm:ws:t1:c1")
        realtime._redis_pubsub = fake.pubsub()
        calls, sleeps = {"n": 0}, []

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            realtime._subscribed_topics.clear()  # then exits cleanly

        async def fake_sleep(d):
            sleeps.append(d)

        monkeypatch.setattr(realtime, "_listen_once", flaky)
        await realtime._listener_supervisor(sleep=fake_sleep)
        assert calls["n"] == 3 and sleeps == [1.0, 2.0]
    run(go())


# ── M7: limits ─────────────────────────────────────────────────────────────

def test_slow_socket_is_dropped_without_delaying_others(monkeypatch):
    async def go():
        monkeypatch.setenv("WS_SEND_TIMEOUT", "0.2")
        fast, slow, broken = register("t", "c", "a"), register("t", "c", "b", FakeWS("b", slow=True)), \
            register("t", "c", "c", FakeWS("c", fail=True))
        t0 = asyncio.get_event_loop().time()
        await realtime.broadcast_message("t", "c", {"id": 1})
        assert asyncio.get_event_loop().time() - t0 < 1.0  # concurrent, bounded by the timeout
        assert len(fast.sent) == 1
        remaining = {u for u, _ in realtime._connections["t"]["c"]}
        assert remaining == {"a"}
        assert slow.closed == 1013
    run(go())


def test_sliding_window_and_frame_size(monkeypatch):
    w = realtime.SlidingWindow(3, 10.0)
    assert [w.allow(now=t) for t in (0, 1, 2, 3)] == [True, True, True, False]
    assert w.allow(now=11.5) is True
    monkeypatch.setenv("WS_MAX_MESSAGE_BYTES", "10")
    assert realtime.frame_too_large("x" * 11) and not realtime.frame_too_large("x" * 10)


def test_oversized_and_flooding_clients_are_closed(monkeypatch):
    async def go():
        monkeypatch.setenv("WS_MAX_MESSAGE_BYTES", "20")
        big = InboundWS("u", ["x" * 50])
        register("t", "c", "u", big)
        await realtime.handle_connection(big, "t", "c", "u")
        assert big.closed == 1009
        monkeypatch.setenv("WS_INBOUND_PER_10S", "2")
        flood = InboundWS("u2", [json.dumps({"type": "pong"})] * 5)
        register("t", "c", "u2", flood)
        await realtime.handle_connection(flood, "t", "c", "u2")
        assert flood.closed == 4429
    run(go())


def test_idle_connection_closed_with_4408(monkeypatch):
    class Silent(FakeWS):
        async def receive_text(self):
            await asyncio.sleep(30)

    async def go():
        monkeypatch.setenv("WS_IDLE_TIMEOUT", "0.2")
        s = Silent("u")
        register("t", "c", "u", s)
        await realtime.handle_connection(s, "t", "c", "u")
        assert s.closed == 4408
    run(go())


def test_per_user_connection_cap(monkeypatch):
    monkeypatch.setenv("WS_MAX_CONNECTIONS_PER_USER", "2")
    register("t", "c1", "u")
    register("t", "c2", "u")
    register("t", "c1", "other")
    assert realtime.user_connection_count("t", "u") == 2
    assert realtime.max_connections_per_user() == 2
    assert realtime.user_connection_count("t", "other") == 1
    assert realtime.user_connection_count("t2", "u") == 0


@pytest.mark.parametrize("origin,host,allowed,public,expected", [
    (None, "svc", None, None, True),                                   # non-browser client
    ("http://localhost:3000", "svc", None, None, True),                # dev
    ("https://app.example.com", "svc", None, "https://app.example.com", True),
    ("https://evil.example.net", "svc", None, "https://app.example.com", False),
    ("https://evil.example.net", "svc", "https://other.example.com", None, False),
    ("https://other.example.com", "svc", "https://other.example.com, https://x.io", None, True),
    ("http://other.example.com", "svc", "https://other.example.com", None, False),   # scheme mismatch
    ("https://anything.io", "svc", "*", None, True),
    ("https://svc.example.com", "svc.example.com:8020", None, None, True),          # same host
    ("not a url", "svc", None, None, False),
])
def test_origin_allowed(origin, host, allowed, public, expected):
    assert realtime.origin_allowed(origin, host, allowed, public) is expected
