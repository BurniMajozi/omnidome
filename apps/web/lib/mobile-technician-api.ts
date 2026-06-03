"use client"

/**
 * Mobile Technician API client.
 * Aggregates data from Support, Network, IoT, Inventory services.
 */

const API = "/api"

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export interface TechJob {
  id: string
  ticket_id?: string
  customer_name: string
  customer_phone: string
  customer_address: string
  subject: string
  description: string
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT"
  status: "OPEN" | "IN_PROGRESS" | "ON_HOLD" | "CLOSED"
  category: string
  created_at: string
  scheduled_date?: string
  fno_reference?: string
}

export interface TechDevice {
  id: string
  device_name: string
  device_type: string
  mac_address?: string
  serial_number?: string
  status: "ONLINE" | "OFFLINE" | "MAINTENANCE"
  firmware_version?: string
  last_seen?: string
  rx_power_dbm?: number
  tx_power_dbm?: number
  temperature_c?: number
}

export interface TechInventoryItem {
  id: string
  sku: string
  name: string
  soh: number
  allocated: number
  available: number
  warehouse_name: string
}

export interface SpeedTestResult {
  download_mbps: number
  upload_mbps: number
  latency_ms: number
  jitter_ms: number
  timestamp: string
}

export interface JobCompletionData {
  job_id: string
  resolution_notes: string
  parts_used: Array<{ product_id: string; quantity: number }>
  speed_test?: SpeedTestResult
  photos?: string[]
  customer_signature?: string
  fcr: boolean
}

// ── API methods ──────────────────────────────────────────────────────

export const technicianApi = {
  // Job queue
  getMyJobs: (params?: { status?: string; priority?: string }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set("status", params.status)
    if (params?.priority) q.set("priority", params.priority)
    return fetchJSON<TechJob[]>(`/support/tickets?${q}`)
  },

  getJob: (jobId: string) =>
    fetchJSON<TechJob>(`/support/tickets/${jobId}`),

  acceptJob: (jobId: string) =>
    fetchJSON<{ status: string }>(`/support/tickets/${jobId}/accept`, { method: "POST" }),

  startJob: (jobId: string) =>
    fetchJSON<{ status: string }>(`/support/tickets/${jobId}/start`, { method: "POST" }),

  completeJob: (data: JobCompletionData) =>
    fetchJSON<{ status: string; commission_earned?: number }>(`/support/tickets/${data.job_id}/resolve`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  escalateJob: (jobId: string, reason: string) =>
    fetchJSON<{ status: string }>(`/support/tickets/${jobId}/escalate-fno`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // Customer devices at site
  getCustomerDevices: (contactId: string) =>
    fetchJSON<TechDevice[]>(`/iot/devices?contact_id=${contactId}`),

  getDeviceSignal: (deviceId: string) =>
    fetchJSON<{ rx_power_dbm: number; tx_power_dbm: number; temperature_c: number; measured_at: string }>(
      `/iot/devices/${deviceId}/signal`
    ),

  rebootDevice: (deviceId: string) =>
    fetchJSON<{ status: string }>(`/iot/devices/${deviceId}/reboot`, { method: "POST" }),

  // RADIUS account check
  getRadiusAccount: (contactId: string) =>
    fetchJSON<{
      username: string
      status: string
      profile_name: string
      static_ip?: string
    }>(`/network/radius-accounts?contact_id=${contactId}`),

  // Inventory — check parts availability
  checkParts: (sku: string) =>
    fetchJSON<TechInventoryItem[]>(`/inventory/stock?sku=${encodeURIComponent(sku)}`),

  checkoutParts: (data: { job_id: string; items: Array<{ product_id: string; quantity: number }> }) =>
    fetchJSON<{ status: string; reference: string }>("/inventory/stock/checkout", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Speed test (runs from gateway)
  runSpeedTest: () =>
    fetchJSON<SpeedTestResult>("/network/speed-test", { method: "POST" }),

  // My stats
  getMyStats: () =>
    fetchJSON<{
      jobs_today: number
      jobs_week: number
      avg_resolution_min: number
      fcr_rate: number
      customer_rating: number
      revenue_generated: number
    }>(`/support/technicians/me/stats`),
}
