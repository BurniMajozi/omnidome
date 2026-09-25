"""M4 conversation-compaction (SPEC-orchestrator-memory-hardening.md).

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import asyncio
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import compaction as c  # noqa: E402


def convo(n, size=400):
    """n alternating user/assistant messages of ~size chars, with ids."""
    return [{"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant", "content": f"{i} " + "x" * size}
            for i in range(n)]


class Summariser:
    def __init__(self, text="Goals: keep Thandi.\nDecisions: 15% off.", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    async def __call__(self, previous, messages):
        self.calls.append((previous, [m["id"] for m in messages]))
        if self.fail:
            raise RuntimeError("model down")
        return self.text


def run(history, state=None, summariser=None, threshold=2000, keep=500):
    return asyncio.run(c.compact(history, state, summariser or Summariser(), threshold, keep))


def test_short_conversation_is_sent_unchanged():
    history = convo(6)
    out, state, compacted = run(history, threshold=100_000)
    assert out == history and state is None and not compacted


def test_cut_keeps_recent_messages_and_starts_on_a_user_turn():
    history = convo(40)
    cut = c.cut_point(history, keep_tokens=500)
    assert 0 < cut < 40 and history[cut]["role"] == "user"
    assert c.estimate_tokens(history[cut:]) <= 500 + c.estimate_tokens([history[cut]])


def test_cut_always_keeps_at_least_the_last_exchange():
    history = convo(4, size=10_000)
    assert c.cut_point(history, keep_tokens=10) == 2


def test_long_conversation_is_summarised_once_and_bounded():
    history = convo(200)                                  # ~20k tokens
    s = Summariser()
    out, state, compacted = run(history, summariser=s)
    assert compacted and len(s.calls) == 1
    assert out[0]["content"].startswith("<conversation_summary>") and "15% off" in out[0]["content"]
    assert c.estimate_tokens(out) < 2000
    assert state["summary"] == s.text and state["summarised_through_message_id"] == s.calls[0][1][-1]
    assert state["compaction"]["times"] == 1


def test_stored_summary_is_reused_next_turn_without_a_new_call():
    history = convo(200)
    _, state, _ = run(history)
    history += [{"id": "m200", "role": "user", "content": "and now?"}]
    s = Summariser()
    out, new_state, compacted = run(history, state=state, summariser=s)
    assert s.calls == [] and new_state is None and not compacted
    assert out[-1]["content"] == "and now?" and "15% off" in out[0]["content"]


def test_summary_is_matched_by_fingerprint_when_messages_have_no_ids():
    history = [{k: v for k, v in m.items() if k != "id"} for m in convo(200)]
    _, state, _ = run(history)
    s = Summariser()
    run(history + [{"role": "user", "content": "next"}], state=state, summariser=s)
    assert s.calls == []


def test_summary_from_another_history_is_ignored():
    _, state, _ = run(convo(200))
    other = [{"role": m["role"], "content": "other " + m["content"]} for m in convo(8)]
    out, _, _ = run(other, state=state, threshold=100_000)
    assert out == other


def test_summariser_failure_drops_the_oldest_messages_instead():
    history = convo(200)
    out, state, compacted = run(history, summariser=Summariser(fail=True))
    assert compacted and state is None
    assert c.estimate_tokens(out) < 2000 and out[-1] == history[-1]


def test_nothing_to_compact_is_remembered_for_that_size():
    history = convo(2, size=20_000)                       # huge, but only one exchange
    s = Summariser()
    out, state, compacted = run(history, summariser=s)
    assert not compacted and s.calls == [] and state["compaction"]["nothing_at"] > 0
    out2, state2, _ = run(history, state=state, summariser=s)
    assert state2 is None                                 # not retried at the same size
