/**
 * Unified Orchestrator Client — @omnidome/agent-chat
 *
 * Single implementation used by all OmniDome apps.
 * Supports:
 *   - AG-UI streaming (SSE) — default
 *   - Sync request/response fallback
 *   - Auth forwarding (Bearer token + X-Tenant-ID)
 *   - Configurable base URL per app
 */

import type {
  AgentAuthContext,
  AgentInfo,
  AgentInvokeRequest,
  AgentInvokeResponse,
  AGUIEvent,
  ConversationRead,
} from "./types";

// ── Config ────────────────────────────────────────────────────────────────

export interface OrchestratorConfig {
  /**
   * Base URL to the orchestrator.
   *
   * - Web admin app: "/api/orchestrator"  (proxied by Next.js)
   * - Mobile/customer apps: process.env.NEXT_PUBLIC_ORCHESTRATOR_URL
   */
  baseUrl: string;
  /** Auth context — supply tokens from your app's auth store */
  auth?: AgentAuthContext;
}

function buildHeaders(auth?: AgentAuthContext): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth?.accessToken) headers["Authorization"] = `Bearer ${auth.accessToken}`;
  if (auth?.tenantId) headers["X-Tenant-ID"] = auth.tenantId;
  return headers;
}

// ── Sync invoke ───────────────────────────────────────────────────────────

export async function invokeAgent(
  req: AgentInvokeRequest,
  config: OrchestratorConfig,
): Promise<AgentInvokeResponse> {
  const res = await fetch(`${config.baseUrl}/agents/invoke`, {
    method: "POST",
    headers: buildHeaders(config.auth),
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "Request failed");
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json();
}

// ── AG-UI streaming invoke ────────────────────────────────────────────────

export async function invokeAgentStreaming(
  req: AgentInvokeRequest,
  onEvent: (event: AGUIEvent) => void,
  config: OrchestratorConfig,
): Promise<string | null> {
  const res = await fetch(`${config.baseUrl}/agents/invoke/stream`, {
    method: "POST",
    headers: buildHeaders(config.auth),
    body: JSON.stringify({ ...req, stream_tokens: true }),
  });

  if (!res.ok) {
    const err = await res.text().catch(() => "Stream failed");
    throw new Error(`${res.status}: ${err}`);
  }

  if (!res.body) throw new Error("No response body for streaming");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let conversationId: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") continue;
      try {
        const event: AGUIEvent = JSON.parse(data);
        if (event.conversation_id) conversationId = event.conversation_id;
        onEvent(event);
      } catch {
        // Skip malformed SSE frames
      }
    }
  }

  return conversationId;
}

// ── Agent list ────────────────────────────────────────────────────────────

export async function listAgents(config: OrchestratorConfig): Promise<AgentInfo[]> {
  const res = await fetch(`${config.baseUrl}/agents`, {
    headers: buildHeaders(config.auth),
  });
  if (!res.ok) throw new Error(`listAgents: ${res.status}`);
  return res.json();
}

// ── Conversation API ──────────────────────────────────────────────────────

export async function getConversation(
  conversationId: string,
  config: OrchestratorConfig,
): Promise<ConversationRead> {
  const res = await fetch(`${config.baseUrl}/conversations/${conversationId}`, {
    headers: buildHeaders(config.auth),
  });
  if (!res.ok) throw new Error(`getConversation: ${res.status}`);
  return res.json();
}

export async function listConversations(
  config: OrchestratorConfig,
  agentType?: string,
): Promise<ConversationRead[]> {
  const qs = agentType ? `?agent_type=${encodeURIComponent(agentType)}` : "";
  const res = await fetch(`${config.baseUrl}/conversations${qs}`, {
    headers: buildHeaders(config.auth),
  });
  if (!res.ok) throw new Error(`listConversations: ${res.status}`);
  return res.json();
}

// ── Default config builders (one per app) ────────────────────────────────

/**
 * For the web admin app — uses the Next.js proxy route.
 * No direct orchestrator URL needed.
 */
export function webAdminConfig(auth?: AgentAuthContext): OrchestratorConfig {
  return { baseUrl: "/api/orchestrator", auth };
}

/**
 * For customer-app, field-sales-app, technician-app.
 * Reads NEXT_PUBLIC_ORCHESTRATOR_URL from env.
 */
export function mobileAppConfig(auth?: AgentAuthContext): OrchestratorConfig {
  const baseUrl =
    (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_ORCHESTRATOR_URL) ||
    (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
    "http://localhost:8021";
  return { baseUrl, auth };
}
