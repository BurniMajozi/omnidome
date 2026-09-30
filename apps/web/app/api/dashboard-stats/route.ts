import { devFallbackAllowed } from "@/lib/dev-identity"
import { signedFetch } from "@/lib/internal-identity"
import { NextResponse } from "next/server"
import { buildBriefing, buildInsights, customerTotalOf, dealTotals, fmtZar, topDeals } from "@/lib/overview-derive"

/**
 * Real headline stats for the Dashboard Overview, computed from the actual
 * backend services (sales, crm) instead of the Supabase module_data blob
 * (see app/api/modules/[module]/route.ts). Added 2026-09-22 when the blob
 * became unreachable (its Supabase project was paused) -- rather than patch
 * around that specific outage, this replaces the two stats that ARE
 * computable from real data (revenue, subscribers) with genuine numbers, and
 * is honest ("—") where a source is unreachable. The Overview page itself now
 * reads each tile from its own service client-side (see lib/overview-api.ts)
 * so it can distinguish loading / not running / error; this route stays as a
 * real-data-only server aggregate (no invented suggestions or capabilities).
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
  const tenantId = request.headers.get("x-tenant-id") || (devFallbackAllowed() ? DEV_TENANT_ID : "")
  const h: Record<string, string> = tenantId ? { "x-tenant-id": tenantId } : {}
  // proxy.ts injects the verified x-user-id; backends reject a tenant without a user.
  const userId = request.headers.get("x-user-id")
  if (userId) h["x-user-id"] = userId
  if (auth) h["authorization"] = auth
  return h
}

async function fetchJson(url: string, headers: HeadersInit): Promise<unknown | null> {
  try {
    const res = await signedFetch(url, { headers, cache: "no-store", signal: AbortSignal.timeout(1500) })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export async function GET(request: Request) {
  const headers = headersFor(request)

  const [deals, customers, crmInsights] = await Promise.all([
    fetchJson(`${SALES_SERVICE_URL}/deals`, headers),
    fetchJson(`${CRM_SERVICE_URL}/customers?page=1&page_size=1`, headers),
    fetchJson(`${CRM_SERVICE_URL}/customers/insights`, headers),
  ])

  const dealsArr: any[] | null = Array.isArray(deals) ? deals : null
  const customerCount = customerTotalOf(customers)
  const t = dealsArr ? dealTotals(dealsArr) : null

  // Only tiles computable from the sales + crm services. Tickets, uptime and the
  // rest are NOT reported here: the Overview page reads them from their own
  // services with explicit loading / not-running states.
  const stats: Stat[] = [
    {
      id: "revenue",
      title: "Won Revenue",
      value: t ? fmtZar(t.wonValue) : "—",
      change: "",
      changeType: "neutral",
      iconKey: "revenue",
      description: t ? `${t.won} won of ${t.count} deals` : "sales service unavailable",
    },
    {
      id: "subscribers",
      title: "Active Customers",
      value: customerCount !== null ? customerCount.toLocaleString("en-ZA") : "—",
      change: "",
      changeType: "neutral",
      iconKey: "subscribers",
      description: customerCount !== null ? "from CRM" : "crm service unavailable",
    },
  ]

  const recs =
    crmInsights && typeof crmInsights === "object" && Array.isArray((crmInsights as any).aiRecommendations)
      ? (crmInsights as any).aiRecommendations
      : null

  return NextResponse.json({
    stats,
    recentDeals: dealsArr ? topDeals(dealsArr, 4) : null,
    executiveSummary: buildBriefing(dealsArr, customerCount),
    aiSuggestions: buildInsights(dealsArr, recs),
    sources: { deals: dealsArr !== null, customers: customerCount !== null, insights: recs !== null },
  })
}
