/**
 * Orchestrator API Client for Mobile Apps
 *
 * Direct HTTP calls to the orchestrator service.
 * No Next.js proxy needed — mobile apps call the orchestrator directly.
 *
 * API_BASE must be set via NEXT_PUBLIC_API_URL env var.
 * The orchestrator is accessible at {API_BASE}/api/agents, {API_BASE}/api/conversations, etc.
 *
 * Each app passes its own context:
 *   customer-app:    customer_id from auth store
 *   technician-app:  job_id, customer_id from current job
 *   field-sales-app: customer_id from viewed contact, deal_id from active deal
 */

const ORCHESTRATOR_API =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8021";

// ── Types ────────────────────────────────────────────────────────────────

export interface AgentInfo {
  agent_type: string;
  description: string;
  llm: string;
  tools: string[];
}

export interface AgentMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: { name: string; arguments: Record<string, unknown> }[];
  tool_results?: unknown[];
}

export interface AgentInvokeRequest {
  agent_type: string;
  message: string;
  context?: Record<string, unknown>;
  tenant_id?: string;
  conversation_id?: string;
}

export interface AgentInvokeResponse {
  conversation_id: string;
  message: string;
  tool_calls: { name: string; arguments: Record<string, unknown>; result: unknown }[];
  agent_type: string;
}

export interface ConversationRead {
  id: string;
  tenant_id: string;
  agent_type: string;
  channel: string;
  status: string;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  messages?: AgentMessage[];
}

// ── Agent catalog (mirrors backend config) ───────────────────────────────

export const AGENT_CATALOG: Record<
  string,
  { name: string; description: string; icon: string }
> = {
  customer_facing: {
    name: "DomeBot",
    description: "Customer assistant — balances, invoices, coverage, tickets",
    icon: "🤖",
  },
  support: {
    name: "SupportBot",
    description: "Support assistant — tickets, diagnostics, network status",
    icon: "🔧",
  },
  provisioning: {
    name: "ProvisionBot",
    description: "Provisioning assistant — coverage, onboarding, network checks",
    icon: "⚡",
  },
  executive: {
    name: "InsightBot",
    description: "Executive assistant — analytics, pipeline, financials",
    icon: "📊",
  },
  retention: {
    name: "ChurnGuard",
    description: "Retention assistant — churn risk, predictions, campaigns",
    icon: "🛡️",
  },
};

// ── API functions ────────────────────────────────────────────────────────

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${ORCHESTRATOR_API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    },
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "Request failed");
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json();
}

export async function listAgents(): Promise<AgentInfo[]> {
  return request<AgentInfo[]>("/api/agents");
}

export async function invokeAgent(req: AgentInvokeRequest): Promise<AgentInvokeResponse> {
  return request<AgentInvokeResponse>("/api/agents/invoke", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getConversation(conversationId: string): Promise<ConversationRead> {
  return request<ConversationRead>(`/api/conversations/${conversationId}`);
}

export async function listConversations(agentType?: string): Promise<ConversationRead[]> {
  const qs = agentType ? `?agent_type=${encodeURIComponent(agentType)}` : "";
  return request<ConversationRead[]>(`/api/conversations${qs}`);
}
