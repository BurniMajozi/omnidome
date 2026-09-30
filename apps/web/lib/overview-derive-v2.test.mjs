// Run: node --test lib/overview-derive-v2.test.mjs
// Dates are built from local components so the suite does not depend on the machine time zone.
import test from "node:test"
import assert from "node:assert/strict"
import {
  bucketWonDeals, sumBuckets, dealsClosingThisMonth, parseDealDate, openEscalationCount, OPEN_ESCALATIONS_LABEL,
  readDealSummary, resolveDealTotals, lowerBound, stageNamesInOrder, pipelineByStage, corpKpiView,
} from "./overview-derive.ts"

const NOW = new Date(2026, 8, 30, 12, 0, 0) // Wed 30 Sep 2026
const at = (y, m, d, h = 0, mi = 0) => new Date(y, m - 1, d, h, mi).toISOString()
const won = (closed_at, value = 100) => ({ status: "WON", value_zar: value, closed_at })
const day = (b, key) => b.find((x) => x.key === key)

test("bucketWonDeals: local calendar days, today is the last bucket", () => {
  const b = bucketWonDeals([won(at(2026, 9, 29, 8), 1000.5)], "7D", NOW)
  assert.equal(b.length, 7)
  assert.equal(b[6].key, "2026-09-30")
  assert.equal(b[0].key, "2026-09-24")
  assert.deepEqual(sumBuckets(b), { revenue: 1000.5, deals: 1 })
  assert.equal(b[5].deals, 1)
  assert.deepEqual(sumBuckets(bucketWonDeals([], "1Y", NOW)), { revenue: 0, deals: 0 })
})

test("bucketWonDeals: closed yesterday 16:00 is yesterday, not today; boundary days included", () => {
  const b = bucketWonDeals(
    [
      won(at(2026, 9, 29, 16), 10),
      won(at(2026, 9, 30, 0, 1), 20), // just after local midnight: today
      won(at(2026, 9, 29, 23, 59), 40), // just before: yesterday
      won(at(2026, 9, 24, 0, 0), 80), // first day of the 7D window
      won(at(2026, 9, 23, 23, 59), 160), // one minute outside
      won(at(2026, 10, 1, 9), 320), // future: not placed
    ],
    "7D",
    NOW,
  )
  assert.equal(day(b, "2026-09-29").revenue, 50)
  assert.equal(day(b, "2026-09-30").revenue, 20)
  assert.equal(day(b, "2026-09-24").revenue, 80)
  assert.equal(sumBuckets(b).revenue, 150)
})

test("bucketWonDeals: date-only close_date is a local day", () => {
  const b = bucketWonDeals([{ status: "WON", value_zar: 7, close_date: "2026-09-30" }], "7D", NOW)
  assert.equal(day(b, "2026-09-30").deals, 1)
  const d = parseDealDate("2026-09-30")
  assert.equal(d.getDate(), 30)
  assert.equal(d.getHours(), 0)
  assert.equal(parseDealDate("nope"), null)
  assert.equal(parseDealDate(null), null)
  assert.deepEqual(sumBuckets(bucketWonDeals([{ status: "WON", value_zar: 5 }], "30D", NOW)), { revenue: 0, deals: 0 })
})

test("bucketWonDeals 30D is 30 consecutive distinct days", () => {
  const b = bucketWonDeals([], "30D", NOW)
  assert.equal(b.length, 30)
  assert.equal(b[0].key, "2026-09-01")
  assert.equal(b[29].key, "2026-09-30")
  assert.equal(new Set(b.map((x) => x.key)).size, 30)
})

test("bucketWonDeals 90D: 13 ISO weeks (Monday start) ending with the current week", () => {
  // 2026-09-30 is a Wednesday; its ISO week starts Monday 2026-09-28.
  const b = bucketWonDeals([won(at(2026, 9, 28, 8), 5), won(at(2026, 9, 27, 23, 0), 9)], "90D", NOW)
  assert.equal(b.length, 13)
  assert.equal(b[12].key, "2026-09-28")
  assert.equal(b[11].key, "2026-09-21")
  assert.equal(b[0].key, "2026-07-06")
  assert.equal(b[12].revenue, 5)
  assert.equal(b[11].revenue, 9) // Sunday belongs to the previous week
})

test("bucketWonDeals 1Y: 12 calendar months, unique labels, 360-365 day deals included", () => {
  const b = bucketWonDeals([won(at(2025, 10, 1, 8), 11), won(at(2025, 9, 30, 8), 99)], "1Y", NOW)
  assert.equal(b.length, 12)
  assert.equal(b[0].key, "2025-10")
  assert.equal(b[11].key, "2026-09")
  assert.equal(new Set(b.map((x) => x.label)).size, 12)
  assert.equal(b[0].revenue, 11)
  assert.equal(sumBuckets(b).revenue, 11) // Sep 2025 is outside
  const feb = bucketWonDeals([], "1Y", new Date(2027, 2, 15))
  assert.deepEqual(feb.map((x) => x.key).slice(8), ["2026-12", "2027-01", "2027-02", "2027-03"])
})

test("bucketWonDeals handles leap-year February", () => {
  const now = new Date(2028, 2, 1, 10) // 1 March 2028
  const b30 = bucketWonDeals([won(at(2028, 2, 29, 12), 5), won(at(2028, 2, 28, 12), 3), won(at(2028, 3, 1, 9), 1)], "30D", now)
  assert.equal(day(b30, "2028-02-29").revenue, 5)
  assert.equal(day(b30, "2028-02-28").revenue, 3)
  assert.equal(day(b30, "2028-03-01").revenue, 1)
  const b1y = bucketWonDeals([won(at(2028, 2, 29, 12), 5), won(at(2028, 2, 1, 0, 0), 2)], "1Y", now)
  assert.equal(b1y.find((x) => x.key === "2028-02").revenue, 7)
  assert.ok(!bucketWonDeals([], "30D", new Date(2027, 2, 1)).some((x) => x.key === "2027-02-29"))
})

test("closing this month parses date-only close_date as a local date (M7)", () => {
  const now = new Date(2026, 8, 30, 12)
  const open = (close_date) => ({ status: "OPEN", close_date })
  assert.equal(dealsClosingThisMonth([open("2026-10-01")], now).length, 0)
  assert.equal(dealsClosingThisMonth([open("2026-09-01"), open("2026-09-30")], now).length, 2)
  assert.equal(dealsClosingThisMonth([open("2026-08-31")], now).length, 0)
  assert.equal(dealsClosingThisMonth([open(null), open("garbage")], now).length, 0)
})

test("escalation headline: one shared definition and label", () => {
  assert.equal(openEscalationCount({ open: 3, inProgress: 2 }), 5)
  assert.equal(OPEN_ESCALATIONS_LABEL, "Open + in progress")
})

test("readDealSummary / resolveDealTotals: summary wins, rows are the fallback, partial is flagged", () => {
  const sum = { count: 10, total_value_zar: "1000.5", won_count: 3, won_value_zar: "300", open_count: 6, open_value_zar: 600, lost_count: 1, lost_value_zar: 100.5 }
  const rowsIn = [{ status: "WON", value_zar: 1 }, { status: "OPEN", value_zar: 2 }]
  assert.ok(readDealSummary(sum))
  assert.equal(readDealSummary({ count: 1 }), null)
  assert.equal(readDealSummary(null), null)
  assert.equal(readDealSummary([]), null)
  const r = resolveDealTotals(rowsIn, readDealSummary(sum), 5000)
  assert.equal(r.source, "summary")
  assert.equal(r.count, 10)
  assert.equal(r.wonValue, 300)
  assert.equal(r.winRate, 0.75)
  assert.equal(r.partial, false)
  const rows = resolveDealTotals(rowsIn, null, 2)
  assert.equal(rows.source, "rows")
  assert.equal(rows.count, 2)
  assert.equal(rows.partial, false)
  assert.equal(resolveDealTotals(rowsIn, null, 1000).partial, true)
  assert.equal(resolveDealTotals(null, null), null)
  assert.equal(lowerBound("R 5", true), "R 5+")
  assert.equal(lowerBound("R 5", false), "R 5")
})

test("pipelineByStage follows real stage order, unknown stages alphabetical, Unstaged last", () => {
  const order = stageNamesInOrder([
    { name: "Won", sort_order: 4 },
    { name: "Qualified", sort_order: 1 },
    { name: "Proposal", sort_order: 2 },
  ])
  assert.deepEqual(order, ["Qualified", "Proposal", "Won"])
  assert.deepEqual(stageNamesInOrder({ nope: 1 }), [])
  const open = (stage_name, v) => ({ status: "OPEN", stage_name, value_zar: v })
  const out = pipelineByStage(
    [open("Proposal", 5), open(undefined, 1), open("Zeta", 2), open("Alpha", 3), open("Qualified", 7), open("Proposal", 5), { status: "WON", stage_name: "Won", value_zar: 9 }],
    order,
  )
  assert.deepEqual(out.map((x) => x.month), ["Qualified", "Proposal", "Alpha", "Zeta", "Unstaged"])
  assert.equal(out[1].revenue, 10)
  assert.equal(out[1].deals, 2)
  assert.deepEqual(pipelineByStage([open("B", 1), open("A", 1)]).map((x) => x.month), ["A", "B"])
})

test("corpKpiView shows target and actual separately", () => {
  assert.deepEqual(corpKpiView({ budget: null, actual: null, achievementPct: null }), { targetText: "No target set", actualText: "Not connected", badge: null })
  const targetOnly = corpKpiView({ budget: 500000, actual: null, achievementPct: null })
  assert.equal(targetOnly.targetText, "R 500 000")
  assert.equal(targetOnly.actualText, "Not connected")
  assert.equal(targetOnly.badge, null)
  const actualOnly = corpKpiView({ budget: null, actual: 135382, achievementPct: null })
  assert.equal(actualOnly.targetText, "No target set")
  assert.equal(actualOnly.actualText, "R 135 382")
  assert.equal(corpKpiView({ budget: 200000, actual: 100000, achievementPct: 50 }).badge, "50.0% of target")
  assert.equal(corpKpiView({ budget: 0, actual: 0, achievementPct: null }).targetText, "No target set")
  assert.equal(corpKpiView(null).actualText, "Not connected")
})
