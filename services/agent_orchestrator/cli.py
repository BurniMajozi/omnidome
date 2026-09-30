"""omnidome — command-line client for the OmniDome agent orchestrator.

Talks to the orchestrator API as one tenant, the same way the Agent Manager
and Workflows pages do. Nothing here bypasses the API: approvals, the SQL
tool's allowlist and tenant scoping all apply.

    omnidome status                         where am I pointed, is it up
    omnidome agents                         agents, their tools and what needs approval
    omnidome chat retention "..."           one question (-c CONV to continue)
    omnidome chat retention                 interactive chat (Ctrl-D / "exit" to leave)
    omnidome approvals [--status all]       the approval queue (pending by default)
    omnidome approve APP-1A2B3C4D [--notes ...]
    omnidome reject APP-1A2B3C4D --reason "..."
    omnidome workflows                      agent flows and their triggers
    omnidome run "Quote request → proposal" [--input '{"k": "v"}']
    omnidome runs "Quote request → proposal"
    omnidome memory search "Thandi discount" [--module retention]
    omnidome memory housekeeping            dry run; add --run --yes to apply
    omnidome skills                         OKF skills
    omnidome sql "SELECT stage, count(*) FROM deals GROUP BY 1"
    omnidome usage [--days 7]               LLM calls, tokens, loop-guard stops
    omnidome event portal.cart.abandoned --payload '{...}'

Configuration (environment):
    OMNIDOME_URL        orchestrator base URL      (default http://localhost:8021)
    OMNIDOME_TENANT_ID  tenant to act as            (default the local dev tenant)
    OMNIDOME_USER_ID    user id sent as X-User-Id   (default = tenant id, local convention)
    OMNIDOME_TOKEN      bearer token (JWT auth mode); sent as Authorization
Add --json to any command for the raw API response.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, TextIO

import httpx

DEV_TENANT = "00000000-0000-0000-0000-000000000001"
DEFAULT_URL = "http://localhost:8021"


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


class Client:
    def __init__(self, base_url: str, tenant_id: str, user_id: str, token: Optional[str] = None,
                 transport: Optional[httpx.BaseTransport] = None, timeout: float = 300.0):
        headers = {"X-Tenant-Id": tenant_id, "X-User-Id": user_id}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.base_url, self.tenant_id = base_url.rstrip("/"), tenant_id
        self.http = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)

    def request(self, method: str, path: str, **kw) -> Any:
        resp = self.http.request(method, path, **kw)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text[:500]
            raise ApiError(resp.status_code, detail)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **params) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, json=body if body is not None else {})


# ── Output helpers ──────────────────────────────────────────────────────────

def _table(out: TextIO, rows: List[List[Any]], headers: List[str]) -> None:
    if not rows:
        out.write("(none)\n")
        return
    cells = [[str(c if c is not None else "") for c in r] for r in rows]
    widths = [min(max(len(h), *(len(r[i]) for r in cells)), 60) for i, h in enumerate(headers)]
    line = lambda r: "  ".join(c[:w].ljust(w) for c, w in zip(r, widths)).rstrip()  # noqa: E731
    out.write(line(headers) + "\n" + line(["-" * w for w in widths]) + "\n")
    for r in cells:
        out.write(line(r) + "\n")


def _json_arg(raw: Optional[str], what: str) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--{what} is not valid JSON: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"--{what} must be a JSON object")
    return value


def _approval_id(c: Client, ref: str) -> str:
    """Accept the approval UUID or its reference (APP-XXXXXXXX)."""
    if not ref.upper().startswith("APP-"):
        return ref
    prefix = ref.split("-", 1)[1].lower()
    for a in (c.get("/api/approvals", limit=200) or {}).get("items", []):
        if str(a.get("id", "")).lower().startswith(prefix):
            return a["id"]
    raise ApiError(404, f"No approval with reference {ref}")


def _workflow(c: Client, key: str) -> dict:
    """Accept a workflow id or its exact (case-insensitive) name."""
    items = c.get("/api/workflows") or []
    items = items.get("data", items) if isinstance(items, dict) else items
    for w in items:
        if str(w.get("id")) == key or str(w.get("name", "")).lower() == key.lower():
            return w
    raise ApiError(404, f"No workflow '{key}'")


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_status(c: Client, a, out) -> Any:
    health = c.get("/health")
    out.write(f"orchestrator {c.base_url}  tenant {c.tenant_id}\n")
    return health


def cmd_agents(c: Client, a, out) -> Any:
    agents = c.get("/api/agents")
    rows = []
    for ag in agents:
        pol = ag.get("tool_policies") or []
        needs = [p["name"] for p in pol if p.get("requires_approval")]
        name = str(ag.get("description", "")).split(" — ")[0]
        rows.append([ag["agent_type"], name, len(ag.get("tools") or []), ", ".join(needs) or "-"])
    _table(out, rows, ["agent", "name", "tools", "needs approval"])
    return agents


def _print_reply(out, res: dict) -> None:
    out.write(res.get("message", "") + "\n")
    for tc in res.get("tool_calls") or []:
        r = tc.get("result") if isinstance(tc.get("result"), dict) else {}
        if r.get("requires_approval"):
            out.write(f"  ⏸ {tc.get('name')} waits for approval {r.get('reference')} — omnidome approve {r.get('reference')}\n")
        else:
            out.write(f"  · {tc.get('name')} {'ok' if r.get('success', True) else 'failed: ' + str(r.get('error'))}\n")


def cmd_chat(c: Client, a, out, read_line: Callable[[str], str] = input) -> Any:
    conv = a.conversation
    ask = lambda msg: c.post("/api/agents/invoke", {  # noqa: E731
        "agent_type": a.agent, "message": msg, **({"conversation_id": conv} if conv else {})})
    if a.message:
        res = ask(" ".join(a.message))
        if not a.json:
            _print_reply(out, res)
            out.write(f"(conversation {res.get('conversation_id')} — continue with -c)\n")
        return res
    out.write(f"Chatting with {a.agent} as tenant {c.tenant_id}. Ctrl-D or 'exit' to leave.\n")
    last = None
    while True:
        try:
            msg = read_line("you> ").strip()
        except EOFError:
            break
        if msg.lower() in ("exit", "quit"):
            break
        if not msg:
            continue
        last = ask(msg)
        conv = last.get("conversation_id") or conv
        _print_reply(out, last)
    if conv:
        out.write(f"(conversation {conv})\n")
    return None


def cmd_approvals(c: Client, a, out) -> Any:
    res = c.get("/api/approvals", status=None if a.status == "all" else a.status, agent=a.agent, limit=a.limit)
    rows = [[x.get("reference"), x.get("status"), x.get("agent_type"), x.get("tool_name"),
             json.dumps(x.get("arguments") or {}, ensure_ascii=False)[:60], (x.get("created_at") or "")[:16]]
            for x in res.get("items", [])]
    if not a.json:
        _table(out, rows, ["ref", "status", "agent", "tool", "arguments", "requested"])
    return res


def cmd_decide(c: Client, a, out) -> Any:
    approval_id = _approval_id(c, a.ref)
    if a.command == "approve":
        res = c.post(f"/api/approvals/{approval_id}/approve", {"notes": a.notes} if a.notes else {})
    else:
        res = c.post(f"/api/approvals/{approval_id}/reject", {"reason": a.reason})
    if not a.json:
        outcome = res.get("execution_result")
        out.write(f"{res.get('reference')} {res.get('status')}")
        if isinstance(outcome, dict):
            out.write(" — ran " + ("ok" if outcome.get("success", True) else f"but failed: {outcome.get('error')}"))
        out.write("\n")
    return res


def cmd_workflows(c: Client, a, out) -> Any:
    items = c.get("/api/workflows") or []
    items = items.get("data", items) if isinstance(items, dict) else items
    rows = [[w.get("name"), w.get("status"),
             w.get("trigger_event") or (w.get("schedule_cron") if w.get("schedule_enabled") else "manual"), w.get("id")]
            for w in items]
    if not a.json:
        _table(out, rows, ["workflow", "status", "trigger", "id"])
    return items


def cmd_run(c: Client, a, out) -> Any:
    wf = _workflow(c, a.workflow)
    res = c.post(f"/api/workflows/{wf['id']}/run", {"input": _json_arg(a.input, "input")})
    if not a.json:
        out.write(f"{wf['name']}: {res.get('status')}  run {res.get('run_id')}\n")
        for node, step in (res.get("steps") or {}).items():
            ok = not (isinstance(step, dict) and step.get("ok") is False)
            out.write(f"  {'✓' if ok else '✗'} {node}\n")
        if res.get("error"):
            out.write(f"  error: {res['error']}\n")
    return res


def cmd_runs(c: Client, a, out) -> Any:
    wf = _workflow(c, a.workflow)
    res = c.get(f"/api/workflows/{wf['id']}/runs")
    items = res.get("data", res) if isinstance(res, dict) else res
    rows = [[(r.get("started_at") or "")[:16], r.get("status"), r.get("trigger"), r.get("id"), (r.get("error") or "")[:50]]
            for r in items or []]
    if not a.json:
        _table(out, rows, ["started", "status", "trigger", "run", "error"])
    return res


def cmd_memory(c: Client, a, out) -> Any:
    if a.memory_command == "search":
        res = c.get("/api/memory/recall", q=" ".join(a.query), module=a.module, limit=a.limit)
        if not a.json:
            for s in res.get("summaries", []):
                out.write(f"[summary {s.get('module') or 'general'}] {s.get('title')}: {s.get('summary')}\n")
            for e in res.get("entries", []):
                when = (e.get("occurred_at") or e.get("created_at") or "")[:10]
                out.write(f"{when} [{e.get('module') or 'general'}] {e.get('title')}: "
                          f"{(e.get('summary') or e.get('content') or '')[:200]}\n")
            if not res.get("summaries") and not res.get("entries"):
                out.write("(nothing remembered for that)\n")
        return res
    # housekeeping
    if a.run and not a.yes:
        raise SystemExit("Housekeeping archives and rolls up memories; add --yes to apply (or leave out --run for a dry run).")
    res = c.post("/api/memory/housekeeping/run" if a.run else "/api/memory/housekeeping/dry-run")
    if not a.json:
        mode = "applied" if a.run else "dry run — nothing changed"
        out.write(f"Memory housekeeping ({mode}):\n"
                  f"  exact duplicates to archive:    {res.get('duplicates_count', 0)}\n"
                  f"  low-importance (old) to archive: {res.get('low_importance_count', 0)}\n"
                  f"  entries rolled into summaries:  {res.get('entries_rolled_up', 0)} "
                  f"in {res.get('groups_rolled_up', 0)} group(s)\n")
        for r in res.get("rollups") or []:
            out.write(f"    {r.get('module') or 'general'}/{r.get('scope_key')}: {r.get('entry_count')} entries\n")
    return res


def cmd_skills(c: Client, a, out) -> Any:
    res = c.get("/api/memory/skills")
    items = res.get("items", res) if isinstance(res, dict) else res
    rows = [[s.get("skill_name"), s.get("source_agent_type"), ", ".join(s.get("target_agent_types") or []) or "all",
             ", ".join(s.get("tools_required") or []) or "-", s.get("id")] for s in items or []]
    if not a.json:
        _table(out, rows, ["skill", "from", "for", "tools", "id"])
    return res


def cmd_sql(c: Client, a, out) -> Any:
    res = c.post("/api/tools/invoke", {"tool_name": "analytics.query", "tool_input": {"query": " ".join(a.query)}})
    if not res.get("success"):
        raise ApiError(400, res.get("error") or res.get("result"))
    data = res.get("result") or {}
    if not a.json:
        cols = data.get("columns") or []
        _table(out, [[row.get(col) for col in cols] for row in data.get("rows", [])], cols)
        if data.get("truncated"):
            out.write(f"({data.get('note')})\n")
    return res


def cmd_usage(c: Client, a, out) -> Any:
    res = c.get("/api/usage/llm", days=a.days)
    if not a.json:
        out.write(f"Agents, last {a.days} days:\n")
        _table(out, [[x["agent_type"], x["turns"], x["tool_calls"], x["tokens"], x.get("avg_duration_ms"),
                      x["stopped_step_limit"] + x["stopped_empty"] + x["stopped_truncated"], x["ai_unavailable"]]
                     for x in res.get("agents", [])],
               ["agent", "turns", "tool calls", "tokens", "avg ms", "guard stops", "ai down"])
        out.write("Models:\n")
        _table(out, [[m["model"], m["calls"], m["failures"], m["tokens"], m.get("avg_latency_ms")] for m in res.get("models", [])],
               ["model", "calls", "failed", "tokens", "avg ms"])
    return res


def cmd_event(c: Client, a, out) -> Any:
    body = {"type": a.type, "payload": _json_arg(a.payload, "payload")}
    if a.key:
        body["idempotency_key"] = a.key
    res = c.post("/api/events", body)
    if not a.json:
        out.write(f"{res.get('type')} {res.get('status')} (event {res.get('event_id')}) — flows with this trigger run shortly\n")
    return res


# ── Parser / entry point ────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omnidome", description="OmniDome agent orchestrator CLI",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    p.add_argument("--json", action="store_true", help="print the raw API response")
    p.add_argument("--url", default=os.getenv("OMNIDOME_URL", DEFAULT_URL))
    p.add_argument("--tenant", default=os.getenv("OMNIDOME_TENANT_ID", DEV_TENANT))
    p.add_argument("--user", default=os.getenv("OMNIDOME_USER_ID"))
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("agents").set_defaults(fn=cmd_agents)

    s = sub.add_parser("chat")
    s.add_argument("agent")
    s.add_argument("message", nargs="*")
    s.add_argument("-c", "--conversation")
    s.set_defaults(fn=cmd_chat)

    s = sub.add_parser("approvals")
    s.add_argument("--status", default="pending", choices=["pending", "approved", "rejected", "expired", "all"])
    s.add_argument("--agent")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_approvals)
    s = sub.add_parser("approve")
    s.add_argument("ref", help="APP-XXXXXXXX or approval id")
    s.add_argument("--notes")
    s.set_defaults(fn=cmd_decide)
    s = sub.add_parser("reject")
    s.add_argument("ref", help="APP-XXXXXXXX or approval id")
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_decide)

    sub.add_parser("workflows").set_defaults(fn=cmd_workflows)
    s = sub.add_parser("run")
    s.add_argument("workflow", help="workflow id or exact name")
    s.add_argument("--input", help="JSON object passed as the run input")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("runs")
    s.add_argument("workflow")
    s.set_defaults(fn=cmd_runs)

    m = sub.add_parser("memory").add_subparsers(dest="memory_command", required=True)
    s = m.add_parser("search")
    s.add_argument("query", nargs="+")
    s.add_argument("--module")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(fn=cmd_memory)
    s = m.add_parser("housekeeping")
    s.add_argument("--run", action="store_true", help="apply instead of a dry run")
    s.add_argument("--yes", action="store_true", help="confirm --run")
    s.set_defaults(fn=cmd_memory)

    sub.add_parser("skills").set_defaults(fn=cmd_skills)
    s = sub.add_parser("sql")
    s.add_argument("query", nargs="+")
    s.set_defaults(fn=cmd_sql)
    s = sub.add_parser("usage")
    s.add_argument("--days", type=int, default=7)
    s.set_defaults(fn=cmd_usage)
    s = sub.add_parser("event")
    s.add_argument("type")
    s.add_argument("--payload")
    s.add_argument("--key", help="idempotency key")
    s.set_defaults(fn=cmd_event)
    return p


def main(argv: Optional[List[str]] = None, transport: Optional[httpx.BaseTransport] = None,
         out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> int:
    a = build_parser().parse_args(argv)
    c = Client(a.url, a.tenant, a.user or a.tenant, os.getenv("OMNIDOME_TOKEN"), transport=transport)
    try:
        result = a.fn(c, a, out)
    except ApiError as exc:
        err.write(f"error: {exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)} (HTTP {exc.status})\n")
        return 1
    except httpx.HTTPError as exc:
        err.write(f"error: cannot reach {a.url}: {exc}\n")
        return 1
    if a.json and result is not None:
        out.write(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n")
    elif a.command == "status" and result is not None:
        out.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
