// Run with: node scripts/test-deck-studio.mjs   (bundles with esbuild, then runs under node:test)
import test from "node:test"
import assert from "node:assert/strict"
import { createRequire } from "node:module"
import { resolveToken, resolveText, formatNumber } from "../components/modules/analytics/deck-studio/tokens"
import { buildPptx } from "../components/modules/analytics/deck-studio/pptx-export"
import { computeFrames } from "../components/modules/analytics/deck-studio/layout"
import { modelFrom, modelToSpec, modelToSeries, validateModel, fitToType } from "../components/modules/analytics/deck-studio/builder-model"
import type { ExportBundle, QueryResult } from "../lib/bi-studio-api"

const require = createRequire(import.meta.url)

// Synthetic fixtures (test only): monthly invoiced and invoiced by plan.
const monthly: QueryResult = {
  columns: [
    { id: "created_at", label: "Invoice date", kind: "time", type: "time", grain: "month" },
    { id: "invoiced", label: "Invoiced", kind: "measure", type: "number", format: "currency_zar", additive: true },
    { id: "outstanding", label: "Outstanding", kind: "measure", type: "number", format: "currency_zar", additive: true },
  ],
  rows: [
    ["2026-01-01", 1000, 200],
    ["2026-02-01", 1500, 300],
    ["2026-03-01", 1200, 250],
  ],
  totals: { invoiced: 3700, outstanding: 750 },
  meta: { dataset: "billing_invoices", generated_at: "2026-04-01T10:00:00Z", row_count: 3, truncated: false },
}
const byPlan: QueryResult = {
  columns: [
    { id: "plan", label: "Plan", kind: "dimension", type: "category" },
    { id: "invoiced", label: "Invoiced", kind: "measure", type: "number", format: "currency_zar", additive: true },
  ],
  rows: [
    ["Fibre 100", 2500],
    ["Fibre 50", 1200],
  ],
  totals: { invoiced: 3700 },
  meta: { dataset: "billing_invoices", generated_at: "2026-04-01T10:00:00Z", row_count: 2, truncated: false },
}

test("tokens resolve statistics and formats", () => {
  const data = { rev: monthly, plan: byPlan }
  assert.equal(resolveToken("rev.invoiced.last|currency", data).display, "R1 200")
  assert.equal(resolveToken("rev.invoiced.total", data).display, "R3 700")
  assert.equal(resolveToken("rev.invoiced.delta", data).display, "-R300")
  assert.equal(resolveToken("rev.invoiced.delta_pct", data).display, "-20.0%")
  assert.equal(resolveToken("rev.invoiced.last.label", data).display, "2026-03-01")
  assert.equal(resolveToken("plan.invoiced.top1.label", data).display, "Fibre 100")
  assert.equal(resolveToken("plan.invoiced.top1.share|percent0", data).display, "68%")
  assert.equal(resolveToken("nope.invoiced", data).ok, false)
  assert.equal(resolveText("Up {{rev.invoiced.max|currency_compact}} and {{?}}", data), "Up R1.5k and [add figure]")
  assert.equal(formatNumber(0.4567, "percent"), "45.7%")
})

test("layout places chart left and text/kpi stacked on the right", () => {
  const f = computeFrames({
    id: "s",
    layout: "chart_plus_text",
    title: "t",
    blocks: [
      { type: "chart", id: "c1", chart_type: "column", series: {} },
      { type: "text", id: "t1", items: [{ text: "x" }] },
      { type: "kpi", id: "k1", label: "k", value_ref: "a.b" },
    ],
  } as never)
  assert.ok(f.blocks.c1.x + f.blocks.c1.w <= f.blocks.t1.x + 0.01)
  assert.ok(f.blocks.t1.y + f.blocks.t1.h <= f.blocks.k1.y + 0.01)
})

test("builder model round-trips and enforces chart constraints", () => {
  const spec = { dataset: "billing_invoices", measures: ["invoiced", "outstanding"], dimensions: ["plan"], time: { dimension: "created_at", grain: "month" as const } }
  const m = modelFrom(spec, { x: "created_at", y: ["invoiced"], y2: ["outstanding"], series: "plan" }, "combo")!
  assert.equal(m.series, "plan")
  assert.deepEqual(m.y2, ["outstanding"])
  const back = modelToSpec(m, "combo")
  assert.deepEqual([...back.measures].sort(), ["invoiced", "outstanding"])
  assert.equal(modelToSeries(m, "combo").x, "created_at")
  const { model } = fitToType(m, "pie")
  assert.equal(model.y.length, 1)
  assert.equal(validateModel(model, "pie"), null)
  assert.match(validateModel({ ...m, y2: [] }, "combo") ?? "", /second measure/)
})

test("pptx export produces real charts, tables, notes", async () => {
  const bundle: ExportBundle = {
    format: "omnidome-deck/1",
    exported_at: "2026-04-01T10:00:00Z",
    deck: { id: "d1", title: "Q1 Review", version: 3, status: "draft" },
    doc: { schema_version: 1, title: "Q1 Review", queries: {}, slides: [] },
    brand_kit: null,
    theme: {
      palette: { primary: "#0B5FFF", secondary: "#1F2A44", accent: "#F5A623", background: "#FFFFFF", text: "#1B1F2A", chart: ["#0B5FFF", "#F5A623", "#2BB673"] },
      fonts: { heading: "Calibri", body: "Calibri" },
      footer_text: "Confidential",
      slide_numbers: true,
    },
    as_of: "2026-04-01T10:00:00Z",
    run_id: "r1",
    stale_data: false,
    unresolved: [],
    query_errors: {},
    data: { rev: monthly, plan: byPlan },
    slides: [
      { id: "s1", layout: "title", title: "Q1 Review", subtitle: "Prepared for the board", notes: "Opening", blocks: [] },
      {
        id: "s2",
        layout: "chart_plus_text",
        title: "Revenue",
        notes: "Total R3 700",
        blocks: [
          { id: "c1", type: "chart", chart_type: "column", title: "Invoiced by month", query_alias: "rev", series: { x: "created_at", y: ["invoiced"] }, legend: "bottom", labels: true },
          { id: "t1", type: "text", role: "body", items: [{ text: "Latest month R1 200", bullet: true }] },
          { id: "k1", type: "kpi", label: "Outstanding", value: "R750", delta: "-20.0%", delta_direction: "down", delta_is_good: true },
        ],
      },
      { id: "s3", layout: "chart_full", title: "Mix", blocks: [{ id: "c2", type: "chart", chart_type: "donut", query_alias: "plan", series: { x: "plan", y: ["invoiced"] }, legend: "right" }] },
      { id: "s4", layout: "chart_full", title: "Combo", blocks: [{ id: "c3", type: "chart", chart_type: "combo", query_alias: "rev", series: { x: "created_at", y: ["invoiced"], y2: ["outstanding"] } }] },
      {
        id: "s5",
        layout: "chart_full",
        title: "Trend",
        blocks: [
          { id: "c4", type: "chart", chart_type: "line", query_alias: "rev", series: { x: "created_at", y: ["invoiced", "outstanding"] } },
          { id: "c5", type: "chart", chart_type: "area", query_alias: "rev", series: { x: "created_at", y: ["invoiced"] } },
        ],
      },
      { id: "s6", layout: "table", title: "By plan", blocks: [{ id: "tb", type: "table", query_alias: "plan", columns: [{ field: "plan" }, { field: "invoiced" }], max_rows: 10 }] },
    ],
  }
  const pptx = await buildPptx(bundle)
  const buf: Buffer = await pptx.write({ outputType: "nodebuffer" })
  const JSZip = require("jszip")
  const zip = await JSZip.loadAsync(buf)
  const names: string[] = Object.keys(zip.files)
  const charts = names.filter((n) => /^ppt\/charts\/chart\d+\.xml$/.test(n))
  assert.ok(charts.length >= 5, `expected >=5 chart parts, got ${charts.length}`)
  const chartXml: string[] = await Promise.all(charts.map((n) => zip.file(n).async("string")))
  assert.ok(chartXml.some((x) => x.includes("<c:barChart>")), "bar chart")
  assert.ok(chartXml.some((x) => x.includes("<c:doughnutChart>")), "doughnut chart")
  assert.ok(chartXml.some((x) => x.includes("<c:lineChart>")), "line chart")
  assert.ok(chartXml.some((x) => x.includes("<c:areaChart>")), "area chart")
  assert.ok(chartXml.some((x) => x.includes("0B5FFF")), "brand palette colour applied to series")
  assert.equal(names.filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n)).length, 6, "6 slides")
  const slide6: string = await zip.file("ppt/slides/slide6.xml").async("string")
  assert.ok(slide6.includes("<a:tbl>"), "real table")
  assert.ok(slide6.includes("Fibre 100") && slide6.includes("R2 500"), "table cells resolved")
  assert.ok(names.some((n) => n.startsWith("ppt/notesSlides/")), "speaker notes")
  const slide2: string = await zip.file("ppt/slides/slide2.xml").async("string")
  assert.ok(slide2.includes("Latest month R1 200"), "resolved token text")
  assert.ok(slide2.includes("Outstanding"), "kpi")
  const embeds = names.filter((n) => n.startsWith("ppt/embeddings/"))
  assert.ok(embeds.length >= 5, "charts carry embedded workbooks so data stays editable")
})
