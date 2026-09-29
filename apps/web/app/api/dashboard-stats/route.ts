import { NextResponse } from "next/server"

/**
 * Real headline stats for the Dashboard Overview, computed from the actual
 * backend services (sales, crm) instead of the Supabase module_data blob
 * (see app/api/modules/[module]/route.ts). Added 2026-09-22 when the blob
 * became unreachable (its Supabase project was paused) -- rather than patch
 * around that specific outage, this replaces the two stats that ARE
 * computable from real data (revenue, subscribers) with genuine numbers, and
 * is honest ("neutral"/"—") about the two that need services not running
 * locally (support tickets, network uptime) rather than showing fabricated
 * placeholder numbers as if they were real.
 */

const SALES_SERVICE_URL = process.env.SALES_SERVICE_URL || "http://sales:8002"
const CRM_SERVICE_URL = process.env.CRM_SERVICE_URL || "http://crm:8001"
const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"

type Stat = {
  id: string
  title: string
  value: string
  change: string
  changeType: "positive" | "negative" | "neutral"
  iconKey: string
  description: string
}

function headersFor(request: Request): HeadersInit {
  const auth = request.headers.get("authorization")
  const tenantId = request.headers.get("x-tenant-id") || DEV_TENANT_ID
  const h: Record<string, string> = { "x-tenant-id": tenantId }
  if (auth) h["authorization"] = auth
  return h
}

async function fetchJson(url: string, headers: HeadersInit): Promise<unknown | null> {
  try {
    const res = await fetch(url, { headers, cache: "no-store", signal: AbortSignal.timeout(1500) })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export async function GET(request: Request) {
  const headers = headersFor(request)

  const [deals, customers] = await Promise.all([
    fetchJson(`${SALES_SERVICE_URL}/deals`, headers),
    fetchJson(`${CRM_SERVICE_URL}/customers`, headers),
  ])

  const dealsArr = Array.isArray(deals) ? deals : []
  const totalRevenue = dealsArr.reduce((sum: number, d: any) => {
    const v = Number.parseFloat(d?.value_zar ?? "0")
    return sum + (Number.isFinite(v) ? v : 0)
  }, 0)

  // CRM's /customers returns a paginated envelope ({items, total, page, ...}),
  // not a raw array -- read .total (falls back to items.length) so a real
  // empty result (total: 0) is distinguished from the service being down.
  let customerCount: number | null = null
  if (customers && typeof customers === "object") {
    const c = customers as any
    if (typeof c.total === "number") customerCount = c.total
    else if (Array.isArray(c.items)) customerCount = c.items.length
  } else if (Array.isArray(customers)) {
    customerCount = customers.length
  }

  const stats: Stat[] = [
    {
      id: "revenue",
      title: "Total Revenue (Open + Closed Deals)",
      value: dealsArr.length > 0 || deals !== null
        ? `R${totalRevenue.toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`
        : "—",
      change: deals === null ? "" : `${dealsArr.length} deal${dealsArr.length === 1 ? "" : "s"}`,
      changeType: deals === null ? "neutral" : "positive",
      iconKey: "revenue",
      description: deals === null ? "sales service unavailable" : "from sales pipeline",
    },
    {
      id: "subscribers",
      title: "Active Customers",
      value: customerCount !== null ? customerCount.toLocaleString("en-ZA") : "—",
      change: "",
      changeType: customerCount !== null ? "positive" : "neutral",
      iconKey: "subscribers",
      description: customerCount !== null ? "from CRM" : "crm service unavailable",
    },
    {
      id: "tickets",
      title: "Open Tickets",
      value: "—",
      change: "",
      changeType: "neutral",
      iconKey: "tickets",
      description: "support service not running locally",
    },
    {
      id: "uptime",
      title: "Network Uptime",
      value: "—",
      change: "",
      changeType: "neutral",
      iconKey: "uptime",
      description: "network telemetry not running locally",
    },
  ]

  const openDeals = dealsArr.filter((d: any) => d.status === "OPEN")
  const wonDeals = dealsArr.filter((d: any) => d.status === "WON")
  const openRevenue = openDeals.reduce((sum: number, d: any) => sum + (Number.parseFloat(d?.value_zar ?? "0") || 0), 0)

  // Map real top deals by value
  const recentDeals = [...dealsArr]
    .sort((a: any, b: any) => (Number.parseFloat(b?.value_zar ?? "0") || 0) - (Number.parseFloat(a?.value_zar ?? "0") || 0))
    .slice(0, 4)
    .map((d: any) => {
      const isWon = d.status === "WON"
      const val = Number.parseFloat(d.value_zar ?? "0") || 0
      return {
        client: d.name || "Commercial Account",
        type: d.lead_reference ? `Lead ${d.lead_reference}` : (isWon ? "Closed Won Deal" : "Active Opportunity"),
        amount: `R ${val.toLocaleString("en-ZA", { maximumFractionDigits: 0 })}`,
        stage: d.stage_name || (isWon ? "Closed Won" : "In Pipeline"),
        stageColor: isWon
          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
          : "bg-blue-500/10 text-blue-400 border-blue-500/20",
        rep: d.owner_name || "Sales Team",
      }
    })

  // Executive summary driven by real metrics
  const executiveSummary = (dealsArr.length > 0 || customerCount !== null)
    ? `Active sales pipeline currently tracks R${totalRevenue.toLocaleString("en-ZA", { maximumFractionDigits: 0 })} across ${dealsArr.length} deals (${wonDeals.length} won, ${openDeals.length} open proposals). CRM records ${customerCount ?? 0} active customer accounts. InsightDome advises prioritizing the ${openDeals.length} in-flight pipeline opportunities and running automated web lead scans via Firecrawl.`
    : "AI Agent Orchestrator is operational. Connect sales and CRM data streams to view live portfolio health."

  // Dynamic AI Suggestions driven by orchestrator & live telemetry
  const aiSuggestions = [
    {
      id: "sug-1",
      title: "Accelerate In-Flight Commercial Deals",
      description: `${openDeals.length} active proposals totaling R${openRevenue.toLocaleString("en-ZA", { maximumFractionDigits: 0 })} await closure. Deploy InsightDome to draft targeted follow-ups.`,
      category: "Sales Pipeline",
      impact: "high" as const,
      actionPrompt: "Analyze our open sales deals in the pipeline and draft tailored follow-up proposals to accelerate closure.",
      agentType: "executive",
    },
    {
      id: "sug-2",
      title: "Autonomous Lead Generation (Firecrawl)",
      description: "Extract and enrich high-value B2B commercial fiber tender opportunities in key business corridors.",
      category: "Lead Generation",
      impact: "high" as const,
      actionPrompt: "Run an opportunity scan for high-potential commercial fiber tender and corporate leads in Gauteng and Western Cape.",
      agentType: "assistant",
    },
    {
      id: "sug-3",
      title: "Workforce & Talent Health (StaffBot)",
      description: "Monitor NOC shift fatigue and field technician dispatch schedules for upcoming infrastructure work.",
      category: "HR & Talent",
      impact: "medium" as const,
      actionPrompt: "Check StaffBot talent health and employee roster coverage for upcoming maintenance windows.",
      agentType: "talent",
    },
    {
      id: "sug-4",
      title: "Customer Retention & Proactive Care",
      description: "Run churn prediction analysis on active accounts and verify statutory RICA identification compliance.",
      category: "Retention & Compliance",
      impact: "medium" as const,
      actionPrompt: "Run churn prediction analysis on active accounts and review any pending RICA verification flags.",
      agentType: "retention",
    },
  ]

  return NextResponse.json({
    stats,
    recentDeals: recentDeals.length > 0 ? recentDeals : null,
    executiveSummary,
    aiSuggestions,
    sources: { deals: deals !== null, customers: customerCount !== null },
  })
}
