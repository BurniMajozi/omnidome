"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import {
  Bot,
  Send,
  Loader2,
  Wrench,
  Sparkles,
  MessageSquare,
  Trash2,
  Plus,
  MoreHorizontal,
  Edit3,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import {
  invokeAgent,
  listAgents,
  AGENT_CATALOG,
  type AgentInfo,
} from "@/lib/orchestrator-api"

// ── Types ────────────────────────────────────────────────────────────────

type AgentType = keyof typeof AGENT_CATALOG

interface AgentChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  toolCalls?: Array<{ name: string; args: Record<string, unknown>; result: unknown }>
  isStreaming?: boolean
  timestamp: Date
}

interface AgentConversation {
  id: string
  agentType: AgentType
  messages: AgentChatMessage[]
  createdAt: Date
}

// ── Props ────────────────────────────────────────────────────────────────

interface AgentChannelProps {
  /** OmniDome context — current customer, property, etc. */
  context?: Record<string, unknown>
  /** Callback when agent creates a task */
  onCreateTask?: (task: { title: string; description: string; priority: string }) => void
}

// ── Component ────────────────────────────────────────────────────────────

export function AgentChannel({ context = {}, onCreateTask }: AgentChannelProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [selectedAgent, setSelectedAgent] = useState<AgentType>("customer_facing")
  const [conversations, setConversations] = useState<AgentConversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [inputValue, setInputValue] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const activeConversation = conversations.find((c) => c.id === activeConversationId)
  const activeAgent = AGENT_CATALOG[selectedAgent]

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [conversations, scrollToBottom])

  // Load agent info
  useEffect(() => {
    listAgents()
      .then(setAgents)
      .catch(() => {})
  }, [])

  // ── Start new conversation ─────────────────────────────────────────────

  const startNewConversation = () => {
    const newConv: AgentConversation = {
      id: `conv-${Date.now()}`,
      agentType: selectedAgent,
      messages: [],
      createdAt: new Date(),
    }
    setConversations((prev) => [newConv, ...prev])
    setActiveConversationId(newConv.id)
    setError(null)
  }

  // ── Send message ───────────────────────────────────────────────────────

  const handleSend = async () => {
    if (!inputValue.trim() || isSending) return
    setError(null)

    // Auto-create conversation if none active
    let convId = activeConversationId
    if (!convId) {
      const newConv: AgentConversation = {
        id: `conv-${Date.now()}`,
        agentType: selectedAgent,
        messages: [],
        createdAt: new Date(),
      }
      setConversations((prev) => [newConv, ...prev])
      convId = newConv.id
      setActiveConversationId(convId)
    }

    const userMessage: AgentChatMessage = {
      id: `msg-${Date.now()}`,
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    }

    const assistantId = `msg-${Date.now() + 1}`
    const streamingMessage: AgentChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      isStreaming: true,
      timestamp: new Date(),
    }

    // Add user message + streaming placeholder
    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? { ...c, messages: [...c.messages, userMessage, streamingMessage] }
          : c,
      ),
    )

    const messageText = inputValue
    setInputValue("")
    setIsSending(true)

    try {
      // Build conversation history for context
      const conv = conversations.find((c) => c.id === convId)
      const history = conv?.messages
        .filter((m) => !m.isStreaming)
        .map((m) => ({ role: m.role, content: m.content })) || []

      const response = await invokeAgent({
        agent_type: selectedAgent,
        message: messageText,
        context: {
          ...context,
          conversation_history: history,
          ui_context: "agent_channel",
        },
      })

      // Update with actual response
      setConversations((prev) =>
        prev.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: response.message, toolCalls: response.tool_calls, isStreaming: false }
                    : m,
                ),
              }
            : c,
        ),
      )

      // Check if agent created a task
      if (onCreateTask) {
        const taskTool = response.tool_calls?.find(
          (tc) => tc.name === "support.create_task" || tc.name === "crm.create_task",
        )
        if (taskTool) {
          onCreateTask({
            title: String(taskTool.args.title || taskTool.args.subject || "New task"),
            description: String(taskTool.args.description || ""),
            priority: String(taskTool.args.priority || "medium"),
          })
        }
      }
    } catch (err) {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === convId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: `⚠️ Error: ${err instanceof Error ? err.message : "Failed to reach agent"}`,
                        isStreaming: false,
                      }
                    : m,
                ),
              }
            : c,
        ),
      )
      setError(err instanceof Error ? err.message : "Agent error")
    } finally {
      setIsSending(false)
      inputRef.current?.focus()
    }
  }

  // ── Quick actions per agent ────────────────────────────────────────────

  const quickActions: Record<AgentType, Array<{ label: string; prompt: string }>> = {
    customer_facing: [
      { label: "Check coverage", prompt: "Check fibre coverage for " },
      { label: "Get balance", prompt: "Get the current balance for customer " },
      { label: "Create ticket", prompt: "Create a support ticket: " },
      { label: "Customer 360", prompt: "Show me the full 360 view for customer " },
    ],
    retention: [
      { label: "Churn report", prompt: "Show me the top 10 customers at risk of churning" },
      { label: "Open cases", prompt: "List all open retention cases" },
      { label: "Predictions", prompt: "Get churn predictions for this month" },
    ],
    provisioning: [
      { label: "New customer", prompt: "Start provisioning for new customer " },
      { label: "Check status", prompt: "Check network service status for customer " },
      { label: "Coverage map", prompt: "Show coverage map for area " },
    ],
    executive: [
      { label: "Executive summary", prompt: "Give me the executive summary for this month" },
      { label: "Pipeline", prompt: "Show me the current sales pipeline" },
      { label: "Financials", prompt: "Get the financial summary for this quarter" },
    ],
    support: [
      { label: "Customer 360", prompt: "Show me the full 360 view for customer " },
      { label: "Create ticket", prompt: "Create a support ticket: " },
      { label: "Network status", prompt: "Check network status for customer " },
    ],
  }

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full">
      {/* Conversation List Sidebar */}
      <div className="w-56 flex-shrink-0 border-r border-border bg-background/50 flex flex-col">
        <div className="p-3 border-b border-border">
          <Button size="sm" className="w-full gap-2" onClick={startNewConversation}>
            <Plus className="h-4 w-4" />
            New Chat
          </Button>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {conversations.length === 0 && (
              <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                No conversations yet. Start a chat with any agent.
              </p>
            )}
            {conversations.map((conv) => {
              const agentInfo = AGENT_CATALOG[conv.agentType]
              const lastMessage = conv.messages[conv.messages.length - 1]
              return (
                <div key={conv.id} className="flex items-start gap-1">
                  <button
                    onClick={() => setActiveConversationId(conv.id)}
                    className={cn(
                      "flex min-w-0 flex-1 items-start gap-2 rounded-md px-2 py-2 text-left transition-colors",
                      activeConversationId === conv.id
                        ? "bg-primary/10 text-primary"
                        : "text-foreground hover:bg-secondary",
                    )}
                  >
                    <span className="mt-0.5 text-sm">{agentInfo.icon}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-medium">{agentInfo.name}</span>
                        <span className="text-[10px] text-muted-foreground">
                          {conv.createdAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      {lastMessage && (
                        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                          {lastMessage.role === "user" ? "You: " : ""}
                          {lastMessage.content.slice(0, 40)}
                        </p>
                      )}
                    </div>
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      <DropdownMenuItem className="gap-2" onClick={() => setActiveConversationId(conv.id)}>
                        <MessageSquare className="h-4 w-4" />
                        Open
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2">
                        <Edit3 className="h-4 w-4" />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuItem className="gap-2 text-red-400">
                        <Trash2 className="h-4 w-4" />
                        Close
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              )
            })}
          </div>
        </ScrollArea>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {!activeConversation ? (
          /* No conversation selected — show agent picker + quick start */
          <div className="flex-1 flex flex-col items-center justify-center p-6">
            <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
              <Bot className="h-8 w-8 text-primary" />
            </div>
            <h3 className="text-lg font-semibold text-foreground">Agent Channel</h3>
            <p className="mt-1 text-sm text-muted-foreground text-center max-w-sm">
              Chat with AI agents that have full access to your OmniDome operating system.
              Each agent specializes in different tasks.
            </p>

            {/* Agent selection grid */}
            <div className="mt-6 grid grid-cols-1 gap-2 w-full max-w-md">
              {(Object.entries(AGENT_CATALOG) as [AgentType, typeof AGENT_CATALOG[AgentType]][]).map(
                ([type, info]) => (
                  <button
                    key={type}
                    onClick={() => {
                      setSelectedAgent(type)
                      const newConv: AgentConversation = {
                        id: `conv-${Date.now()}`,
                        agentType: type,
                        messages: [],
                        createdAt: new Date(),
                      }
                      setConversations((prev) => [newConv, ...prev])
                      setActiveConversationId(newConv.id)
                    }}
                    className="flex items-center gap-3 rounded-lg border border-border bg-card p-3 text-left hover:bg-secondary transition-colors"
                  >
                    <span className="text-2xl">{info.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">{info.name}</span>
                        {agents.find((a) => a.agent_type === type) && (
                          <Badge variant="secondary" className="text-[10px]">
                            {agents.find((a) => a.agent_type === type)?.tools.length} tools
                          </Badge>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">{info.description}</p>
                    </div>
                    <Sparkles className="h-4 w-4 text-muted-foreground" />
                  </button>
                ),
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Chat Header */}
            <div className="flex items-center justify-between border-b border-border px-4 py-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">{activeAgent.icon}</span>
                <div>
                  <span className="text-sm font-medium text-foreground">{activeAgent.name}</span>
                  <p className="text-[10px] text-muted-foreground">
                    {agents.find((a) => a.agent_type === selectedAgent)?.tools.length || "—"} tools available
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setActiveConversationId(null)
                  }}
                  className="h-7 text-xs"
                >
                  <Trash2 className="h-3 w-3 mr-1" />
                  Close
                </Button>
              </div>
            </div>

            {/* Quick Actions */}
            {activeConversation.messages.length === 0 && (
              <div className="border-b border-border bg-background/30 px-4 py-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Quick actions:</p>
                <div className="flex flex-wrap gap-1.5">
                  {quickActions[activeConversation.agentType]?.map((action) => (
                    <button
                      key={action.label}
                      onClick={() => {
                        setInputValue(action.prompt)
                        inputRef.current?.focus()
                      }}
                      className="rounded-md border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 border-b border-red-500/30 bg-red-500/10 px-4 py-2">
                <span className="text-xs text-red-400">{error}</span>
                <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
                  <span className="text-xs">Dismiss</span>
                </button>
              </div>
            )}

            {/* Messages */}
            <ScrollArea className="flex-1">
              <div className="space-y-4 p-4">
                {activeConversation.messages.map((message) => (
                  <div key={message.id}>
                    <div
                      className={cn(
                        "flex gap-2",
                        message.role === "user" ? "justify-end" : "justify-start",
                      )}
                    >
                      <div
                        className={cn(
                          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                          message.role === "user"
                            ? "bg-primary text-primary-foreground"
                            : "bg-secondary text-foreground",
                        )}
                      >
                        <p className="whitespace-pre-wrap">{message.content}</p>
                        {message.isStreaming && (
                          <span className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Thinking...
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Tool calls */}
                    {message.toolCalls && message.toolCalls.length > 0 && (
                      <div className="mt-2 ml-2 space-y-1.5">
                        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                          Tools used:
                        </p>
                        {message.toolCalls.map((tc, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-2 rounded-md border border-border/50 bg-background/50 px-2.5 py-1.5"
                          >
                            <Wrench className="h-3 w-3 text-cyan-400" />
                            <span className="text-xs font-mono text-foreground">{tc.name}</span>
                            <span className="text-[10px] text-muted-foreground truncate">
                              {JSON.stringify(tc.args).slice(0, 60)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>

            {/* Input */}
            <div className="border-t border-border p-4">
              <div className="flex gap-2">
                <Input
                  ref={inputRef}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder={`Message ${activeAgent.name}...`}
                  className="flex-1"
                  disabled={isSending}
                />
                <Button
                  onClick={handleSend}
                  disabled={isSending || !inputValue.trim()}
                  size="icon"
                  className="shrink-0"
                >
                  {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
              <p className="mt-1.5 text-[10px] text-muted-foreground">
                {activeAgent.name} has access to {agents.find((a) => a.agent_type === selectedAgent)?.tools.length || "—"} tools across your OmniDome OS
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
