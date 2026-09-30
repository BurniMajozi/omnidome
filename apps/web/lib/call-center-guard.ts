import { NextResponse } from "next/server"
import { CALL_CENTER_SIMULATED_TELEPHONY_ENABLED } from "@/lib/flags"

/**
 * The call-center routes keep module-level in-memory demo stores (seeded fake
 * CDRs, invoices, hardware). They must not be reachable unless a deployment
 * explicitly enables simulated telephony (same flag the UI uses), and even then
 * a single tenant owns the demo data so tenants are never mixed.
 */

export interface GuardResult {
  status: number
  error: string
}

/** Pure decision: null = allowed. `owner` holds the tenant that claimed the demo stores. */
export function decideSimulatedAccess(
  enabled: boolean,
  tenantId: string | null,
  owner: { tenantId: string | null },
): GuardResult | null {
  if (!enabled) return { status: 404, error: "Not found" }
  if (!tenantId) return { status: 401, error: "Tenant identity required" }
  if (owner.tenantId === null) owner.tenantId = tenantId
  if (owner.tenantId !== tenantId) return { status: 403, error: "Simulated telephony demo data belongs to another tenant" }
  return null
}

const OWNER_KEY = "__omnidome_call_center_demo_owner__"
function sharedOwner(): { tenantId: string | null } {
  const g = globalThis as unknown as Record<string, { tenantId: string | null }>
  return (g[OWNER_KEY] ??= { tenantId: null })
}

/** Returns a response to send when the request must not reach the demo stores, else null. */
export function simulatedTelephonyGuard(req: Request): NextResponse | null {
  const denied = decideSimulatedAccess(
    CALL_CENTER_SIMULATED_TELEPHONY_ENABLED,
    req.headers.get("x-tenant-id"),
    sharedOwner(),
  )
  return denied ? NextResponse.json({ error: denied.error }, { status: denied.status }) : null
}
