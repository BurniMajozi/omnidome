import { getSessionSafe } from "@/lib/supabase/client"
import { loadableFromStatus, type Loadable } from "@/lib/service-state"

/** Typed client for the call-center telephony endpoints (docs/call-center-telephony.md). */

const API_BASE = "/svc/call-center"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000002"

async function makeHeaders(): Promise<Record<string, string>> {
  const { data } = await getSessionSafe()
  const user = data.session?.user
  return {
    "x-tenant-id": user?.user_metadata?.tenant_id ?? user?.app_metadata?.tenant_id ?? FALLBACK_TENANT_ID,
    "x-user-id": user?.id ?? FALLBACK_USER_ID,
    "Content-Type": "application/json",
  }
}

export class TelephonyApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function parseError(res: Response): Promise<TelephonyApiError> {
  let code = "error"
  let message = `Request failed (HTTP ${res.status})`
  try {
    const body = await res.json()
    const d = body?.detail
    if (d && typeof d === "object" && !Array.isArray(d)) {
      code = d.code ?? code
      message = d.message ?? message
    } else if (typeof d === "string") {
      message = d
    }
  } catch {
    /* non-JSON error body */
  }
  return new TelephonyApiError(res.status, code, message)
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: await makeHeaders(),
    cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw await parseError(res)
  return (res.status === 204 ? undefined : await res.json()) as T
}

/** GET -> Loadable so the UI shows honest "not running / not permitted" states instead of fake data. */
async function load<T>(path: string): Promise<Loadable<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: await makeHeaders(), cache: "no-store" })
    if (!res.ok) {
      const err = await parseError(res)
      return loadableFromStatus<T>(res.status, undefined, err.message)
    }
    return loadableFromStatus<T>(res.status, (await res.json()) as T)
  } catch {
    return loadableFromStatus<T>(null, undefined)
  }
}

// ── types ───────────────────────────────────────────────────────────────

export type TrunkState =
  | "not_configured" | "config_error" | "pbx_unavailable" | "disabled" | "not_loaded"
  | "registered" | "reachable" | "unreachable" | "rejected" | "unregistered" | "stopped" | string

export interface TelephonyStatus {
  available: boolean
  bridge_connected: boolean
  enabled: boolean
  configured: boolean
  registered: boolean
  state: TrunkState
  detail: string
  mode: "registration" | "ip" | null
  last_error: string | null
  recording_effective: boolean
  allowed_prefixes: string[]
  host?: string
  port?: number
  transport?: string
  applied?: { changed: boolean; reloaded: boolean }
}

export interface TelephonySettings {
  tenant_id: string
  enabled: boolean
  dids: string[]
  inbound_queue_id: string | null
  allowed_prefixes: string[]
  blocked_prefixes: string[]
  max_concurrent_calls: number
  max_call_seconds: number
  max_calls_per_agent_hour: number
  recording_enabled: boolean
  recording_announcement_confirmed: boolean
  recording_effective: boolean
}

export type TelephonySettingsPatch = Partial<Omit<TelephonySettings, "tenant_id" | "recording_effective" | "inbound_queue_id">> & {
  inbound_queue_id?: string | null
}

export interface ActiveCall {
  id: string
  session_id: string | null
  direction: "INBOUND" | "OUTBOUND"
  state: "ringing" | "agent_ringing" | "dialing" | "announcing" | "connected" | "transferring" | "ended"
  number: string
  agent_id: string | null
  held: boolean
  recording: boolean
  started_at: string
  answered_at: string | null
  max_seconds: number
}

export interface WebrtcCredentials {
  sip_uri: string
  username: string
  password: string
  realm: string
  ws_url: string
  ice_servers: RTCIceServer[]
  display_name: string
  agent_id: string
  expires_at: string
  expires_in: number
}

export interface SipCredentialMeta {
  provider: string
  configured: boolean
  fields: string[]
  updated_at: string | null
}

export interface SipTrunkForm {
  host: string
  port?: string
  username?: string
  password?: string
  transport: "udp" | "tcp" | "tls"
  auth_mode: "registration" | "ip"
  caller_id?: string
}

// ── calls / softphone ───────────────────────────────────────────────────

export const getTelephonyStatus = () => load<TelephonyStatus>("/telephony/status")
export const requestWebrtcCredentials = () => request<WebrtcCredentials>("POST", "/telephony/agents/me/webrtc-credentials")
export const placeCall = (to: string) => request<ActiveCall>("POST", "/telephony/calls", { to })
export const listActiveCalls = () => request<ActiveCall[]>("GET", "/telephony/calls/active")
export const hangupCall = (id: string) => request<unknown>("POST", `/telephony/calls/${id}/hangup`)
export const holdCall = (id: string, on: boolean) => request<ActiveCall>("POST", `/telephony/calls/${id}/hold`, { on })
export const sendDtmf = (id: string, digits: string) => request<ActiveCall>("POST", `/telephony/calls/${id}/dtmf`, { digits })
export const transferCall = (id: string, target: { to_agent_id?: string; to_number?: string }) =>
  request<ActiveCall>("POST", `/telephony/calls/${id}/transfer`, target)

// ── admin settings ──────────────────────────────────────────────────────

export const getTelephonySettings = () => load<TelephonySettings>("/telephony/settings")
export const putTelephonySettings = (patch: TelephonySettingsPatch) => request<TelephonySettings>("PUT", "/telephony/settings", patch)
export const getTrunkStatusAdmin = () => load<TelephonyStatus>("/telephony/trunk/status")
export const testTrunkRegistration = () => request<TelephonyStatus>("POST", "/telephony/trunk/test")
export const getSipCredentialMeta = async (): Promise<Loadable<SipCredentialMeta | null>> => {
  const l = await load<SipCredentialMeta[]>("/provider-credentials")
  return l.state === "ready" ? { state: "ready", data: l.data.find((c) => c.provider === "sip") ?? null } : l
}
export const saveSipTrunk = (form: SipTrunkForm) => {
  const fields: Record<string, string> = { host: form.host.trim(), transport: form.transport, auth_mode: form.auth_mode }
  if (form.port?.trim()) fields.port = form.port.trim()
  if (form.username?.trim()) fields.username = form.username.trim()
  if (form.password) fields.password = form.password
  if (form.caller_id?.trim()) fields.caller_id = form.caller_id.trim()
  return request<SipCredentialMeta>("PUT", "/provider-credentials/sip", { fields })
}
export const removeSipTrunk = () => request<void>("DELETE", "/provider-credentials/sip")
