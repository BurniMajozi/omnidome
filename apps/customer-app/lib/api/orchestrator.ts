/**
 * @deprecated
 * Import directly from @omnidome/agent-chat instead.
 * This file is kept as a re-export shim to avoid breaking existing imports.
 */

export {
  AGENT_CATALOG,
  invokeAgent,
  invokeAgentStreaming as invokeAgentStream,
  listAgents,
  getConversation,
  listConversations,
  mobileAppConfig,
  type AgentInfo,
  type AgentInvokeRequest,
  type AgentInvokeResponse,
  type ConversationRead,
  type AgentMessage,
} from "@omnidome/agent-chat";
