// Run: node --test lib/service-state.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import { classifyHttpStatus, loadableFromStatus, describeLoadable, tileLabel, sumMoney } from "./service-state.ts"

test("classifyHttpStatus maps status codes to states", () => {
  assert.equal(classifyHttpStatus(200), "ok")
  assert.equal(classifyHttpStatus(204), "ok")
  assert.equal(classifyHttpStatus(null), "unreachable")
  assert.equal(classifyHttpStatus(0), "unreachable")
  assert.equal(classifyHttpStatus(502), "unreachable")
  assert.equal(classifyHttpStatus(503), "unreachable")
  assert.equal(classifyHttpStatus(504), "unreachable")
  assert.equal(classifyHttpStatus(401), "denied")
  assert.equal(classifyHttpStatus(403), "denied")
  assert.equal(classifyHttpStatus(500), "error")
  assert.equal(classifyHttpStatus(404), "error")
  assert.equal(classifyHttpStatus(422), "error")
})

test("loadableFromStatus keeps real empty data as ready (zeros are real)", () => {
  const l = loadableFromStatus(200, [])
  assert.equal(l.state, "ready")
  assert.deepEqual(l.data, [])
  assert.equal(loadableFromStatus(200, 0).state, "ready")
})

test("loadableFromStatus never yields ready for failures", () => {
  assert.equal(loadableFromStatus(502, undefined).state, "unreachable")
  assert.equal(loadableFromStatus(null, undefined).state, "unreachable")
  assert.equal(loadableFromStatus(500, undefined, "boom").state, "error")
  assert.equal(loadableFromStatus(403, undefined).state, "denied")
  assert.equal(loadableFromStatus(200, undefined).state, "error")
})

test("copy and tile labels are honest", () => {
  const un = loadableFromStatus(503, undefined)
  assert.equal(describeLoadable(un, "Compliance").title, "Service not running")
  assert.match(describeLoadable(un, "Compliance").detail, /503/)
  assert.equal(tileLabel(un), "Service not running")
  assert.equal(tileLabel(loadableFromStatus(500, undefined)), "Error loading")
  assert.equal(tileLabel({ state: "ready", data: 1 }), null)
  assert.equal(describeLoadable({ state: "loading" }), null)
})

test("sumMoney handles decimal strings and ignores junk", () => {
  assert.equal(sumMoney(["10.50", 2, null, undefined, "x"]), 12.5)
  assert.equal(sumMoney([]), 0)
})
