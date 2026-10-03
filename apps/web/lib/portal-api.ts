import type { PortalLandingPage } from "@/app/api/portal/pages/route"
import type { PortalAiAgent } from "@/app/api/portal/ai-agents/route"
import { getSessionSafe } from "@/lib/supabase/client"

export type { PortalLandingPage, PortalAiAgent }

async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await getSessionSafe()
  const headers = new Headers(init.headers)
  if (data.session?.access_token) {
    headers.set("Authorization", `Bearer ${data.session.access_token}`)
  }
  return fetch(url, { ...init, headers })
}

export interface PortalStats {
  websiteVisitors: number
  visitorsGrowth: string
  aiConversations: number
  aiResolutionRate: string
  fieldAgentsActive: number
  leadsToday: number
  dealsWonToday: number
  techniciansActive: number
  jobsCompletedToday: number
  averageJobTime: string
  customerRating: number
  visitorTraffic: Array<{
    day: string
    website: number
    customerPortal: number
    fieldApp: number
    techApp: number
  }>
  systemStatus: {
    mainWebsite: { url: string; status: string }
    aiChatSystem: { activeBots: number; status: string }
    fieldSalesApp: { version: string; status: string }
    technicianApp: { version: string; status: string }
  }
}

export async function fetchPortalPages(): Promise<PortalLandingPage[]> {
  const res = await authFetch("/api/portal/pages", { cache: "no-store" })
  if (!res.ok) throw new Error("Failed to fetch landing pages")
  const json = await res.json()
  return json.data || []
}

export async function createPortalPage(page: Partial<PortalLandingPage>): Promise<PortalLandingPage> {
  const res = await authFetch("/api/portal/pages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(page),
  })
  if (!res.ok) throw new Error("Failed to create landing page")
  const json = await res.json()
  return json.data
}

export async function updatePortalPage(
  id: string | number,
  updates: Partial<PortalLandingPage>
): Promise<PortalLandingPage> {
  const res = await authFetch("/api/portal/pages", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...updates, id }),
  })
  if (!res.ok) throw new Error("Failed to update landing page")
  const json = await res.json()
  return json.data
}

export async function deletePortalPage(id: string | number): Promise<void> {
  const res = await authFetch(`/api/portal/pages?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error("Failed to delete landing page")
}

export async function fetchPortalStats(): Promise<PortalStats | null> {
  try {
    const res = await authFetch("/api/portal/stats", { cache: "no-store" })
    if (!res.ok) return null
    const json = await res.json()
    return json.data
  } catch {
    return null
  }
}

export async function fetchAiAgents(): Promise<PortalAiAgent[]> {
  try {
    const res = await authFetch("/api/portal/ai-agents", { cache: "no-store" })
    if (!res.ok) return []
    const json = await res.json()
    return json.data || []
  } catch {
    return []
  }
}

export async function createAiAgent(agent: Partial<PortalAiAgent>): Promise<PortalAiAgent> {
  const res = await authFetch("/api/portal/ai-agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(agent),
  })
  if (!res.ok) throw new Error("Failed to create AI Agent")
  const json = await res.json()
  return json.data
}

export async function toggleAiAgentStatus(
  id: number | string,
  newStatus: "active" | "paused"
): Promise<PortalAiAgent> {
  const res = await authFetch("/api/portal/ai-agents", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, status: newStatus }),
  })
  if (!res.ok) throw new Error("Failed to update AI Agent")
  const json = await res.json()
  return json.data
}
