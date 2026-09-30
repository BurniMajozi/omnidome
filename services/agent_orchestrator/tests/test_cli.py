"""omnidome CLI (services/agent_orchestrator/cli.py) against a fake orchestrator API.

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import io
import json
import os
import sys

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator import cli  # noqa: E402

T = "00000000-0000-0000-0000-000000000001"
APPROVAL = {"id": "a6555693-e013-4cee-a976-b0ddfffd79ef", "reference": "APP-A6555693", "status": "pending",
            "agent_type": "crm", "tool_name": "crm_create_customer", "arguments": {"first_name": "TEST"},
            "created_at": "2026-09-30T05:00:00+00:00"}
WORKFLOW = {"id": "wf-1", "name": "Quote request → proposal", "status": "active",
            "trigger_event": "portal.quote.requested"}


class FakeApi:
    def __init__(self):
        self.calls = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, dict(req.url.params), body, req.headers))
        path = req.url.path
        if path == "/api/agents/invoke":
            return httpx.Response(200, json={"conversation_id": "conv-1", "agent_type": body["agent_type"],
                                             "message": f"echo: {body['message']}", "tool_calls": [
                {"name": "crm_create_customer", "result": {"requires_approval": True, "reference": "APP-A6555693"}}]})
        if path == "/api/approvals":
            return httpx.Response(200, json={"items": [APPROVAL], "pending_count": 1})
        if path.endswith("/approve"):
            return httpx.Response(200, json={**APPROVAL, "status": "approved", "execution_result": {"success": True}})
        if path.endswith("/reject"):
            return httpx.Response(200, json={**APPROVAL, "status": "rejected"})
        if path == "/api/workflows":
            return httpx.Response(200, json={"data": [WORKFLOW]})
        if path == "/api/workflows/wf-1/run":
            return httpx.Response(200, json={"run_id": "run-1", "status": "succeeded", "error": None,
                                             "steps": {"trigger": {"ok": True}, "lead": {"ok": True}}})
        if path == "/api/memory/housekeeping/dry-run":
            return httpx.Response(200, json={"dry_run": True, "duplicates_count": 2, "low_importance_count": 1,
                                             "entries_rolled_up": 5, "groups_rolled_up": 1,
                                             "rollups": [{"module": "sales", "scope_key": "lead:1", "entry_count": 5}]})
        if path == "/api/tools/invoke":
            if "delete" in body["tool_input"]["query"].lower():
                return httpx.Response(200, json={"tool_name": "analytics.query", "success": False, "result": None,
                                                 "error": "Only SELECT queries are permitted"})
            return httpx.Response(200, json={"tool_name": "analytics.query", "success": True, "error": None,
                                             "result": {"columns": ["stage", "n"], "rows": [{"stage": "won", "n": 3}]}})
        if path == "/api/events":
            return httpx.Response(202, json={"event_id": "e1", "type": body["type"], "status": "accepted"})
        return httpx.Response(404, json={"detail": f"no route {path}"})


def run(*argv, env=None, api=None, monkeypatch=None):
    api = api or FakeApi()
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), transport=httpx.MockTransport(api), out=out, err=err)
    return code, out.getvalue(), err.getvalue(), api


def test_requests_carry_the_tenant_and_user():
    code, _, _, api = run("--tenant", T, "workflows")
    headers = api.calls[0][4]
    assert code == 0 and headers["x-tenant-id"] == T and headers["x-user-id"] == T


def test_bearer_token_is_sent_when_configured(monkeypatch):
    monkeypatch.setenv("OMNIDOME_TOKEN", "tok123")
    _, _, _, api = run("workflows")
    assert api.calls[0][4]["authorization"] == "Bearer tok123"


def test_chat_one_shot_prints_reply_pending_approval_and_conversation():
    code, out, _, api = run("chat", "crm", "create", "a", "customer", "-c", "conv-0")
    method, path, _, body, _ = api.calls[0]
    assert (method, path) == ("POST", "/api/agents/invoke")
    assert body == {"agent_type": "crm", "message": "create a customer", "conversation_id": "conv-0"}
    assert "echo: create a customer" in out and "APP-A6555693" in out and "conversation conv-1" in out


def test_interactive_chat_keeps_the_conversation():
    api, out = FakeApi(), io.StringIO()
    lines = iter(["hello", "again", "exit"])
    args = cli.build_parser().parse_args(["chat", "retention"])
    client = cli.Client("http://x", T, T, transport=httpx.MockTransport(api))
    cli.cmd_chat(client, args, out, read_line=lambda _p: next(lines))
    bodies = [c[3] for c in api.calls]
    assert bodies[0] == {"agent_type": "retention", "message": "hello"}
    assert bodies[1]["conversation_id"] == "conv-1"


def test_approvals_default_to_pending_and_all_drops_the_filter():
    _, out, _, api = run("approvals")
    assert api.calls[0][2]["status"] == "pending" and "APP-A6555693" in out
    _, _, _, api = run("approvals", "--status", "all")
    assert "status" not in api.calls[0][2]


def test_approve_accepts_the_reference():
    code, out, _, api = run("approve", "APP-A6555693")
    assert code == 0 and api.calls[-1][1] == f"/api/approvals/{APPROVAL['id']}/approve"
    assert "approved" in out and "ran ok" in out


def test_reject_requires_a_reason():
    with pytest.raises(SystemExit):
        run("reject", "APP-A6555693")
    code, _, _, api = run("reject", APPROVAL["id"], "--reason", "not now")
    assert code == 0 and api.calls[-1][3] == {"reason": "not now"}


def test_run_resolves_a_workflow_by_name_and_passes_input():
    code, out, _, api = run("run", "quote request → proposal", "--input", '{"quote_total_zar": 899}')
    assert code == 0 and api.calls[-1][1] == "/api/workflows/wf-1/run"
    assert api.calls[-1][3] == {"input": {"quote_total_zar": 899}} and "succeeded" in out


def test_unknown_workflow_is_an_error():
    code, _, err, _ = run("run", "nope")
    assert code == 1 and "No workflow 'nope'" in err


def test_housekeeping_is_a_dry_run_unless_confirmed():
    code, out, _, api = run("memory", "housekeeping")
    assert code == 0 and api.calls[-1][1] == "/api/memory/housekeeping/dry-run"
    assert "dry run" in out and "5 in 1 group" in out
    with pytest.raises(SystemExit):
        run("memory", "housekeeping", "--run")


def test_sql_prints_a_table_and_surfaces_refusals():
    code, out, _, api = run("sql", "SELECT stage, count(*) n FROM deals GROUP BY 1")
    assert code == 0 and api.calls[-1][3]["tool_name"] == "analytics.query"
    assert "won" in out and "3" in out
    code, _, err, _ = run("sql", "DELETE FROM deals")
    assert code == 1 and "Only SELECT" in err


def test_json_flag_prints_the_raw_response():
    code, out, _, _ = run("--json", "event", "portal.cart.abandoned", "--payload", '{"test": true}')
    assert code == 0 and json.loads(out)["status"] == "accepted"


def test_api_errors_exit_1_with_the_detail():
    code, _, err, _ = run("runs", "x")
    assert code == 1 and "error:" in err
