// Run: node --test lib/format.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { fmtZar, fmtZarCompact } from "./format.ts"

test("fmtZar: full value with space thousands, whole rand", () => {
  assert.equal(fmtZar(135382), "R 135 382")
  assert.equal(fmtZar(0), "R 0")
  assert.equal(fmtZar(999), "R 999")
  assert.equal(fmtZar(1000), "R 1 000")
  assert.equal(fmtZar(1234567.6), "R 1 234 568")
  assert.equal(fmtZar(-2500), "-R 2 500")
  assert.equal(fmtZar(-0.2), "R 0")
  assert.equal(fmtZar(Number.NaN), "—")
})

test("fmtZarCompact: never R1000k, never 5496 -> R5k", () => {
  assert.equal(fmtZarCompact(5496), "R5,5k")
  assert.equal(fmtZarCompact(5000), "R5k")
  assert.equal(fmtZarCompact(950), "R950")
  assert.equal(fmtZarCompact(1_234_567), "R1,2M")
  assert.equal(fmtZarCompact(999_960), "R1M")
  assert.equal(fmtZarCompact(999_400), "R999,4k")
  assert.equal(fmtZarCompact(1_000_000), "R1M")
  assert.equal(fmtZarCompact(-5496), "-R5,5k")
  assert.ok(!/1000k/i.test(fmtZarCompact(999_999)))
  assert.equal(fmtZarCompact(Number.POSITIVE_INFINITY), "—")
})
