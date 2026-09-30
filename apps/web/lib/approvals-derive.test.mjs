// Run: node --test lib/approvals-derive.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { describeApprovalFailure, shouldRefreshAfter, readApprovalItems, summarizeBatch } from "./approvals-derive.ts"

test("describeApprovalFailure distinguishes 403 / 409 / 5xx / offline and keeps the server text", () => {
  assert.match(describeApprovalFailure("approve", { status: 403, message: "Approval requires role: executive" }), /Not permitted \(HTTP 403\): Approval requires role: executive/)
  assert.match(describeApprovalFailure("approve", { status: 409, message: "Already approved" }), /Already decided or expired \(HTTP 409\): Already approved/)
  assert.match(describeApprovalFailure("approve", { status: 500, message: "tool crashed" }), /Orchestrator error \(HTTP 500\): tool crashed/)
  assert.match(describeApprovalFailure("dismiss", { status: 503, message: "" }), /Orchestrator error \(HTTP 503\)/)
  assert.match(describeApprovalFailure("approve", { status: null, message: "" }), /Could not reach the orchestrator/)
  assert.match(describeApprovalFailure("dismiss", { status: 403, message: "" }), /permission to dismiss/)
  assert.match(describeApprovalFailure("approve", { status: 422, message: "bad" }), /Could not approve \(HTTP 422\): bad/)
})

test("shouldRefreshAfter: stale items (404/409) trigger a re-read, others do not", () => {
  assert.equal(shouldRefreshAfter({ status: 409, message: "" }), true)
  assert.equal(shouldRefreshAfter({ status: 404, message: "" }), true)
  assert.equal(shouldRefreshAfter({ status: 500, message: "" }), false)
  assert.equal(shouldRefreshAfter({ status: null, message: "" }), false)
})

test("readApprovalItems: a non-array response is an error (null), [] is a real empty queue", () => {
  assert.deepEqual(readApprovalItems({ items: [], pending_count: 0 }), [])
  assert.deepEqual(readApprovalItems({ items: [{ id: "a" }] }), [{ id: "a" }])
  assert.equal(readApprovalItems(null), null)
  assert.equal(readApprovalItems({}), null)
  assert.equal(readApprovalItems({ items: "nope" }), null)
  assert.equal(readApprovalItems([]), null)
})

test("summarizeBatch reports per-item results and keeps failures identifiable", () => {
  const ok = (id) => ({ id, title: id, ok: true })
  const bad = (id, status, message) => ({ id, title: id, ok: false, failure: { status, message } })
  const all = summarizeBatch([ok("a"), ok("b"), ok("c")])
  assert.deepEqual([all.text, all.allOk, all.failed], ["3 approved", true, 0])
  const mixed = summarizeBatch([ok("a"), ok("b"), ok("c"), bad("d", 403, "no role")])
  assert.equal(mixed.approved, 3)
  assert.equal(mixed.failed, 1)
  assert.deepEqual(mixed.failedIds, ["d"])
  assert.match(mixed.text, /^3 approved, 1 failed: Not permitted \(HTTP 403\): no role/)
  const none = summarizeBatch([bad("x", 500, "boom"), bad("y", 500, "boom")])
  assert.match(none.text, /^0 approved, 2 failed: Orchestrator error \(HTTP 500\): boom/)
  assert.ok(!/other reason/.test(none.text))
  const two = summarizeBatch([bad("x", 500, "boom"), bad("y", 409, "done")])
  assert.match(two.text, /\(\+1 other reason\)/)
  assert.equal(summarizeBatch([]).text, "0 approved")
})
