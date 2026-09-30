import test from "node:test"
import assert from "node:assert/strict"

// Load the TS helpers through node's type stripping.
const { listLoadable } = await import("./service-state.ts")

test("200 with channels is ready", () => {
  const l = listLoadable(200, { data: [{ id: "1" }] })
  assert.equal(l.state, "ready")
  assert.equal(l.data.length, 1)
})

test("200 with zero channels is ready-and-empty (empty state, not an error)", () => {
  const l = listLoadable(200, { data: [] })
  assert.equal(l.state, "ready")
  assert.equal(l.data.length, 0)
})

test("502/503/504 and network failure are unreachable", () => {
  for (const s of [502, 503, 504, null, 0]) assert.equal(listLoadable(s, { data: [] }).state, "unreachable")
})

test("401/403 denied, 500 error, malformed 200 is error", () => {
  assert.equal(listLoadable(401, {}).state, "denied")
  assert.equal(listLoadable(500, {}).state, "error")
  assert.equal(listLoadable(200, {}).state, "error")
})
