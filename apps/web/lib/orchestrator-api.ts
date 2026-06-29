/**
 * Agent Orchestrator API client.
 *
 * Wraps the orchestrator service (port 8021) which provides:
 *   - Agent invocation (sync + streaming)
 *   - Conversation persistence
 *   - Tool execution across all OmniDome microservices
 *   - AG-UI typed streaming events
 *   - A2UI component validation
 *   - UCP checkout sessions
 *   - AP2 payment mandates
 */

import { supabase } from "@/lib/supabase/client"

const ORCHESTRATOR_BASE = "/api/orchestrator"

// Attaches the current Supabase session as a Bearer token so the orchestrator
// proxy can resolve real {user_id, tenant_id} identity server-side.
async function authFetch(url: string, init: RequestInit): Promise<Response> {
  const { data } = await supabase.auth.getSession()
  const headers = new Headers(init.headers)
  if (data.session?.access_token) {
    headers.set("Authorization", `Bearer ${data.session.access_token}`)
  }
  return fetch(url, { ...init, headers })
}

// ── Types ────────────────────────────────────────────────────────────────

export interface AgentInfo {
  agent_type: string
  description: string
  llm: string
  tools: string[]
}

export interface AgentMessage {
  role: "user" | "assistant" | "system" | "tool"
  content: string
  tool_calls?: { name: string; arguments: Record<string, unknown> }[]
  tool_results?: unknown[]
}

export interface AgentInvokeRequest {
  agent_type: string
  message: string
  context?: Record<string, unknown>
  tenant_id?: string
  conversation_id?: string
}

export interface AgentInvokeResponse {
  conversation_id: string
  message: string
  tool_calls: { name: string; arguments: Record<string, unknown>; result: unknown }[]
  agent_type: string
  correlation_id?: string
}

export interface ConversationRead {
  id: string
  tenant_id: string
  agent_type: string
  channel: string
  status: string
  context: Record<string, unknown>
  created_at: string
  updated_at: string
  messages?: AgentMessage[]
}

// ── AG-UI Types ──────────────────────────────────────────────────────────

export type AGUIEventType =
  | "RUN_STARTED"
  | "TEXT_MESSAGE_CONTENT"
  | "TOOL_CALL_START"
  | "TOOL_CALL_RESULT"
  | "TOOL_CALL_END"
  | "MEMORY_WRITE"
  | "RUN_FINISHED"
  | "RUN_ERROR"

export interface AGUIEvent {
  type: AGUIEventType
  run_id: string
  tenant_id?: string
  conversation_id?: string
  timestamp: string
  data: Record<string, unknown>
}

export interface AGUIRunRequest {
  agent_type: string
  message: string
  context?: Record<string, unknown>
  conversation_id?: string
  stream_tokens?: boolean
}

export interface AGUIStreamState {
  runId: string
  status: "idle" | "running" | "finished" | "error"
  content: string
  toolCalls: ToolCallEvent[]
  memoryWrites: MemoryWriteEvent[]
  error?: string
}

export interface ToolCallEvent {
  runId: string
  toolCallId?: string
  toolName?: string
  arguments?: Record<string, unknown>
  result?: unknown
  status: "start" | "result" | "end"
}

export interface MemoryWriteEvent {
  runId: string
  correlationId?: string
  status?: string
}

// ── A2UI Types ───────────────────────────────────────────────────────────

export interface A2UIComponent {
  id: string
  component: Record<string, unknown>
}

export interface A2UIPayload {
  surface_id: string
  root: string
  components: A2UIComponent[]
  data?: Record<string, unknown>
}

export interface A2UIValidationResult {
  status: string
  surface_id: string
  components: number
}

// ── UCP Types ────────────────────────────────────────────────────────────

export interface UCPLineItem {
  item_id: string
  label: string
  quantity: number
  unit_amount: number
  currency: string
}

export interface UCPCheckoutSession {
  id: string
  status: string
  currency: string
  total: number
  merchant: string
  purpose: string
  line_items: UCPLineItem[]
  payment_mandate_id?: string
  created_at: string
  metadata?: Record<string, unknown>
}

export interface UCPCheckoutCreateRequest {
  merchant: string
  purpose: string
  line_items: UCPLineItem[]
  metadata?: Record<string, unknown>
}

// ── AP2 Types ────────────────────────────────────────────────────────────

export interface IntentMandate {
  id: string
  natural_language_description: string
  merchants: string[]
  max_amount: number
  currency: string
  expires_at: string
  requires_user_confirmation: boolean
  signed: boolean
  metadata?: Record<string, unknown>
}

export interface IntentMandateCreate {
  natural_language_description: string
  merchants?: string[]
  max_amount: number
  currency?: string
  expires_in_minutes?: number
  requires_user_confirmation?: boolean
  metadata?: Record<string, unknown>
}

export interface PaymentMandate {
  id: string
  intent_mandate_id: string
  payment_details_id: string
  merchant_agent: string
  amount: number
  currency: string
  label: string
  signed_authorization?: string
  status: string
  metadata?: Record<string, unknown>
}

export interface PaymentMandateCreate {
  intent_mandate_id: string
  payment_details_id: string
  merchant_agent: string
  amount: number
  currency?: string
  label: string
  signed_authorization?: string
  metadata?: Record<string, unknown>
}

export interface PaymentReceipt {
  id: string
  payment_mandate_id: string
  payment_id: string
  amount: number
  currency: string
  merchant_confirmation_id: string
  created_at: string
  metadata?: Record<string, unknown>
}

export interface PaymentReceiptCreate {
  payment_mandate_id: string
  payment_id: string
  amount: number
  currency?: string
  merchant_confirmation_id: string
  metadata?: Record<string, unknown>
}

// ── Agent catalog ────────────────────────────────────────────────────────

export const AGENT_CATALOG: Record<string, { name: string; description: string; icon: string; color: string }> = {
  customer_facing: {
    name: "DomeBot",
    description: "Customer-facing assistant. Handles balances, invoices, coverage checks, ticket creation.",
    icon: "🤖",
    color: "cyan",
  },
  retention: {
    name: "ChurnGuard",
    description: "Autonomous churn prediction and retention. Knows every customer's risk score and history.",
    icon: "🛡️",
    color: "purple",
  },
  provisioning: {
    name: "ProvisionBot",
    description: "Onboarding automation. Checks coverage, creates accounts, provisions services.",
    icon: "⚡",
    color: "green",
  },
  executive: {
    name: "InsightBot",
    description: "Executive briefings. MRR, churn, ARPU, pipeline, financial summaries.",
    icon: "📊",
    color: "amber",
  },
  support: {
    name: "SupportBot",
    description: "Support ticket management and diagnostics. Full access to customer 360° data.",
    icon: "🔧",
    color: "blue",
  },
}

// ── API functions ────────────────────────────────────────────────────────

export async function listAgents(): Promise<AgentInfo[]> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/agents`)
  if (!res.ok) throw new Error(`Failed to list agents: ${res.status}`)
  return res.json()
}

export async function invokeAgent(req: AgentInvokeRequest): Promise<AgentInvokeResponse> {
  const res = await authFetch(`${ORCHESTRATOR_BASE}/agents/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Agent invocation failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function invokeAgentStream(
  req: AgentInvokeRequest,
  onToken: (token: string) => void,
  onDone: (fullResponse: AgentInvokeResponse) => void,
): Promise<void> {
  const res = await authFetch(`${ORCHESTRATOR_BASE}/agents/invoke/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Agent stream failed: ${res.status} — ${err}`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body")

  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n\n")
    buffer = lines.pop() || ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6)
        if (data === "[DONE]") continue
        onToken(data)
      }
    }
  }
}

// ── AG-UI Streaming Client ──────────────────────────────────────────────

export async function invokeAgentAGUI(
  req: AGUIRunRequest,
  onEvent: (event: AGUIEvent) => void,
): Promise<void> {
  const res = await authFetch(`${ORCHESTRATOR_BASE}/protocols/ag-ui/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`AG-UI run failed: ${res.status} — ${err}`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body")

  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n\n")
    buffer = lines.pop() || ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6)
        if (data === "[DONE]") continue
        try {
          const event: AGUIEvent = JSON.parse(data)
          onEvent(event)
        } catch {
          // Skip malformed events
        }
      }
    }
  }
}

// ── A2UI API ─────────────────────────────────────────────────────────────

export async function validateA2UI(payload: A2UIPayload): Promise<A2UIValidationResult> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/a2ui/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`A2UI validation failed: ${res.status} — ${err}`)
  }
  return res.json()
}

// ── UCP API ──────────────────────────────────────────────────────────────

export async function createUCPSession(req: UCPCheckoutCreateRequest): Promise<UCPCheckoutSession> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ucp/checkout-sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`UCP checkout failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function completeUCPSession(sessionId: string, paymentMandateId?: string): Promise<UCPCheckoutSession> {
  const url = new URL(`${ORCHESTRATOR_BASE}/protocols/ucp/checkout-sessions/${sessionId}/complete`)
  if (paymentMandateId) url.searchParams.set("payment_mandate_id", paymentMandateId)
  const res = await fetch(url.toString(), { method: "POST" })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`UCP complete failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function listUCPSessions(limit = 50): Promise<UCPCheckoutSession[]> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ucp/checkout-sessions?limit=${limit}`)
  if (!res.ok) throw new Error(`UCP list failed: ${res.status}`)
  return res.json()
}

// ── AP2 API ──────────────────────────────────────────────────────────────

export async function createIntentMandate(req: IntentMandateCreate): Promise<IntentMandate> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ap2/intent-mandates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`AP2 intent mandate failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function signIntentMandate(mandateId: string): Promise<IntentMandate> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ap2/intent-mandates/${mandateId}/sign`, {
    method: "POST",
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`AP2 sign failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function createPaymentMandate(req: PaymentMandateCreate): Promise<PaymentMandate> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ap2/payment-mandates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`AP2 payment mandate failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function createPaymentReceipt(req: PaymentReceiptCreate): Promise<PaymentReceipt> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ap2/payment-receipts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`AP2 receipt failed: ${res.status} — ${err}`)
  }
  return res.json()
}

export async function listIntentMandates(limit = 50): Promise<IntentMandate[]> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ap2/intent-mandates?limit=${limit}`)
  if (!res.ok) throw new Error(`AP2 list failed: ${res.status}`)
  return res.json()
}

export async function listPaymentMandates(limit = 50): Promise<PaymentMandate[]> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/protocols/ap2/payment-mandates?limit=${limit}`)
  if (!res.ok) throw new Error(`AP2 list failed: ${res.status}`)
  return res.json()
}

// ── Conversation API ─────────────────────────────────────────────────────

export async function getConversation(conversationId: string): Promise<ConversationRead> {
  const res = await fetch(`${ORCHESTRATOR_BASE}/conversations/${conversationId}`)
  if (!res.ok) throw new Error(`Failed to load conversation: ${res.status}`)
  return res.json()
}

export async function listConversations(agentType?: string): Promise<ConversationRead[]> {
  const url = new URL(`${ORCHESTRATOR_BASE}/conversations`, window.location.origin)
  if (agentType) url.searchParams.set("agent_type", agentType)
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`Failed to list conversations: ${res.status}`)
  return res.json()
}
