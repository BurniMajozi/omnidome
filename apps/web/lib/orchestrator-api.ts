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

import { getSessionSafe } from "@/lib/supabase/client"

const ORCHESTRATOR_BASE = "/api/orchestrator"

// Attaches the current Supabase session as a Bearer token so the orchestrator
// proxy can resolve real {user_id, tenant_id} identity server-side.
async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await getSessionSafe()
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
  /** Per-tool policy (spec A6): reads vs changes data, approval, timeout, output cap. */
  tool_policies?: ToolPolicyInfo[]
  /** Models the agent's own loop uses (MCP specialist, workflows): primary then fallbacks. */
  specialist_models?: string[]
}

export interface ToolPolicyInfo {
  name: string
  mutates: boolean
  requires_approval: boolean
  timeout_s: number
  max_output_chars: number
}

/** GET /api/usage/llm (spec A7). */
export interface AgentUsage {
  agent_type: string
  turns: number
  tool_calls: number
  tokens: number
  avg_duration_ms: number | null
  stopped_step_limit: number
  stopped_empty: number
  stopped_truncated: number
  ai_unavailable: number
}

export interface ModelUsage {
  model: string
  calls: number
  tokens: number
  failures: number
  avg_latency_ms: number | null
}

export interface LlmUsage {
  days: number
  agents: AgentUsage[]
  models: ModelUsage[]
}

export interface WorkflowNode {
  id: string
  type: string
  name?: string
  config?: Record<string, unknown>
}

export interface Workflow {
  id: string
  name: string
  description?: string | null
  definition: { nodes?: WorkflowNode[]; edges?: { from: string; to: string }[] }
  status: string
  schedule_cron?: string | null
  schedule_enabled?: boolean
  trigger_event?: string | null
  last_run_at?: string | null
}

export interface WorkflowRunSummary {
  id: string
  status: string
  trigger: string
  started_at: string | null
  finished_at: string | null
  error: string | null
}

export interface WorkflowRunDetail {
  id: string
  status: string
  input: Record<string, unknown> | null
  output: Record<string, unknown> | null
  error: string | null
  steps: { node_id: string; node_type: string; status: string; output: unknown; error: string | null }[]
}

/** Event types workflows can start on (bus events published today). */
export const KNOWN_EVENT_TYPES: { type: string; label: string }[] = [
  { type: "portal.cart.abandoned", label: "Portal: basket abandoned" },
  { type: "portal.quote.requested", label: "Portal: quote requested" },
  { type: "portal.registration.inactive", label: "Portal: registration inactive" },
  { type: "sales.lead.created", label: "Sales: lead created" },
  { type: "sales.lead.stage_changed", label: "Sales: lead stage changed" },
  { type: "sales.lead.assigned", label: "Sales: lead assigned" },
  { type: "sales.lead.escalated", label: "Sales: lead escalated" },
  { type: "sales.lead.outbound_requested", label: "Sales: sent to outbound agent" },
  { type: "sales.lead.campaign_requested", label: "Sales: sent to marketing campaign" },
  { type: "sales.deal.stage_changed", label: "Sales: deal moved on the board" },
  { type: "sales.deal.won", label: "Sales: deal won" },
  { type: "sales.deal.lost", label: "Sales: deal lost" },
]

export interface AgentMessage {
  id?: string
  role: "user" | "assistant" | "system" | "tool"
  content: string
  tool_calls?: { name: string; arguments?: Record<string, unknown> }[] | unknown[]
  tool_results?: unknown[]
}

export interface AgentInvokeRequest {
  agent_type: string
  message: string
  prompt?: string
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
  title?: string
  last_message?: string
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
  assistant: {
    name: "OmniAssist",
    description: "Versatile internal assistant. Drafts docs, emails, plans, SQL, and code into the editable canvas.",
    icon: "✨",
    color: "cyan",
  },
}

// ── API functions ────────────────────────────────────────────────────────

export async function listAgents(): Promise<AgentInfo[]> {
  // authFetch attaches the Supabase bearer; the orchestrator proxy resolves
  // identity ONLY from that header (not cookies), so a plain fetch here 401s.
  const res = await authFetch(`${ORCHESTRATOR_BASE}/agents`)
  if (!res.ok) throw new Error(`Failed to list agents: ${res.status}`)
  return res.json()
}

export async function invokeAgent(req: AgentInvokeRequest): Promise<AgentInvokeResponse> {
  const payload = {
    ...req,
    prompt: req.prompt || req.message,
    message: req.message || req.prompt,
  }
  const res = await authFetch(`${ORCHESTRATOR_BASE}/agents/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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
  const res = await authFetch(`${ORCHESTRATOR_BASE}/conversations/${conversationId}`)
  if (!res.ok) throw new Error(`Failed to load conversation: ${res.status}`)
  return res.json()
}

export async function listConversations(agentType?: string, page = 1, pageSize = 20): Promise<{ items: ConversationRead[]; total: number; page: number; pages: number }> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (agentType) query.set("agent_type", agentType)
  const res = await authFetch(`${ORCHESTRATOR_BASE}/conversations?${query.toString()}`)
  if (!res.ok) throw new Error(`Failed to list conversations: ${res.status}`)
  return res.json()
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const res = await authFetch(`${ORCHESTRATOR_BASE}/conversations/${conversationId}`, {
    method: "DELETE",
  })
  if (!res.ok) throw new Error(`Failed to delete conversation: ${res.status}`)
}

export interface AgentActionAuditItem {
  id: string
  conversation_id: string
  agent_type: string
  tool_name: string
  tool_input: unknown
  tool_output: unknown
  success: boolean
  prompt?: string
  response?: string
  satisfaction?: "thumbs_up" | "thumbs_down" | null
  created_at: string
}

export async function listAgentActions(params?: { agentType?: string; limit?: number; since?: string }): Promise<{ items: AgentActionAuditItem[] }> {
  const query = new URLSearchParams()
  if (params?.agentType) query.set("agent_type", params.agentType)
  if (params?.limit) query.set("limit", String(params.limit))
  if (params?.since) query.set("since", params.since)
  const suffix = query.toString() ? `?${query.toString()}` : ""
  const res = await authFetch(`${ORCHESTRATOR_BASE}/agents/actions${suffix}`)
  if (!res.ok) throw new Error(`Failed to list agent actions: ${res.status}`)
  return res.json()
}

// ── Agent Satisfaction Feedback ─────────────────────────────────────────

export interface AgentFeedbackPayload {
  conversation_id?: string
  agent_type: string
  satisfaction: "thumbs_up" | "thumbs_down"
  prompt?: string
  response?: string
}

export async function recordAgentFeedback(payload: AgentFeedbackPayload): Promise<{ status: string }> {
  const res = await authFetch(`${ORCHESTRATOR_BASE}/agents/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Failed to record feedback: ${res.status} — ${err}`)
  }
  return res.json()
}

// ── Usage + workflows (Agent Manager / agent flow; spec A7) ─────────────

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authFetch(`${ORCHESTRATOR_BASE}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    let detail = text
    try { detail = JSON.parse(text)?.detail ?? text } catch { /* not JSON */ }
    throw new Error(detail || `Orchestrator error ${res.status}`)
  }
  return res.json()
}

export const getLlmUsage = (days = 7) => getJson<LlmUsage>(`/usage/llm?days=${days}`)

export const listWorkflows = () => getJson<{ data: Workflow[] }>("/workflows").then((r) => r.data ?? [])

export const updateWorkflow = (id: string, patch: Partial<Workflow>) =>
  getJson<Workflow>(`/workflows/${id}`, { method: "PUT", body: JSON.stringify(patch) })

export const listWorkflowRuns = (id: string) =>
  getJson<{ data: WorkflowRunSummary[] }>(`/workflows/${id}/runs`).then((r) => r.data ?? [])

export const getWorkflowRun = (runId: string) => getJson<WorkflowRunDetail>(`/workflows/runs/${runId}`)

/** Workflows with an agent step for this agent type (the agent's "flows"). */
export function workflowsUsingAgent(workflows: Workflow[], agentType: string): Workflow[] {
  return workflows.filter((w) =>
    (w.definition?.nodes ?? []).some((n) => n.type === "agent_invoke" && n.config?.agent_type === agentType))
}

