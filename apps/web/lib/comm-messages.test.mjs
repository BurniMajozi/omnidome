import test from "node:test"
import assert from "node:assert/strict"
import { upsertMessage, reconcileSend, mergeNewestPage, prependOlder, parseHistoryPage, sendFailure, decisionError, canManageChannel, APPROVAL_STATES } from "./comm-messages.ts"

const row = (id, key = id, time = "2026-10-02T12:00:00Z") => ({ id, client_msg_id: key, user_id: "u", content: "same", created_at: time })

test("POST and socket converge in either order, including repeated echoes", () => {
  for (const responses of [[row("server", "key"), row("server", "key")], [row("server", "key"), row("server", "key")].reverse()]) {
    let messages = [{ ...row("local", "key"), pending: true }]
    for (const response of responses) messages = upsertMessage(messages, response)
    assert.equal(messages.length, 1)
    assert.equal(messages[0].id, "server")
    assert.equal(messages[0].pending, false)
  }
  const repaired = upsertMessage([{ ...row("local", "key"), failed: true }, row("server", "key")], row("server", "key"))
  assert.equal(repaired.length, 1)
  assert.equal(repaired[0].failed, false)
})

test("identical content with distinct keys stays separate", () => {
  const first = { ...row("local", "one"), pending: true }
  assert.equal(upsertMessage([first], row("server", "two")).length, 2)
  assert.equal(upsertMessage([first], { ...row("server", "one"), user_id: "other" }).length, 2)
})

test("unkeyed socket echoes reconcile by POST id, even with two identical outstanding sends", () => {
  const first = { ...row("local1", "key1"), pending: true }
  const second = { ...row("local2", "key2"), pending: true }
  const echo1 = row("server1", null)
  const echo2 = row("server2", null)
  const otherDevice = row("server3", null)
  let messages = reconcileSend([first, second], echo2, "key2", [])
  assert.equal(messages.length, 2)
  assert.equal(messages[0].pending, true)
  messages = reconcileSend(messages, echo1, "key1", [echo1, echo2, otherDevice])
  assert.deepEqual(messages.map((m) => m.id), ["server1", "server2", "server3"])
  assert.equal(messages[0].client_msg_id, "key1")
  assert.equal(messages[1].client_msg_id, "key2")
  assert.equal(messages[0].pending, false)
})

test("cursor history displays oldest first, keeps live arrivals and confirms pending sends", () => {
  const oldest = row("a", "a", "2026-10-02T10:00:00Z")
  const newest = row("b", "b", "2026-10-02T11:00:00Z")
  const live = row("c", "c", "2026-10-02T12:00:00Z")
  for (const items of [[newest, oldest], [oldest, newest]]) {
    const page = parseHistoryPage({ data: items, next_before: "a", has_more: true })
    assert.deepEqual(page.items.map((m) => m.id), ["a", "b"])
    assert.equal(page.next_before, "a")
    const merged = mergeNewestPage([{ ...newest, id: "local", failed: true }, live], page.items)
    assert.deepEqual(merged.map((m) => m.id), ["a", "b", "c"])
    assert.equal(merged[1].failed, false)
    assert.deepEqual(prependOlder(merged, [oldest, oldest]).map((m) => m.id), ["a", "b", "c"])
  }
  assert.equal(parseHistoryPage({ data: [], has_more: true }).has_more, false)
})

test("permission and conflict errors are distinct; validation retains server detail", () => {
  assert.equal(sendFailure(401).retryable, false)
  assert.match(sendFailure(401).text, /sign in/)
  assert.match(sendFailure(403, "Only the owner").text, /Only the owner/)
  assert.equal(sendFailure(422, "Parent message invalid").text, "Parent message invalid")
  assert.equal(sendFailure(null).retryable, true)
  assert.equal(sendFailure(503).retryable, true)
  assert.equal(sendFailure(429).retryable, true)
  assert.match(sendFailure(429).text, /short wait/)
  assert.equal(decisionError(409), "Already decided")
  assert.match(decisionError(403, "Cannot decide your own request"), /own request/)
  assert.ok(APPROVAL_STATES.includes("cancelled"))
  assert.equal(canManageChannel({ created_by: "u" }, "u", null), true)
  assert.equal(canManageChannel({ created_by: "u" }, "other", ["manager"]), false)
  assert.equal(canManageChannel({ created_by: "u" }, "other", ["org_admin"]), true)
})
