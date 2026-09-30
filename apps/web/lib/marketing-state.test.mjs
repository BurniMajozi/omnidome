// Run: node --test lib/marketing-state.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import {
  nextPollDelay, clampRefreshMs, describeMutationError, parseEmailBatch, summarizeEmailBatch, createGetCache, MIN_POLL_MS,
} from "./marketing-state.ts"

test("nextPollDelay never polls faster than 5s and caps at 30s", () => {
  for (let i = 0; i < 40; i++) {
    const d = nextPollDelay(i)
    assert.ok(d >= MIN_POLL_MS && d <= 30_000)
  }
  assert.equal(nextPollDelay(0), 5000)
  assert.ok(nextPollDelay(6) > nextPollDelay(2))
})

test("clampRefreshMs enforces a 30s floor and treats 0 as off", () => {
  assert.equal(clampRefreshMs(0), 0)
  assert.equal(clampRefreshMs(undefined), 0)
  assert.equal(clampRefreshMs(1000), 30_000)
  assert.equal(clampRefreshMs(60_000), 60_000)
})

test("describeMutationError surfaces the server detail", () => {
  assert.match(describeMutationError(403, "writers only"), /Not permitted: writers only/)
  assert.match(describeMutationError(409, "already published"), /already published/)
  assert.match(describeMutationError(501), /Not available yet/)
  assert.match(describeMutationError(503, "provider not configured"), /provider not configured/)
  assert.match(describeMutationError(0), /Service not running/)
  assert.equal(describeMutationError(500, "boom"), "boom")
  assert.equal(describeMutationError(500), "Request failed (500)")
})

test("parseEmailBatch keeps unreported counts as null and detects terminal state", () => {
  const b = parseEmailBatch({ status: "Sending", total_queued: 10, total_sent: 4 })
  assert.equal(b.done, false)
  assert.equal(b.failed, null)
  assert.equal(b.suppressed, null)
  assert.equal(summarizeEmailBatch(b), "4 sent, 10 queued")
  const d = parseEmailBatch({ status: "partial", total_queued: 10, total_sent: 7, total_bounced: 2, total_suppressed: 1 })
  assert.equal(d.done, true)
  assert.equal(summarizeEmailBatch(d), "7 sent, 2 failed, 1 suppressed, 10 queued")
  assert.equal(parseEmailBatch(null).status, "unknown")
  assert.equal(summarizeEmailBatch(parseEmailBatch(null)), "status: unknown")
})

test("createGetCache de-duplicates in-flight reads, honours ttl and force", async () => {
  let t = 0
  let calls = 0
  const cache = createGetCache(1000, 100, (v) => v === "fail", () => t)
  const loader = async () => { calls++; return "ok" }
  const [a, b] = await Promise.all([cache.get("k", loader), cache.get("k", loader)])
  assert.equal(a, "ok"); assert.equal(b, "ok"); assert.equal(calls, 1)
  t = 500
  await cache.get("k", loader); assert.equal(calls, 1)
  t = 1500
  await cache.get("k", loader); assert.equal(calls, 2)
  await cache.get("k", loader, { force: true }); assert.equal(calls, 3)
  cache.clear(); assert.equal(cache.size(), 0)
})

test("createGetCache caches failures only briefly", async () => {
  let t = 0
  let calls = 0
  const cache = createGetCache(1000, 100, (v) => v === "fail", () => t)
  const loader = async () => { calls++; return "fail" }
  await cache.get("k", loader)
  t = 50
  await cache.get("k", loader); assert.equal(calls, 1)
  t = 200
  await cache.get("k", loader); assert.equal(calls, 2)
})
