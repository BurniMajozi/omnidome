// Technician App — Shared TypeScript Types
// Mirrors the mobile-technician-api.ts types for standalone use

export interface TechJob {
  id: string
  tenant_id: string
  customer_id: string
  subject: string
  description: string | null
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT"
  status: "OPEN" | "IN_PROGRESS" | "ON_HOLD" | "CLOSED" | "ESCALATED"
  category: string | null
  assigned_to: string | null
  external_fno_ref: string | null
  is_fcr: boolean
  resolution_notes: string | null
  resolved_at: string | null
  created_at: string
  updated_at: string | null
  // Enriched from CRM
  customer_name?: string
  customer_phone?: string
  customer_address?: string
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

export interface TechStats {
  jobs_today: number
  jobs_week: number
  avg_resolution_min: number
  fcr_rate: number
  customer_rating: number
  revenue_generated: number
}

export interface SSSEvent {
  event: string
  data: unknown
}

export interface DeviceSignal {
  rx_power_dbm: number
  tx_power_dbm: number
  temperature_c: number
  measured_at: string
}

export interface RadiusAccount {
  username: string
  status: string
  profile_name: string
  static_ip?: string
}
