// Run: node --test lib/safe-path.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import { hasUnsafePath, isUnsafeSegment, joinSafePath } from "./safe-path.ts"

const BS = String.fromCharCode(92)
const W = "/svc/marketing/social/webhooks/"

const BAD_PATHS = [
  W + "..%2F..%2Fhealth",
  W + "..%2f..%2fhealth",
  W + "%2e%2e/health",
  W + "%2E%2E%2Fhealth",
  W + "%252e%252e%252fhealth", // double-encoded
  W + "%25252e%25252e/x", // triple-encoded
  W + "a%5cb",
  W + "a%5Cb",
  W + "a" + BS + "b",
  W + "a%00b",
  "/svc/marketing/social//health",
  W + "../health",
  W + "․․/health", // one-dot leaders
  W + "．．/health", // fullwidth dots
  W + "‥/health", // two-dot leader
  W + "%EF%BC%8E%EF%BC%8E/x", // encoded fullwidth dots
]
const GOOD_PATHS = [
  W + "zernio",
  W + "zernio/inbound",
  "/svc/marketing/email/webhook",
  "/api/workflows/hook/abc-123_X",
  "/svc/admin/users/a%40b.com",
  "/svc/crm/customers/123e4567-e89b-12d3-a456-426614174000",
]

test("hasUnsafePath rejects traversal / encoded separators", () => {
  for (const p of BAD_PATHS) assert.equal(hasUnsafePath(p), true, p)
})
test("hasUnsafePath allows normal paths", () => {
  for (const p of GOOD_PATHS) assert.equal(hasUnsafePath(p), false, p)
})

test("isUnsafeSegment", () => {
  const bad = ["", ".", "..", "a/b", "a" + BS + "b", "../x", "..%2Fx", "%2e%2e", "%2E%2E", "%252e%252e", "%2f", "%2F", "%5c", "%5C", "a\u0000b", "․․", "．．", "‥", "a\nb"]
  for (const s of bad) assert.equal(isUnsafeSegment(s), true, JSON.stringify(s))
  for (const s of ["customers", "a-b_c", "123", "a.b", "report.pdf", "a@b.com"]) {
    assert.equal(isUnsafeSegment(s), false, s)
  }
})

test("joinSafePath", () => {
  assert.equal(joinSafePath(["customers", "123", "notes"]), "customers/123/notes")
  assert.equal(joinSafePath(["a", ".."]), null)
  assert.equal(joinSafePath(["a", "..%2F..%2Fhealth"]), null)
  assert.equal(joinSafePath(["a", "../health"]), null)
  assert.equal(joinSafePath(["a", "b" + BS + "c"]), null)
  assert.equal(joinSafePath(undefined), null)
})

// Public-route patterns copied from proxy.ts: encoded slashes must not match even before the guard.
test("public webhook patterns are tight", () => {
  const re = /^\/svc\/marketing\/social\/webhooks\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)?$/
  assert.ok(re.test(W + "zernio"))
  assert.ok(re.test(W + "zernio/inbound"))
  assert.ok(!re.test(W + "..%2F..%2Fhealth"))
  assert.ok(!re.test(W + "../health"))
  assert.ok(!re.test(W + "a/b/c"))
})
