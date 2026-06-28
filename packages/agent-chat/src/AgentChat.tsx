"use client";

/**
 * AgentChat — @omnidome/agent-chat
 *
 * Single shared chat component used by all OmniDome apps.
 *
 * Features:
 *   - AG-UI streaming (SSE) with tool-call display
 *   - Auth context forwarded to orchestrator (Bearer + X-Tenant-ID)
 *   - Light and dark themes
 *   - Agent picker (or locked to a single agent via initialAgent)
 *   - Quick actions per agent
 *   - onTicketCreated callback — fires when agent creates a support ticket
 */

import { useState, useRef, useEffect, useCallback } from "react";
import {
  Send, Bot, ChevronDown, ArrowLeft, Sparkles,
  Wrench, Loader2, CheckCircle2, AlertCircle, X,
} from "lucide-react";

import {
  AGENT_CATALOG,
  type AgentType,
  type ChatMessage,
  type AGUIEvent,
  type ToolCallEvent,
  type AgentAuthContext,
} from "./types";

import {
  invokeAgentStreaming,
  listAgents,
  mobileAppConfig,
  webAdminConfig,
  type OrchestratorConfig,
} from "./orchestrator";

// ── Theme ─────────────────────────────────────────────────────────────────

const THEMES = {
  light: {
    shell: "bg-gray-50",
    header: "bg-white border-gray-200",
    card: "bg-white border-gray-200",
    text: "text-gray-900",
    textSub: "text-gray-500",
    textMuted: "text-gray-400",
    input: "bg-white border-gray-200 text-gray-900",
    userBubble: "bg-blue-600 text-white",
    botBubble: "bg-white border border-gray-200 text-gray-900",
    toolRow: "bg-gray-50 border-gray-200",
    sendBtn: "bg-blue-600 hover:bg-blue-700 text-white",
    hover: "hover:bg-gray-100",
    activeAgent: "bg-blue-50 text-blue-700",
  },
  dark: {
    shell: "bg-slate-900",
    header: "bg-slate-900 border-slate-700",
    card: "bg-slate-800 border-slate-700",
    text: "text-slate-100",
    textSub: "text-slate-400",
    textMuted: "text-slate-500",
    input: "bg-slate-800 border-slate-700 text-slate-100",
    userBubble: "bg-indigo-600 text-white",
    botBubble: "bg-slate-800 border border-slate-700 text-slate-100",
    toolRow: "bg-slate-800/60 border-slate-700",
    sendBtn: "bg-indigo-600 hover:bg-indigo-700 text-white",
    hover: "hover:bg-slate-800",
    activeAgent: "bg-indigo-500/10 text-indigo-400",
  },
} as const;

// ── Props ─────────────────────────────────────────────────────────────────

export interface AgentChatProps {
  /** Lock to a specific agent — shows the picker if omitted */
  initialAgent?: AgentType;
  /** Domain context forwarded to the agent (customer_id, job_id, etc.) */
  context?: Record<string, unknown>;
  /** Auth context — supply from your app's auth store */
  auth?: AgentAuthContext;
  /** "mobile" apps hit the orchestrator directly; "web" uses the Next.js proxy */
  target?: "mobile" | "web";
  /** Visual theme */
  theme?: "light" | "dark";
  /** Optional back button handler */
  onBack?: () => void;
  /**
   * Fires when the AI creates a support ticket inline.
   * Payload: { ticketId, subject, status }
   */
  onTicketCreated?: (ticket: { ticketId: string; subject: string; status: string }) => void;
}

// ── Component ─────────────────────────────────────────────────────────────

export function AgentChat({
  initialAgent,
  context = {},
  auth,
  target = "mobile",
  theme = "dark",
  onBack,
  onTicketCreated,
}: AgentChatProps) {
  const t = THEMES[theme];

  const config: OrchestratorConfig =
    target === "web" ? webAdminConfig(auth) : mobileAppConfig(auth);

  const [selectedAgent, setSelectedAgent] = useState<AgentType>(
    initialAgent ?? "customer_facing",
  );
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showPicker, setShowPicker] = useState(!initialAgent);
  const [view, setView] = useState<"list" | "chat">(initialAgent ? "chat" : "list");
  const [error, setError] = useState<string | null>(null);
  const [liveTools, setLiveTools] = useState<ToolCallEvent[]>([]);

  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // ── Start new chat ────────────────────────────────────────────────────

  const startChat = (agentType?: AgentType) => {
    if (agentType) setSelectedAgent(agentType);
    setMessages([]);
    setConversationId(null);
    setError(null);
    setLiveTools([]);
    setView("chat");
    setShowPicker(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  // ── Send message ──────────────────────────────────────────────────────

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    setError(null);
    setLiveTools([]);

    const text = input;
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    const assistantId = `a-${Date.now()}`;
    const botMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      toolCalls: [],
      isStreaming: true,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg, botMsg]);
    setInput("");
    setSending(true);

    try {
      const newConvId = await invokeAgentStreaming(
        {
          agent_type: selectedAgent,
          message: text,
          context: { ...context, conversation_id: conversationId },
          conversation_id: conversationId ?? undefined,
          stream_tokens: true,
        },
        (event: AGUIEvent) => handleStreamEvent(event, assistantId),
        config,
      );
      if (newConvId) setConversationId(newConvId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to reach agent";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `⚠️ ${msg}`, isStreaming: false }
            : m,
        ),
      );
      setError(msg);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  // ── AG-UI stream event handler ────────────────────────────────────────

  const handleStreamEvent = (event: AGUIEvent, assistantId: string) => {
    switch (event.type) {
      case "TEXT_MESSAGE_CONTENT":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: m.content + ((event.data.delta as string) ?? "") }
              : m,
          ),
        );
        break;

      case "TOOL_CALL_START": {
        const tc: ToolCallEvent = {
          runId: event.run_id,
          toolCallId: event.data.tool_call_id as string,
          toolName: event.data.tool_name as string,
          arguments: (event.data.arguments as Record<string, unknown>) ?? {},
          status: "start",
        };
        setLiveTools((prev) => [...prev, tc]);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, toolCalls: [...(m.toolCalls ?? []), tc] } : m,
          ),
        );
        break;
      }

      case "TOOL_CALL_RESULT": {
        const update = (tc: ToolCallEvent): ToolCallEvent =>
          tc.toolCallId === event.data.tool_call_id
            ? { ...tc, result: event.data.result, status: "result" }
            : tc;
        setLiveTools((prev) => prev.map(update));
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, toolCalls: m.toolCalls?.map(update) }
              : m,
          ),
        );
        // Check if agent created a ticket — fire callback
        if (
          event.data.tool_name === "create_support_ticket" &&
          event.data.result &&
          onTicketCreated
        ) {
          const r = event.data.result as Record<string, unknown>;
          onTicketCreated({
            ticketId: r.id as string,
            subject: r.subject as string,
            status: (r.status as string) ?? "open",
          });
        }
        break;
      }

      case "TOOL_CALL_END": {
        const end = (tc: ToolCallEvent): ToolCallEvent =>
          tc.toolCallId === event.data.tool_call_id ? { ...tc, status: "end" } : tc;
        setLiveTools((prev) => prev.map(end));
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, toolCalls: m.toolCalls?.map(end) } : m,
          ),
        );
        break;
      }

      case "RUN_FINISHED":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false } : m,
          ),
        );
        break;

      case "RUN_ERROR": {
        const errMsg = (event.data.error as string) ?? "Agent error";
        setError(errMsg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `⚠️ ${errMsg}`, isStreaming: false }
              : m,
          ),
        );
        break;
      }
    }
  };

  const activeAgentInfo = AGENT_CATALOG[selectedAgent];

  // ── Agent picker view ─────────────────────────────────────────────────

  if (view === "list" && !initialAgent) {
    return (
      <div className={`h-full flex flex-col ${t.shell}`}>
        <div className={`sticky top-0 z-10 border-b px-4 pt-4 pb-3 ${t.header}`}>
          <div className="flex items-center gap-2 mb-1">
            {onBack && (
              <button onClick={onBack} className={t.textSub}>
                <ArrowLeft size={20} />
              </button>
            )}
            <Bot size={20} className="text-indigo-400" />
            <h2 className={`text-lg font-bold ${t.text}`}>AI Assistant</h2>
          </div>
          <p className={`text-xs ${t.textSub}`}>Choose an agent to get started</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {(Object.entries(AGENT_CATALOG) as [AgentType, typeof AGENT_CATALOG[AgentType]][]).map(
            ([type, info]) => (
              <button
                key={type}
                onClick={() => startChat(type)}
                className={`w-full flex items-center gap-3 rounded-xl border p-3 text-left transition-all active:scale-[0.98] ${t.card} ${t.hover}`}
              >
                <span className="text-2xl">{info.icon}</span>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-semibold ${t.text}`}>{info.name}</p>
                  <p className={`text-xs mt-0.5 line-clamp-2 ${t.textSub}`}>{info.description}</p>
                </div>
                <ChevronDown size={16} className={`${t.textSub} -rotate-90 shrink-0`} />
              </button>
            ),
          )}
        </div>
      </div>
    );
  }

  // ── Chat view ─────────────────────────────────────────────────────────

  return (
    <div className={`h-full flex flex-col ${t.shell}`}>
      {/* Header */}
      <div className={`sticky top-0 z-10 border-b px-4 pt-3 pb-2 ${t.header}`}>
        <div className="flex items-center gap-2">
          {!initialAgent && (
            <button
              onClick={() => { setView("list"); setMessages([]); setLiveTools([]); }}
              className={t.textSub}
            >
              <ArrowLeft size={20} />
            </button>
          )}
          {onBack && initialAgent && (
            <button onClick={onBack} className={t.textSub}>
              <ArrowLeft size={20} />
            </button>
          )}
          <span className="text-xl">{activeAgentInfo.icon}</span>
          <p className={`text-sm font-semibold flex-1 ${t.text}`}>{activeAgentInfo.name}</p>
          {!initialAgent && (
            <button
              onClick={() => setShowPicker(!showPicker)}
              className={`p-1.5 rounded-lg ${t.hover}`}
            >
              <Sparkles size={16} className="text-indigo-400" />
            </button>
          )}
        </div>

        {/* Inline agent switcher */}
        {showPicker && (
          <div className={`mt-2 rounded-xl border overflow-hidden ${t.card}`}>
            {(Object.entries(AGENT_CATALOG) as [AgentType, typeof AGENT_CATALOG[AgentType]][]).map(
              ([type, info]) => (
                <button
                  key={type}
                  onClick={() => {
                    setSelectedAgent(type);
                    setShowPicker(false);
                    setMessages([]);
                    setConversationId(null);
                    setLiveTools([]);
                  }}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 text-left text-sm ${t.hover} ${
                    selectedAgent === type ? t.activeAgent : t.text
                  }`}
                >
                  <span>{info.icon}</span>
                  <span className="font-medium">{info.name}</span>
                  {selectedAgent === type && (
                    <CheckCircle2 size={13} className="ml-auto" />
                  )}
                </button>
              ),
            )}
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mt-2 flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2">
          <AlertCircle size={14} className="text-red-400 shrink-0" />
          <p className="text-xs text-red-400 flex-1">{error}</p>
          <button onClick={() => setError(null)}>
            <X size={13} className="text-red-400" />
          </button>
        </div>
      )}

      {/* Quick actions */}
      {messages.length === 0 && (
        <div className="px-4 pt-4">
          <p className={`text-xs mb-2 ${t.textSub}`}>Try asking:</p>
          <div className="flex flex-wrap gap-1.5">
            {activeAgentInfo.quickActions.map((qa) => (
              <button
                key={qa.label}
                onClick={() => { setInput(qa.prompt); inputRef.current?.focus(); }}
                className={`rounded-lg border px-2.5 py-1.5 text-xs transition-all active:scale-95 ${t.card} ${t.textSub}`}
              >
                {qa.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.map((msg) => (
          <div key={msg.id}>
            <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm ${
                  msg.role === "user" ? t.userBubble : t.botBubble
                }`}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.isStreaming && (
                  <span className={`mt-1 inline-flex items-center gap-1 text-xs ${t.textMuted}`}>
                    <Loader2 size={11} className="animate-spin" />
                    Thinking…
                  </span>
                )}
              </div>
            </div>

            {/* Tool calls */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div className="mt-1.5 ml-1 space-y-1">
                {msg.toolCalls.map((tc, i) => (
                  <div
                    key={i}
                    className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${t.toolRow}`}
                  >
                    <Wrench
                      size={11}
                      className={
                        tc.status === "start"
                          ? "text-amber-400"
                          : tc.status === "result"
                          ? "text-cyan-400"
                          : "text-emerald-400"
                      }
                    />
                    <span className={`font-mono ${t.text}`}>{tc.toolName}</span>
                    {tc.status === "start" && (
                      <Loader2 size={10} className="animate-spin text-amber-400 ml-auto" />
                    )}
                    {tc.status === "end" && (
                      <CheckCircle2 size={10} className="text-emerald-400 ml-auto" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className={`border-t px-3 py-3 ${t.header}`}>
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={`Message ${activeAgentInfo.name}…`}
            disabled={sending}
            className={`flex-1 h-10 rounded-xl border px-3 text-sm placeholder:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 disabled:opacity-50 ${t.input}`}
          />
          <button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className={`h-10 w-10 rounded-xl flex items-center justify-center shrink-0 transition-all active:scale-95 disabled:opacity-40 ${t.sendBtn}`}
          >
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}
