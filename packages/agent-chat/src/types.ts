// ── Agent catalog — single source of truth across all apps ───────────────

export const AGENT_CATALOG = {
  customer_facing: {
    name: "DomeBot",
    description: "Customer assistant — balances, invoices, coverage, tickets",
    icon: "🤖",
    quickActions: [
      { label: "Check my balance", prompt: "What is my current account balance?" },
      { label: "My invoices", prompt: "Show me my recent invoices" },
      { label: "Report an issue", prompt: "I want to report a service issue" },
      { label: "Coverage check", prompt: "Check fibre coverage for " },
    ],
  },
  support: {
    name: "SupportBot",
    description: "Support assistant — tickets, diagnostics, network status",
    icon: "🔧",
    quickActions: [
      { label: "Network status", prompt: "Check the network service status" },
      { label: "Create ticket", prompt: "Create a support ticket:" },
      { label: "RADIUS check", prompt: "Check RADIUS account for" },
    ],
  },
  provisioning: {
    name: "ProvisionBot",
    description: "Provisioning assistant — coverage, onboarding, network checks",
    icon: "⚡",
    quickActions: [
      { label: "New customer", prompt: "Start provisioning for a new customer at " },
      { label: "Check coverage", prompt: "Check fibre coverage for address " },
      { label: "Network status", prompt: "Check network service status" },
    ],
  },
  executive: {
    name: "InsightBot",
    description: "Executive assistant — analytics, pipeline, financials",
    icon: "📊",
    quickActions: [
      { label: "Executive summary", prompt: "Give me the executive summary for this month" },
      { label: "Pipeline status", prompt: "Show me the current sales pipeline" },
      { label: "Churn report", prompt: "Show me churn risk predictions" },
    ],
  },
  retention: {
    name: "ChurnGuard",
    description: "Retention assistant — churn risk, predictions, campaigns",
    icon: "🛡️",
    quickActions: [
      { label: "Churn report", prompt: "Show me the top customers at risk of churning" },
      { label: "Open cases", prompt: "List all open retention cases" },
    ],
  },
} as const;

export type AgentType = keyof typeof AGENT_CATALOG;

// ── API types ─────────────────────────────────────────────────────────────

export interface AgentInfo {
  agent_type: string;
  description: string;
  llm: string;
  tools: string[];
}

export interface AgentInvokeRequest {
  agent_type: string;
  message: string;
  context?: Record<string, unknown>;
  tenant_id?: string;
  conversation_id?: string;
  stream_tokens?: boolean;
}

export interface AgentInvokeResponse {
  conversation_id: string;
  message: string;
  tool_calls: { name: string; arguments: Record<string, unknown>; result: unknown }[];
  agent_type: string;
  correlation_id?: string;
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

export interface AgentMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: { name: string; arguments: Record<string, unknown> }[];
  tool_results?: unknown[];
}

// ── AG-UI streaming event types ───────────────────────────────────────────

export type AGUIEventType =
  | "RUN_STARTED"
  | "TEXT_MESSAGE_CONTENT"
  | "TOOL_CALL_START"
  | "TOOL_CALL_RESULT"
  | "TOOL_CALL_END"
  | "MEMORY_WRITE"
  | "RUN_FINISHED"
  | "RUN_ERROR";

export interface AGUIEvent {
  type: AGUIEventType;
  run_id: string;
  tenant_id?: string;
  conversation_id?: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface ToolCallEvent {
  runId: string;
  toolCallId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: "start" | "result" | "end";
}

// ── Chat UI types ─────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallEvent[];
  isStreaming?: boolean;
  timestamp?: Date;
}

// ── Auth context — passed from each app to authorize orchestrator calls ───

export interface AgentAuthContext {
  /** JWT access token — forwarded as Authorization: Bearer <token> */
  accessToken?: string;
  /** Tenant ID — forwarded as X-Tenant-ID header */
  tenantId?: string;
}
