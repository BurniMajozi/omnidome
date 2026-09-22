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
    const res = await fetch(url, { headers, cache: "no-store", signal: AbortSignal.timeout(5000) })
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

  return NextResponse.json({ stats, sources: { deals: deals !== null, customers: customerCount !== null } })
}
