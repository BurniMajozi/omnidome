// Run: node --test lib/talent-derive.test.mjs
import test from "node:test"
import assert from "node:assert/strict"

const d = await import("./talent-derive.ts")
const { fmtZar } = await import("./format.ts")

test("roles: HR admin set", () => {
  assert.equal(d.hasHrAdminRole(["org_user"]), false)
  assert.equal(d.hasHrAdminRole(null), false)
  assert.equal(d.hasHrAdminRole(["x", "HR_Manager"]), true)
  for (const r of ["hr", "hr_admin", "admin", "tenant_admin", "owner", "org_admin"]) assert.equal(d.hasHrAdminRole([r]), true)
})

test("errors: parse status and server text", () => {
  const e = new Error('HR API error 422: {"detail":[{"loc":["body","kpis",0,"current_level"],"msg":"must be 1..5"}]}')
  const p = d.parseHrError(e)
  assert.equal(p.status, 422)
  assert.match(p.message, /current_level: must be 1\.\.5/)
  assert.match(d.formatHrError(e), /^Rejected by the server/)
  const f = d.parseHrError(new Error('HR API error 403: {"detail":"HR admin role required"}'))
  assert.equal(f.status, 403)
  assert.equal(d.isDeniedError(new Error("HR API error 403: x")), true)
  assert.match(d.formatHrError(new Error('HR API error 403: {"detail":"nope"}')), /^Not permitted: nope/)
  assert.equal(d.parseHrError(new TypeError("fetch failed")).status, null)
})

test("503 PAYE tables not verified is detected", () => {
  const e = new Error('HR API error 503: {"detail":"PAYE tables for tax year 2026/2027 are not verified"}')
  assert.equal(d.isUnverifiedTablesError(e), true)
  assert.equal(d.isUnverifiedTablesError(new Error('HR API error 503: {"detail":"db down"}')), false)
  assert.equal(d.isUnverifiedTablesError(new Error('HR API error 500: PAYE tables not verified')), false)
})

test("clampLevel is always an integer 1..5", () => {
  assert.equal(d.clampLevel(0), 1)
  assert.equal(d.clampLevel(9), 5)
  assert.equal(d.clampLevel(3.6), 4)
  assert.equal(d.clampLevel("x"), 3)
  assert.equal(d.clampLevel(undefined), 3)
  assert.equal(d.levelScorePct(3), 100)
})

test("headline: server composite wins unless dirty; template has no score", () => {
  const composite = { total: 62.5 }
  assert.deepEqual(d.pickHeadline({ composite, sheetDirty: false, localEstimate: 80 }), { value: 62.5, basis: "server" })
  assert.deepEqual(d.pickHeadline({ composite, sheetDirty: true, localEstimate: 80 }), { value: 80, basis: "estimate" })
  assert.deepEqual(d.pickHeadline({ composite: null, sheetDirty: false, localEstimate: null }), { value: null, basis: "none" })
  assert.deepEqual(d.pickHeadline({ composite, sheetDirty: false, localEstimate: 80, isTemplate: true }), { value: null, basis: "none" })
})

test("estimate mirrors the backend formula and breakdown adds up to the total", () => {
  const w = { shared: 30, values: 10, individual: 60 }
  const est = d.estimateComposite({
    companyIndex: 100,
    valuesRatings: [3, 3, 3, 3],
    kpis: [{ current_level: 3, weight_pct: 30 }, { current_level: 3, weight_pct: 30 }],
    weights: w,
  })
  assert.equal(est.total, 100)
  const missing = d.estimateComposite({ companyIndex: null, valuesRatings: null, kpis: [], weights: w })
  assert.equal(missing.total, 0)
  assert.equal(missing.sharedPts, null)
  const srv = d.pointsFromComposite({ total: 80, shared_score: 100, values_score: 100, individual_score: 66.67, values_rated: true, company_missing: false }, w)
  assert.ok(Math.abs(srv.sharedPts + srv.valuesPts + srv.indivPts - 80) < 0.1)
  assert.equal(d.pointsFromComposite({ total: null }, w), null)
})

test("company index tile: Set company targets instead of placeholders", () => {
  const ok = { sales_budget_zar: 10, cost_budget_zar: 10, profit_budget_zar: 10 }
  assert.deepEqual(d.companyIndexTile({ ...ok, corporate_attainment_index: 71.2 }), { kind: "value", value: 71.2 })
  assert.deepEqual(d.companyIndexTile({ ...ok, corporate_attainment_index: null }), { kind: "set_targets" })
  assert.deepEqual(d.companyIndexTile({ ...ok, company_missing: true, corporate_attainment_index: 50 }), { kind: "set_targets" })
  assert.deepEqual(d.companyIndexTile({ ...ok, sales_budget_zar: 0, corporate_attainment_index: 50 }), { kind: "set_targets" })
  assert.deepEqual(d.companyIndexTile(null), { kind: "set_targets" })
})

test("mapLimit keeps order, caps concurrency, isolates failures", async () => {
  let active = 0
  let peak = 0
  const out = await d.mapLimit(
    [1, 2, 3, 4, 5, 6, 7, 8, 9],
    4,
    async (n) => {
      active++
      peak = Math.max(peak, active)
      await new Promise((r) => setTimeout(r, 5))
      active--
      if (n === 5) throw new Error("boom")
      return n * 2
    },
    () => -1,
  )
  assert.deepEqual(out, [2, 4, 6, 8, -1, 12, 14, 16, 18])
  assert.ok(peak <= 4)
})

test("collectOrThrow: partial failures are tolerated, total failure rethrows (403 is not 'empty')", () => {
  const err = new Error("HR API error 403: x")
  assert.deepEqual(d.collectOrThrow([{ ok: true, rows: [1] }, { ok: false, err }, { ok: true, rows: [2, 3] }]), [1, 2, 3])
  assert.throws(() => d.collectOrThrow([{ ok: false, err }, { ok: false, err }]), /403/)
  assert.deepEqual(d.collectOrThrow([]), [])
})

test("hires vs exits come only from real rows", () => {
  const now = new Date(2026, 9, 15) // Oct 2026
  const pts = d.hiresVsExits(
    [{ hire_date: "2026-10-02" }, { hire_date: "2026-10-09" }, { hire_date: "2026-03-01" }, { hire_date: "2019-01-01" }, { hire_date: null }],
    [{ last_working_date: "2026-03-30" }, { notice_date: "2026-10-01" }],
    now,
  )
  assert.equal(pts.length, 12)
  assert.equal(pts[11].month, "Oct 26")
  assert.deepEqual([pts[11].hires, pts[11].exits, pts[11].net], [2, 1, 1])
  assert.equal(pts.reduce((a, p) => a + p.hires, 0), 3)
  const empty = d.hiresVsExits([], [], now)
  assert.ok(empty.every((p) => p.hires === 0 && p.exits === 0))
})

test("department counts, turnover, years of service, averages", () => {
  assert.deepEqual(d.departmentCounts([{ department: "A" }, { department: "B" }, { department: "A" }, {}]), [
    { department: "A", count: 2 },
    { department: "B", count: 1 },
    { department: "Unassigned", count: 1 },
  ])
  assert.equal(d.turnoverPct(2, 21), 9.5)
  assert.equal(d.turnoverPct(1, 0), null)
  const now = new Date(2026, 9, 15)
  assert.equal(d.exitsInLast12Months([{ last_working_date: "2026-01-01" }, { last_working_date: "2024-01-01" }, { notice_date: "2027-01-01" }], now), 1)
  assert.equal(d.yearsOfService("2021-10-16", now), 4)
  assert.equal(d.yearsOfService("2021-10-15", now), 5)
  assert.equal(d.yearsOfService("nope", now), null)
  assert.equal(d.averageScore([{ overall_score: null }]), null)
  assert.deepEqual(d.averageScore([{ overall_score: 80 }, { overall_score: 90 }, { overall_score: null }]), { avg: 85, scored: 2 })
})

test("redacted money shows a dash, never R 0", () => {
  assert.equal(d.fmtMoneyOrDash(undefined), "—")
  assert.equal(d.fmtMoneyOrDash(null), "—")
  assert.equal(d.fmtMoneyOrDash(""), "—")
  assert.equal(d.fmtMoneyOrDash("abc"), "—")
  assert.equal(d.fmtMoneyOrDash(0), "R 0")
  for (const n of [135382, 5496.4, -2500, 1234567]) assert.equal(d.fmtMoneyOrDash(n), fmtZar(n))
  assert.equal(d.fmtMoneyCents(1234.5), "R 1 234,50")
  assert.equal(d.fmtMoneyCents(undefined), "—")
})

test("performance summary payload is normalised", () => {
  const rows = d.readPerformanceSummary([
    { employee_id: "a", overall_score: 71.5, status: "APPROVED", fiscal_year: "FY 2026/2027", composite: { total: 71.5 } },
    { employee_id: "b", overall_score: null },
    { nope: 1 },
  ])
  assert.equal(rows.length, 2)
  assert.equal(rows[0].overall_score, 71.5)
  assert.equal(rows[1].overall_score, null)
  assert.equal(d.readPerformanceSummary({ items: [{ employee_id: "z" }] }).length, 1)
  assert.equal(d.readPerformanceSummary("x"), null)
  assert.equal(d.readPerformanceSummary(null), null)
})
