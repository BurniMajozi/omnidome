// Run: node --test lib/request-cache.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { createTtlCache } from "./request-cache.ts"

test("in-flight calls with the same key share one loader run", async () => {
  const c = createTtlCache(30_000, () => 0)
  let n = 0
  const loader = async () => { n++; return { state: "ready", n } }
  const [a, b] = await Promise.all([c.get("k", loader), c.get("k", loader)])
  assert.equal(n, 1)
  assert.equal(a, b)
})

test("settled value is reused inside the TTL and refreshed after it", async () => {
  let t = 0
  const c = createTtlCache(30_000, () => t)
  let n = 0
  const loader = async () => ++n
  await c.get("k", loader)
  t = 29_999
  await c.get("k", loader)
  assert.equal(n, 1)
  t = 30_000
  await c.get("k", loader)
  assert.equal(n, 2)
})

test("failed results are not cached (shouldCache false / rejection)", async () => {
  const c = createTtlCache(30_000, () => 0)
  let n = 0
  const bad = async () => { n++; return { state: "error" } }
  const ok = (r) => r.state === "ready"
  await c.get("k", bad, ok)
  await c.get("k", bad, ok)
  assert.equal(n, 2)
  let m = 0
  const boom = async () => { m++; throw new Error("x") }
  await assert.rejects(c.get("r", boom))
  await assert.rejects(c.get("r", boom))
  assert.equal(m, 2)
})

test("different keys are independent; invalidate forces a reload", async () => {
  const c = createTtlCache(30_000, () => 0)
  let n = 0
  const loader = async () => ++n
  await c.get("a", loader)
  await c.get("b", loader)
  assert.equal(n, 2)
  c.invalidate("a")
  await c.get("a", loader)
  assert.equal(n, 3)
  await c.get("b", loader)
  assert.equal(n, 3)
  c.invalidate()
  assert.equal(c.size(), 0)
})
