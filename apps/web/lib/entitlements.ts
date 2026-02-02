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
  valid: true,
  modules: [],
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
  talent: "talent",
  billing: "billing",
  products: "products",
  portal: "portal",
}

export function isModuleEnabled(modules: string[], moduleId: string): boolean {
  if (!modules || modules.length === 0) {
    return true
  }
  return modules.includes(moduleId)
}

export async function fetchEntitlements(): Promise<Entitlements> {
  const base = process.env.NEXT_PUBLIC_GATEWAY_URL?.replace(/\/$/, "") || ""
  const res = await fetch(`${base}/entitlements`, { cache: "no-store" })
  if (!res.ok) {
    return DEFAULT_ENTITLEMENTS
  }
  const data = (await res.json()) as Entitlements
  if (!Array.isArray(data.modules)) {
    data.modules = []
  }
  return data
}
