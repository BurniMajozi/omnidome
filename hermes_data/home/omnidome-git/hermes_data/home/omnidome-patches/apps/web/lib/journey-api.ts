"use client"

/**
 * Journey Engine API client.
 * Talks to the journey engine service via Next.js API proxy.
 */

const JOURNEY_API = "/api/journey-engine"

async function fetchJourney<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${JOURNEY_API}${path}`
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    cache: "no-store",
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || `Journey API error: ${res.status}`)
  }
  return res.json()
}

// Types
export interface Journey {
  id: string
  name: string
  description?: string
  trigger_event: string
  status: string
  priority: number
  offer_id?: string
  fallback_offer_id?: string
  channel: string
  ab_test_enabled: boolean
  times_triggered: number
  times_shown: number
  times_accepted: number
  times_rejected: number
  revenue_preserved: number
  rules?: JourneyRule[]
  created_at?: string
  updated_at?: string
}

export interface JourneyRule {
  id: string
  journey_id: string
  rule_group: number
  attribute: string
  operator: string
  value: Record<string, any>
  is_active: boolean
  sort_order: number
}

export interface Offer {
  id: string
  name: string
  description?: string
  offer_type: string
  parameters: Record<string, any>
  max_per_customer: number
  max_total_redemptions?: number
  total_redemptions: number
  estimated_cost_per_use?: number
  status: string
  created_at?: string
  updated_at?: string
}

export interface FunnelData {
  journey_id: string
  journey_name: string
  triggered: number
  shown: number
  accepted: number
  rejected: number
  acceptance_rate: number
  revenue_preserved: number
}

export interface OutcomeData {
  id: string
  customer_id: string
  outcome: string
  monthly_revenue_before: number
  monthly_revenue_after?: number
  discount_cost_zar: number
  retained_90d?: boolean
  response_time_seconds?: number
  created_at?: string
}

export interface ROIEntry {
  journey_id?: string
  journey_name: string
  total_events: number
  accepted: number
  acceptance_rate: number
  total_discount_cost: number
  revenue_at_risk: number
  roi_percent: number
}

export interface AttributeDef {
  name: string
  type: string
  description: string
}

export interface OperatorDef {
  op: string
  label: string
  types: string[]
}

export interface OfferTypeDef {
  type: string
  label: string
  params: Record<string, string>
}

// API functions
export const journeyApi = {
  // Journeys
  listJourneys: (tenantId: string, status?: string) =>
    fetchJourney<{ journeys: Journey[] }>(
      `/journeys?tenant_id=${tenantId}${status ? `&status=${status}` : ""}`
    ),

  getJourney: (id: string) =>
    fetchJourney<{ journey: Journey }>(`/journeys/${id}`),

  createJourney: (data: Partial<Journey> & { tenant_id: string }) =>
    fetchJourney<{ journey: Journey }>("/journeys", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateJourney: (id: string, data: Partial<Journey>) =>
    fetchJourney<{ journey: Journey }>(`/journeys/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteJourney: (id: string) =>
    fetchJourney<{ status: string }>(`/journeys/${id}`, { method: "DELETE" }),

  // Rules
  addRules: (journeyId: string, rules: Partial<JourneyRule>[]) =>
    fetchJourney<{ rules: JourneyRule[] }>(`/journeys/${journeyId}/rules`, {
      method: "POST",
      body: JSON.stringify(rules),
    }),

  updateRule: (ruleId: string, data: Partial<JourneyRule>) =>
    fetchJourney<{ rule: JourneyRule }>(`/rules/${ruleId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteRule: (ruleId: string) =>
    fetchJourney<{ status: string }>(`/rules/${ruleId}`, { method: "DELETE" }),

  // Offers
  listOffers: (tenantId: string, offerType?: string) =>
    fetchJourney<{ offers: Offer[] }>(
      `/offers?tenant_id=${tenantId}${offerType ? `&offer_type=${offerType}` : ""}`
    ),

  getOffer: (id: string) =>
    fetchJourney<{ offer: Offer }>(`/offers/${id}`),

  createOffer: (data: Partial<Offer> & { tenant_id: string }) =>
    fetchJourney<{ offer: Offer }>("/offers", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateOffer: (id: string, data: Partial<Offer>) =>
    fetchJourney<{ offer: Offer }>(`/offers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteOffer: (id: string) =>
    fetchJourney<{ status: string }>(`/offers/${id}`, { method: "DELETE" }),

  // Analytics
  getFunnel: (tenantId: string, journeyId?: string, days?: number) =>
    fetchJourney<{ funnel: FunnelData[] }>(
      `/analytics/funnel?tenant_id=${tenantId}${journeyId ? `&journey_id=${journeyId}` : ""}&days=${days || 30}`
    ),

  getOutcomes: (tenantId: string, journeyId?: string, limit?: number) =>
    fetchJourney<{ outcomes: OutcomeData[]; summary: any }>(
      `/analytics/outcomes?tenant_id=${tenantId}${journeyId ? `&journey_id=${journeyId}` : ""}&limit=${limit || 100}`
    ),

  getROI: (tenantId: string, days?: number) =>
    fetchJourney<{ roi: ROIEntry[] }>(
      `/analytics/roi?tenant_id=${tenantId}&days=${days || 30}`
    ),

  getAttributes: () =>
    fetchJourney<{
      attributes: AttributeDef[]
      operators: OperatorDef[]
      offer_types: OfferTypeDef[]
    }>("/attributes"),
}
