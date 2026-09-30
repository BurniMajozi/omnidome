// Run: node --test lib/comm-helpers.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import {
  displayNameFromUser, resolveAuthorLabel, nextPollDelay, reconnectDelay, shouldStopReconnect, corpTargetText, looksLikeUuid,
} from "./comm-helpers.ts"

const U = "11111111-1111-4111-8111-111111111111"
test("displayNameFromUser", () => {
  assert.equal(displayNameFromUser({ email: "a.b@x.com", user_metadata: { full_name: " Ann B " } }), "Ann B")
  assert.equal(displayNameFromUser({ email: "a.b@x.com", user_metadata: { name: "Zed" } }), "Zed")
  assert.equal(displayNameFromUser({ email: "a.b@x.com" }), "a.b")
  assert.equal(displayNameFromUser(null), null)
})
test("resolveAuthorLabel never leaks uuid/unknown", () => {
  assert.equal(resolveAuthorLabel({ userId: U, currentUserId: U, currentUserName: "Me" }), "Me")
  assert.equal(resolveAuthorLabel({ userId: U, directory: { [U]: "Pat" } }), "Pat")
  assert.equal(resolveAuthorLabel({ userId: U }), "Team member")
  assert.equal(resolveAuthorLabel({ authorName: U }), "Team member")
  assert.equal(resolveAuthorLabel({ authorName: "Unknown" }), "Team member")
  assert.equal(resolveAuthorLabel({ authorName: "DomeBot" }), "DomeBot")
  assert.ok(looksLikeUuid(U))
})
test("nextPollDelay", () => {
  assert.equal(nextPollDelay(30000, false), 60000)
  assert.equal(nextPollDelay(200000, false), 300000)
  assert.equal(nextPollDelay(300000, false), 300000)
  assert.equal(nextPollDelay(120000, true), 30000)
})
test("reconnectDelay", () => {
  assert.equal(reconnectDelay(0, 0.5), 1000)
  assert.equal(reconnectDelay(3, 0.5), 8000)
  assert.ok(reconnectDelay(10, 0.99) <= 30000)
  assert.ok(reconnectDelay(0, 0) >= 800 && reconnectDelay(0, 0.999) <= 1200)
})
test("shouldStopReconnect", () => {
  assert.equal(shouldStopReconnect(4403, 0), true)
  assert.equal(shouldStopReconnect(1008, 0), true)
  assert.equal(shouldStopReconnect(1006, 5), false)
  assert.equal(shouldStopReconnect(1006, 6), true)
})
test("corpTargetText", () => {
  const f = (v) => `R ${v}`
  assert.equal(corpTargetText({ budget: 100, actual: 5 }, f), "R 100")
  assert.equal(corpTargetText({ budget: 100, actual: null }, f), null)
  assert.equal(corpTargetText({ budget: null, actual: 5 }, f), null)
  assert.equal(corpTargetText({ budget: 0, actual: 5 }, f), null)
  assert.equal(corpTargetText(null, f), null)
})
