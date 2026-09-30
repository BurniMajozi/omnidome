import { devFallbackAllowed } from "@/lib/dev-identity"
import { signedFetch } from "@/lib/internal-identity"
import { NextResponse } from "next/server"
import {
  num, isOpen, deriveActivities, deriveRecommendations, sastMonthRange, summarizeDeals, parseDealSummary, wonByMonth, parseTotalCount,
  type DealRow, type DealSummary,
} from "@/lib/sales-derive"

/**
 * Real Sales widget data, computed from the sales service's real deals.
 *
 * Money figures prefer GET /deals/summary (SQL sums over NUMERIC); when that
 * endpoint is not deployed (404/405) the same figures are computed from the
 * paginated /deals rows with identical semantics (lib/sales-derive.ts):
 *   Monthly Revenue = WON deals closed this SAST month (closed_at), not deals created.
 *   Open Pipeline   = status OPEN only.
 * Errors keep their HTTP meaning (503 unreachable, 504 timeout, upstream status
 * otherwise) so the UI can tell "service not running" from "error". Nothing
 * here has a built-in default; issues/tasks are not served at all (no source).
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
  const tenantId = request.headers.get("x-tenant-id") || (devFallbackAllowed() ? DEV_TENANT_ID : "")
  const h: Record<string, string> = tenantId ? { "x-tenant-id": tenantId } : {}
  // proxy.ts injects the verified x-user-id; backends reject a tenant without a user.
  const userId = request.headers.get("x-user-id")
  if (userId) h["x-user-id"] = userId
  if (auth) h["authorization"] = auth
  return h
}

function fmtCurrency(value: number): string {
  return `R ${Math.round(value).toLocaleString("en-ZA")}`
}

const PAGE = 1000
const MAX_PAGES = 10

class Upstream extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function getJson(path: string, headers: HeadersInit): Promise<{ status: number; body: unknown; res: Response }> {
  let res: Response
  try {
    res = await signedFetch(`${SALES_SERVICE_URL}${path}`, { headers, cache: "no-store", signal: AbortSignal.timeout(8000) })
  } catch (err) {
    const timeout = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError")
    throw new Upstream(timeout ? 504 : 503, timeout ? "Sales service timed out" : "Sales service unreachable")
  }
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    body = null
  }
  return { status: res.status, body, res }
}

async function fetchAllDeals(headers: HeadersInit): Promise<{ deals: DealRow[]; total: number }> {
  const deals: DealRow[] = []
  let total: number | null = null
  for (let page = 0; page < MAX_PAGES; page++) {
    const { status, body, res } = await getJson(`/deals?limit=${PAGE}&offset=${page * PAGE}`, headers)
    if (status < 200 || status >= 300 || !Array.isArray(body)) {
      const detail = (body as { detail?: unknown } | null)?.detail
      throw new Upstream(status >= 400 ? status : 502, typeof detail === "string" ? detail : `Sales service returned ${status}`)
    }
    deals.push(...(body as DealRow[]))
    total = parseTotalCount(res.headers.get("x-total-count")) ?? total
    // Old backend: no pagination, one response holds everything (no header).
    if (total === null || (body as unknown[]).length < PAGE || deals.length >= total) break
  }
  return { deals, total: total ?? deals.length }
}

async function fetchSummary(path: string, headers: HeadersInit): Promise<DealSummary | null> {
  try {
    const { status, body } = await getJson(path, headers)
    return status === 200 ? parseDealSummary(body) : null
  } catch {
    return null
  }
}

export async function GET(request: Request) {
  const headers = headersFor(request)
  const now = new Date()
  const range = sastMonthRange(now)

  let deals: DealRow[]
  let dealsTotal: number
  try {
    ;({ deals, total: dealsTotal } = await fetchAllDeals(headers))
  } catch (err) {
    const status = err instanceof Upstream ? err.status : 503
    return NextResponse.json(
      { available: false, detail: err instanceof Error ? err.message : "Sales service unavailable" },
      { status },
    )
  }

  // Prefer the SQL summary; fall back to the rows with the same semantics.
  const [allSummary, monthSummary] = await Promise.all([
    fetchSummary("/deals/summary", headers),
    fetchSummary(`/deals/summary?status=WON&closed_from=${range.closed_from}&closed_to=${range.closed_to}`, headers),
  ])
  const fromRows = summarizeDeals(deals, range)
  const usingSummary = allSummary !== null && monthSummary !== null
  const all: DealSummary = usingSummary ? (allSummary as DealSummary) : fromRows.all
  const month = usingSummary
    ? { count: (monthSummary as DealSummary).won_count, value_zar: (monthSummary as DealSummary).won_value_zar }
    : fromRows.monthWon
  const truncated = deals.length < dealsTotal

  const avgDealSize = all.count > 0 ? all.total_value_zar / all.count : 0

  const salesData = wonByMonth(deals, now, 6)

  // Deals by stage (from the fetched rows).
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

  const flashcardKPIs = [
    {
      id: "1",
      title: "Monthly Revenue",
      value: fmtCurrency(month.value_zar),
      change: `${month.count} deal${month.count === 1 ? "" : "s"} won this month`,
      changeType: "neutral" as const,
      iconKey: "revenue",
      backTitle: "Won revenue",
      backDetails: [
        { label: "Won this month", value: fmtCurrency(month.value_zar) },
        { label: "Won all time", value: fmtCurrency(all.won_value_zar) },
      ],
      backInsight: "Value of deals closed as won this month (by close date); open and lost deals are not counted.",
    },
    {
      id: "2",
      title: "Total Deals",
      value: String(all.count),
      change: "",
      changeType: "neutral" as const,
      iconKey: "deals",
      backTitle: "Deal Analysis",
      backDetails: [
        { label: "Won", value: String(all.won_count) },
        { label: "Lost", value: String(all.lost_count) },
        { label: "Open", value: String(all.open_count) },
      ],
      backInsight: `${all.open_count} deal${all.open_count === 1 ? "" : "s"} still open`,
    },
    {
      id: "3",
      title: "Open Pipeline",
      value: fmtCurrency(all.open_value_zar),
      change: `${all.open_count} open deal${all.open_count === 1 ? "" : "s"}`,
      changeType: "neutral" as const,
      iconKey: "pipeline",
      backTitle: "Open pipeline",
      backDetails: [
        { label: "Open", value: fmtCurrency(all.open_value_zar) },
        { label: "Won", value: fmtCurrency(all.won_value_zar) },
        { label: "Lost", value: fmtCurrency(all.lost_value_zar) },
      ],
      backInsight: "Open deals only; won and lost deals are excluded.",
    },
    {
      id: "4",
      title: "Avg Deal Size",
      value: fmtCurrency(avgDealSize),
      change: "",
      changeType: "neutral" as const,
      iconKey: "avgDeal",
      backTitle: "Deal Size",
      backDetails: [],
      backInsight: all.count > 0 ? `Across ${all.count} deal${all.count === 1 ? "" : "s"} of any status` : "No deals yet",
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
    value: fmtCurrency(num(d?.value_zar)),
    stage: String(d?.stage_name ?? d?.status ?? "—"),
    probability: "—", // not tracked in the sales schema
    closeDate: d?.close_date ?? "—",
    owner: d?.owner_name ?? "—",
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
    all.count > 0
      ? `${all.count} deal${all.count === 1 ? "" : "s"} in total: ${all.open_count} open worth ${fmtCurrency(all.open_value_zar)}, ${all.won_count} won worth ${fmtCurrency(all.won_value_zar)}, ${all.lost_count} lost. Won this month: ${fmtCurrency(month.value_zar)} from ${month.count} deal${month.count === 1 ? "" : "s"}. Average deal size is ${fmtCurrency(avgDealSize)}.`
      : "No deals in the pipeline yet."

  return NextResponse.json({
    available: true,
    source: usingSummary ? "summary" : "rows",
    salesData,
    pipelineData,
    flashcardKPIs,
    tableData,
    tableColumns,
    summary,
    deals: { loaded: deals.length, total: dealsTotal, truncated },
    openDeals: deals.filter(isOpen).length,
    // Facts about real deals only (lib/sales-derive.ts); no invented people, odds or events.
    activities: deriveActivities(deals, now),
    aiRecommendations: deriveRecommendations(deals, now),
  })
}
