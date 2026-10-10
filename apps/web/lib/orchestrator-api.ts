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
  name?: string | null
  requested_model?: string | null
  employee_id?: string | null
  registration_status?: string | null
  /** Per-tool policy (spec A6): reads vs changes data, approval, timeout, output cap. */
  tool_policies?: ToolPolicyInfo[]
  /** Models the agent's own loop uses (MCP specialist, workflows): primary then fallbacks. */
  specialist_models?: string[]
  /** Allowlisted tables for the safe SQL tool (spec A9). */
  sql_table_allowlist?: string[]
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
  auto: {
    name: "OmniDome Orchestrator",
    description: "Smart Intent Router. Automatically analyzes your request and routes to the best specialist agent.",
    icon: "🧠",
    color: "violet",
  },
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
    try {
      const parsed = JSON.parse(text)?.detail ?? text
      // FastAPI validation errors arrive as [{loc, msg}]; show them as readable sentences.
      detail = Array.isArray(parsed)
        ? parsed.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).filter((p) => p !== "body").join(".")}${e.loc?.length ? ": " : ""}${e.msg ?? ""}`).join("; ")
        : parsed
    } catch { /* not JSON */ }
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

// ── Memory & Skills (SPEC M1-M5) ──────────────────────────────────────────

export interface MemoryEntry {
  id: string
  tenant_id: string
  source_type: string
  source_id?: string | null
  module?: string | null
  scope_key?: string | null
  title: string
  content: string
  summary?: string | null
  visibility: string
  importance: string
  tags: string[]
  metadata?: Record<string, unknown>
  occurred_at: string
  archived_at?: string | null
  created_at: string
}

export interface MemorySummary {
  id: string
  tenant_id: string
  scope_key: string
  module?: string | null
  title: string
  summary: string
  source_entry_ids: string[]
  updated_at: string
}

export interface MemoryRecallResult {
  summaries: MemorySummary[]
  entries: MemoryEntry[]
}

export type SkillScope = "platform" | "tenant" | "team" | "user"
export type SkillStatus = "draft" | "active" | "deprecated"
export type SkillSafety = "read_only" | "drafts_only" | "can_act"

export interface SkillInputDef {
  name: string
  type: "string" | "number" | "integer" | "boolean" | "date" | "list"
  description?: string
  required?: boolean
}

export interface SkillExample {
  title?: string
  input?: string
  output?: string
}

/** A skill as the API returns it (docs/skills.md). Legacy fields (guidance_prompt, is_active) are kept. */
export interface OKFSkill {
  id: string
  tenant_id?: string | null
  slug: string
  skill_name: string
  description: string
  instructions: string
  guidance_prompt: string
  category: string
  tags: string[]
  source_agent_type: string
  target_agent_types: string[]
  tools_required: string[]
  tools_optional: string[]
  inputs: SkillInputDef[]
  triggers: string[]
  examples: SkillExample[]
  safety_class: SkillSafety
  version: string
  changelog: string
  status: SkillStatus
  is_active: boolean
  scope: SkillScope
  visibility_roles: string[]
  forked_from_id?: string | null
  forked_from_version?: string | null
  usage_count: number
  helpful_count: number
  unhelpful_count: number
  last_used_at?: string | null
  created_at: string
  updated_at?: string
  can_edit?: boolean
  can_publish?: boolean
  import_warnings?: string[]
}

export interface SkillWriteInput {
  skill_name: string
  description: string
  instructions: string
  category?: string
  tags?: string[]
  target_agent_types?: string[]
  tools_required?: string[]
  tools_optional?: string[]
  inputs?: SkillInputDef[]
  triggers?: string[]
  examples?: SkillExample[]
  safety_class?: SkillSafety
  version?: string
  changelog?: string
  visibility_roles?: string[]
  scope?: SkillScope
  status?: "draft" | "active"
}

export interface SkillToolInfo {
  name: string
  description?: string
  mutates: boolean
  requires_approval: boolean
  soft?: boolean
}

export interface SkillsMeta {
  tools: SkillToolInfo[]
  tools_source?: "registry" | "snapshot"
  agent_types: string[]
  categories: string[]
  safety_classes: SkillSafety[]
  scopes: SkillScope[]
  statuses: SkillStatus[]
  caller: { admin: boolean; author: boolean }
}

export interface SkillImportPreview {
  ok: boolean
  skill: Partial<SkillWriteInput> | null
  errors: string[]
  warnings: string[]
}

export interface SkillVersionRow {
  id: string
  version: string
  status: SkillStatus
  changelog: string
  created_at: string
  updated_at: string
}

export interface SkillListParams {
  scope?: SkillScope
  status?: SkillStatus | "all"
  agent_type?: string
  category?: string
  safety_class?: SkillSafety
  q?: string
  mine?: boolean
}

export interface HousekeepingReport {
  dry_run: boolean
  executed_at: string
  duplicates_count: number
  duplicate_ids: string[]
  low_importance_count: number
  low_importance_ids: string[]
  groups_rolled_up: number
  entries_rolled_up: number
  total_archived: number
  rollups: Array<{
    module: string
    scope_key: string
    entry_count: number
    entry_ids: string[]
  }>
  new_summaries?: Array<{
    module: string
    scope_key: string
    summary: string
  }>
}

export interface CompactionStats {
  tenant_id: string
  compacted_conversations_count: number
  total_compaction_runs: number
}

export const recallMemory = (q?: string, module?: string) => {
  const params = new URLSearchParams()
  if (q) params.set("q", q)
  if (module) params.set("module", module)
  return getJson<MemoryRecallResult>(`/memory/recall?${params.toString()}`)
}

export const listMemoryEntries = (module?: string, includeArchived = false) => {
  const params = new URLSearchParams()
  if (module) params.set("module", module)
  if (includeArchived) params.set("include_archived", "true")
  return getJson<{ items: MemoryEntry[] }>(`/memory/entries?${params.toString()}`).then((r) => r.items ?? [])
}

export const createStrategyEntry = (entry: { title: string; content: string; agent_type?: string }) =>
  getJson<MemoryEntry>("/memory/strategy", {
    method: "POST",
    body: JSON.stringify(entry),
  })

export const archiveMemoryEntry = (id: string, archived = true) =>
  getJson<MemoryEntry>(`/memory/entries/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ archived }),
  })

export const listOKFSkills = (agentType?: string) => {
  const p = agentType ? `?agent_type=${encodeURIComponent(agentType)}` : ""
  return getJson<{ items: OKFSkill[] }>(`/memory/skills${p}`).then((r) => r.items ?? [])
}

/** Skills v2 list: platform library + organisation + team + my private skills, with filters (docs/skills.md). */
export const listSkills = (params: SkillListParams = {}) => {
  const qs = new URLSearchParams()
  if (params.scope) qs.set("scope", params.scope)
  qs.set("status", params.status ?? "all")
  if (params.agent_type) qs.set("agent_type", params.agent_type)
  if (params.category) qs.set("category", params.category)
  if (params.safety_class) qs.set("safety_class", params.safety_class)
  if (params.q) qs.set("q", params.q)
  if (params.mine) qs.set("mine", "true")
  return getJson<{ items: OKFSkill[] }>(`/memory/skills?${qs.toString()}`).then((r) => r.items ?? [])
}

export const getSkillsMeta = () => getJson<SkillsMeta>("/memory/skills/meta")

export const getSkillVersions = (skillId: string) =>
  getJson<{ items: SkillVersionRow[] }>(`/memory/skills/${skillId}/versions`).then((r) => r.items ?? [])

export const createSkill = (skill: SkillWriteInput) =>
  getJson<OKFSkill>("/memory/skills", {
    method: "POST",
    body: JSON.stringify({ ...skill, name: skill.skill_name, description: skill.description }),
  })

export const updateSkill = (skillId: string, skill: Partial<SkillWriteInput>) =>
  getJson<OKFSkill>(`/memory/skills/${skillId}`, { method: "PUT", body: JSON.stringify(skill) })

export const activateSkill = (skillId: string) =>
  getJson<OKFSkill>(`/memory/skills/${skillId}/activate`, { method: "POST" })

export const deprecateSkill = (skillId: string) =>
  getJson<OKFSkill>(`/memory/skills/${skillId}/deprecate`, { method: "POST" })

export const forkSkill = (skillId: string, scope: "user" | "tenant" = "user", skillName?: string) =>
  getJson<OKFSkill>(`/memory/skills/${skillId}/fork`, {
    method: "POST",
    body: JSON.stringify({ scope, skill_name: skillName || undefined }),
  })

export const shareSkill = (skillId: string) =>
  getJson<OKFSkill>(`/memory/skills/${skillId}/share`, { method: "POST" })

export const exportSkill = (skillId: string) =>
  getJson<{ filename: string; markdown: string }>(`/memory/skills/${skillId}/export`)

export const previewSkillImport = (markdown: string) =>
  getJson<SkillImportPreview>("/memory/skills/import/preview", { method: "POST", body: JSON.stringify({ markdown }) })

export const importSkill = (markdown: string, scope: "user" | "tenant" = "user") =>
  getJson<OKFSkill>("/memory/skills/import", { method: "POST", body: JSON.stringify({ markdown, scope }) })

export const sendSkillFeedback = (skillId: string, helpful: boolean) =>
  getJson<{ ok: boolean }>(`/memory/skills/${skillId}/feedback`, { method: "POST", body: JSON.stringify({ helpful }) })

export const createOKFSkill = (skill: { name: string; description: string; source_agent_type: string; target_agent_types: string[]; guidance_prompt: string; tools_required: string[] }) =>
  getJson<OKFSkill>("/memory/skills", { method: "POST", body: JSON.stringify(skill) })

export const deactivateOKFSkill = (skillId: string) =>
  getJson<{ status: string }>(`/memory/skills/${skillId}/deactivate`, { method: "POST" })

export const transferOKFSkill = (skillId: string, targetAgentType: string) =>
  getJson<{ status: string }>(`/memory/skills/${skillId}/transfer`, {
    method: "POST",
    body: JSON.stringify({ target_agent_type: targetAgentType }),
  })

export const dryRunHousekeeping = () =>
  getJson<HousekeepingReport>("/memory/housekeeping/dry-run", { method: "POST" })

export const runHousekeeping = () =>
  getJson<HousekeepingReport>("/memory/housekeeping/run", { method: "POST" })

export const getHousekeepingStatus = () =>
  getJson<{ tenant_id: string; config: { rollup_days: number; low_importance_retention_days: number }; last_run?: HousekeepingReport | null }>("/memory/housekeeping/status")

export const getCompactionStats = () =>
  getJson<CompactionStats>("/memory/compaction/stats")

// ── Knowledge index (docs/knowledge-layer.md) ─────────────────────────────
// Served by tenant_memory through the /svc/memory proxy (verified identity + roles are injected by proxy.ts).

const MEMORY_SVC_BASE = "/svc/memory/api/v1"

export class KnowledgeApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function knowledgeJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await authFetch(`${MEMORY_SVC_BASE}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    })
  } catch (e) {
    throw new KnowledgeApiError(e instanceof Error ? e.message : "Memory service unreachable", 0)
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    let detail = text
    try {
      const j = JSON.parse(text)
      detail = j?.detail ?? j?.error ?? text
    } catch { /* not JSON */ }
    throw new KnowledgeApiError(typeof detail === "string" && detail ? detail : `Memory service error ${res.status}`, res.status)
  }
  return res.json()
}

export interface KnowledgeEmbeddingHealth {
  ok: boolean
  model?: string
  dim?: number
  reachable?: boolean
  circuit_open?: boolean
  hint?: string | null
  error?: string
}
export interface KnowledgeHealth {
  enabled: boolean
  store_ok?: boolean
  embedding?: KnowledgeEmbeddingHealth
}
export interface KnowledgeCoverageRow {
  source_type: string
  module: string
  chunks: number
  tombstoned?: number
  last_indexed?: string | null
}
export interface KnowledgeWatermark {
  source: string
  last_ts?: string | null
  last_full_at?: string | null
}
export interface KnowledgeFailure {
  source: string
  source_ref?: unknown
  error: string
  created_at?: string | null
}
export interface KnowledgeCoverage {
  sources: KnowledgeCoverageRow[]
  watermarks: KnowledgeWatermark[]
  failures: KnowledgeFailure[]
  queue: { queued: number; running: number }
  not_yet_indexed?: string[]
  embedding?: KnowledgeEmbeddingHealth
}
export interface KnowledgeHit {
  source_type: string
  source_id: string
  chunk_no?: number
  title: string
  module: string
  as_of?: string | null
  age_days?: number | null
  stale: boolean
  score: number
  via?: string
  deep_link?: string | null
  tags?: string[]
  markdown: string
}
export interface KnowledgeSearchResult {
  degraded?: string | null
  results: KnowledgeHit[]
}

export const getKnowledgeHealth = () => knowledgeJson<KnowledgeHealth>("/knowledge/health")
export const getKnowledgeCoverage = () => knowledgeJson<KnowledgeCoverage>("/knowledge/admin/coverage")
export const reindexKnowledge = (modules: string[], full = false) =>
  knowledgeJson<{ job_id: string; status: string }>("/knowledge/admin/reindex", {
    method: "POST",
    body: JSON.stringify({ modules, full }),
  })
/** Same hybrid retrieval an agent gets, run as the signed-in user (so the same role filtering applies). */
export const searchKnowledge = (query: string, modules?: string[], k = 8) =>
  knowledgeJson<KnowledgeSearchResult>("/knowledge/search", {
    method: "POST",
    body: JSON.stringify({ query, k, ...(modules?.length ? { modules } : {}) }),
  })

// ── Approval Gate (Spec A8) ────────────────────────────────────────────────

export interface ApprovalItem {
  id: string
  reference: string
  tenant_id: string
  agent: string
  agent_type: string
  tool_name: string
  arguments: Record<string, unknown>
  conversation_id?: string | null
  run_id?: string | null
  requested_by?: string | null
  status: "pending" | "approved" | "rejected" | "expired"
  rejection_reason?: string | null
  execution_result?: Record<string, unknown> | null
  executed_at?: string | null
  expires_at: string
  decided_at?: string | null
  decided_by?: string | null
  created_at: string
  timestamp: string
  title: string
  agentName: string
  agentIcon: string
  impact: "critical" | "high" | "medium"
  category: string
  summary: string
  context: string
}

export const listApprovals = (status?: string, agent?: string) => {
  const params = new URLSearchParams()
  if (status) params.set("status", status)
  if (agent) params.set("agent", agent)
  return getJson<{ items: ApprovalItem[]; pending_count: number }>(`/approvals?${params.toString()}`)
}

export const approveApproval = (id: string, notes?: string) =>
  getJson<ApprovalItem>(`/approvals/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  })

export const rejectApproval = (id: string, reason?: string) =>
  getJson<ApprovalItem>(`/approvals/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  })

