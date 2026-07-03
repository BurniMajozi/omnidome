"use client"

import type React from "react"

import { useState, useRef, useEffect, useCallback } from "react"
import {
  X,
  Send,
  Bot,
  Sparkles,
  Wrench,
  ChevronDown,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Cpu,
  Play,
  Square,
  Mic,
  MicOff,
  Volume2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  invokeAgentAGUI,
  AGENT_CATALOG,
  type AGUIEvent,
  type AGUIStreamState,
  type ToolCallEvent,
  type AgentInfo,
} from "@/lib/orchestrator-api"
import { transcribe as voiceboxTranscribe, speak as voiceboxSpeak } from "@/lib/voicebox-api"
import { toWav } from "@/lib/audio-utils"

// ── Types ────────────────────────────────────────────────────────────────

interface AGUIMessage {
  id: string
  role: "user" | "assistant"
  content: string
  isStreaming?: boolean
  toolCalls?: ToolCallEvent[]
  memoryWrites?: { correlationId?: string; status?: string }[]
}

type AgentType = keyof typeof AGENT_CATALOG

const AGENT_LIST = Object.entries(AGENT_CATALOG).map(([type, info]) => ({
  type: type as AgentType,
  ...info,
}))

// ── Component ────────────────────────────────────────────────────────────

interface AGUIChatProps {
  isOpen: boolean
  onClose: () => void
  initialAgent?: AgentType
  context?: Record<string, unknown>
}

export function AGUIChat({ isOpen, onClose, initialAgent, context: initialContext }: AGUIChatProps) {
  const [messages, setMessages] = useState<AGUIMessage[]>([])
  const [inputValue, setInputValue] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<AgentType>(initialAgent || "customer_facing")
  const [showAgentPicker, setShowAgentPicker] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [context] = useState<Record<string, unknown>>(initialContext || {})
  const [error, setError] = useState<string | null>(null)
  const [streamState, setStreamState] = useState<AGUIStreamState>({
    runId: "",
    status: "idle",
    content: "",
    toolCalls: [],
    memoryWrites: [],
  })

  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [speakingMessageId, setSpeakingMessageId] = useState<string | null>(null)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const voiceRecorder = useRef<MediaRecorder | null>(null)
  const voiceChunks = useRef<Blob[]>([])

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  const startVoiceRecording = useCallback(async () => {
    setVoiceError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : ""
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      voiceChunks.current = []
      recorder.ondataavailable = (e) => e.data.size > 0 && voiceChunks.current.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const rawBlob = new Blob(voiceChunks.current, { type: mimeType || "audio/webm" })
        if (rawBlob.size < 100) {
          setVoiceError("No audio captured — hold the button while speaking, then release.")
          return
        }
        const wavBlob = await toWav(rawBlob).catch(() => rawBlob)
        setIsTranscribing(true)
        try {
          const result = await voiceboxTranscribe(wavBlob)
          if (result.text?.trim()) {
            setInputValue((prev) => (prev ? `${prev} ${result.text}` : result.text).trim())
          }
        } catch (err) {
          console.error("Voice transcription failed", err)
          setVoiceError(err instanceof Error ? err.message : "Transcription failed")
        } finally {
          setIsTranscribing(false)
        }
      }
      recorder.start(250) // timeslice ensures ondataavailable fires even for short recordings
      voiceRecorder.current = recorder
      setIsRecording(true)
    } catch (err) {
      console.error("Microphone access denied", err)
      setVoiceError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access denied — allow it in your browser's site permissions."
          : "Could not access microphone",
      )
    }
  }, [])

  const stopVoiceRecording = useCallback(() => {
    voiceRecorder.current?.stop()
    setIsRecording(false)
  }, [])

  const handleSpeakMessage = async (message: AGUIMessage) => {
    if (!message.content?.trim()) return
    setSpeakingMessageId(message.id)
    setVoiceError(null)
    try {
      const blob = await voiceboxSpeak({
        text: message.content,
        scope: "orchestrator_agent_type",
        scope_ref: selectedAgent,
        requested_by_service: "ag_ui_chat",
      })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => setSpeakingMessageId(null)
      audio.onerror = () => setSpeakingMessageId(null)
      await audio.play()
    } catch (err) {
      console.error("Speak failed", err)
      setVoiceError(
        err instanceof Error
          ? `${err.message} — bind a voice to "${selectedAgent}" in Call Center → Voice Studio first.`
          : "Speech playback failed",
      )
      setSpeakingMessageId(null)
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  useEffect(() => {
    if (!isOpen) {
      setMessages([])
      setInputValue("")
      setConversationId(null)
      setError(null)
      setStreamState({ runId: "", status: "idle", content: "", toolCalls: [], memoryWrites: [] })
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    fetch("/api/orchestrator/agents")
      .then((r) => r.json())
      .then((data: AgentInfo[]) => setAgents(data))
      .catch(() => {})
  }, [isOpen])

  const activeAgent = AGENT_CATALOG[selectedAgent]

  // ── Send message via AG-UI streaming ───────────────────────────────────

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isSending) return
    setError(null)

    const messageText = inputValue

    const userMessage: AGUIMessage = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
    }

    const assistantId = (Date.now() + 1).toString()
    const streamingMessage: AGUIMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      isStreaming: true,
      toolCalls: [],
      memoryWrites: [],
    }

    setMessages((prev) => [...prev, userMessage, streamingMessage])
    setInputValue("")
    setIsSending(true)
    setStreamState({ runId: "", status: "running", content: "", toolCalls: [], memoryWrites: [] })

    try {
      await invokeAgentAGUI(
        {
          agent_type: selectedAgent,
          message: messageText,
          context: {
            ...context,
            conversation_id: conversationId,
          },
          conversation_id: conversationId || undefined,
          stream_tokens: true,
        },
        (event: AGUIEvent) => {
          setStreamState((prev) => {
            const next = { ...prev }
            next.runId = event.run_id

            switch (event.type) {
              case "RUN_STARTED":
                next.status = "running"
                break

              case "TEXT_MESSAGE_CONTENT":
                next.content += (event.data.delta as string) || ""
                // Update the streaming message content
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: next.content }
                      : m,
                  ),
                )
                break

              case "TOOL_CALL_START":
                next.toolCalls = [
                  ...next.toolCalls,
                  {
                    runId: event.run_id,
                    toolCallId: event.data.tool_call_id as string,
                    toolName: event.data.tool_name as string,
                    arguments: event.data.arguments as Record<string, unknown>,
                    status: "start",
                  },
                ]
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? { ...m, toolCalls: next.toolCalls }
                      : m,
                  ),
                )
                break

              case "TOOL_CALL_RESULT":
                next.toolCalls = next.toolCalls.map((tc) =>
                  tc.toolCallId === event.data.tool_call_id
                    ? { ...tc, result: event.data.result, status: "result" as const }
                    : tc,
                )
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? { ...m, toolCalls: next.toolCalls }
                      : m,
                  ),
                )
                break

              case "TOOL_CALL_END":
                next.toolCalls = next.toolCalls.map((tc) =>
                  tc.toolCallId === event.data.tool_call_id
                    ? { ...tc, status: "end" as const }
                    : tc,
                )
                break

              case "MEMORY_WRITE":
                next.memoryWrites = [
                  ...next.memoryWrites,
                  {
                    runId: (event.data.run_id as string) ?? (event.data.correlation_id as string) ?? "",
                    correlationId: event.data.correlation_id as string,
                    status: event.data.status as string,
                  },
                ]
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? { ...m, memoryWrites: next.memoryWrites }
                      : m,
                  ),
                )
                break

              case "RUN_FINISHED":
                next.status = "finished"
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? { ...m, isStreaming: false }
                      : m,
                  ),
                )
                break

              case "RUN_ERROR":
                next.status = "error"
                next.error = event.data.error as string
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          content: `⚠️ Error: ${event.data.error}`,
                          isStreaming: false,
                        }
                      : m,
                  ),
                )
                break
            }

            return next
          })
        },
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
      setStreamState((prev) => ({ ...prev, status: "error" }))
    } finally {
      setIsSending(false)
    }
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
            <h3 className="font-semibold text-foreground">AG-UI Agent Chat</h3>
            <p className="text-xs text-muted-foreground">Typed streaming with tool call events</p>
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
                        setConversationId(null)
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

        {/* Stream state indicator */}
        {streamState.status !== "idle" && (
          <div className="mt-2 flex items-center gap-2">
            <div
              className={cn(
                "h-2 w-2 rounded-full",
                streamState.status === "running" && "bg-amber-400 animate-pulse",
                streamState.status === "finished" && "bg-emerald-400",
                streamState.status === "error" && "bg-red-400",
              )}
            />
            <span className="text-xs text-muted-foreground capitalize">{streamState.status}</span>
            {streamState.runId && (
              <span className="text-[10px] text-muted-foreground font-mono">
                run: {streamState.runId.slice(0, 8)}...
              </span>
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

      {/* Messages Area */}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                <span className="text-2xl">{activeAgent.icon}</span>
              </div>
              <p className="text-sm font-medium text-foreground">{activeAgent.name} ready</p>
              <p className="mt-1 text-xs text-muted-foreground">
                AG-UI typed streaming — tool calls, memory writes, and structured events
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

                {message.isStreaming && (
                  <span className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Streaming...
                  </span>
                )}
              </div>
              {message.role === "assistant" && !message.isStreaming && message.content && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 shrink-0 self-end"
                  onClick={() => handleSpeakMessage(message)}
                  disabled={speakingMessageId === message.id}
                  title="Speak message"
                >
                  {speakingMessageId === message.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Volume2 className="h-3.5 w-3.5 text-muted-foreground" />
                  )}
                </Button>
              )}
            </div>

            {/* Tool call events */}
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="mt-2 ml-2 space-y-1.5">
                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Tool Calls:
                </p>
                {message.toolCalls.map((tc, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 rounded-md border border-border/50 bg-background/50 px-2.5 py-1.5"
                  >
                    <Wrench className={cn(
                      "h-3 w-3",
                      tc.status === "start" && "text-amber-400",
                      tc.status === "result" && "text-cyan-400",
                      tc.status === "end" && "text-emerald-400",
                    )} />
                    <span className="text-xs font-mono text-foreground">{tc.toolName}</span>
                    {tc.status === "start" && (
                      <Loader2 className="h-3 w-3 animate-spin text-amber-400" />
                    )}
                    {tc.status === "end" && (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    )}
                    {tc.arguments && (
                      <span className="text-[10px] text-muted-foreground truncate">
                        {JSON.stringify(tc.arguments).slice(0, 60)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Memory write events */}
            {message.memoryWrites && message.memoryWrites.length > 0 && (
              <div className="mt-2 ml-2 space-y-1">
                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Memory:
                </p>
                {message.memoryWrites.map((mw, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 rounded-md border border-border/50 bg-background/50 px-2.5 py-1.5"
                  >
                    <Cpu className="h-3 w-3 text-purple-400" />
                    <span className="text-xs text-muted-foreground">
                      {mw.status === "written" ? "Written" : "Writing"} — {mw.correlationId?.slice(0, 8)}...
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-border bg-secondary p-4">
        {voiceError && (
          <div className="mb-2 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
            <span>{voiceError}</span>
            <button type="button" onClick={() => setVoiceError(null)} className="ml-2 shrink-0 hover:text-red-300">×</button>
          </div>
        )}
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSendMessage()
              }
            }}
            placeholder={`Message ${activeAgent.name}...`}
            className="flex-1"
            disabled={isSending}
          />
          <Button
            variant={isRecording ? "destructive" : "outline"}
            size="icon"
            onClick={isRecording ? stopVoiceRecording : startVoiceRecording}
            disabled={isTranscribing}
            title={isRecording ? "Stop recording" : "Voice input"}
          >
            {isTranscribing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isRecording ? (
              <MicOff className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </Button>
          <Button
            onClick={handleSendMessage}
            disabled={isSending || !inputValue.trim()}
            size="icon"
          >
            {isSending ? (
              <Square className="h-4 w-4" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          AG-UI streaming • Tool calls visible • Memory writes tracked • Voice in/out via Voicebox
        </p>
      </div>
    </div>
  )
}
