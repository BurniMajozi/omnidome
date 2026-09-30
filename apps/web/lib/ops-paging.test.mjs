// Run: node --test lib/ops-paging.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import { isPartial, countText, totalText, partialNote, planPages, networkTile } from "./ops-derive.ts"

const meta = (o) => ({ loaded: 100, total: 100, totalKnown: true, truncated: false, failedPages: [], ...o })

test("planPages: server total decides the walk; the cap reports truncation", () => {
  assert.deepEqual(planPages(250, 100, 10), { pages: 3, truncated: false })
  assert.deepEqual(planPages(0, 100, 10), { pages: 1, truncated: false })
  assert.deepEqual(planPages(1000, 100, 10), { pages: 10, truncated: false })
  assert.deepEqual(planPages(1001, 100, 10), { pages: 10, truncated: true })
  assert.deepEqual(planPages(650, 100, 5), { pages: 5, truncated: true }) // escalations cap: 5 pages / 500 rows
  assert.deepEqual(planPages(null, 100, 5), { pages: 5, truncated: false })
})

test("complete load: counts are exact, no note", () => {
  const m = meta({ loaded: 42, total: 42 })
  assert.equal(isPartial(m), false)
  assert.equal(countText(7, m), "7")
  assert.equal(totalText(m), "42")
  assert.equal(partialNote(m), null)
})

test("truncated load: counts become lower bounds, total stays the server total", () => {
  const m = meta({ loaded: 500, total: 1234, truncated: true })
  assert.equal(isPartial(m), true)
  assert.equal(countText(120, m), "120+")
  assert.equal(totalText(m), "1 234")
  assert.match(partialNote(m), /first 500 of 1.234/)
})

test("failed page: marked partial even when the server total was reached on paper", () => {
  const m = meta({ loaded: 300, total: 300, failedPages: [3] })
  assert.equal(isPartial(m), true)
  assert.equal(countText(10, m), "10+")
  assert.match(partialNote(m), /a page failed/)
  assert.match(partialNote(meta({ failedPages: [2, 3] })), /2 pages failed/)
})

test("unknown server total: N+ only when we had to stop early", () => {
  assert.equal(totalText(meta({ loaded: 500, total: 500, totalKnown: false, truncated: true })), "500+")
  assert.equal(totalText(meta({ loaded: 40, total: 40, totalKnown: false })), "40")
  assert.match(partialNote(meta({ loaded: 500, total: 500, totalKnown: false, truncated: true })), /more exist/)
})

test("networkTile: Active and Registered are consistent when only part is loaded", () => {
  const rows = [{ status: "active", device_type: "olt" }, { status: "active", device_type: "olt" }, { status: "offline", device_type: "onu" }]
  const full = networkTile(rows, meta({ loaded: 3, total: 3 }))
  assert.deepEqual(full, { active: "2", registered: "3", activeOfRegistered: "2 of 3", note: null })
  const part = networkTile(rows, meta({ loaded: 3, total: 4200, truncated: true }))
  assert.equal(part.active, "2+")
  assert.equal(part.registered, "4 200")
  assert.equal(part.activeOfRegistered, "2+ of 4 200")
  assert.ok(part.note)
})
