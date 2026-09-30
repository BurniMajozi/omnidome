// Run: node --test lib/ops-derive.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import {
  loadableFromOps, allSettled, dataOr, itemsOf, relativeTime, healthBuckets, atRiskCustomers, mrrBySegment,
  statusCountsFromSummary, normTaskStatus, normPriority, normIssueStatus, escalationStats, deviceStats,
  eventsPerHour, networkDeviceStats, metricByHour, latestAverage, pct,
} from "./ops-derive.ts"

test("loadableFromOps: outcome -> state", () => {
  assert.equal(loadableFromOps(200, []).state, "ready")
  assert.equal(loadableFromOps(200, undefined).state, "error")
  assert.equal(loadableFromOps(null, undefined).state, "unreachable")
  assert.equal(loadableFromOps(502, undefined).state, "unreachable")
  assert.equal(loadableFromOps(503, undefined).state, "unreachable")
  assert.equal(loadableFromOps(504, undefined).state, "unreachable")
  assert.equal(loadableFromOps(403, undefined).state, "denied")
  assert.equal(loadableFromOps(500, undefined).state, "error")
})

test("loadableFromOps: rewrite-proxied 500 without JSON detail means not running", () => {
  assert.equal(loadableFromOps(500, undefined, { rewriteProxy: true }).state, "unreachable")
  // a real FastAPI 500 carries {"detail": ...} and stays an error
  const real = loadableFromOps(500, undefined, { rewriteProxy: true, hasJsonDetail: true, message: "Internal server error" })
  assert.equal(real.state, "error")
  // route-handler proxies are not affected
  assert.equal(loadableFromOps(500, undefined, { rewriteProxy: false }).state, "error")
})

test("allSettled / dataOr", () => {
  assert.equal(allSettled({ state: "loading" }, { state: "ready", data: 1 }), false)
  assert.equal(allSettled({ state: "error", status: 500 }, { state: "ready", data: 1 }), true)
  assert.equal(dataOr({ state: "unreachable", status: 502 }, []).length, 0)
  assert.deepEqual(dataOr({ state: "ready", data: [1] }, []), [1])
})

test("itemsOf accepts arrays and paginated envelopes", () => {
  assert.deepEqual(itemsOf([1, 2]), [1, 2])
  assert.deepEqual(itemsOf({ items: [3] }), [3])
  assert.deepEqual(itemsOf(null), [])
  assert.deepEqual(itemsOf({ nope: 1 }), [])
})

test("relativeTime", () => {
  const now = new Date("2026-09-30T12:00:00Z")
  assert.equal(relativeTime("2026-09-30T11:59:40Z", now), "just now")
  assert.equal(relativeTime("2026-09-30T11:30:00Z", now), "30 min ago")
  assert.equal(relativeTime("2026-09-30T09:00:00Z", now), "3 hours ago")
  assert.equal(relativeTime("2026-09-28T12:00:00Z", now), "2 days ago")
  assert.equal(relativeTime(null, now), "—")
})

test("retention: health buckets, watchlist, mrr per segment come only from the rows given", () => {
  const rows = [
    { id: "1", health: "At Risk", mrr: 800, customer_type: "SMB" },
    { id: "2", health: "Critical", mrr: 0, customer_type: "Residential" },
    { id: "3", health: "Good", mrr: 300, customer_type: "Residential" },
    { id: "4", mrr: 500, customer_type: "SMB" },
  ]
  assert.deepEqual(healthBuckets(rows).map((b) => [b.name, b.value]), [["Good", 1], ["At Risk", 1], ["Critical", 1], ["Unknown", 1]])
  assert.deepEqual(atRiskCustomers(rows).map((c) => c.id), ["1", "2"])
  assert.deepEqual(mrrBySegment(rows), [
    { segment: "SMB", avgMrr: 650, customers: 2 },
    { segment: "Residential", avgMrr: 300, customers: 1 },
  ])
  assert.deepEqual(healthBuckets([]), [])
  assert.deepEqual(mrrBySegment([]), [])
})

test("statusCountsFromSummary", () => {
  const kpis = [{ backDetails: [{ label: "Active", value: "7" }, { label: "Suspended", value: "1" }, { label: "Churned", value: "2" }] }]
  assert.deepEqual(statusCountsFromSummary(kpis), { active: 7, suspended: 1, churned: 2 })
  assert.equal(statusCountsFromSummary(undefined), null)
  assert.equal(statusCountsFromSummary([{ backDetails: [{ label: "Active", value: "x" }] }]), null)
})

test("layout vocabulary normalisation", () => {
  assert.equal(normTaskStatus("In Progress"), "in-progress")
  assert.equal(normTaskStatus("open"), "todo")
  assert.equal(normTaskStatus("Completed"), "done")
  assert.equal(normPriority("Critical"), "urgent")
  assert.equal(normPriority(undefined), "normal")
  assert.equal(normIssueStatus("in_progress"), "in-progress")
  assert.equal(normIssueStatus("closed"), "resolved")
})

test("service: escalation stats (zeros are real, averages only from resolved rows)", () => {
  const now = new Date("2026-09-30T12:00:00Z")
  const empty = escalationStats([], now)
  assert.equal(empty.total, 0)
  assert.equal(empty.avgResolutionHours, null)
  assert.equal(empty.days.length, 7)
  assert.ok(empty.days.every((d) => d.open === 0 && d.resolved === 0))

  const s = escalationStats([
    { id: "a", status: "open", created_at: "2026-09-30T08:00:00Z", updated_at: "2026-09-30T08:00:00Z" },
    { id: "b", status: "in_progress", created_at: "2026-09-29T08:00:00Z", updated_at: "2026-09-29T09:00:00Z" },
    { id: "c", status: "resolved", created_at: "2026-09-29T08:00:00Z", updated_at: "2026-09-29T12:00:00Z" },
  ], now)
  assert.equal(s.open, 1)
  assert.equal(s.inProgress, 1)
  assert.equal(s.resolved, 1)
  assert.equal(s.avgResolutionHours, 4)
  assert.equal(s.days[6].open, 1)
  assert.equal(s.days[5].open, 2)
  assert.equal(s.days[5].resolved, 1)
})

test("iot: device stats and hourly events", () => {
  const d = deviceStats([
    { id: "1", friendly_name: "a", device_type: "camera", status: "online", battery_level: 10 },
    { id: "2", friendly_name: "b", device_type: "camera", status: "offline", battery_level: 90 },
    { id: "3", friendly_name: "c", device_type: "light", status: "online" },
  ])
  assert.equal(d.total, 3)
  assert.equal(d.online, 2)
  assert.equal(d.lowBattery, 1)
  assert.equal(d.withBattery, 2)
  assert.deepEqual(d.byType.find((t) => t.type === "camera"), { type: "camera", count: 2, online: 1, offline: 1 })
  assert.equal(deviceStats([]).total, 0)

  const now = new Date("2026-09-30T12:30:00Z")
  const hours = eventsPerHour([
    { id: "1", event_type: "x", created_at: "2026-09-30T12:10:00Z" },
    { id: "2", event_type: "x", created_at: "2026-09-30T12:20:00Z" },
    { id: "3", event_type: "x", created_at: "2026-09-28T12:20:00Z" }, // outside 24h window
  ], now)
  assert.equal(hours.length, 24)
  assert.equal(hours.reduce((a, h) => a + h.events, 0), 2)
})

test("network: device stats, metric hour buckets leave gaps as null", () => {
  const n = networkDeviceStats([
    { id: "1", device_type: "ont", status: "active" },
    { id: "2", device_type: "ont", status: "offline" },
  ])
  assert.equal(n.total, 2)
  assert.equal(n.active, 1)
  assert.deepEqual(n.byType, [{ type: "ont", active: 1, count: 2 }])

  const now = new Date("2026-09-30T12:30:00Z")
  const rows = [
    { metric_type: "latency_ms", metric_value: 10, collected_at: "2026-09-30T12:10:00Z" },
    { metric_type: "latency_ms", metric_value: 20, collected_at: "2026-09-30T12:20:00Z" },
    { metric_type: "download_mbps", metric_value: 99, collected_at: "2026-09-30T12:20:00Z" },
  ]
  const series = metricByHour(rows, "latency_ms", now)
  assert.equal(series.filter((p) => p.value !== null).length, 1)
  assert.equal(series.find((p) => p.value !== null).value, 15)
  assert.equal(latestAverage(rows, "latency_ms"), 15)
  assert.equal(latestAverage([], "latency_ms"), null)
  assert.ok(metricByHour([], "latency_ms", now).every((p) => p.value === null))
})

test("pct never divides by zero", () => {
  assert.equal(pct(0, 0), "0%")
  assert.equal(pct(1, 4), "25.0%")
})
