"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Send,
  Bot,
  ChevronDown,
  X,
  Wrench,
  Loader2,
  ArrowLeft,
  Sparkles,
} from "lucide-react";
import {
  invokeAgent,
  listAgents,
  AGENT_CATALOG,
  type AgentInfo,
  type AgentInvokeResponse,
} from "../api/orchestrator";

// ── Types ────────────────────────────────────────────────────────────────

interface AgentChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: Array<{ name: string; args: Record<string, unknown>; result: unknown }>;
  isStreaming?: boolean;
}

interface AgentChatProps {
  /** Pre-selected agent type */
  initialAgent?: string;
  /** Context to pass to the agent (customer_id, job_id, etc.) */
  context?: Record<string, unknown>;
  /** Optional title override */
  title?: string;
  /** Callback when user goes back */
  onBack?: () => void;
  /** Theme: 'light' for customer portal, 'dark' for technician/sales apps */
  theme?: "light" | "dark";
}

// ── Theme classes ────────────────────────────────────────────────────────

const themes = {
  light: {
    bg: "bg-gray-50",
    headerBg: "bg-white",
    headerBorder: "border-gray-200",
    cardBg: "bg-white",
    cardBorder: "border-gray-200",
    text: "text-gray-900",
    textSecondary: "text-gray-500",
    textMuted: "text-gray-400",
    inputBg: "bg-white",
    inputBorder: "border-gray-200",
    userBubble: "bg-blue-600",
    assistantBubble: "bg-white",
    assistantText: "text-gray-900",
    primaryBg: "",
    primaryText: "text-white",
  },
  dark: {
    bg: "bg-slate-900",
    headerBg: "bg-slate-900",
    headerBorder: "border-slate-700",
    cardBg: "bg-slate-800",
    cardBorder: "border-slate-700",
    text: "text-slate-100",
    textSecondary: "text-slate-400",
    textMuted: "text-slate-500",
    inputBg: "bg-slate-800",
    inputBorder: "border-slate-700",
    userBubble: "bg-indigo-600",
    assistantBubble: "bg-slate-800",
    assistantText: "text-slate-100",
    primaryBg: "bg-indigo-600",
    primaryText: "text-white",
  },
};

// ── Component ────────────────────────────────────────────────────────────

export function AgentChat({ initialAgent, context = {}, title, onBack, theme = "dark" }: AgentChatProps) {
  const t = themes[theme];

  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState(initialAgent || "customer_facing");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [showAgentPicker, setShowAgentPicker] = useState(!initialAgent);
  const [error, setError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Array<{ id: string; agentType: string; lastMessage: string; time: string }>>([]);
  const [activeView, setActiveView] = useState<"list" | "chat">("list");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Load agents + conversations on mount
  useEffect(() => {
    listAgents()
      .then(setAgents)
      .catch(() => {});
    // Load previous conversations
    // listConversations().then(setConversations).catch(() => {});
  }, []);

  const activeAgent = AGENT_CATALOG[selectedAgent];

  // ── Start new conversation ─────────────────────────────────────────

  const startChat = (agentType?: string) => {
    if (agentType) setSelectedAgent(agentType);
    setMessages([]);
    setConversationId(null);
    setError(null);
    setActiveView("chat");
    setShowAgentPicker(false);
  };

  // ── Send message ───────────────────────────────────────────────────

  const handleSend = async () => {
    if (!inputValue.trim() || isSending) return;
    setError(null);

    const userMsg: AgentChatMessage = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    const assistantId = `msg-${Date.now() + 1}`;
    const streamingMsg: AgentChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      isStreaming: true,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg, streamingMsg]);
    const messageText = inputValue;
    setInputValue("");
    setIsSending(true);

    try {
      const response = await invokeAgent({
        agent_type: selectedAgent,
        message: messageText,
        context: {
          ...context,
          ui_context: "mobile_agent_chat",
        },
        conversation_id: conversationId || undefined,
      });

      setConversationId(response.conversation_id);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: response.message, toolCalls: response.tool_calls, isStreaming: false }
            : m,
        ),
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `⚠️ ${err instanceof Error ? err.message : "Error"}`, isStreaming: false }
            : m,
        ),
      );
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  };

  // ── Agent picker (first screen when no initialAgent) ───────────────

  if (activeView === "list" && !initialAgent) {
    return (
      <div className={`h-full flex flex-col ${t.bg}`}>
        <div className={`sticky top-0 z-10 ${t.headerBg} border-b ${t.headerBorder} px-4 pt-3 pb-3`}>
          <div className="flex items-center gap-2 mb-2">
            {onBack && (
              <button onClick={onBack} className={t.textSecondary}>
                <ArrowLeft size={20} />
              </button>
            )}
            <Bot size={20} className="text-indigo-400" />
            <h2 className={`text-lg font-bold ${t.text}`}>AI Assistant</h2>
          </div>
          <p className={`text-xs ${t.textSecondary}`}>Choose an agent to help you</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {Object.entries(AGENT_CATALOG).map(([type, info]) => {
            const liveInfo = agents.find((a) => a.agent_type === type);
            const toolCount = liveInfo?.tools.length || 0;
            return (
              <button
                key={type}
                onClick={() => startChat(type)}
                className={`w-full flex items-center gap-3 rounded-xl ${t.cardBg} border ${t.cardBorder} p-3 text-left active:scale-[0.98] transition-transform`}
              >
                <span className="text-2xl">{info.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${t.text}`}>{info.name}</span>
                    {toolCount > 0 && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${theme === "dark" ? "bg-slate-700 text-slate-400" : "bg-gray-100 text-gray-500"}`}>
                        {toolCount} tools
                      </span>
                    )}
                  </div>
                  <p className={`text-xs ${t.textSecondary} mt-0.5 line-clamp-2`}>{info.description}</p>
                </div>
                <ChevronDown size={16} className={`${t.textSecondary} -rotate-90`} />
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // ── Chat view ──────────────────────────────────────────────────────

  return (
    <div className={`h-full flex flex-col ${t.bg}`}>
      {/* Header */}
      <div className={`sticky top-0 z-10 ${t.headerBg} border-b ${t.headerBorder} px-4 pt-3 pb-2`}>
        <div className="flex items-center gap-2">
          <button onClick={() => { setActiveView("list"); setMessages([]); }} className={t.textSecondary}>
            <ArrowLeft size={20} />
          </button>
          <span className="text-lg">{activeAgent?.icon}</span>
          <div className="flex-1 min-w-0">
            <span className={`text-sm font-semibold ${t.text}`}>{activeAgent?.name || "Agent"}</span>
            {agents.find((a) => a.agent_type === selectedAgent)?.tools.length ? (
            <p className={`text-[10px] ${t.textSecondary}`}>
            {agents.find((a) => a.agent_type === selectedAgent)?.tools.length} tools available
            </p>
            ) : null}
          </div>
          <button onClick={() => setShowAgentPicker(!showAgentPicker)} className={`p-1.5 rounded-lg ${theme === "dark" ? "hover:bg-slate-800" : "hover:bg-gray-100"}`}>
            <Sparkles size={16} className="text-indigo-400" />
          </button>
        </div>

        {/* Agent picker dropdown */}
        {showAgentPicker && (
          <div className={`mt-2 rounded-lg ${t.cardBg} border ${t.cardBorder} overflow-hidden`}>
            {Object.entries(AGENT_CATALOG).map(([type, info]) => (
              <button
                key={type}
                onClick={() => { setSelectedAgent(type); setShowAgentPicker(false); setMessages([]); setConversationId(null); }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-left ${selectedAgent === type ? (theme === "dark" ? "bg-indigo-500/10" : "bg-blue-50") : ""} ${theme === "dark" ? "hover:bg-slate-700" : "hover:bg-gray-50"}`}
              >
                <span>{info.icon}</span>
                <span className={`text-xs font-medium ${t.text}`}>{info.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="mx-4 mt-2 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2">
          <p className="text-xs text-red-400">{error}</p>
          <button onClick={() => setError(null)} className="text-[10px] text-red-400 underline mt-0.5">Dismiss</button>
        </div>
      )}

      {/* Quick actions (shown when no messages) */}
      {messages.length === 0 && (
        <div className="px-4 pt-4">
          <p className={`text-xs ${t.textSecondary} mb-2`}>Quick actions:</p>
          <div className="flex flex-wrap gap-1.5">
            {getQuickActions(selectedAgent).map((action) => (
              <button
                key={action.label}
                onClick={() => { setInputValue(action.prompt); inputRef.current?.focus(); }}
                className={`rounded-lg border px-2.5 py-1.5 text-xs ${t.textSecondary} ${t.cardBorder} ${t.cardBg} active:scale-95 transition-transform`}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => (
          <div key={msg.id}>
            <div className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  msg.role === "user"
                    ? `${t.userBubble} text-white`
                    : `${t.assistantBubble} border ${t.cardBorder} ${t.assistantText}`
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.isStreaming && (
                  <span className="mt-1 inline-flex items-center gap-1 text-xs text-indigo-400">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Thinking...
                  </span>
                )}
              </div>
            </div>

            {/* Tool calls */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div className="mt-1.5 ml-2 space-y-1">
                <p className={`text-[10px] font-medium uppercase tracking-wider ${t.textSecondary}`}>Tools used:</p>
                {msg.toolCalls.map((tc, idx) => (
                  <div key={idx} className={`flex items-center gap-1.5 rounded-md border px-2 py-1 ${t.cardBorder} ${theme === "dark" ? "bg-slate-800/50" : "bg-gray-50"}`}>
                    <Wrench className="h-3 w-3 text-cyan-400" />
                    <span className={`text-[10px] font-mono ${t.text}`}>{tc.name}</span>
                    <span className={`text-[10px] ${t.textSecondary} truncate`}>{JSON.stringify(tc.args).slice(0, 40)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className={`border-t ${t.headerBorder} p-3 ${t.headerBg}`}>
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder={`Message ${activeAgent?.name || "agent"}...`}
            className={`flex-1 h-10 rounded-xl border px-3 text-sm ${t.inputBg} ${t.inputBorder} ${t.text} placeholder:${theme === "dark" ? "text-slate-500" : "text-gray-400"} focus:outline-none focus:border-indigo-500`}
            disabled={isSending}
          />
          <button
            onClick={handleSend}
            disabled={isSending || !inputValue.trim()}
            className="h-10 w-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center disabled:opacity-50 active:scale-95 transition-transform shrink-0"
          >
            {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Quick actions per agent ─────────────────────────────────────────────

function getQuickActions(agentType: string): Array<{ label: string; prompt: string }> {
  switch (agentType) {
    case "customer_facing":
      return [
        { label: "Check my balance", prompt: "What is my current account balance?" },
        { label: "My invoices", prompt: "Show me my recent invoices" },
        { label: "Report an issue", prompt: "I want to report a service issue:" },
        { label: "Coverage check", prompt: "Check fibre coverage for " },
      ];
    case "support":
      return [
        { label: "Network status", prompt: "Check the network service status" },
        { label: "Create ticket", prompt: "Create a support ticket:" },
        { label: "RADIUS check", prompt: "Check RADIUS account for" },
      ];
    case "provisioning":
      return [
        { label: "New customer", prompt: "Start provisioning for a new customer at " },
        { label: "Check coverage", prompt: "Check fibre coverage for address " },
        { label: "Network status", prompt: "Check network service status" },
      ];
    case "executive":
      return [
        { label: "Executive summary", prompt: "Give me the executive summary for this month" },
        { label: "Pipeline status", prompt: "Show me the current sales pipeline" },
        { label: "Churn report", prompt: "Show me churn risk predictions" },
      ];
    case "retention":
      return [
        { label: "Churn report", prompt: "Show me the top customers at risk of churning" },
        { label: "Open cases", prompt: "List all open retention cases" },
      ];
    default:
      return [];
  }
}
