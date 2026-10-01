// Run: node --test lib/compliance-state.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import {
  statusOf, loadableFromError, combineErrors, describeSection, extractErrorDetail,
  scoreView, meanAssessed, validatePrn, validateFiledDate, validatePeriod, isFiledStatus, zarOrNA,
} from "./compliance-state.ts"

const err = (status, detail) => ({ status, detail })

test("state mapping per failure kind", () => {
  assert.equal(loadableFromError(err(null)).state, "unreachable") // timeout / network
  assert.equal(loadableFromError(new TypeError("fetch failed")).state, "unreachable")
  for (const s of [502, 503, 504]) assert.equal(loadableFromError(err(s)).state, "unreachable")
  assert.equal(loadableFromError(err(403)).state, "denied")
  assert.equal(loadableFromError(err(401)).state, "denied")
  assert.equal(loadableFromError(err(500, "boom")).state, "error")
  assert.equal(loadableFromError(err(500, "boom")).message, "boom")
  assert.equal(loadableFromError(err(404)).state, "error")
})

test("combineErrors: ready when all succeed; worst wins otherwise", () => {
  assert.equal(combineErrors([null, undefined]).state, "ready")
  assert.equal(combineErrors([]).state, "ready")
  assert.equal(combineErrors([null, err(500)]).state, "error")
  assert.equal(combineErrors([err(500), err(403)]).state, "denied")
  assert.equal(combineErrors([err(403), err(null), err(500)]).state, "unreachable")
})

test("copy: empty is NOT confused with down; 403 names the roles", () => {
  assert.equal(describeSection({ state: "ready", data: null }), null)
  assert.equal(describeSection({ state: "loading" }), null)
  assert.equal(describeSection({ state: "unreachable", status: 503 }).title, "Service not running")
  assert.equal(describeSection({ state: "error", status: 500 }).title, "Error loading")
  assert.match(describeSection({ state: "denied", status: 403 }).detail, /requires compliance or admin role/)
})

test("statusOf", () => {
  assert.equal(statusOf(err(0)), null)
  assert.equal(statusOf(undefined), null)
  assert.equal(statusOf(err(422)), 422)
})

test("extractErrorDetail is verbatim for validation / SSRF messages", () => {
  assert.equal(extractErrorDetail('{"detail":"URL host is not allowed"}'), "URL host is not allowed")
  assert.equal(
    extractErrorDetail('{"detail":[{"msg":"bad url","loc":["x"]},{"msg":"too long"}]}'),
    "bad url; too long",
  )
  assert.equal(extractErrorDetail('{"error":"nope"}'), "nope")
  assert.equal(extractErrorDetail("plain text"), "plain text")
  assert.equal(extractErrorDetail(""), "")
  assert.equal(extractErrorDetail("x".repeat(1000)).length, 400)
})

test("scores: null is Not assessed, never 0 or 100", () => {
  assert.deepEqual(scoreView(null), { assessed: false, value: null, label: "Not assessed" })
  assert.equal(scoreView(undefined).assessed, false)
  assert.equal(scoreView(NaN).assessed, false)
  assert.equal(scoreView("100").assessed, false)
  assert.equal(scoreView(0).assessed, true)
  assert.equal(scoreView(72.4).label, "72%")
  assert.equal(scoreView(140).value, 100)
  assert.equal(meanAssessed([null, undefined]), null)
  assert.equal(meanAssessed([80, null, 60]), 70)
})

test("PRN validation: 16-19 alphanumerics", () => {
  assert.equal(validatePrn("").ok, false)
  assert.equal(validatePrn("ABC123").ok, false)
  assert.equal(validatePrn("A".repeat(15)).ok, false)
  assert.equal(validatePrn("A".repeat(20)).ok, false)
  assert.equal(validatePrn("1234-5678-9012-3456").ok, false) // symbols
  assert.deepEqual(validatePrn("a".repeat(16)), { ok: true, prn: "A".repeat(16) })
  assert.equal(validatePrn("A".repeat(19)).ok, true)
  assert.deepEqual(validatePrn(" 1234 5678 9012 3456 "), { ok: true, prn: "1234567890123456" }) // pasted spacing
})

test("filed date validation", () => {
  const now = new Date("2026-10-01T10:00:00Z")
  assert.equal(validateFiledDate("2026-09-07", now).ok, true)
  assert.equal(validateFiledDate("2026-10-01", now).ok, true)
  assert.equal(validateFiledDate("2026-10-05", now).ok, false)
  assert.equal(validateFiledDate("2026-02-30", now).ok, false)
  assert.equal(validateFiledDate("07/09/2026", now).ok, false)
  assert.equal(validateFiledDate("", now).ok, false)
})

test("period + filed status + ZAR", () => {
  assert.equal(validatePeriod("2026-09"), true)
  assert.equal(validatePeriod("2026-13"), false)
  assert.equal(isFiledStatus("PREPARED_NOT_FILED"), false)
  assert.equal(isFiledStatus("FILED"), true)
  assert.equal(zarOrNA(null), "Not available")
  assert.equal(zarOrNA(undefined), "Not available")
  assert.equal(zarOrNA(NaN), "Not available")
  assert.equal(zarOrNA(0), "R 0,00")
  assert.equal(zarOrNA(1234567.5), "R 1 234 567,50")
})
