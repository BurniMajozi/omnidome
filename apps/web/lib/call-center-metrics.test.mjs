// Run: node --test lib/call-center-metrics.test.mjs   (Node >= 22.6 strips TS types natively)
import test from "node:test"
import assert from "node:assert/strict"
import {
  unwrapList, callsToday, avgHandleSeconds, avgWaitSeconds, activeAgentCount,
  hourlyVolume, directionSplit, agentPerformance, formatDuration,
} from "./call-center-metrics.ts"

const now = new Date(2026, 8, 30, 15, 0, 0) // local 30 Sep 2026

test("empty inputs give null / zero / [] - never invented values", () => {
  assert.equal(callsToday([], now), 0)
  assert.equal(avgHandleSeconds([]), null)
  assert.equal(avgWaitSeconds([]), null)
  assert.equal(activeAgentCount([]), 0)
  assert.deepEqual(hourlyVolume([]), [])
  assert.deepEqual(directionSplit([]), [])
  assert.deepEqual(agentPerformance([], []), [])
})

test("unwrapList accepts arrays and legacy wrapped shapes", () => {
  assert.deepEqual(unwrapList([1], "agents"), [1])
  assert.deepEqual(unwrapList({ agents: [2] }, "agents"), [2])
  assert.deepEqual(unwrapList(null, "agents"), [])
  assert.deepEqual(unwrapList({ agents: "x" }, "agents"), [])
})

test("callsToday counts only local-today sessions", () => {
  const s = [
    { start_time: new Date(2026, 8, 30, 8, 0).toISOString() },
    { start_time: new Date(2026, 8, 29, 23, 0).toISOString() },
    { start_time: null },
  ]
  assert.equal(callsToday(s, now), 1)
})

test("averages ignore null durations", () => {
  assert.equal(avgHandleSeconds([{ duration_seconds: 60 }, { duration_seconds: 120 }, { duration_seconds: null }]), 90)
  assert.equal(avgWaitSeconds([{ avg_wait_seconds: 10 }, { avg_wait_seconds: null }, { avg_wait_seconds: 30 }]), 20)
  assert.equal(formatDuration(332), "5m 32s")
})

test("hourly volume buckets by real start hour and direction", () => {
  const v = hourlyVolume([
    { start_time: new Date(2026, 8, 30, 9, 5).toISOString(), direction: "INBOUND" },
    { start_time: new Date(2026, 8, 30, 9, 40).toISOString(), direction: "OUTBOUND" },
    { start_time: new Date(2026, 8, 30, 14, 0).toISOString(), direction: "inbound" },
  ])
  assert.deepEqual(v, [
    { hour: "09:00", inbound: 1, outbound: 1 },
    { hour: "14:00", inbound: 1, outbound: 0 },
  ])
  assert.deepEqual(directionSplit([{ direction: "OUTBOUND" }, { direction: "INBOUND" }, { direction: "INBOUND" }]), [
    { name: "Inbound", value: 2 },
    { name: "Outbound", value: 1 },
  ])
})

test("agent performance uses real session counts and stored csat (null stays null)", () => {
  const p = agentPerformance(
    [{ id: "a1", name: "Ann", csat_score: 4.5 }, { id: "a2", name: "Bo" }],
    [{ agent_id: "a2" }, { agent_id: "a2" }, { agent_id: "a1" }],
  )
  assert.deepEqual(p, [
    { name: "Bo", calls: 2, satisfaction: null },
    { name: "Ann", calls: 1, satisfaction: 4.5 },
  ])
  assert.equal(activeAgentCount([{ id: "1", status: "active" }, { id: "2", status: "on_call" }, { id: "3", status: "offline" }]), 2)
})
