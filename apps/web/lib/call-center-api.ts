const API_BASE = "/svc/call-center"
const TENANT_ID = "00000000-0000-0000-0000-000000000001"
const headers = { "x-tenant-id": TENANT_ID, "Content-Type": "application/json" }

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}`)
  }
  return response.json() as Promise<T>
}

// ── Agents ──────────────────────────────────────────────────────────────────

export async function listAgents(params?: { status?: string }): Promise<any> {
  const url = new URL(`${API_BASE}/agents`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3000")
  if (params?.status) url.searchParams.set("status", params.status)
  const res = await fetch(url.toString(), { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function createAgent(data: {
  name: string
  extension: string
  status?: string
  daily_sales?: number
  mttr_minutes?: number
  csat_score?: number
  skills?: string[]
}): Promise<any> {
  const res = await fetch(`${API_BASE}/agents`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function getAgent(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/agents/${id}`, { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function updateAgent(id: string, data: any): Promise<any> {
  const res = await fetch(`${API_BASE}/agents/${id}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

// ── Queues ───────────────────────────────────────────────────────────────────

export async function listQueues(params?: { direction?: string; status?: string }): Promise<any> {
  const url = new URL(`${API_BASE}/queues`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3000")
  if (params?.direction) url.searchParams.set("direction", params.direction)
  if (params?.status) url.searchParams.set("status", params.status)
  const res = await fetch(url.toString(), { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function createQueue(data: {
  name: string
  direction: string
  category: string
  routing_strategy?: string
  priority?: number
  max_wait_seconds?: number
  required_skills?: string[]
}): Promise<any> {
  const res = await fetch(`${API_BASE}/queues`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function getQueue(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/queues/${id}`, { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function updateQueue(id: string, data: any): Promise<any> {
  const res = await fetch(`${API_BASE}/queues/${id}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function deleteQueue(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/queues/${id}`, {
    method: "DELETE",
    headers,
  })
  return handleResponse(res)
}

export async function getQueueStats(queueId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/queues/${queueId}/stats`, { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function getQueuesDashboard(): Promise<any> {
  const res = await fetch(`${API_BASE}/queues/dashboard/summary`, { headers, cache: "no-store" })
  return handleResponse(res)
}

// ── Sessions ─────────────────────────────────────────────────────────────────

export async function listSessions(params?: { direction?: string; agent_id?: string }): Promise<any> {
  const url = new URL(`${API_BASE}/sessions`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3000")
  if (params?.direction) url.searchParams.set("direction", params.direction)
  if (params?.agent_id) url.searchParams.set("agent_id", params.agent_id)
  const res = await fetch(url.toString(), { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function createSession(data: {
  agent_id: string
  customer_id?: string
  direction?: string
  queue_id?: string
  start_time: string
}): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function getSession(id: string): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${id}`, { headers, cache: "no-store" })
  return handleResponse(res)
}

export async function endSession(
  id: string,
  data: {
    end_time: string
    duration_seconds: number
    outcome?: string
    notes?: string
  }
): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${id}/end`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function updateLiveTranscript(sessionId: string, transcript: string): Promise<any> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/live-transcript`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ transcript }),
  })
  return handleResponse(res)
}

// ── Whisper ──────────────────────────────────────────────────────────────────

export async function createWhisperSession(data: {
  call_session_id: string
  agent_id: string
  language?: string
}): Promise<any> {
  const res = await fetch(`${API_BASE}/whisper/sessions`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  })
  return handleResponse(res)
}

export async function stopWhisperSession(whisperId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/whisper/sessions/${whisperId}/stop`, {
    method: "PUT",
    headers,
  })
  return handleResponse(res)
}

// ── Customer 360 ────────────────────────────────────────────────────────────

export async function getCustomer360(customerId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/customer-360/${customerId}`, { headers, cache: "no-store" })
  return handleResponse(res)
}

// ── Analytics ────────────────────────────────────────────────────────────────

export async function getSentimentAnalytics(): Promise<any> {
  const res = await fetch(`${API_BASE}/analytics/sentiment`, { headers, cache: "no-store" })
  return handleResponse(res)
}

// ── Whisper WebSocket helper ─────────────────────────────────────────────────

export function getWhisperWsUrl(callSessionId: string, agentId: string, language: string = "en"): string {
  const protocol = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:"
  const host = typeof window !== "undefined" ? window.location.host : "localhost:3000"
  return `${protocol}//${host}/svc/call-center/ws/whisper/${callSessionId}?tenant_id=${TENANT_ID}&agent_id=${agentId}&language=${language}`
}
