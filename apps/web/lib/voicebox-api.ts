import { supabase } from "@/lib/supabase/client"

const API_BASE = "/svc/voicebox"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"
const FALLBACK_USER_ID = "00000000-0000-0000-0000-000000000002"

async function getTenantId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return (
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  )
}

async function getUserId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return data.session?.user?.id ?? FALLBACK_USER_ID
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const [tenantId, userId] = await Promise.all([getTenantId(), getUserId()])
  return { "x-tenant-id": tenantId, "x-user-id": userId }
}

async function makeHeaders(): Promise<Record<string, string>> {
  return { ...(await getAuthHeaders()), "Content-Type": "application/json" }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

// ── Types ───────────────────────────────────────────────────────────────────

export type VoiceType = "cloned" | "preset" | "designed"

export interface VoiceProfile {
  id: string
  tenant_id: string
  name: string
  description: string | null
  language: string
  voice_type: VoiceType
  engine: string | null
  engine_profile_id: string | null
  status: "pending" | "ready" | "failed"
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface VoicePersonality {
  id: string
  tenant_id: string
  name: string
  description: string | null
  style_prompt: string | null
  default_voice_profile_id: string | null
  created_at: string | null
}

export type BindingScope = "call_center_agent" | "orchestrator_agent_type" | "webchat_bot"

export interface AgentVoiceBinding {
  id: string
  tenant_id: string
  scope: BindingScope
  scope_ref: string
  voice_profile_id: string
  personality_id: string | null
}

export interface PresetVoice {
  voice_id: string
  name: string
  gender: string
  language: string
}

// ── Voices ──────────────────────────────────────────────────────────────────

export async function listVoices(voiceType?: VoiceType): Promise<VoiceProfile[]> {
  const url = new URL(`${API_BASE}/voices`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3000")
  if (voiceType) url.searchParams.set("voice_type", voiceType)
  const res = await fetch(url.toString(), { headers: await makeHeaders(), cache: "no-store" })
  return handleResponse(res)
}

export async function cloneVoice(data: {
  name: string
  description?: string
  language?: string
  engine?: string
  reference_text: string
  sample: File | Blob
}): Promise<VoiceProfile> {
  const form = new FormData()
  form.append("name", data.name)
  if (data.description) form.append("description", data.description)
  form.append("language", data.language ?? "en")
  if (data.engine) form.append("engine", data.engine)
  form.append("reference_text", data.reference_text)
  form.append("sample", data.sample, "sample.webm")

  const res = await fetch(`${API_BASE}/voices/clone`, {
    method: "POST",
    headers: await getAuthHeaders(),
    body: form,
  })
  return handleResponse(res)
}

export async function createPresetVoice(data: {
  name: string
  description?: string
  language?: string
  preset_engine: string
  preset_voice_id: string
}): Promise<VoiceProfile> {
  const res = await fetch(`${API_BASE}/voices/preset`, {
    method: "POST",
    headers: await makeHeaders(),
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function listPresetVoices(engine: string): Promise<{ engine: string; voices: PresetVoice[] }> {
  const res = await fetch(`${API_BASE}/voices/presets/${engine}`, { headers: await makeHeaders(), cache: "no-store" })
  return handleResponse(res)
}

export async function deleteVoice(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/voices/${id}`, { method: "DELETE", headers: await makeHeaders() })
  if (!res.ok && res.status !== 204) throw new Error(await res.text())
}

// ── Personalities ───────────────────────────────────────────────────────────

export async function listPersonalities(): Promise<VoicePersonality[]> {
  const res = await fetch(`${API_BASE}/personalities`, { headers: await makeHeaders(), cache: "no-store" })
  return handleResponse(res)
}

export async function createPersonality(data: {
  name: string
  description?: string
  style_prompt?: string
  default_voice_profile_id?: string
}): Promise<VoicePersonality> {
  const res = await fetch(`${API_BASE}/personalities`, {
    method: "POST",
    headers: await makeHeaders(),
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function updatePersonality(id: string, data: Partial<{
  name: string
  description: string
  style_prompt: string
  default_voice_profile_id: string
}>): Promise<VoicePersonality> {
  const res = await fetch(`${API_BASE}/personalities/${id}`, {
    method: "PUT",
    headers: await makeHeaders(),
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function deletePersonality(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/personalities/${id}`, { method: "DELETE", headers: await makeHeaders() })
  if (!res.ok && res.status !== 204) throw new Error(await res.text())
}

// ── Bindings ─────────────────────────────────────────────────────────────────

export async function setBinding(data: {
  scope: BindingScope
  scope_ref: string
  voice_profile_id: string
  personality_id?: string
}): Promise<AgentVoiceBinding> {
  const res = await fetch(`${API_BASE}/bindings`, {
    method: "PUT",
    headers: await makeHeaders(),
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function listBindings(params?: { scope?: BindingScope; scope_ref?: string }): Promise<AgentVoiceBinding[]> {
  const url = new URL(`${API_BASE}/bindings`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3000")
  if (params?.scope) url.searchParams.set("scope", params.scope)
  if (params?.scope_ref) url.searchParams.set("scope_ref", params.scope_ref)
  const res = await fetch(url.toString(), { headers: await makeHeaders(), cache: "no-store" })
  return handleResponse(res)
}

// ── Speak / Transcribe ───────────────────────────────────────────────────────

export async function speak(data: {
  text: string
  voice_profile_id?: string
  scope?: BindingScope
  scope_ref?: string
  personality_id?: string
  use_personality?: boolean
  requested_by_service?: string
}): Promise<Blob> {
  const res = await fetch(`${API_BASE}/speak`, {
    method: "POST",
    headers: await makeHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.blob()
}

export async function transcribe(audio: File | Blob, language?: string): Promise<{ text: string; duration: number }> {
  const form = new FormData()
  form.append("file", audio, "audio.webm")
  if (language) form.append("language", language)

  const res = await fetch(`${API_BASE}/transcribe`, {
    method: "POST",
    headers: await getAuthHeaders(),
    body: form,
  })
  return handleResponse(res)
}
