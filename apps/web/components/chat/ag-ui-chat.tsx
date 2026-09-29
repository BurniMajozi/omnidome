"use client"

import type React from "react"

import { useState, useRef, useEffect, useCallback, useMemo } from "react"
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
  Square,
  Mic,
  MicOff,
  Volume2,
  FileCode2,
  Copy,
  Check,
  PanelRightClose,
  Hash,
  ThumbsUp,
  ThumbsDown,
  History,
  Plus,
  Trash2,
  Clock,
  MessageSquare,
  Eye,
  Code,
  Maximize2,
  Minimize2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import {
  invokeAgentAGUI,
  listAgents,
  recordAgentFeedback,
  listConversations,
  getConversation,
  deleteConversation,
  AGENT_CATALOG,
  type AGUIEvent,
  type AGUIStreamState,
  type ToolCallEvent,
  type AgentInfo,
  type ConversationRead,
} from "@/lib/orchestrator-api"
import { transcribe as voiceboxTranscribe, speak as voiceboxSpeak } from "@/lib/voicebox-api"
import { toWavWithStats, SILENCE_RMS_THRESHOLD } from "@/lib/audio-utils"
import { getSavedMicId, saveMicId, resolvePreferredMicId, micAudioConstraints } from "@/lib/mic-device"

// ── Types ────────────────────────────────────────────────────────────────

interface AGUIMessage {
  id: string
  role: "user" | "assistant"
  content: string
  isStreaming?: boolean
  toolCalls?: ToolCallEvent[]
  memoryWrites?: { correlationId?: string; status?: string }[]
  routedAgent?: string
  routedAgentName?: string
}

export interface Artifact {
  id: string
  title: string
  lang: string
  code: string
}

export interface Segment {
  type: "text" | "artifact"
  value: string
}

type AgentType = keyof typeof AGENT_CATALOG

const AGENT_LIST = [
  { type: "auto" as AgentType, name: "OmniDome Orchestrator", icon: "🧠", description: "Smart routing. Automatically analyzes your request and dispatches to the best specialist agent." },
  { type: "customer_facing" as AgentType, name: "DomeBot", icon: "🤖", description: "Customer-facing assistant. Handles balances, invoices, coverage checks, ticket creation." },
  { type: "executive" as AgentType, name: "InsightDome", icon: "📊", description: "Executive briefings. MRR, churn, ARPU, pipeline, financial summaries." },
  { type: "retention" as AgentType, name: "ChurnGuard", icon: "🛡️", description: "Autonomous churn prediction and retention risk scores." },
  { type: "provisioning" as AgentType, name: "ProvisionBot", icon: "⚡", description: "Onboarding automation. Checks coverage, creates accounts, provisions services." },
  { type: "support" as AgentType, name: "SupportBot", icon: "🔧", description: "Support ticket management and diagnostics with 360° context." },
  { type: "assistant" as AgentType, name: "OmniAssist", icon: "✨", description: "Versatile assistant. Writes docs, SQL, and code into the canvas." },
]

const DEFAULT_TEAM_USERS = [
  { id: "u-1", name: "Sarah Chen", email: "sarah.chen@omnidome.co.za" },
  { id: "u-2", name: "Mike Johnson", email: "mike.johnson@omnidome.co.za" },
  { id: "u-3", name: "Emily Davis", email: "emily.davis@omnidome.co.za" },
  { id: "u-4", name: "James Wilson", email: "james.wilson@omnidome.co.za" },
  { id: "u-5", name: "Lisa Park", email: "lisa.park@omnidome.co.za" },
]

const AGENT_ITEMS = [
  ...AGENT_LIST.map((a) => ({
    id: `agent-${a.type}`,
    name: a.name,
    role: a.description,
    agent_type: a.type,
    isAgent: true,
    icon: a.icon,
  })),
  {
    id: "agent-insightbot-alias",
    name: "InsightBot",
    role: "Executive briefings & MRR",
    agent_type: "executive" as AgentType,
    isAgent: true,
    icon: "📊",
  },
]

const PLATFORM_COMPONENTS = [
  "sales", "marketing", "crm", "finance", "network", "support",
  "retention", "inventory", "billing", "analytics", "provisioning",
  "compliance", "portal", "call-center", "hr",
]

const CHANNELS_LIST = [
  { id: "c-general", name: "general" },
  { id: "c-sales", name: "sales-team" },
  { id: "c-support", name: "support-tickets" },
  { id: "c-network", name: "network-alerts" },
  { id: "c-marketing", name: "marketing" },
]

const FENCE = /```([^\n\r`]+)?\n?([\s\S]*?)```/g

function extractArtifactTitle(code: string, langInfo: string, idx: number): string {
  const titleAttr = langInfo.match(/title=["']([^"']+)["']/i)
  if (titleAttr && titleAttr[1].trim()) {
    return titleAttr[1].trim()
  }

  const lines = code.trim().split("\n")
  for (let i = 0; i < Math.min(lines.length, 6); i++) {
    const line = lines[i].trim()
    const headingMatch = line.match(/^#{1,3}\s+([^#\n\r]+)/)
    if (headingMatch && headingMatch[1].trim()) {
      return headingMatch[1].trim().replace(/[*_`]/g, "")
    }
    const subjectMatch = line.match(/^Subject:\s*(.+)$/i)
    if (subjectMatch && subjectMatch[1].trim()) {
      return `Email: ${subjectMatch[1].trim()}`
    }
    const titleLineMatch = line.match(/^Title:\s*(.+)$/i)
    if (titleLineMatch && titleLineMatch[1].trim()) {
      return titleLineMatch[1].trim().replace(/[*_`]/g, "")
    }
  }

  const lower = code.toLowerCase()
  if (lower.includes("subject:") || lower.includes("dear ") || lower.includes("recipient:") || langInfo.includes("email")) {
    return `Email Draft (${idx + 1})`
  }
  if (lower.includes("slide ") || lower.includes("presentation") || lower.includes("agenda") || langInfo.includes("presentation") || langInfo.includes("deck")) {
    return `Presentation Outline (${idx + 1})`
  }
  if (lower.includes("strategy") || lower.includes("proposal") || lower.includes("action plan") || lower.includes("executive summary")) {
    return `Strategy Proposal (${idx + 1})`
  }
  if (langInfo.includes("sql") || lower.includes("select ") || lower.includes("from ")) {
    return `SQL Query (${idx + 1})`
  }

  return `Proposal Artifact ${idx + 1}`
}

function parseMessage(msgId: string, content: string): { segments: Segment[]; artifacts: Artifact[] } {
  const segments: Segment[] = []
  const artifacts: Artifact[] = []
  let last = 0
  let idx = 0
  let m: RegExpExecArray | null
  FENCE.lastIndex = 0
  while ((m = FENCE.exec(content)) !== null) {
    if (m.index > last) segments.push({ type: "text", value: content.slice(last, m.index) })
    const rawLang = (m[1] || "text").trim()
    const lang = rawLang.split(/[\s:]/)[0].toLowerCase() || "text"
    const code = m[2] ?? ""
    const id = `${msgId}-art-${idx}`
    const title = extractArtifactTitle(code, rawLang, idx)
    artifacts.push({ id, title, lang, code })
    segments.push({ type: "artifact", value: id })
    last = m.index + m[0].length
    idx += 1
  }
  if (last < content.length) segments.push({ type: "text", value: content.slice(last) })
  if (segments.length === 0) segments.push({ type: "text", value: content })
  return { segments, artifacts }
}

// ── Markdown & Table Formatter Component ─────────────────────────────────

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const tokens: React.ReactNode[] = []
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(text.slice(lastIndex, match.index))
    }
    const token = match[0]
    if (token.startsWith("`") && token.endsWith("`")) {
      tokens.push(
        <code key={match.index} className="px-1.5 py-0.5 rounded bg-muted/80 text-[11px] font-mono text-cyan-300 border border-border/50">
          {token.slice(1, -1)}
        </code>
      )
    } else if (token.startsWith("**") && token.endsWith("**")) {
      tokens.push(
        <strong key={match.index} className="font-semibold text-foreground">
          {token.slice(2, -2)}
        </strong>
      )
    } else if (token.startsWith("*") && token.endsWith("*")) {
      tokens.push(
        <em key={match.index} className="italic text-foreground/90">
          {token.slice(1, -1)}
        </em>
      )
    } else if (token.startsWith("[")) {
      const linkMatch = token.match(/\[([^\]]+)\]\(([^)]+)\)/)
      if (linkMatch) {
        tokens.push(
          <a key={match.index} href={linkMatch[2]} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
            {linkMatch[1]}
          </a>
        )
      } else {
        tokens.push(token)
      }
    }
    lastIndex = regex.lastIndex
  }
  if (lastIndex < text.length) {
    tokens.push(text.slice(lastIndex))
  }
  return tokens
}

export function FormattedMarkdown({ content }: { content: string }) {
  if (!content) return null
  const lines = content.split("\n")
  const elements: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Table detection: line starts and ends with '|'
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        tableLines.push(lines[i].trim())
        i++
      }
      if (tableLines.length >= 2) {
        const parseRow = (rowStr: string) =>
          rowStr.slice(1, -1).split("|").map((c) => c.trim())
        const headerCells = parseRow(tableLines[0])
        const hasDivider = tableLines[1].includes("---")
        const bodyLines = hasDivider ? tableLines.slice(2) : tableLines.slice(1)

        elements.push(
          <div key={`table-${i}`} className="overflow-x-auto my-2.5 rounded-md border border-border bg-card/60">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-muted/40 font-semibold border-b border-border">
                  {headerCells.map((hc, idx) => (
                    <th key={idx} className="px-3 py-2 text-foreground font-semibold">
                      {renderInlineMarkdown(hc)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {bodyLines.map((rowStr, rIdx) => {
                  const cells = parseRow(rowStr)
                  return (
                    <tr key={rIdx} className={rIdx % 2 === 1 ? "bg-muted/10 hover:bg-muted/20" : "hover:bg-muted/20"}>
                      {cells.map((cell, cIdx) => (
                        <td key={cIdx} className="px-3 py-2 text-foreground/90 align-top">
                          {renderInlineMarkdown(cell)}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
        continue
      }
    }

    // Headings
    if (line.startsWith("# ")) {
      elements.push(
        <h2 key={i} className="text-base font-bold text-foreground mt-3 mb-1.5 pb-1 border-b border-border/40">
          {renderInlineMarkdown(line.slice(2))}
        </h2>
      )
      i++
      continue
    }
    if (line.startsWith("## ")) {
      elements.push(
        <h3 key={i} className="text-sm font-bold text-cyan-400 mt-2.5 mb-1 flex items-center gap-1.5">
          {renderInlineMarkdown(line.slice(3))}
        </h3>
      )
      i++
      continue
    }
    if (line.startsWith("### ")) {
      elements.push(
        <h4 key={i} className="text-xs font-semibold text-foreground mt-2 mb-0.5">
          {renderInlineMarkdown(line.slice(4))}
        </h4>
      )
      i++
      continue
    }

    // Blockquote
    if (line.startsWith("> ")) {
      elements.push(
        <blockquote key={i} className="border-l-2 border-cyan-500/50 pl-2.5 my-1.5 italic text-xs text-muted-foreground bg-cyan-500/5 py-1 rounded-r">
          {renderInlineMarkdown(line.slice(2))}
        </blockquote>
      )
      i++
      continue
    }

    // Bullet lists
    if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
      const listItems: string[] = []
      while (i < lines.length && (lines[i].trim().startsWith("- ") || lines[i].trim().startsWith("* "))) {
        listItems.push(lines[i].trim().slice(2))
        i++
      }
      elements.push(
        <ul key={`ul-${i}`} className="list-disc list-inside space-y-1 my-1.5 text-xs text-foreground/90 pl-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ul>
      )
      continue
    }

    // Numbered lists
    if (/^\d+\.\s/.test(line.trim())) {
      const listItems: string[] = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^\d+\.\s/, ""))
        i++
      }
      elements.push(
        <ol key={`ol-${i}`} className="list-decimal list-inside space-y-1 my-1.5 text-xs text-foreground/90 pl-1">
          {listItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ol>
      )
      continue
    }

    // Regular line / paragraph
    if (line.trim().length > 0) {
      elements.push(
        <p key={i} className="my-1 text-xs leading-relaxed text-foreground/95">
          {renderInlineMarkdown(line)}
        </p>
      )
    } else {
      elements.push(<div key={i} className="h-1" />)
    }
    i++
  }

  return <div className="space-y-0.5 text-xs">{elements}</div>
}

function formatInitials(name?: string) {
  if (!name) return "??"
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function formatActionChip(toolName?: string, args?: Record<string, unknown>): {
  label: string
  detail?: string
  icon: string
} {
  const name = (toolName || "").toLowerCase()
  const a = args || {}

  if (name.includes("consult_specialist")) {
    const specialist = String(a.specialist || "Specialist").toUpperCase()
    return {
      label: `Consulted Specialist: ${specialist}`,
      detail: a.query ? String(a.query).slice(0, 80) : undefined,
      icon: "👥",
    }
  }

  if (name.includes("coverage") || name.includes("network")) {
    const loc = a.suburb || a.address || a.location || "Network Node"
    return {
      label: `Verified FNO Coverage (${loc})`,
      detail: a.provider ? `Provider: ${a.provider}` : undefined,
      icon: "⚡",
    }
  }

  if (name.includes("email") || name.includes("agentmail")) {
    const to = a.to || a.recipient || "Subscriber"
    return {
      label: `Dispatched Email to ${to}`,
      detail: a.subject ? String(a.subject) : undefined,
      icon: "✉️",
    }
  }

  if (name.includes("ticket")) {
    const tId = a.ticket_id || a.id || ""
    return {
      label: `Created Trouble Ticket ${tId ? `#${tId}` : ""}`,
      detail: a.title ? String(a.title) : undefined,
      icon: "🎫",
    }
  }

  if (name.includes("customer") || name.includes("crm")) {
    const cId = a.customer_id || a.query || "Profile"
    return {
      label: `Retrieved Customer 360 (${cId})`,
      icon: "👤",
    }
  }

  if (name.includes("billing") || name.includes("invoice")) {
    return {
      label: `Processed Invoicing & Balance`,
      detail: a.amount ? `R${a.amount}` : undefined,
      icon: "📄",
    }
  }

  if (name.includes("schedule") || name.includes("task")) {
    return {
      label: `Scheduled Follow-up Action`,
      detail: a.title ? String(a.title) : undefined,
      icon: "📅",
    }
  }

  if (name.includes("ucp") || name.includes("checkout")) {
    return {
      label: `Initialized UCP Checkout Session`,
      detail: a.purpose ? String(a.purpose) : undefined,
      icon: "🛒",
    }
  }

  if (name.includes("ap2") || name.includes("mandate")) {
    return {
      label: `Authorized AP2 Payment Mandate`,
      detail: a.max_amount ? `Max: R${a.max_amount}` : undefined,
      icon: "💳",
    }
  }

  // Generic clean fallback
  const cleanName = name.replace(/^(crm|billing|support|network|sales|orchestrator)\./, "").replace(/_/g, " ")
  return {
    label: cleanName.charAt(0).toUpperCase() + cleanName.slice(1),
    detail: Object.keys(a).length > 0 ? JSON.stringify(a).slice(0, 60) : undefined,
    icon: "⚡",
  }
}

// ── Component ────────────────────────────────────────────────────────────

interface AGUIChatProps {
  isOpen: boolean
  onClose: () => void
  initialAgent?: AgentType
  context?: Record<string, unknown>
  initialDraft?: string
}

export function AGUIChat({ isOpen, onClose, initialAgent, context: initialContext, initialDraft }: AGUIChatProps) {
  const [messages, setMessages] = useState<AGUIMessage[]>([])
  const [inputValue, setInputValue] = useState(initialDraft || "")
  const [isSending, setIsSending] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<AgentType>(initialAgent || "auto")
  const [showAgentPicker, setShowAgentPicker] = useState(false)
  const [panelSize, setPanelSize] = useState<"compact" | "wide" | "expanded">("compact")
  const [customArtifacts, setCustomArtifacts] = useState<Record<string, Artifact>>({})
  const [artifactViewMode, setArtifactViewMode] = useState<"preview" | "code">("preview")
  const [artifactRevisionPrompt, setArtifactRevisionPrompt] = useState("")
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

  useEffect(() => {
    if (initialDraft !== undefined) {
      setInputValue(initialDraft)
      setTimeout(() => inputRef.current?.focus(), 60)
    }
  }, [initialDraft])

  useEffect(() => {
    if (initialAgent && AGENT_LIST.some((a) => a.type === initialAgent)) {
      setSelectedAgent(initialAgent)
    }
  }, [initialAgent])

  useEffect(() => {
    const handleOpenChat = (event: Event) => {
      const customEvent = event as CustomEvent<{ prompt?: string; agent?: AgentType; draft?: string }>
      const prompt = customEvent.detail?.draft || customEvent.detail?.prompt
      const agent = customEvent.detail?.agent
      if (agent && AGENT_LIST.some((a) => a.type === agent)) {
        setSelectedAgent(agent)
      }
      if (prompt) {
        setInputValue(prompt)
        setTimeout(() => inputRef.current?.focus(), 60)
      }
    }
    window.addEventListener("open-agent-chat", handleOpenChat)
    return () => window.removeEventListener("open-agent-chat", handleOpenChat)
  }, [])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  const startVoiceRecording = useCallback(async () => {
    setVoiceError(null)
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone recording is not available in this browser.")
      }
      const resolvedMicId = await resolvePreferredMicId(getSavedMicId())
      saveMicId(resolvedMicId)
      const stream = await navigator.mediaDevices.getUserMedia({ audio: micAudioConstraints(resolvedMicId) })
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
        const stats = await toWavWithStats(rawBlob).catch(() => null)
        if (stats && stats.rms < SILENCE_RMS_THRESHOLD) {
          setVoiceError(
            "The recording contains no sound. Pick the correct microphone in Call Center → Speech to Text, then try again here.",
          )
          return
        }
        const wavBlob = stats ? stats.wav : rawBlob
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

  // Artifact side bar state
  const [artifactEdits, setArtifactEdits] = useState<Record<string, string>>({})
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const [feedbackMap, setFeedbackMap] = useState<Record<string, "thumbs_up" | "thumbs_down">>({})

  const handleCopyMessage = async (message: AGUIMessage) => {
    if (!message.content) return
    try {
      await navigator.clipboard.writeText(message.content)
      setCopiedMessageId(message.id)
      setTimeout(() => setCopiedMessageId(null), 2000)
    } catch {
      /* clipboard blocked */
    }
  }

  const handleFeedback = async (message: AGUIMessage, rating: "thumbs_up" | "thumbs_down") => {
    // Find preceding user prompt if available
    const msgIdx = messages.findIndex((m) => m.id === message.id)
    let prompt = ""
    for (let i = msgIdx - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        prompt = messages[i].content
        break
      }
    }

    setFeedbackMap((prev) => ({ ...prev, [message.id]: rating }))
    try {
      await recordAgentFeedback({
        conversation_id: conversationId || undefined,
        agent_type: selectedAgent,
        satisfaction: rating,
        prompt,
        response: message.content,
      })
    } catch (err) {
      console.error("Failed to record feedback", err)
    }
  }

  // Autocomplete token detection
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const lastToken = inputValue.split(/\s/).pop() ?? ""
  const mentionActive = lastToken.startsWith("@") && lastToken.length >= 1
  const slashActive = lastToken.startsWith("/") && lastToken.length >= 1
  const hashActive = lastToken.startsWith("#") && lastToken.length >= 1

  const mentionQuery = lastToken.slice(1).toLowerCase()
  const mentionMatches = mentionActive
    ? [
        ...AGENT_ITEMS.filter((a) => a.name.toLowerCase().includes(mentionQuery)),
        ...DEFAULT_TEAM_USERS.filter((u) => u.name.toLowerCase().includes(mentionQuery)),
      ].slice(0, 8)
    : []

  const slashMatches = slashActive
    ? PLATFORM_COMPONENTS.filter((c) => c.startsWith(lastToken.slice(1).toLowerCase())).slice(0, 8)
    : []

  const hashMatches = hashActive
    ? CHANNELS_LIST.filter((c) => c.name.toLowerCase().includes(lastToken.slice(1).toLowerCase()))
    : []

  const autocompleteOpen =
    (mentionActive && mentionMatches.length > 0) ||
    (slashActive && slashMatches.length > 0) ||
    (hashActive && hashMatches.length > 0)

  const applyAutocomplete = (prefix: "@" | "/" | "#", value: string, agentType?: string) => {
    const idx = inputValue.lastIndexOf(lastToken)
    const next = inputValue.slice(0, idx) + prefix + value + " "
    setInputValue(next)
    if (agentType) {
      setSelectedAgent(agentType as AgentType)
    }
    setTimeout(() => inputRef.current?.focus(), 20)
  }

  // Parse all messages → artifacts + per-message segments.
  const { segmentsByMsg, artifactsById } = useMemo(() => {
    const segmentsByMsg: Record<string, Segment[]> = {}
    const artifactsById: Record<string, Artifact> = {}
    for (const msg of messages) {
      if (msg.role !== "assistant") continue
      const { segments, artifacts } = parseMessage(msg.id, msg.content)
      segmentsByMsg[msg.id] = segments
      for (const a of artifacts) artifactsById[a.id] = a
    }
    for (const [id, a] of Object.entries(customArtifacts)) {
      artifactsById[id] = a
    }
    return { segmentsByMsg, artifactsById }
  }, [messages, customArtifacts])

  // Auto-open newest artifact
  useEffect(() => {
    const ids = Object.keys(artifactsById)
    if (ids.length && (!activeArtifact || !artifactsById[activeArtifact])) {
      setActiveArtifact(ids[ids.length - 1])
    }
  }, [artifactsById, activeArtifact])

  const artifactValue = (a: Artifact) => artifactEdits[a.id] ?? a.code
  const active = activeArtifact ? artifactsById[activeArtifact] : null
  const canvasOpen = Boolean(active)
  const allArtifacts = Object.values(artifactsById)

  const copyActive = async () => {
    if (!active) return
    try {
      await navigator.clipboard.writeText(artifactValue(active))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked */
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  // Conversation history state
  const [showHistory, setShowHistory] = useState(false)
  const [conversationsList, setConversationsList] = useState<ConversationRead[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [loadingConvId, setLoadingConvId] = useState<string | null>(null)

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const res = await listConversations(undefined, 1, 50)
      setConversationsList(res.items || [])
    } catch (err) {
      console.warn("Failed to load conversation history:", err)
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  useEffect(() => {
    if (!isOpen) {
      setError(null)
      setShowHistory(false)
    } else {
      void loadHistory()
    }
  }, [isOpen, loadHistory])

  const handleSelectConversation = async (id: string) => {
    setLoadingConvId(id)
    try {
      const data = await getConversation(id)
      const loaded: AGUIMessage[] = []
      for (const m of data.messages || []) {
        if (m.role === "user") {
          loaded.push({
            id: m.id || `${id}-${loaded.length}`,
            role: "user",
            content: m.content || "",
          })
        } else if (m.role === "assistant") {
          const rawToolCalls = (m.tool_calls as any[]) || []
          const rawToolResults = (m.tool_results as any[]) || []
          const mappedToolCalls: ToolCallEvent[] = rawToolCalls.map((tc: any, idx: number) => ({
            runId: id,
            toolCallId: tc.id || `tc-${idx}`,
            toolName: tc.name || "tool",
            arguments: tc.arguments || {},
            result: rawToolResults[idx] ?? tc.result,
            status: "result" as const,
          }))
          loaded.push({
            id: m.id || `${id}-${loaded.length}`,
            role: "assistant",
            content: m.content || "",
            toolCalls: mappedToolCalls,
          })
        }
      }
      setMessages(loaded)
      setConversationId(data.id)
      if (data.agent_type && AGENT_LIST.some((a) => a.type === data.agent_type)) {
        setSelectedAgent(data.agent_type as AgentType)
      }
      setShowHistory(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation")
    } finally {
      setLoadingConvId(null)
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setInputValue("")
    setConversationId(null)
    setError(null)
    setActiveArtifact(null)
    setShowHistory(false)
    setStreamState({ runId: "", status: "idle", content: "", toolCalls: [], memoryWrites: [] })
  }

  const handleDeleteConversation = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    try {
      await deleteConversation(id)
      setConversationsList((prev) => prev.filter((c) => c.id !== id))
      if (conversationId === id) {
        handleNewChat()
      }
    } catch (err) {
      console.warn("Failed to delete conversation:", err)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    // listAgents() uses authFetch (Supabase bearer); a raw fetch here 401s.
    listAgents()
      .then((data: AgentInfo[]) => setAgents(data))
      .catch(() => {})
  }, [isOpen])

  const activeAgent = AGENT_LIST.find((a) => a.type === selectedAgent) ?? AGENT_LIST[0]

  // ── Send message via AG-UI streaming ───────────────────────────────────

  const handleSendMessage = async (textOverride?: string) => {
    const rawText = textOverride !== undefined ? textOverride : inputValue
    if (!rawText.trim() || isSending) return
    setError(null)

    const messageText = rawText.trim()

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
    if (textOverride === undefined) {
      setInputValue("")
    }
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
                if (event.conversation_id) {
                  setConversationId(event.conversation_id)
                }
                const routedType = event.data?.agent_type as string | undefined
                const autoRouted = event.data?.auto_routed as boolean | undefined
                if (routedType && (autoRouted || selectedAgent === "auto")) {
                  const routedAgentObj = AGENT_LIST.find((a) => a.type === routedType)
                  const routedName = routedAgentObj ? routedAgentObj.name : routedType
                  setMessages((prevMsgs) =>
                    prevMsgs.map((m) =>
                      m.id === assistantId
                        ? { ...m, routedAgent: routedType, routedAgentName: routedName }
                        : m,
                    ),
                  )
                }
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
                if (event.conversation_id) {
                  setConversationId(event.conversation_id)
                }
                setMessages((prevMsgs) =>
                  prevMsgs.map((m) =>
                    m.id === assistantId
                      ? { ...m, isStreaming: false }
                      : m,
                  ),
                )
                void loadHistory()
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

  const handleReviseArtifact = async () => {
    if (!active || !artifactRevisionPrompt.trim() || isSending) return
    const instructions = artifactRevisionPrompt.trim()
    setArtifactRevisionPrompt("")
    const currentCode = artifactValue(active)
    const prompt = `Please revise the artifact "${active.title}" based on these instructions:\n"${instructions}"\n\nCurrent artifact content:\n\`\`\`${active.lang}\n${currentCode}\n\`\`\``
    await handleSendMessage(prompt)
  }

  // ── Render ─────────────────────────────────────────────────────────────

  if (!isOpen) return null

  return (
    <div
      className={cn(
        "fixed inset-y-0 right-0 z-50 flex flex-row border-l border-border bg-card shadow-2xl transition-all duration-300",
        panelSize === "expanded"
          ? "w-full max-w-[100vw] sm:w-[94vw] lg:w-[90vw] xl:w-[85vw]"
          : canvasOpen
          ? "w-full sm:w-[720px] md:w-[880px] lg:w-[1040px] xl:w-[1140px] max-w-[96vw]"
          : "w-full sm:w-[480px] md:w-[520px] max-w-xl",
      )}
    >
      {/* Left Chat Column */}
      <div className={cn("flex min-w-0 flex-1 flex-col overflow-hidden", canvasOpen && "w-1/2 border-r border-border")}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-secondary/80 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-primary/10 p-1.5 text-primary">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <h3 className="text-sm font-semibold text-foreground">AG-UI Agent Chat</h3>
                <Badge variant="outline" className="text-[10px] px-1 py-0 bg-background/50 font-mono">
                  {activeAgent.name}
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">AG-UI typed streaming • Tool execution & memory</p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <Button
              variant={showHistory ? "secondary" : "ghost"}
              size="sm"
              className={cn(
                "h-7 text-xs gap-1 px-2 text-muted-foreground hover:text-foreground",
                showHistory && "bg-secondary text-foreground",
              )}
              onClick={() => {
                setShowHistory((prev) => !prev)
                if (!showHistory) void loadHistory()
              }}
              title="View Chat History"
            >
              <History className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">History</span>
            </Button>

            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1 px-2 text-muted-foreground hover:text-foreground"
              onClick={handleNewChat}
              title="Start New Chat"
            >
              <Plus className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">New</span>
            </Button>

            {allArtifacts.length > 0 && !canvasOpen && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1 border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/10"
                onClick={() => setActiveArtifact(allArtifacts[allArtifacts.length - 1].id)}
                title="Open Artifact Canvas"
              >
                <FileCode2 className="h-3.5 w-3.5" />
                <span>Canvas ({allArtifacts.length})</span>
              </Button>
            )}

            <Button
              variant="ghost"
              size="icon"
              onClick={() => setPanelSize((prev) => (prev === "expanded" ? "compact" : "expanded"))}
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              title={panelSize === "expanded" ? "Restore Size" : "Expand to Full Screen"}
            >
              {panelSize === "expanded" ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>

            <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8 text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Stream state indicator */}
        {streamState.status !== "idle" && (
          <div className="border-b border-border/60 bg-muted/20 px-4 py-1.5 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "h-2 w-2 rounded-full",
                  streamState.status === "running" && "bg-amber-400 animate-pulse",
                  streamState.status === "finished" && "bg-emerald-400",
                  streamState.status === "error" && "bg-red-400",
                )}
              />
              <span className="text-muted-foreground capitalize text-[11px] font-medium">{streamState.status}</span>
              {streamState.runId && (
                <span className="text-[10px] text-muted-foreground font-mono">
                  run: {streamState.runId.slice(0, 8)}...
                </span>
              )}
            </div>
            <span className="text-[10px] text-muted-foreground font-mono">AG-UI v1.2</span>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="flex items-center gap-2 border-b border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
              <X className="h-3 w-3" />
            </button>
          </div>
        )}

        {/* History Panel or Active Chat */}
        {showHistory ? (
          <div className="flex-1 overflow-y-auto p-3 flex flex-col space-y-3 bg-card">
            <div className="flex items-center justify-between border-b border-border pb-2 px-1">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold text-foreground">Past Conversations</span>
                <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0">
                  {conversationsList.length}
                </Badge>
              </div>
              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleNewChat}
                  className="h-6 text-[11px] gap-1 px-2 border-primary/40 text-primary hover:bg-primary/10"
                >
                  <Plus className="h-3 w-3" />
                  <span>New Chat</span>
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowHistory(false)}
                  className="h-6 w-6 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            {loadingHistory ? (
              <div className="flex flex-col items-center justify-center py-16 gap-2 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
                <span className="text-xs">Loading conversations...</span>
              </div>
            ) : conversationsList.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground gap-2">
                <MessageSquare className="h-8 w-8 text-muted-foreground/40" />
                <p className="text-xs font-medium text-foreground">No saved conversations yet</p>
                <p className="text-[11px] text-muted-foreground max-w-[220px]">
                  Messages you send to autonomous agents will be saved and listed here.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleNewChat}
                  className="mt-2 h-7 text-xs gap-1.5 border-primary/40 text-primary"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Start a conversation
                </Button>
              </div>
            ) : (
              <div className="space-y-2 overflow-y-auto">
                {conversationsList.map((conv) => {
                  const agentObj = AGENT_LIST.find((a) => a.type === conv.agent_type) ?? AGENT_LIST[0]
                  const isCurrent = conv.id === conversationId
                  const isLoadingThis = loadingConvId === conv.id
                  const dateStr = conv.updated_at
                    ? new Date(conv.updated_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : ""

                  return (
                    <div
                      key={conv.id}
                      onClick={() => !isLoadingThis && handleSelectConversation(conv.id)}
                      className={cn(
                        "group relative flex flex-col gap-1.5 rounded-lg border p-3 text-left transition-all cursor-pointer",
                        isCurrent
                          ? "border-primary bg-primary/10 shadow-xs"
                          : "border-border/70 bg-secondary/30 hover:bg-secondary hover:border-border",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="text-sm shrink-0">{agentObj.icon}</span>
                          <span className="text-xs font-semibold text-foreground truncate">
                            {agentObj.name}
                          </span>
                          {isCurrent && (
                            <Badge variant="outline" className="text-[9px] px-1 py-0 border-primary/40 text-primary font-mono shrink-0">
                              Active
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {dateStr}
                          </span>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={(e) => handleDeleteConversation(e, conv.id)}
                            className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                            title="Delete conversation"
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>

                      <p className="line-clamp-2 text-xs text-muted-foreground group-hover:text-foreground transition-colors leading-relaxed">
                        {conv.title || conv.last_message || `Conversation ${conv.id.slice(0, 8)}...`}
                      </p>

                      {isLoadingThis && (
                        <div className="absolute inset-0 bg-background/80 backdrop-blur-xs flex items-center justify-center rounded-lg">
                          <Loader2 className="h-4 w-4 animate-spin text-primary" />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Messages List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground">
              <div className="rounded-2xl bg-secondary/80 p-4 shadow-inner">
                <span className="text-3xl">{activeAgent.icon}</span>
              </div>
              <div className="max-w-xs space-y-1">
                <p className="text-sm font-semibold text-foreground">Chat with {activeAgent.name}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{activeAgent.description}</p>
                <p className="text-[11px] text-muted-foreground/80 pt-2 font-mono">
                  Type @ for agents & team, / for components, # for channels. Artifacts open directly in canvas!
                </p>
              </div>
            </div>
          )}

          {messages.map((message) => {
            const segments = segmentsByMsg[message.id] ?? [{ type: "text" as const, value: message.content }]
            return (
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
                    {message.content === "" && message.isStreaming && (
                      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                        Generating response...
                      </span>
                    )}

                    {message.role === "assistant" ? (
                      <div className="space-y-2">
                        {message.routedAgent && (
                          <div className="flex items-center gap-1.5 mb-1.5 text-[11px] text-cyan-400 font-medium bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-0.5 rounded-full w-fit">
                            <Sparkles className="h-3 w-3 text-cyan-400 shrink-0" />
                            <span>Orchestrated to <strong>{message.routedAgentName || message.routedAgent}</strong></span>
                          </div>
                        )}
                        {segments.map((seg, i) => {
                          if (seg.type === "text") {
                            return seg.value.trim() ? (
                              <FormattedMarkdown key={i} content={seg.value.trim()} />
                            ) : null
                          }
                          const art = artifactsById[seg.value]
                          if (!art) return null
                          return (
                            <button
                              key={i}
                              type="button"
                              onClick={() => {
                                setActiveArtifact(art.id)
                                setArtifactViewMode("preview")
                              }}
                              className={cn(
                                "flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors my-1.5",
                                activeArtifact === art.id
                                  ? "border-primary bg-primary/15 text-foreground"
                                  : "border-border bg-card/80 hover:bg-secondary text-foreground",
                              )}
                            >
                              <FileCode2 className="h-4 w-4 text-cyan-400 shrink-0" />
                              <span className="flex-1 truncate text-xs font-semibold">{art.title}</span>
                              <Badge variant="outline" className="text-[10px] uppercase font-mono px-1 py-0">
                                {art.lang}
                              </Badge>
                            </button>
                          )
                        })}
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    )}

                    {message.isStreaming && message.content !== "" && (
                      <span className="mt-1 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Streaming...
                      </span>
                    )}
                  </div>

                  {message.role === "assistant" && !message.isStreaming && message.content && (
                    <div className="flex items-center gap-0.5 shrink-0 self-end">
                      {/* Copy message button */}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-foreground"
                        onClick={() => handleCopyMessage(message)}
                        title="Copy message"
                      >
                        {copiedMessageId === message.id ? (
                          <Check className="h-3.5 w-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </Button>

                      {/* Open in Canvas button */}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-cyan-400"
                        onClick={() => {
                          const customId = `art-${message.id}`
                          const isHtml = message.content.trim().startsWith("<")
                          setCustomArtifacts((prev) => ({
                            ...prev,
                            [customId]: {
                              id: customId,
                              msgId: message.id,
                              title: `Response Artifact (${message.id.slice(0, 6)})`,
                              lang: isHtml ? "html" : "markdown",
                              code: message.content,
                            },
                          }))
                          setActiveArtifact(customId)
                        }}
                        title="Open in Canvas"
                      >
                        <FileCode2 className="h-3.5 w-3.5" />
                      </Button>

                      {/* Thumbs Up button */}
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                          "h-6 w-6 text-muted-foreground hover:text-foreground",
                          feedbackMap[message.id] === "thumbs_up" && "text-emerald-400 hover:text-emerald-300"
                        )}
                        onClick={() => handleFeedback(message, "thumbs_up")}
                        title="Helpful response"
                      >
                        <ThumbsUp className={cn("h-3.5 w-3.5", feedbackMap[message.id] === "thumbs_up" && "fill-current")} />
                      </Button>

                      {/* Thumbs Down button */}
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                          "h-6 w-6 text-muted-foreground hover:text-foreground",
                          feedbackMap[message.id] === "thumbs_down" && "text-rose-400 hover:text-rose-300"
                        )}
                        onClick={() => handleFeedback(message, "thumbs_down")}
                        title="Not helpful"
                      >
                        <ThumbsDown className={cn("h-3.5 w-3.5", feedbackMap[message.id] === "thumbs_down" && "fill-current")} />
                      </Button>

                      {/* Speak button */}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-muted-foreground hover:text-foreground"
                        onClick={() => handleSpeakMessage(message)}
                        disabled={speakingMessageId === message.id}
                        title="Speak message"
                      >
                        {speakingMessageId === message.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Volume2 className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  )}
                </div>

                {/* Visual Action Chips */}
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {message.toolCalls.map((tc, idx) => {
                      const chip = formatActionChip(tc.toolName, tc.arguments as Record<string, unknown>)
                      const isRunning = tc.status === "start"
                      const isDone = tc.status === "end" || tc.status === "result"
                      return (
                        <div
                          key={idx}
                          className={cn(
                            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150 shadow-sm",
                            isRunning
                              ? "bg-amber-500/10 border-amber-500/30 text-amber-400 animate-pulse"
                              : isDone
                              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                              : "bg-muted/50 border-border/60 text-foreground"
                          )}
                          title={`${tc.toolName}: ${JSON.stringify(tc.arguments || {})}`}
                        >
                          <span className="text-xs select-none">{chip.icon}</span>
                          <span className="font-semibold text-foreground/90">{chip.label}</span>
                          {chip.detail && (
                            <span className="text-[11px] opacity-75 max-w-[220px] truncate hidden sm:inline">
                              · {chip.detail}
                            </span>
                          )}
                          {isRunning ? (
                            <Loader2 className="h-3 w-3 animate-spin text-amber-400 ml-0.5" />
                          ) : (
                            <CheckCircle2 className="h-3 w-3 text-emerald-400 ml-0.5" />
                          )}
                        </div>
                      )
                    })}
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
            )
          })}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area with Autocomplete */}
        <div className="border-t border-border bg-card/70 p-3">
          {voiceError && (
            <div className="mb-2 flex items-center justify-between rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
              <span>{voiceError}</span>
              <button type="button" onClick={() => setVoiceError(null)} className="ml-2 shrink-0 hover:text-red-300">×</button>
            </div>
          )}

          <div className="relative rounded-2xl border border-border/80 bg-secondary/30 p-2 shadow-sm transition-all focus-within:border-primary/50 focus-within:bg-secondary/50">
            {/* Autocomplete Menu */}
            {autocompleteOpen && (
              <div className="absolute bottom-full left-0 z-30 mb-2 w-72 overflow-hidden rounded-xl border border-border bg-popover shadow-xl">
                {mentionActive ? (
                  <div className="max-h-56 overflow-y-auto">
                    <div className="px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground bg-muted/30">
                      Team & Autonomous Agents
                    </div>
                    {mentionMatches.map((u: any) => (
                      <button
                        key={u.id}
                        type="button"
                        onClick={() => applyAutocomplete("@", u.name.replace(/\s+/g, ""), u.agent_type)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-secondary"
                      >
                        <Avatar className="h-6 w-6">
                          <AvatarFallback className={cn("text-[10px]", u.isAgent ? "bg-cyan-500/20 text-cyan-400 font-bold" : "bg-primary/20 text-primary")}>
                            {u.icon || formatInitials(u.name)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate font-medium">{u.name}</span>
                            {u.isAgent && (
                              <Badge variant="secondary" className="h-4 text-[9px] px-1 bg-cyan-500/20 text-cyan-400">
                                Agent
                              </Badge>
                            )}
                          </div>
                          {u.role && <p className="text-[10px] text-muted-foreground truncate">{u.role}</p>}
                        </div>
                      </button>
                    ))}
                  </div>
                ) : hashActive ? (
                  <div className="max-h-56 overflow-y-auto">
                    <div className="px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground bg-muted/30">
                      Channels
                    </div>
                    {hashMatches.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => applyAutocomplete("#", c.name)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-secondary"
                      >
                        <Hash className="h-4 w-4 text-muted-foreground" />
                        <span className="truncate font-medium">{c.name}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="max-h-56 overflow-y-auto">
                    <div className="px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground bg-muted/30">
                      Platform Modules
                    </div>
                    {slashMatches.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => applyAutocomplete("/", c)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm capitalize hover:bg-secondary"
                      >
                        <Hash className="h-4 w-4 text-muted-foreground" />
                        <span>{c}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Multiline Input Textarea */}
            <div className="px-1 py-1">
              <textarea
                ref={inputRef}
                rows={2}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    if (autocompleteOpen) {
                      if (mentionActive && mentionMatches[0]) {
                        applyAutocomplete("@", mentionMatches[0].name.replace(/\s+/g, ""), (mentionMatches[0] as any).agent_type)
                      } else if (hashActive && hashMatches[0]) {
                        applyAutocomplete("#", hashMatches[0].name)
                      } else if (slashActive && slashMatches[0]) {
                        applyAutocomplete("/", slashMatches[0])
                      }
                    } else {
                      void handleSendMessage()
                    }
                  }
                }}
                placeholder={`Ask ${activeAgent.name}… Type / for modules, @ for agents, # for channels`}
                className="w-full resize-none border-0 bg-transparent p-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                disabled={isSending}
              />
            </div>

            {/* Bottom Action Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-2 px-1">
              <div className="flex items-center gap-1.5">
                {/* Agent Dropdown Pill */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-md border border-border/70 bg-secondary/80 px-2.5 py-1 text-xs font-semibold text-foreground hover:bg-secondary hover:border-primary/40 transition-all shadow-sm"
                      title="Switch active agent (DomeBot, InsightDome, etc.)"
                    >
                      <span className="text-sm leading-none">{activeAgent.icon}</span>
                      <span className="text-primary font-bold">{activeAgent.name}</span>
                      <ChevronDown className="h-3 w-3 text-muted-foreground ml-0.5" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-64 p-1.5 z-50">
                    <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                      Switch Active Agent
                    </div>
                    {AGENT_LIST.map((agent) => (
                      <DropdownMenuItem
                        key={agent.type}
                        onClick={() => {
                          setSelectedAgent(agent.type)
                          setConversationId(null)
                        }}
                        className={cn(
                          "flex items-start gap-2.5 px-2 py-1.5 cursor-pointer rounded-md text-xs",
                          selectedAgent === agent.type ? "bg-primary/15 text-primary font-medium" : "text-foreground hover:bg-secondary",
                        )}
                      >
                        <span className="text-base leading-none mt-0.5">{agent.icon}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold">{agent.name}</span>
                            <span className="text-[10px] text-muted-foreground font-mono capitalize">{agent.type}</span>
                          </div>
                          <p className="text-[10px] text-muted-foreground truncate mt-0.5">{agent.description}</p>
                        </div>
                        {selectedAgent === agent.type && <Check className="h-3.5 w-3.5 text-primary shrink-0 ml-1 mt-0.5" />}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                {/* Voice Input Button */}
                <Button
                  variant={isRecording ? "destructive" : "ghost"}
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground"
                  onClick={isRecording ? stopVoiceRecording : startVoiceRecording}
                  disabled={isTranscribing}
                  title={isRecording ? "Stop recording" : "Voice input via Voicebox"}
                >
                  {isTranscribing ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : isRecording ? (
                    <MicOff className="h-3.5 w-3.5 animate-pulse" />
                  ) : (
                    <Mic className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>

              <div className="flex items-center gap-1.5">
                <Button
                  size="icon"
                  className="h-8 w-8 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground"
                  onClick={() => void handleSendMessage()}
                  disabled={isSending || !inputValue.trim()}
                  title="Send message"
                >
                  {isSending ? <Square className="h-3.5 w-3.5" /> : <Send className="h-3.5 w-3.5" />}
                </Button>
              </div>
            </div>
          </div>
        </div>
          </>
        )}
      </div>

      {/* Right Artifact Canvas Sidebar */}
      {canvasOpen && active && (
        <div className="flex w-1/2 min-w-0 flex-col bg-background">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5 bg-secondary/30">
            <FileCode2 className="h-4 w-4 text-cyan-400" />
            <span className="text-sm font-semibold text-foreground truncate">{active.title}</span>
            <Badge variant="outline" className="text-[10px] uppercase font-mono px-1.5 py-0 bg-background/50">
              {active.lang}
            </Badge>

            {/* View Mode Toggle: Preview vs Code */}
            <div className="flex items-center gap-1 border border-border/80 rounded-md p-0.5 bg-background/50 ml-2">
              <Button
                size="sm"
                variant={artifactViewMode === "preview" ? "secondary" : "ghost"}
                className={cn("h-6 px-2 text-[11px] gap-1", artifactViewMode === "preview" ? "text-cyan-400 font-semibold" : "text-muted-foreground")}
                onClick={() => setArtifactViewMode("preview")}
                title="Visual formatted preview"
              >
                <Eye className="h-3 w-3" />
                <span>Preview</span>
              </Button>
              <Button
                size="sm"
                variant={artifactViewMode === "code" ? "secondary" : "ghost"}
                className={cn("h-6 px-2 text-[11px] gap-1", artifactViewMode === "code" ? "text-cyan-400 font-semibold" : "text-muted-foreground")}
                onClick={() => setArtifactViewMode("code")}
                title="Edit raw code or markdown"
              >
                <Code className="h-3 w-3" />
                <span>Code</span>
              </Button>
            </div>

            <div className="ml-auto flex items-center gap-1">
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={copyActive} title="Copy code">
                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                onClick={() => setActiveArtifact(null)}
                title="Close canvas"
              >
                <PanelRightClose className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Multiple artifacts tab bar */}
          {allArtifacts.length > 1 && (
            <div className="flex flex-wrap gap-1 border-b border-border px-3 py-1.5 bg-muted/20">
              {allArtifacts.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setActiveArtifact(a.id)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors",
                    activeArtifact === a.id
                      ? "bg-primary text-primary-foreground font-medium"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground",
                  )}
                >
                  <FileCode2 className="h-3 w-3" />
                  <span className="truncate max-w-[120px]">{a.title}</span>
                </button>
              ))}
            </div>
          )}

          {/* Canvas content: Preview or Code */}
          <div className="relative flex-1 min-h-0 p-3 overflow-hidden">
            {artifactViewMode === "preview" ? (
              active.lang === "html" || active.code.includes("<!DOCTYPE") || active.code.includes("<html") ? (
                <iframe
                  title={active.title}
                  srcDoc={artifactValue(active)}
                  sandbox="allow-scripts"
                  className="h-full w-full rounded-lg border border-border bg-white"
                />
              ) : (
                <div className="h-full w-full overflow-y-auto rounded-lg border border-border bg-card/60 p-4 text-xs leading-relaxed text-foreground custom-scrollbar">
                  <FormattedMarkdown content={artifactValue(active)} />
                </div>
              )
            ) : (
              <textarea
                value={artifactValue(active)}
                onChange={(e) => setArtifactEdits((prev) => ({ ...prev, [active.id]: e.target.value }))}
                className="h-full w-full resize-none rounded-lg border border-border bg-card p-3 font-mono text-xs text-foreground focus:border-primary/50 focus:outline-none custom-scrollbar"
                placeholder="Artifact content..."
                spellCheck={false}
              />
            )}
          </div>

          {/* Interactive Direct & Revise Action Bar */}
          <div className="border-t border-border p-3 bg-secondary/30 flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
              <span className="flex items-center gap-1.5 text-cyan-400">
                <Sparkles className="h-3.5 w-3.5" />
                Direct & Revise Artifact
              </span>
              <span className="text-[10px] text-muted-foreground/70">
                AI Orchestrator updates this artifact
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={artifactRevisionPrompt}
                onChange={(e) => setArtifactRevisionPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    handleReviseArtifact()
                  }
                }}
                placeholder="e.g. Add a pricing tier comparison, or make the email friendlier..."
                className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-cyan-500/60"
                disabled={isSending}
              />
              <Button
                size="sm"
                onClick={handleReviseArtifact}
                disabled={!artifactRevisionPrompt.trim() || isSending}
                className="h-7 text-xs gap-1.5 bg-cyan-600 hover:bg-cyan-500 text-white shrink-0"
              >
                {isSending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Sparkles className="h-3 w-3" />
                )}
                Revise
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
