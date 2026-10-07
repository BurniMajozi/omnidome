"""Follow-ups to the hardening pass: unowned conversations, per-model pricing,
shared voice rate limit + non-WAV duration, identity roles on service calls.

No database or network: sessions are faked.
"""

import asyncio
import inspect
import os
import sys
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import internal_auth  # noqa: E402
from services.common.auth import AuthContext  # noqa: E402
from services.agent_orchestrator import control_plane, identity, model_pricing, voice_limits  # noqa: E402
from services.agent_orchestrator.routes import conversations as conv_routes  # noqa: E402

TENANT, USER = uuid.uuid4(), uuid.uuid4()


def ctx(roles=(), user=USER, perms=()):
    return AuthContext(user_id=user, tenant_id=TENANT, roles=list(roles), permissions=list(perms))


def run(c):
    return asyncio.run(c)


# -- 1. unowned conversations are admin-only ---------------------------------

def test_unowned_conversation_is_admin_only():
    legacy = SimpleNamespace(context={})
    with pytest.raises(HTTPException) as e:
        identity.check_conversation_access(legacy, ctx())
    assert e.value.status_code == 404
    identity.check_conversation_access(legacy, ctx(roles=["org_admin"]))
    identity.check_conversation_access(SimpleNamespace(context=None), ctx(roles=["admin"]))
    with pytest.raises(HTTPException):
        identity.check_conversation_access(SimpleNamespace(context=None), ctx())


def test_owned_conversation_still_open_to_owner_only():
    conv = SimpleNamespace(context={identity.OWNER_KEY: str(USER)})
    identity.check_conversation_access(conv, ctx())
    with pytest.raises(HTTPException):
        identity.check_conversation_access(conv, ctx(user=uuid.uuid4()))


class _ConvSession:
    def __init__(self, conv):
        self.conv = conv

    async def execute(self, *_a, **_k):
        return SimpleNamespace(scalar_one_or_none=lambda: self.conv)

    async def flush(self):
        pass


def _scope(conv):
    @asynccontextmanager
    async def scope():
        yield _ConvSession(conv)
    return scope


def test_owner_endpoint_admin_can_claim_unowned():
    conv = SimpleNamespace(context={"title": "old"})
    new_owner = uuid.uuid4()
    with patch.object(conv_routes, "get_session", _scope(conv)):
        out = run(conv_routes.set_conversation_owner(uuid.uuid4(), {"user_id": str(new_owner)}, ctx(roles=["admin"])))
    assert out["owner_user_id"] == str(new_owner) and out["previous_owner_user_id"] is None
    assert conv.context[identity.OWNER_KEY] == str(new_owner) and conv.context["title"] == "old"
    identity.check_conversation_access(conv, ctx(user=new_owner))


def test_owner_endpoint_rejects_non_admin_and_bad_input():
    conv = SimpleNamespace(context={})
    with patch.object(conv_routes, "get_session", _scope(conv)):
        with pytest.raises(HTTPException) as e:
            run(conv_routes.set_conversation_owner(uuid.uuid4(), {"user_id": str(USER)}, ctx()))
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            run(conv_routes.set_conversation_owner(uuid.uuid4(), {"user_id": "nope"}, ctx(roles=["admin"])))
        assert e.value.status_code == 422
    assert identity.OWNER_KEY not in conv.context
    with patch.object(conv_routes, "get_session", _scope(None)):
        with pytest.raises(HTTPException) as e:
            run(conv_routes.set_conversation_owner(uuid.uuid4(), {"user_id": str(USER)}, ctx(roles=["admin"])))
        assert e.value.status_code == 404


def test_list_filter_excludes_unowned_for_non_admin():
    assert "is_(None)" not in inspect.getsource(conv_routes.list_conversations)


# -- 2. per-model pricing ----------------------------------------------------

PRICES = {
    "default": {"input_per_1m_usd": 15.0, "output_per_1m_usd": 75.0},
    "anthropic/claude-sonnet": {"input_per_1m_usd": 3.0, "output_per_1m_usd": 15.0},
    "anthropic/": {"input_per_1m_usd": 9.0, "output_per_1m_usd": 9.0},
}


def test_price_uses_split_and_longest_prefix():
    p = model_pricing.price_model("Anthropic/Claude-Sonnet-4", 1_000_000, 1_000_000, 2_000_000, PRICES)
    assert p.usd == pytest.approx(18.0) and p.source == "table" and not p.estimated
    p = model_pricing.price_model("anthropic/other", 1_000_000, 0, 1_000_000, PRICES)
    assert p.usd == pytest.approx(9.0)


def test_price_total_only_uses_higher_rate_and_is_estimated():
    p = model_pricing.price_model("anthropic/claude-sonnet-4", 0, 0, 1_000_000, PRICES)
    assert p.usd == pytest.approx(15.0) and p.estimated


def test_unknown_model_uses_conservative_default_flagged():
    p = model_pricing.price_model("someone/new-model", 1_000_000, 1_000_000, 2_000_000, PRICES)
    assert p.usd == pytest.approx(90.0) and p.source == "default" and p.estimated


def test_local_models_cost_zero():
    for m in ("ollama/gemma3", "ollama:llama3", "gemma3:4b", "qwen2.5:7b"):
        p = model_pricing.price_model(m, 5_000_000, 5_000_000, 10_000_000, PRICES)
        assert p.usd == 0 and p.source == "local" and not p.estimated
    # OpenRouter-style ids are never mistaken for local
    assert model_pricing.price_model("meta-llama/llama-3-70b", 1_000_000, 0, 1_000_000, PRICES).source == "default"


def test_flat_rate_is_last_resort_only(monkeypatch):
    monkeypatch.setenv("AGENT_USD_PER_1K_TOKENS", "0.02")
    p = model_pricing.price_model("x/y", 0, 0, 1000, {"foo": {"input_per_1m_usd": 1, "output_per_1m_usd": 1}})
    assert p.usd == pytest.approx(0.02) and p.source == "flat" and p.estimated


def test_env_overrides_and_bad_json_ignored(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL_PRICES", '{"acme/": {"input_per_1m_usd": 1, "output_per_1m_usd": 2}}')
    prices = model_pricing.load_prices()
    assert prices["acme/"]["output_per_1m_usd"] == 2.0 and "default" in prices
    monkeypatch.setenv("AGENT_MODEL_PRICES", "{not json")
    assert model_pricing.load_prices() == dict(model_pricing.BUILTIN_PRICES)


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _MeterSession:
    def __init__(self, results):
        self.results = list(results)
        self.sql = []

    def begin_nested(self):
        return _Nested()

    async def execute(self, stmt, _params=None):
        self.sql.append(str(stmt))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(all=lambda: r)


def test_metered_spend_prices_per_model(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL_PRICES", raising=False)
    rows = [("ollama/gemma3", 1_000_000, 1_000_000, 2_000_000),
            ("some/model", 1_000_000, 100_000, 1_100_000)]
    s = _MeterSession([rows])
    usd, est = run(control_plane.metered_spend_detail(s, TENANT, None))
    assert usd == pytest.approx(15.0 + 7.5) and est   # default entry => estimated
    assert "prompt_tokens" in s.sql[0]


def test_metered_spend_falls_back_to_total_tokens_when_columns_missing(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL_PRICES", raising=False)
    s = _MeterSession([RuntimeError("column prompt_tokens does not exist"), [("some/model", 0, 0, 1_000_000)]])
    usd, est = run(control_plane.metered_spend_detail(s, TENANT, None))
    assert usd == pytest.approx(75.0) and est
    assert run(control_plane._metered_spend(_MeterSession([RuntimeError("x"), RuntimeError("y")]), TENANT, None)) == 0.0


def test_usage_route_reports_cost_and_estimated_flag():
    from services.agent_orchestrator.routes import usage as usage_routes

    class R:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return SimpleNamespace(all=lambda: self.rows)

    results = [R([]), R([{"model": "ollama/gemma3", "calls": 2, "tokens": 100, "prompt_tokens": 60,
                          "completion_tokens": 40, "failures": 0, "avg_latency_ms": 5},
                         {"model": "x/unknown", "calls": 1, "tokens": 1_000_000, "prompt_tokens": 1_000_000,
                          "completion_tokens": 0, "failures": 0, "avg_latency_ms": 5}])]

    class S:
        async def execute(self, *_a, **_k):
            return results.pop(0)

    @asynccontextmanager
    async def scope():
        yield S()

    with patch.object(usage_routes, "session_scope", scope):
        out = run(usage_routes.llm_usage(days=7, ctx=ctx()))
    local, unknown = out["models"]
    assert local["cost_usd"] == 0 and local["estimated"] is False
    assert unknown["cost_usd"] == pytest.approx(15.0) and unknown["estimated"] is True
    assert out["estimated"] is True and out["cost_usd"] == pytest.approx(15.0)


# -- 3a. shared voice rate limit ---------------------------------------------

class _RateSession:
    def __init__(self, store):
        self.store = store

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "INSERT INTO agent_rate_limits" in sql:
            key = (params["t"], params["b"])
            self.store[key] = self.store.get(key, 0) + 1
            return SimpleNamespace(one=lambda: (self.store[key], 42))
        return SimpleNamespace(one=lambda: None)


def _db(store, broken=False):
    @asynccontextmanager
    async def scope(*_a):
        if broken:
            raise ConnectionError("db down")
        yield _RateSession(store)
    return scope


def test_shared_rate_limit_counts_in_db_across_calls(monkeypatch):
    monkeypatch.setenv("VOICE_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.setattr(voice_limits, "_rate_schema_ready", False)
    store = {}
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    with patch("services.common.db.session_scope", _db(store)):
        run(voice_limits.check_rate_limit_shared(t1))
        run(voice_limits.check_rate_limit_shared(t1))
        with pytest.raises(HTTPException) as e:
            run(voice_limits.check_rate_limit_shared(t1))
        assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "42"
        run(voice_limits.check_rate_limit_shared(t2))   # other tenant unaffected


def test_shared_rate_limit_falls_back_to_process_limiter_and_warns(monkeypatch, caplog):
    monkeypatch.setenv("VOICE_RATE_LIMIT_PER_MINUTE", "1")
    voice_limits._hits.clear()
    t = str(uuid.uuid4())
    with patch("services.common.db.session_scope", _db({}, broken=True)), caplog.at_level("WARNING"):
        run(voice_limits.check_rate_limit_shared(t))
        with pytest.raises(HTTPException) as e:
            run(voice_limits.check_rate_limit_shared(t))
    assert e.value.status_code == 429
    assert "in-process" in caplog.text


# -- 3b. non-WAV duration ceiling --------------------------------------------

def test_non_wav_size_ceiling_by_format(monkeypatch):
    monkeypatch.setenv("VOICE_MAX_AUDIO_SECONDS", "10")
    monkeypatch.setattr(voice_limits, "mutagen_duration_seconds", lambda d: None)
    ok_mp3 = b"ID3" + b"\0" * (10 * 320_000 // 8 - 3)
    voice_limits.check_audio(ok_mp3)
    with pytest.raises(HTTPException) as e:
        voice_limits.check_audio(ok_mp3 + b"\0")
    assert e.value.status_code == 413
    with pytest.raises(HTTPException):
        voice_limits.check_audio(b"OggS" + b"\0" * (10 * 510_000 // 8))
    voice_limits.check_audio(b"OggS" + b"\0" * 1000)
    # declared format is used when the bytes cannot be sniffed
    with pytest.raises(HTTPException):
        voice_limits.check_audio(b"\0" * (10 * 320_000 // 8 + 1), "mp3")
    voice_limits.check_audio(b"\0" * 5000, "mp3")
    # unknown format: only the byte cap applies
    voice_limits.check_audio(b"\0" * (10 * 320_000 // 8 + 1))


def test_non_wav_uses_real_duration_when_mutagen_available(monkeypatch):
    monkeypatch.setenv("VOICE_MAX_AUDIO_SECONDS", "10")
    monkeypatch.setattr(voice_limits, "mutagen_duration_seconds", lambda d: 30.0)
    with pytest.raises(HTTPException):
        voice_limits.check_audio(b"ID3" + b"\0" * 100)
    monkeypatch.setattr(voice_limits, "mutagen_duration_seconds", lambda d: 3.0)
    voice_limits.check_audio(b"ID3" + b"\0" * (10 * 320_000 // 8 + 100))   # real duration wins


def test_format_detection_helpers():
    assert voice_limits.sniff_format(b"fLaC....") == "flac"
    assert voice_limits.sniff_format(b"\x00\x00\x00\x18ftypM4A ") == "m4a"
    assert voice_limits.sniff_format(b"\x1a\x45\xdf\xa3....") == "webm"
    assert voice_limits.declared_format("audio/webm;codecs=opus", None) == "webm"
    assert voice_limits.declared_format(None, "clip.MP3") == "mp3"
    assert voice_limits.declared_format("application/octet-stream", None) is None


# -- 4. identity roles on service-to-service calls ---------------------------

def _hdrs(tenant, user):
    import httpx
    return httpx.Headers({"x-tenant-id": str(tenant), "x-user-id": str(user)})


def test_request_dependency_binds_verified_ctx():
    c = ctx(roles=["staff", "billing_admin"], perms=["crm.read"])
    req = SimpleNamespace(state=SimpleNamespace(auth=c), headers={}, method="GET", url=SimpleNamespace(path="/x"))

    async def go():
        internal_auth.identity_context.set(None)
        await identity.identity_context_dependency(req)
        return internal_auth.identity_context.get()

    bound = asyncio.run(go())
    assert bound["tenant_id"] == str(TENANT) and bound["user_id"] == str(USER)
    assert bound["roles"] == "billing_admin,staff" and bound["permissions"] == "crm.read"


def test_request_dependency_binds_nothing_without_auth():
    async def go():
        internal_auth.identity_context.set(None)
        req = SimpleNamespace(state=SimpleNamespace(), headers={}, method="GET", url=SimpleNamespace(path="/x"))
        with patch.object(identity, "get_auth_context", side_effect=HTTPException(status_code=401)):
            await identity.identity_context_dependency(req)
        return internal_auth.identity_context.get()

    assert asyncio.run(go()) is None


def test_job_identity_uses_stored_roles_and_fails_closed():
    async def go(cp):
        internal_auth.identity_context.set(None)
        identity.bind_job_identity(TENANT, cp)
        h = _hdrs(TENANT, USER)
        internal_auth._fill_roles_from_context(h)
        return h.get("x-roles"), h.get("x-permissions")

    assert asyncio.run(go({"actor_id": str(USER), "actor_roles": ["org_admin"],
                           "actor_permissions": ["a.b"]})) == ("org_admin", "a.b")
    assert asyncio.run(go({"actor_id": str(USER)})) == (None, None)       # older job: no roles stored
    assert asyncio.run(go({})) == (None, None)                            # no creator: nothing bound


def test_job_roles_not_given_to_calls_for_other_user_or_tenant():
    async def go():
        identity.bind_job_identity(TENANT, {"actor_id": str(USER), "actor_roles": ["org_admin"]})
        hs = [_hdrs(TENANT, uuid.uuid4()), _hdrs(uuid.uuid4(), USER), _hdrs(TENANT, TENANT)]
        for h in hs:   # last one: memory/skills fall back to user_id=tenant_id
            internal_auth._fill_roles_from_context(h)
        return [h.get("x-roles") for h in hs]

    assert asyncio.run(go()) == [None, None, None]


def test_job_creation_stores_creator_roles():
    from services.agent_orchestrator.routes import jobs as job_routes
    assert inspect.getsource(job_routes).count('"actor_roles": list(ctx.roles)') == 2
