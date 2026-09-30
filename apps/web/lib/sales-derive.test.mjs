// Run: node --test lib/sales-derive.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import {
  parseTs, sastDate, sastMonthRange, summarizeDeals, parseDealSummary, wonByMonth, deriveActivities,
  deriveRecommendations, truncationNote, parseTotalCount, boardTotals, closingTarget, funnelKey, funnelTier,
  clampPct, aggregateFunnel, sumStageMap, tierConversion, pipelineValueFigure, visibleChannels,
} from "./sales-derive.ts"

const NOW = new Date("2026-09-30T10:00:00Z")

test("SAST date rolls over at 22:00 UTC", () => {
  assert.equal(sastDate(new Date("2026-09-30T21:59:00Z")), "2026-09-30")
  assert.equal(sastDate(new Date("2026-09-30T22:00:00Z")), "2026-10-01")
  assert.deepEqual(sastMonthRange(NOW), { closed_from: "2026-09-01", closed_to: "2026-09-30" })
})

test("parseTs treats offset-less timestamps as UTC", () => {
  assert.equal(parseTs("2026-09-01T00:00:00").toISOString(), "2026-09-01T00:00:00.000Z")
  assert.equal(parseTs("2026-09-01T02:00:00+02:00").toISOString(), "2026-09-01T00:00:00.000Z")
  assert.equal(parseTs(null), null)
  assert.equal(parseTs("garbage"), null)
})

const deals = [
  { id: "1", name: "A", status: "WON", value_zar: "1000", closed_at: "2026-09-10T08:00:00Z", created_at: "2026-09-01T08:00:00Z" },
  { id: "2", name: "B", status: "WON", value_zar: 500, closed_at: "2026-08-31T22:30:00Z", created_at: "2026-08-01T08:00:00Z" }, // 1 Sep SAST
  { id: "3", name: "C", status: "WON", value_zar: 700, closed_at: "2026-08-20T08:00:00Z" },
  { id: "4", name: "D", status: "OPEN", value_zar: 2000, created_at: "2026-09-02T08:00:00Z" },
  { id: "5", name: "E", status: "LOST", value_zar: 9000, closed_at: "2026-09-05T08:00:00Z" },
]

test("monthly revenue is WON value closed this month, not everything created", () => {
  const { all, monthWon } = summarizeDeals(deals, sastMonthRange(NOW))
  assert.equal(monthWon.value_zar, 1500) // A + B (B closed 1 Sep SAST)
  assert.equal(monthWon.count, 2)
  assert.equal(all.open_value_zar, 2000)
  assert.equal(all.won_value_zar, 2200)
  assert.equal(all.lost_value_zar, 9000)
  assert.equal(all.count, 5)
  assert.equal(all.total_value_zar, 13200)
})

test("parseDealSummary requires the contract fields", () => {
  const ok = { count: 1, total_value_zar: 2, won_count: 0, won_value_zar: 0, open_count: 1, open_value_zar: 2, lost_count: 0, lost_value_zar: 0 }
  assert.deepEqual(parseDealSummary(ok), ok)
  assert.equal(parseDealSummary({ count: 1 }), null)
  assert.equal(parseDealSummary(null), null)
  assert.equal(parseDealSummary({ detail: "Not Found" }), null)
})

test("wonByMonth buckets by closed month", () => {
  const b = wonByMonth(deals, NOW, 3)
  assert.deepEqual(b.map((x) => x.month), ["Jul", "Aug", "Sep"])
  assert.deepEqual(b.map((x) => x.revenue), [0, 700, 1500])
})

test("activities come from real rows only, newest first, no invented people", () => {
  const a = deriveActivities(deals, NOW)
  assert.equal(a[0].target, "A")
  assert.ok(a.every((x) => ["Pipeline"].includes(x.user)))
  assert.equal(deriveActivities([], NOW).length, 0)
})

test("recommendations are facts about open deals; none without deals", () => {
  assert.deepEqual(deriveRecommendations([], NOW), [])
  const open = [
    { id: "a", name: "Old", status: "OPEN", value_zar: 100, updated_at: "2026-08-01T00:00:00Z", close_date: "2026-09-01" },
    { id: "b", name: "Soon", status: "OPEN", value_zar: 300, updated_at: "2026-09-29T00:00:00Z", close_date: "2026-09-30" },
    { id: "c", name: "Won", status: "WON", value_zar: 300, updated_at: "2026-01-01T00:00:00Z" },
  ]
  const r = deriveRecommendations(open, NOW)
  assert.deepEqual(r.map((x) => x.id), ["stalled", "overdue", "closing-this-month"])
  assert.ok(!JSON.stringify(r).includes("%"))
})

test("truncation note only when truncated", () => {
  assert.equal(truncationNote(200, 200), null)
  assert.equal(truncationNote(200, null), null)
  assert.match(truncationNote(200, 350), /200.*of.*350/)
  assert.equal(parseTotalCount("12"), 12)
  assert.equal(parseTotalCount(null), null)
  assert.equal(parseTotalCount("x"), null)
})

test("board totals keep open and won apart", () => {
  const t = boardTotals(deals)
  assert.equal(t.openValue, 2000)
  assert.equal(t.wonValue, 2200)
  assert.equal(t.count, 5)
})

test("closing target detection", () => {
  const stages = [{ id: "1", name: "Negotiation" }, { id: "2", name: "Closed Won" }, { id: "3", name: "closed lost" }]
  assert.equal(closingTarget(stages, "1"), null)
  assert.equal(closingTarget(stages, "2"), "won")
  assert.equal(closingTarget(stages, "3"), "lost")
  assert.equal(closingTarget(stages, "zzz"), null)
})

test("funnel keys are case-insensitive and cover won/lost", () => {
  assert.equal(funnelKey("Closed_Won"), "CLOSED WON")
  assert.equal(funnelTier("Qualified"), "mid")
  assert.equal(funnelTier("QUALIFIED"), "mid")
  assert.equal(funnelTier("WON"), "won")
  assert.equal(funnelTier("Closed Lost"), "lost")
  assert.equal(funnelTier("Weird custom"), "other")
})

test("aggregateFunnel merges case duplicates and reports unaccounted leads", () => {
  const stages = [
    { stage: "QUALIFIED", count: 4, value_zar: 100 },
    { stage: "Qualified", count: 1, value_zar: 50 },
    { stage: "NEW", count: 10 },
    { stage: "Custom", count: 2 },
    { stage: "Closed Won", count: 3, cohort_count: 3 },
  ]
  const a = aggregateFunnel(stages, 25)
  assert.equal(a.tiers.mid.count, 5)
  assert.equal(a.tiers.mid.value, 150)
  assert.equal(a.tiers.other.count, 2)
  assert.equal(a.tiers.won.count, 3)
  assert.equal(a.unaccounted, 25 - 20)
  assert.equal(aggregateFunnel(stages, 20).unaccounted, 0)
})

test("tier conversion is clamped 0-100, prefers cohorts, null when nothing to convert from", () => {
  assert.equal(tierConversion({ count: 50, cohort: null }, { count: 10, cohort: null }), 100)
  assert.equal(tierConversion({ count: 2, cohort: 8 }, { count: 10, cohort: 10 }), 80)
  assert.equal(tierConversion({ count: 2, cohort: null }, { count: 0, cohort: null }), null)
  assert.equal(clampPct(-5), 0)
  assert.equal(clampPct(250), 100)
  assert.equal(clampPct(NaN), 0)
})

test("pipeline value label is honest about its basis", () => {
  assert.match(pipelineValueFigure({ open_value_zar: 5, total_pipeline_value_zar: 9 }).label, /Open pipeline/)
  assert.equal(pipelineValueFigure({ open_value_zar: 5, total_pipeline_value_zar: 9 }).value, 5)
  assert.match(pipelineValueFigure({ total_pipeline_value_zar: 9 }).label, /older API/)
  assert.equal(pipelineValueFigure(undefined).value, 0)
})

test("visibleChannels never hides silently", () => {
  const items = [1, 2, 3, 4, 5]
  assert.deepEqual(visibleChannels(items, 3, false), { shown: [1, 2, 3], hidden: 2 })
  assert.deepEqual(visibleChannels(items, 3, true), { shown: items, hidden: 0 })
  assert.deepEqual(visibleChannels(items, 8, false), { shown: items, hidden: 0 })
})

test("tier cohort is the entry stage cohort, not a sum; stage maps are case-insensitive", () => {
  const a = aggregateFunnel([
    { stage: "QUALIFIED", count: 2, cohort_count: 9 },
    { stage: "Prospecting", count: 3, cohort_count: 7 },
    { stage: "Closed Won", count: 1, cohort_count: 1 },
  ], 6)
  assert.equal(a.tiers.mid.cohort, 9)
  assert.equal(a.tiers.won.cohort, 1)
  assert.equal(a.tiers.top.cohort, null)
  assert.equal(sumStageMap({ NEW: 2, Contacted: 3, Qualified: 4 }, "top"), 5)
  assert.equal(sumStageMap({ QUALIFIED: 4 }, "mid"), 4)
  assert.equal(sumStageMap(undefined, "mid"), 0)
})
