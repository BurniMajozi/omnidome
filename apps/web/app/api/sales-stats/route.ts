import { NextResponse } from "next/server"

/**
 * Real Sales widget data, computed from the sales service's actual deals
 * instead of the Supabase module_data blob (see app/api/modules/[module]
 * and app/api/dashboard-stats for the same pattern applied to Overview).
 *
 * Only fields genuinely derivable from real deal data are returned here:
 * revenue/deal-count trends, pipeline stage breakdown, KPI flashcards, and
 * the deals table. Fields that would need systems not present locally --
 * a real activity/audit feed, a support-ticket queue, a task manager, or
 * genuine AI-generated recommendations -- are intentionally left OUT of
 * this response so the frontend keeps its existing (decorative) fallback
 * for those, rather than fabricating fake activity/issues/tasks that look
 * real but aren't. Same for a deal's "probability" and "owner": the sales
 * schema doesn't track either (no probability field; agent_id is unset in
 * seed data), so those table columns show "—" rather than an invented
 * number or name.
 */

const SALES_SERVICE_URL = process.env.SALES_SERVICE_URL || "http://sales:8002"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"

const STAGE_COLORS: Record<string, string> = {
  Prospecting: "#4ade80",
  Negotiation: "#60a5fa",
  Proposal: "#fbbf24",
  "Closed Won": "#a855f7",
  "Closed Lost": "#f87171",
}
const FALLBACK_COLORS = ["#4ade80", "#60a5fa", "#fbbf24", "#a855f7", "#f87171", "#38bdf8", "#e03131"]

function headersFor(request: Request): HeadersInit {
  const auth = request.headers.get("authorization")
  const tenantId = request.headers.get("x-tenant-id") || DEV_TENANT_ID
  const h: Record<string, string> = { "x-tenant-id": tenantId }
  if (auth) h["authorization"] = auth
  return h
}

function fmtCurrency(value: number): string {
  return `R ${Math.round(value).toLocaleString("en-ZA")}`
}

export async function GET(request: Request) {
  const headers = headersFor(request)

  let deals: any[] | null = null
  try {
    const res = await fetch(`${SALES_SERVICE_URL}/deals`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    })
    if (res.ok) {
      const body = await res.json()
      deals = Array.isArray(body) ? body : null
    }
  } catch {
    deals = null
  }

  if (!deals) {
    // Sales service unreachable -- return nothing so the frontend keeps its
    // existing fallback (blob or hardcoded defaults) for everything.
    return NextResponse.json({ available: false })
  }

  const values = deals.map((d) => Number.parseFloat(d?.value_zar ?? "0")).filter(Number.isFinite)
  const totalValue = values.reduce((a, b) => a + b, 0)
  const openDeals = deals.filter((d) => d?.status === "OPEN")
  const openValue = openDeals.reduce((sum, d) => sum + (Number.parseFloat(d?.value_zar ?? "0") || 0), 0)
  const avgDealSize = values.length > 0 ? totalValue / values.length : 0

  // This calendar month's deals (by created_at) for the "Monthly Revenue" KPI.
  const now = new Date()
  const thisMonthDeals = deals.filter((d) => {
    const created = d?.created_at ? new Date(d.created_at) : null
    return created && created.getUTCFullYear() === now.getUTCFullYear() && created.getUTCMonth() === now.getUTCMonth()
  })
  const monthlyRevenue = thisMonthDeals.reduce((sum, d) => sum + (Number.parseFloat(d?.value_zar ?? "0") || 0), 0)

  // ── salesData: revenue + deal count for the last 6 calendar months ──
  const monthLabels: string[] = []
  const monthBuckets: Record<string, { revenue: number; deals: number }> = {}
  for (let i = 5; i >= 0; i--) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1))
    const key = `${d.getUTCFullYear()}-${d.getUTCMonth()}`
    const label = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" })
    monthLabels.push(label)
    monthBuckets[key] = { revenue: 0, deals: 0 }
  }
  for (const d of deals) {
    const created = d?.created_at ? new Date(d.created_at) : null
    if (!created) continue
    const key = `${created.getUTCFullYear()}-${created.getUTCMonth()}`
    if (monthBuckets[key]) {
      monthBuckets[key].revenue += Number.parseFloat(d?.value_zar ?? "0") || 0
      monthBuckets[key].deals += 1
    }
  }
  const salesData = Object.entries(monthBuckets).map(([, v], i) => ({
    month: monthLabels[i],
    revenue: Math.round(v.revenue),
    deals: v.deals,
  }))

  // ── pipelineData: deal count by stage ──
  const stageCounts = new Map<string, number>()
  for (const d of deals) {
    const stage = d?.stage_name || "Unstaged"
    stageCounts.set(stage, (stageCounts.get(stage) || 0) + 1)
  }
  const pipelineData = Array.from(stageCounts.entries()).map(([name, value], i) => ({
    name,
    value,
    fill: STAGE_COLORS[name] || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
  }))

  // ── flashcardKPIs ──
  const wonDeals = deals.filter((d) => d?.status === "CLOSED_WON" || d?.stage_name === "Closed Won")
  const lostDeals = deals.filter((d) => d?.status === "CLOSED_LOST" || d?.stage_name === "Closed Lost")
  const flashcardKPIs = [
    {
      id: "1",
      title: "Monthly Revenue",
      value: fmtCurrency(monthlyRevenue),
      change: `${thisMonthDeals.length} deal${thisMonthDeals.length === 1 ? "" : "s"} this month`,
      changeType: "positive" as const,
      iconKey: "revenue",
      backTitle: "Revenue Breakdown",
      backDetails: [{ label: "All deals (all time)", value: fmtCurrency(totalValue) }],
      backInsight: `${deals.length} total deal${deals.length === 1 ? "" : "s"} in the pipeline`,
    },
    {
      id: "2",
      title: "Total Deals",
      value: String(deals.length),
      change: "",
      changeType: "positive" as const,
      iconKey: "deals",
      backTitle: "Deal Analysis",
      backDetails: [
        { label: "Won", value: String(wonDeals.length) },
        { label: "Lost", value: String(lostDeals.length) },
        { label: "Open", value: String(openDeals.length) },
      ],
      backInsight: `${openDeals.length} deal${openDeals.length === 1 ? "" : "s"} still open`,
    },
    {
      id: "3",
      title: "Pipeline Value",
      value: fmtCurrency(openValue),
      change: "",
      changeType: "positive" as const,
      iconKey: "pipeline",
      backTitle: "Pipeline by Stage",
      backDetails: pipelineData.slice(0, 3).map((p) => ({ label: p.name, value: String(p.value) })),
      backInsight: `${pipelineData.length} active stage${pipelineData.length === 1 ? "" : "s"}`,
    },
    {
      id: "4",
      title: "Avg Deal Size",
      value: fmtCurrency(avgDealSize),
      change: "",
      changeType: "positive" as const,
      iconKey: "avgDeal",
      backTitle: "Deal Size",
      backDetails: [],
      backInsight: values.length > 0 ? `Across ${values.length} valued deals` : "No valued deals yet",
    },
  ]

  // ── tableData: most recent deals ──
  const sorted = [...deals].sort((a, b) => {
    const ta = a?.created_at ? new Date(a.created_at).getTime() : 0
    const tb = b?.created_at ? new Date(b.created_at).getTime() : 0
    return tb - ta
  })
  const tableData = sorted.slice(0, 10).map((d) => ({
    id: String(d?.id ?? ""),
    deal: String(d?.name ?? "Untitled deal"),
    value: fmtCurrency(Number.parseFloat(d?.value_zar ?? "0") || 0),
    stage: String(d?.stage_name ?? d?.status ?? "—"),
    probability: "—", // not tracked in the sales schema -- honest, not fabricated
    closeDate: d?.close_date ?? "—",
    owner: "—", // agent_id isn't resolved to a name; not tracked in seed data
  }))
  const tableColumns = [
    { key: "deal", label: "Deal Name" },
    { key: "value", label: "Value" },
    { key: "stage", label: "Stage" },
    { key: "probability", label: "Probability" },
    { key: "closeDate", label: "Close Date" },
    { key: "owner", label: "Owner" },
  ]

  const summary =
    deals.length > 0
      ? `The pipeline currently holds ${deals.length} deal${deals.length === 1 ? "" : "s"} worth ${fmtCurrency(totalValue)} in total, with ${fmtCurrency(openValue)} still open across ${pipelineData.length} stage${pipelineData.length === 1 ? "" : "s"}. Average deal size is ${fmtCurrency(avgDealSize)}.`
      : "No deals in the pipeline yet."

  return NextResponse.json({
    available: true,
    salesData,
    pipelineData,
    flashcardKPIs,
    tableData,
    tableColumns,
    summary,
  })
}
