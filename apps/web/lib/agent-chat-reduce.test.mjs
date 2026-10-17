// Run: node --test lib/agent-chat-reduce.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { reduceAgentEvent, conversationToMessages } from "./agent-chat-reduce.ts"
import { artifactItemsFromToolCalls } from "./artifact-links.ts"
import { parseMessage, looksLikeDocument } from "./chat-artifacts.ts"

const blank = () => ({ id: "a1", role: "assistant", content: "", isStreaming: true, toolCalls: [] })
const ev = (type, data = {}) => ({ type, run_id: "r1", timestamp: "", data })

test("tool events from the orchestrator carry id and name, so artifact link cards resolve", () => {
  let m = blank()
  m = reduceAgentEvent(m, ev("TOOL_CALL_START", { tool_call_id: "tc-0", tool_name: "artifacts.find", name: "artifacts.find", arguments: {} }), () => undefined)
  m = reduceAgentEvent(m, ev("TOOL_CALL_RESULT", { tool_call_id: "tc-0", tool_name: "artifacts.find", result: { data: { items: [{ title: "Sales deck", deep_link: "/dashboard?section=analytics", kind: "deck" }] } } }), () => undefined)
  assert.equal(m.toolCalls.length, 1)
  assert.equal(m.toolCalls[0].toolName, "artifacts.find")
  assert.equal(artifactItemsFromToolCalls(m.toolCalls).length, 1)
})

test("older events with only `name` (replayed from before the fix) still work", () => {
  let m = reduceAgentEvent(blank(), ev("TOOL_CALL_START", { name: "crm_get_customer" }), () => undefined)
  m = reduceAgentEvent(m, ev("TOOL_CALL_RESULT", { name: "crm_get_customer", result: "ok" }), () => undefined)
  assert.equal(m.toolCalls[0].toolName, "crm_get_customer")
  assert.equal(m.toolCalls.length, 2) // result without a matching id is kept rather than dropped
})

test("custom step events build the activity panel, and finishing closes it", () => {
  let m = reduceAgentEvent(blank(), ev("CUSTOM", { name: "omnidome.step_started", value: { id: "s1", kind: "data", title: "Querying", status: "running" } }), () => undefined)
  assert.ok(m.activity)
  m = reduceAgentEvent(m, ev("TEXT_MESSAGE_CONTENT", { delta: "Hello " }), () => undefined)
  m = reduceAgentEvent(m, ev("TEXT_MESSAGE_CONTENT", { delta: "world" }), () => undefined)
  m = reduceAgentEvent(m, ev("RUN_FINISHED"), () => undefined)
  assert.equal(m.content, "Hello world")
  assert.equal(m.isStreaming, false)
})

test("persisted tool rows fold into the following assistant reply", () => {
  const data = { id: "c1", messages: [
    { role: "user", content: "find the deck" },
    { role: "tool", content: "x", tool_calls: [{ name: "artifacts.find", arguments: {} }], tool_results: [{ data: { items: [] } }] },
    { role: "assistant", content: "Here it is" },
  ] }
  const out = conversationToMessages(data, "c1")
  assert.equal(out.length, 2)
  assert.equal(out[1].toolCalls[0].toolName, "artifacts.find")
})

test("fenced blocks are artifacts; an unfenced long report still gets a canvas document", () => {
  const fenced = parseMessage("m1", "Here:\n```markdown:report.md\n# Report\nrows\n```\nDone")
  assert.equal(fenced.artifacts.length, 1)
  const table = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n" + "text ".repeat(100)
  assert.ok(looksLikeDocument(table))
  const implicit = parseMessage("m2", table)
  assert.equal(implicit.artifacts.length, 1)
  assert.equal(parseMessage("m3", table, false).artifacts.length, 0) // not while streaming
  assert.equal(parseMessage("m4", "Sure, the total is 4.").artifacts.length, 0)
})
