// Run: node --test lib/overview-derive.test.mjs
import test from "node:test"
import assert from "node:assert/strict"
import {
  dealTotals, bucketWonDeals, sumBuckets, dealsClosingThisMonth, stalledOpenDeals, topDeals,
  buildInsights, buildBriefing, toActivityItems, initials, customerTotalOf, countStatus, listOf, mapLoadable, fmtZarCompact,
} from "./overview-derive.ts"

const NOW = new Date("2026-09-30T12:00:00Z")
const deals = [
  { name: "A", value_zar: "1000.50", status: "WON", closed_at: "2026-09-29T08:00:00Z", stage_name: "Closed Won" },
  { name: "B", value_zar: 500, status: "OPEN", close_date: "2026-09-20", updated_at: "2026-08-01T00:00:00Z", stage_name: "Proposal" },
  { name: "C", value_zar: 250, status: "LOST" },
  { name: "D", value_zar: "bad", status: "OPEN", updated_at: "2026-09-29T00:00:00Z" },
]

test("dealTotals sums by status and tolerates bad values", () => {
  const t = dealTotals(deals)
  assert.equal(t.count, 4)
  assert.equal(t.won, 1)
  assert.equal(t.open, 2)
  assert.equal(t.lost, 1)
  assert.equal(t.wonValue, 1000.5)
  assert.equal(t.openValue, 500)
  assert.equal(t.winRate, 0.5)
  assert.equal(dealTotals([]).winRate, null)
})

test("bucketWonDeals places won deals by close date only", () => {
  const b = bucketWonDeals(deals, "7D", NOW)
  assert.equal(b.length, 7)
  assert.deepEqual(sumBuckets(b), { revenue: 1000.5, deals: 1 })
  assert.equal(b[5].deals, 1)
  assert.deepEqual(sumBuckets(bucketWonDeals([], "1Y", NOW)), { revenue: 0, deals: 0 })
  assert.deepEqual(sumBuckets(bucketWonDeals([{ status: "WON", value_zar: 5 }], "30D", NOW)), { revenue: 0, deals: 0 })
})

test("closing this month / stalled", () => {
  assert.equal(dealsClosingThisMonth(deals, NOW).length, 1)
  assert.equal(stalledOpenDeals(deals, 14, NOW).length, 1)
})

test("topDeals has no invented reps", () => {
  const t = topDeals(deals, 2)
  assert.equal(t[0].client, "A")
  assert.equal(t[0].rep, null)
  assert.equal(t[0].won, true)
})

test("buildInsights only from real rows; empty when nothing", () => {
  assert.deepEqual(buildInsights(null, null, NOW), [])
  assert.deepEqual(buildInsights([], [], NOW), [])
  const ins = buildInsights(deals, [{ id: "x", title: "Reach out", description: "d", impact: "high", category: "Retention" }], NOW)
  assert.ok(ins.some((i) => i.id === "deals-closing"))
  assert.ok(ins.every((i) => !/firecrawl/i.test(i.title + i.description + i.actionPrompt)))
  assert.equal(ins.find((i) => i.id.startsWith("crm-")).agentType, "retention")
  assert.ok(ins.length <= 4)
})

test("buildBriefing", () => {
  assert.equal(buildBriefing(null, null), null)
  assert.match(buildBriefing([], 0), /no deals yet/)
  assert.match(buildBriefing(deals, 3), /4 deals/)
  assert.doesNotMatch(buildBriefing(deals, 3), /firecrawl/i)
})

test("activity + misc helpers", () => {
  assert.deepEqual(toActivityItems(null), [])
  assert.equal(toActivityItems([{ id: 1, user: "A B", action: "x", target: "y", time: "1 min ago" }, { id: 2 }]).length, 1)
  assert.equal(initials("Sarah Chen"), "SC")
  assert.equal(initials(""), "?")
  assert.equal(customerTotalOf({ items: [1, 2], total: 9 }), 9)
  assert.equal(customerTotalOf({ items: [1, 2] }), 2)
  assert.equal(customerTotalOf(null), null)
  assert.equal(countStatus([{ status: "Active" }, { status: "x" }], "active"), 1)
  assert.equal(listOf({ nope: 1 }), null)
  assert.deepEqual(mapLoadable({ state: "unreachable", status: 502 }, (x) => x), { state: "unreachable", status: 502 })
  assert.equal(mapLoadable({ state: "ready", data: 2 }, (x) => x * 2).data, 4)
  assert.equal(fmtZarCompact(1_250_000), "R 1.25M")
})
