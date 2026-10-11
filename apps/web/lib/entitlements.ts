export type Entitlements = {
  valid: boolean
  customer_id?: string
  plan?: string
  modules: string[]
  limits?: Record<string, number>
  issued_at?: string
  expires_at?: string
}

export const DEFAULT_ENTITLEMENTS: Entitlements = {
  valid: false,
  modules: ["overview", "admin"],
}

export const moduleBySection: Record<string, string> = {
  overview: "overview",
  communication: "communication",
  sales: "sales",
  crm: "crm",
  service: "support",
  retention: "retention",
  network: "network",
  "call-center": "call_center",
  marketing: "marketing",
  compliance: "compliance",
  talent: "hr",
  billing: "billing",
  finance: "finance",
  products: "products",
  portal: "portal",
  analytics: "analytics",
  inventory: "inventory",
  iot: "iot",
  rica: "rica",
  admin: "admin",
}

export function isModuleEnabled(modules: string[], moduleId: string): boolean {
  if (moduleId === "overview" || moduleId === "admin") return true
  if (!modules || modules.length === 0) {
    return false
  }
  return modules.includes(moduleId)
}

// Sections that are never gated by the module catalog.
const ALWAYS_ON = ["overview", "admin"]

type TenantModuleRow = { module_name?: string; key?: string; enabled?: boolean }

/**
 * Entitlements come from the admin service's tenant-scoped module read
 * (GET /tenants/{own tenant}/modules, readable by tenant members), reached via the gated
 * same-origin /api/admin proxy. The gateway has no /entitlements route.
 *
 * A failed lookup shows only Overview until access can be verified.
 */
export async function fetchEntitlements(): Promise<Entitlements> {
  try {
    const whoRes = await fetch("/api/whoami", { cache: "no-store", signal: AbortSignal.timeout(10_000) })
    if (!whoRes.ok) return DEFAULT_ENTITLEMENTS
    const who = (await whoRes.json()) as { tenant_id?: string; roles?: string[]; is_platform_admin?: boolean }
    if (who.is_platform_admin || who.roles?.includes("platform_admin")) return { valid: true, modules: Object.values(moduleBySection) }
    if (!who.tenant_id) return DEFAULT_ENTITLEMENTS
    const res = await fetch(`/api/admin/tenants/${encodeURIComponent(who.tenant_id)}/modules`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    })
    if (!res.ok) return DEFAULT_ENTITLEMENTS
    const rows = (await res.json()) as TenantModuleRow[]
    if (!Array.isArray(rows) || rows.length === 0) return DEFAULT_ENTITLEMENTS
    return { valid: true, modules: entitledModuleIds(rows) }
  } catch {
    return DEFAULT_ENTITLEMENTS
  }
}

export function entitledModuleIds(rows: TenantModuleRow[]): string[] {
  const enabled = rows.filter((r) => r.enabled).map((r) => r.module_name || r.key || "")
  return Array.from(new Set([...enabled, ...ALWAYS_ON]))
}
