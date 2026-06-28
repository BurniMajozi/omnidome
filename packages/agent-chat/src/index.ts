// Public API for @omnidome/agent-chat

export { AgentChat } from "./AgentChat";
export type { AgentChatProps } from "./AgentChat";

export {
  AGENT_CATALOG,
  type AgentType,
  type ChatMessage,
  type AGUIEvent,
  type ToolCallEvent,
  type AgentAuthContext,
  type AgentInfo,
  type AgentInvokeRequest,
  type AgentInvokeResponse,
  type ConversationRead,
} from "./types";

export {
  invokeAgent,
  invokeAgentStreaming,
  listAgents,
  getConversation,
  listConversations,
  webAdminConfig,
  mobileAppConfig,
  type OrchestratorConfig,
} from "./orchestrator";
