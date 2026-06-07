"use client"

import type React from "react"

import { useState, useRef, useEffect, useCallback } from "react"
import {
  X,
  Send,
  Mic,
  MessageCircle,
  Upload,
  FileText,
  LinkIcon,
  ImageIcon,
  Bot,
  Sparkles,
  Wrench,
  ChevronDown,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  invokeAgent,
  AGENT_CATALOG,
  type AgentInvokeResponse,
  type AgentInfo,
} from "@/lib/orchestrator-api"

// ── Types ────────────────────────────────────────────────────────────────

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  type: "text" | "voice" | "file"
  attachments?: Array<{ type: string; name: string; url?: string }>
  toolCalls?: Array<{ name: string; args: Record<string, unknown>; result: unknown }>
  isStreaming?: boolean
}

type AgentType = keyof typeof AGENT_CATALOG

const AGENT_LIST = Object.entries(AGENT_CATALOG).map(([type, info]) => ({
  type: type as AgentType,
  ...info,
}))

// ── Component ────────────────────────────────────────────────────────────

interface AITaskChatProps {
  isOpen: boolean
  onClose: () => void
  /** Pre-selected agent (e.g. from sidebar quick-action) */
  initialAgent?: AgentType
  /** OmniDome context — current customer, property, etc. */
  context?: Record<string, unknown>
}

export function AITaskChat({ isOpen, onClose, initialAgent, context: initialContext }: AITaskChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState("")
  const [interactionMode, setInteractionMode] = useState<"type" | "voice" | "converse" | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [attachments, setAttachments] = useState<File[]>([])
  const [linkInput, setLinkInput] = useState("")
  const [showLinkInput, setShowLinkInput] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<AgentType>(initialAgent || "customer_facing")
  const [showAgentPicker, setShowAgentPicker] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [context] = useState<Record<string, unknown>>(initialContext || {})
  const [error, setError] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  useEffect(() => {
    if (!isOpen) {
      setInteractionMode(null)
      setMessages([])
      setAttachments([])
      setInputValue("")
      setShowLinkInput(false)
      setConversationId(null)
      setError(null)
    }
  }, [isOpen])

  // Load agent info on mount
  useEffect(() => {
    if (!isOpen) return
    fetch("/api/orchestrator/agents")
      .then((r) => r.json())
      .then((data: AgentInfo[]) => setAgents(data))
      .catch(() => {}) // silent — we have the catalog fallback
  }, [isOpen])

  const activeAgent = AGENT_CATALOG[selectedAgent]

  // ── Send message via orchestrator ──────────────────────────────────────

  const handleSendMessage = async () => {
    if (!inputValue.trim() && attachments.length === 0) return
    setError(null)

    const messageText = inputValue
    const attachmentSummary =
      attachments.length > 0
        ? `\n\nAttachments:\n${attachments.map((f) => `- ${f.name} (${f.type || "unknown"})`).join("\n")}`
        : ""

    const fullMessage = `${messageText}${attachmentSummary}`

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
      type: interactionMode === "voice" ? "voice" : "text",
      attachments: attachments.map((file) => ({ type: file.type, name: file.name })),
    }

    const assistantId = (Date.now() + 1).toString()
    const streamingMessage: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      type: "text",
      isStreaming: true,
    }

    setMessages((prev) => [...prev, userMessage, streamingMessage])
    setInputValue("")
    setAttachments([])
    setIsSending(true)

    try {
      const response = await invokeAgent({
        agent_type: selectedAgent,
        message: fullMessage,
        context: {
          ...context,
          conversation_id: conversationId,
          // Tell the agent this is a task creation context
          ui_context: "task_creation",
        },
        conversation_id: conversationId || undefined,
      })

      setConversationId(response.conversation_id)

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: response.message,
                toolCalls: response.tool_calls,
                isStreaming: false,
              }
            : m,
        ),
      )
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: `⚠️ Error: ${err instanceof Error ? err.message : "Failed to reach agent"}`,
                isStreaming: false,
              }
            : m,
        ),
      )
      setError(err instanceof Error ? err.message : "Agent error")
    } finally {
      setIsSending(false)
    }
  }

  // ── Voice recording ────────────────────────────────────────────────────

  const handleStartRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      const audioChunks: Blob[] = []

      mediaRecorder.ondataavailable = (event) => audioChunks.push(event.data)
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: "audio/wav" })
        const file = new File([audioBlob], `audio-${Date.now()}.wav`, { type: "audio/wav" })
        setAttachments((prev) => [...prev, file])
      }

      mediaRecorder.start()
      setIsRecording(true)
    } catch (error) {
      console.error("Error accessing microphone:", error)
    }
  }

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop())
      setIsRecording(false)
    }
  }

  // ── File upload ────────────────────────────────────────────────────────

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (files) setAttachments((prev) => [...prev, ...Array.from(files)])
    e.currentTarget.value = ""
  }

  const handleAddLink = () => {
    if (linkInput.trim()) {
      setInputValue((prev) => (prev ? `${prev} ${linkInput}` : linkInput))
      setLinkInput("")
      setShowLinkInput(false)
    }
  }

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index))
  }

  // ── Render ─────────────────────────────────────────────────────────────

  if (!isOpen) return null

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex h-screen w-full flex-shrink-0 flex-col border-l border-border bg-card sm:w-[420px] md:static md:z-auto md:h-screen md:w-[400px]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-secondary p-4">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <div>
            <h3 className="font-semibold text-foreground">Agent Task Assistant</h3>
            <p className="text-xs text-muted-foreground">AI-powered with OmniDome context</p>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Agent Selector */}
      <div className="border-b border-border bg-background/50 px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">Agent</span>
          <div className="relative">
            <button
              onClick={() => setShowAgentPicker(!showAgentPicker)}
              className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-sm hover:bg-secondary transition-colors"
            >
              <span>{activeAgent.icon}</span>
              <span className="font-medium text-foreground">{activeAgent.name}</span>
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>

            {showAgentPicker && (
              <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-border bg-card shadow-xl">
                <div className="p-1">
                  {AGENT_LIST.map((agent) => (
                    <button
                      key={agent.type}
                      onClick={() => {
                        setSelectedAgent(agent.type)
                        setShowAgentPicker(false)
                        setConversationId(null) // new agent = new conversation
                        setMessages([])
                      }}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-md px-3 py-2.5 text-left transition-colors",
                        selectedAgent === agent.type
                          ? "bg-primary/10 text-primary"
                          : "text-foreground hover:bg-secondary",
                      )}
                    >
                      <span className="mt-0.5 text-lg">{agent.icon}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{agent.name}</span>
                          {selectedAgent === agent.type && (
                            <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
                          {agent.description}
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Agent tool badges */}
        {agents.find((a) => a.agent_type === selectedAgent) && (
          <div className="mt-2 flex flex-wrap gap-1">
            {agents
              .find((a) => a.agent_type === selectedAgent)
              ?.tools.slice(0, 6)
              .map((tool) => (
                <Badge key={tool} variant="secondary" className="text-[10px] px-1.5 py-0">
                  {tool}
                </Badge>
              ))}
            {(agents.find((a) => a.agent_type === selectedAgent)?.tools.length || 0) > 6 && (
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                +{(agents.find((a) => a.agent_type === selectedAgent)?.tools.length || 0) - 6} more
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 border-b border-red-500/30 bg-red-500/10 px-4 py-2">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <span className="text-xs text-red-400">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Interaction Mode Selection (first time) */}
      {!interactionMode && messages.length === 0 && (
        <div className="flex flex-col gap-3 p-4">
          <p className="text-sm text-muted-foreground">
            Choose how you&apos;d like to work with <strong className="text-foreground">{activeAgent.name}</strong>:
          </p>
          <Button onClick={() => setInteractionMode("type")} className="justify-start gap-2" variant="outline">
            <MessageCircle className="h-4 w-4" />
            Type a task or question
          </Button>
          <Button onClick={() => setInteractionMode("voice")} className="justify-start gap-2" variant="outline">
            <Mic className="h-4 w-4" />
            Voice input
          </Button>
          <Button onClick={() => setInteractionMode("converse")} className="justify-start gap-2" variant="outline">
            <Sparkles className="h-4 w-4" />
            Converse with {activeAgent.name}
          </Button>

          {/* Quick actions based on agent type */}
          <div className="mt-2">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Quick actions:</p>
            <div className="flex flex-wrap gap-2">
              {selectedAgent === "customer_facing" && (
                <>
                  <QuickAction label="Check coverage" onClick={() => { setInputValue("Check fibre coverage for "); setInteractionMode("type") }} />
                  <QuickAction label="Create ticket" onClick={() => { setInputValue("Create a support ticket for "); setInteractionMode("type") }} />
                  <QuickAction label="Get balance" onClick={() => { setInputValue("Get the current balance for customer "); setInteractionMode("type") }} />
                </>
              )}
              {selectedAgent === "retention" && (
                <>
                  <QuickAction label="Churn risk report" onClick={() => { setInputValue("Show me the top 10 customers at risk of churning"); setInteractionMode("type") }} />
                  <QuickAction label="Retention cases" onClick={() => { setInputValue("List all open retention cases"); setInteractionMode("type") }} />
                </>
              )}
              {selectedAgent === "provisioning" && (
                <>
                  <QuickAction label="New provisioning" onClick={() => { setInputValue("Start provisioning for new customer "); setInteractionMode("type") }} />
                  <QuickAction label="Check network status" onClick={() => { setInputValue("Check network service status for customer "); setInteractionMode("type") }} />
                </>
              )}
              {selectedAgent === "executive" && (
                <>
                  <QuickAction label="Executive summary" onClick={() => { setInputValue("Give me the executive summary for this month"); setInteractionMode("type") }} />
                  <QuickAction label="Pipeline status" onClick={() => { setInputValue("Show me the current sales pipeline"); setInteractionMode("type") }} />
                </>
              )}
              {selectedAgent === "support" && (
                <>
                  <QuickAction label="Customer 360" onClick={() => { setInputValue("Show me the full 360 view for customer "); setInteractionMode("type") }} />
                  <QuickAction label="Create ticket" onClick={() => { setInputValue("Create a support ticket: "); setInteractionMode("type") }} />
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Messages Area */}
      {interactionMode && (
        <>
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center text-center">
                <div>
                  <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                    <span className="text-2xl">{activeAgent.icon}</span>
                  </div>
                  <p className="text-sm font-medium text-foreground">{activeAgent.name} ready</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Ask me anything about your OmniDome operations
                  </p>
                </div>
              </div>
            )}

            {messages.map((message) => (
              <div key={message.id}>
                <div className={cn("flex gap-2", message.role === "user" ? "justify-end" : "justify-start")}>
                  <div
                    className={cn(
                      "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                      message.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary text-foreground",
                    )}
                  >
                    <p className="whitespace-pre-wrap">{message.content}</p>

                    {/* Streaming indicator */}
                    {message.isStreaming && (
                      <span className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Thinking...
                      </span>
                    )}

                    {/* Attachments */}
                    {message.attachments && message.attachments.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {message.attachments.map((attachment, idx) => (
                          <div
                            key={idx}
                            className={cn(
                              "flex items-center gap-2 text-xs",
                              message.role === "user" ? "text-primary-foreground/70" : "text-muted-foreground",
                            )}
                          >
                            <FileText className="h-3 w-3" />
                            {attachment.name}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Tool calls used by agent */}
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

          {/* Attachments Preview */}
          {attachments.length > 0 && (
            <div className="border-t border-border bg-secondary p-3">
              <div className="space-y-2">
                {attachments.map((file, idx) => (
                  <div key={idx} className="flex items-center justify-between rounded bg-background p-2 text-xs">
                    <span className="truncate text-muted-foreground">{file.name}</span>
                    <button onClick={() => removeAttachment(idx)} className="text-muted-foreground hover:text-foreground">
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Link Input */}
          {showLinkInput && (
            <div className="border-t border-border bg-secondary p-3">
              <div className="flex gap-2">
                <Input
                  value={linkInput}
                  onChange={(e) => setLinkInput(e.target.value)}
                  placeholder="Paste URL here..."
                  className="flex-1 text-sm"
                  onKeyPress={(e) => e.key === "Enter" && handleAddLink()}
                />
                <Button size="sm" onClick={handleAddLink}>Add</Button>
                <Button size="sm" variant="ghost" onClick={() => setShowLinkInput(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}

          {/* Input Area */}
          <div className="space-y-3 border-t border-border p-4">
            <div className="flex gap-2">
              <Input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
                placeholder={interactionMode === "voice" ? "Add notes or press Record..." : `Ask ${activeAgent.name}...`}
                className="flex-1"
              />
              <Button
                onClick={handleSendMessage}
                disabled={isSending || (!inputValue.trim() && attachments.length === 0)}
                size="icon"
                className="shrink-0"
              >
                {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>

            <div className="flex gap-2">
              <input ref={fileInputRef} type="file" multiple onChange={handleFileUpload} className="hidden" accept=".pdf,.doc,.docx,.txt" />
              <input ref={imageInputRef} type="file" multiple onChange={handleFileUpload} className="hidden" accept="image/*" />
              <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()} className="flex-1 gap-1 text-xs">
                <Upload className="h-3 w-3" /> Docs
              </Button>
              <Button variant="outline" size="sm" onClick={() => imageInputRef.current?.click()} className="flex-1 gap-1 text-xs">
                <ImageIcon className="h-3 w-3" /> Image
              </Button>
              <Button variant="outline" size="sm" className="flex-1 gap-1 text-xs bg-transparent" onClick={() => setShowLinkInput(true)}>
                <LinkIcon className="h-3 w-3" /> Link
              </Button>
              {interactionMode === "voice" && (
                <Button
                  variant={isRecording ? "destructive" : "outline"}
                  size="sm"
                  onClick={isRecording ? handleStopRecording : handleStartRecording}
                  className="flex-1 gap-1 text-xs"
                >
                  <Mic className="h-3 w-3" />
                  {isRecording ? "Stop" : "Rec"}
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Quick Action Button ──────────────────────────────────────────────────

function QuickAction({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-md border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
    >
      {label}
    </button>
  )
}
