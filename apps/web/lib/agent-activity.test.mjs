// Run: node --test lib/agent-activity.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import {
  emptyActivity, reduceActivity, finishActivity, summaryText, liveStatusText, humanizeTool, formatDuration,
  buildAnswerPayload, allAnswered, citationsFromSteps, answerErrorMessage, decisionErrorMessage, formatCountdown, riskTone,
} from "./agent-activity.ts"

const step = (o) => ({ id: "s1", kind: "data", title: "Querying governed data", status: "running", ...o })

test("step upsert keeps arrival order and replaces by id", () => {
  let a = emptyActivity(0)
  a = reduceActivity(a, "omnidome.step", step({ id: "a" }))
  a = reduceActivity(a, "omnidome.step", step({ id: "b", title: "Two" }))
  a = reduceActivity(a, "omnidome.step", step({ id: "a", status: "done", duration_ms: 1200, result_summary: "12 rows" }))
  assert.deepEqual(a.steps.map((s) => s.id), ["a", "b"])
  assert.equal(a.steps[0].status, "done")
  assert.equal(a.steps[0].result_summary, "12 rows")
  assert.equal(a.hasCustom, true)
})

test("status line is replaced, not appended", () => {
  let a = emptyActivity(0)
  a = reduceActivity(a, "omnidome.status", { text: "one", elapsed_ms: 3000 })
  a = reduceActivity(a, "omnidome.status", { text: "two", elapsed_ms: 6000 })
  assert.equal(a.status, "two")
  assert.equal(a.elapsed, 6000)
  assert.equal(liveStatusText(a), "two")
})

test("legacy runs (no custom events) fall back to Working…", () => {
  const a = emptyActivity(1000)
  assert.equal(liveStatusText(a, 6000), "Working… 5s")
  assert.equal(a.hasCustom, false)
})

test("summary row text", () => {
  let a = emptyActivity(0)
  for (let i = 0; i < 6; i++) a = reduceActivity(a, "omnidome.step", step({ id: `s${i}`, status: "done" }))
  assert.equal(summaryText(finishActivity(a, 14000)), "Worked for 14s · 6 steps")
  assert.equal(summaryText(finishActivity(a, 14000, true)), "Stopped after 14s · 6 steps")
  const one = reduceActivity(emptyActivity(0), "omnidome.step", step({ status: "done" }))
  assert.equal(summaryText(finishActivity(one, 65000)), "Worked for 1m 5s · 1 step")
  assert.equal(summaryText(finishActivity(emptyActivity(0), 2000)), "Worked for 2s")
})

test("finishActivity is idempotent but can flag cancel", () => {
  const a = finishActivity(emptyActivity(0), 5000)
  assert.equal(finishActivity(a, 99999).elapsed, 5000)
  assert.equal(finishActivity(a, 99999, true).cancelled, true)
})

test("tool name humaniser", () => {
  assert.equal(humanizeTool("data.query"), "Queried data")
  assert.equal(humanizeTool("knowledge.search"), "Searched memory")
  assert.equal(humanizeTool("support_create_ticket"), "Support Create Ticket")
  assert.equal(humanizeTool(""), "Ran a tool")
  assert.equal(humanizeTool(undefined), "Ran a tool")
  assert.equal(humanizeTool('{"x":1}'), "X 1")
  assert.equal(formatDuration(400), "1s")
})

test("answer payload follows the contract", () => {
  const q = {
    run_id: "r", question_id: "q1", expires_at: "",
    questions: [
      { header: "Scope", question: "Which period?", multi_select: false, options: [{ label: "Week", description: "" }, { label: "Month", description: "" }] },
      { header: "Cols", question: "Which columns?", multi_select: true, options: [{ label: "A", description: "" }, { label: "B", description: "" }] },
    ],
  }
  assert.equal(allAnswered(q, [{ selected: ["Week"], other: "" }, { selected: [], other: "" }]), false)
  const drafts = [{ selected: ["Week", "Month", "Bogus"], other: "  " }, { selected: ["A", "A", "B", "Nope"], other: " custom " }]
  assert.equal(allAnswered(q, drafts), true)
  assert.deepEqual(buildAnswerPayload(q, drafts), {
    question_id: "q1",
    answers: [
      { question: "Which period?", selected: ["Week"], other: null },
      { question: "Which columns?", selected: ["A", "B"], other: "custom" },
    ],
  })
  assert.equal(buildAnswerPayload(q, [{ selected: [], other: "x".repeat(900) }, { selected: [], other: "y" }]).answers[0].other.length, 500)
})

test("unknown and malformed events are tolerated", () => {
  const a = emptyActivity(0)
  assert.equal(reduceActivity(a, "omnidome.thinking", { text: "x" }), a)
  assert.equal(reduceActivity(a, "other.thing", { x: 1 }), a)
  assert.equal(reduceActivity(a, undefined, null), a)
  assert.equal(reduceActivity(a, "omnidome.step", { id: "x" }), a)
  assert.equal(reduceActivity(a, "omnidome.step", step({ status: "weird" })), a)
  assert.equal(reduceActivity(a, "omnidome.question", { question_id: "q", questions: "no" }), a)
  assert.equal(reduceActivity(a, "omnidome.approval", {}), a)
  assert.equal(reduceActivity(a, "omnidome.step", [1]), a)
})

test("question lifecycle and approvals upsert", () => {
  let a = emptyActivity(0)
  const ev = { run_id: "r", question_id: "q", expires_at: "2030-01-01T00:00:00Z", questions: [{ header: "H", question: "Q?", options: [{ label: "L", description: "d" }] }] }
  a = reduceActivity(a, "omnidome.question", ev)
  a = reduceActivity(a, "omnidome.question", ev)
  assert.equal(a.questions.length, 1)
  a = reduceActivity(a, "omnidome.question_resolved", { question_id: "q", status: "expired" })
  assert.equal(a.questions[0].status, "expired")
  a = reduceActivity(a, "omnidome.approval", { approval_id: "p", summary: "s", status: "pending", requested_by_me: true })
  a = reduceActivity(a, "omnidome.approval", { approval_id: "p", summary: "s2", status: "pending" })
  assert.equal(a.approvals.length, 1)
  assert.equal(a.approvals[0].summary, "s2")
})

test("citations only keep safe in-app links", () => {
  const ok = "/dashboard?section=analytics&sub=presentations&deck=11111111-2222-3333-4444-555555555555"
  const steps = [
    { id: "k", kind: "knowledge", title: "t", status: "done", meta: { cards: [{ title: "Deck", deep_link: ok }, { title: "Bad", deep_link: "javascript:1" }, { title: "Deck", deep_link: ok }] } },
    { id: "d", kind: "data", title: "t", status: "done", meta: { cards: [{ title: "Ignored", deep_link: ok }] } },
  ]
  const c = citationsFromSteps(steps)
  assert.equal(c.length, 1)
  assert.equal(c[0].title, "Deck")
})

test("error messages and helpers", () => {
  assert.match(answerErrorMessage(409), /already answered/)
  assert.match(answerErrorMessage(404), /expired/)
  assert.equal(decisionErrorMessage(403, "Manager or admin role required"), "Manager or admin role required")
  assert.match(decisionErrorMessage(403, ""), /permission/)
  assert.equal(formatCountdown(0), "expired")
  assert.equal(formatCountdown(90), "1m 30s left")
  assert.equal(riskTone("review", 4.2), "high")
  assert.equal(riskTone("review"), "review")
})
