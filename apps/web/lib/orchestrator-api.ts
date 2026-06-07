/**
 * Agent Orchestrator API client.
 *
 * Wraps the orchestrator service (port 8021) which provides:
 *   - Agent invocation (sync + streaming)
 *   - Conversation persistence
 *   - Tool execution across all OmniDome microservices
 *
 * Each agent has access to the full OmniDome OS context via its tool set:
 *   DomeBot (customer_facing)  — CRM, billing, network, support tools
 *   ChurnGuard (retention)     — retention predictions, CRM, analytics
 *   ProvisionBot (provisioning) — CRM, network, billing, support
 *   InsightBot (executive)     — analytics, finance, sales, call center
 *   SupportBot (support)       — support tickets, CRM, network, billing
 */

const ORCHESTRATOR_BASE = "/api/orchestrator"

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
  const res = await fetch(`${ORCHESTRATOR_BASE}/agents/invoke`, {
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
  const res = await fetch(`${ORCHESTRATOR_BASE}/agents/invoke/stream`, {
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
