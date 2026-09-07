"use client"

/**
 * AgentArtifactChat — a Claude-Code-style agent chat with an editable artifact
 * canvas. The chat (left) streams agent replies via the authenticated AG-UI
 * path; whenever a reply contains a fenced code/doc block, it is lifted out into
 * an editable canvas (right) instead of cluttering the transcript. The canvas is
 * a working surface — edit freely and copy out.
 *
 * Channel messages (and any extraContext, e.g. upcoming schedule) are fed in so
 * the agent is aware of what the team is doing.
 */
import { useState, useRef, useEffect, useCallback, useMemo } from "react"
import {
  Bot,
  Send,
  Loader2,
  FileCode2,
  Copy,
  Check,
  PanelRightClose,
  X,
  Hash,
  Lock,
  Sparkles,
  Plus,
  Mic,
  MicOff,
  ChevronDown,
  ShieldCheck,
} from "lucide-react"
import { invokeAgentAGUI, type AGUIEvent, AGENT_CATALOG } from "@/lib/orchestrator-api"
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

const DEFAULT_TEAM_USERS = [
  { id: "u-1", name: "Sarah Chen", email: "sarah.chen@omnidome.co.za" },
  { id: "u-2", name: "Mike Johnson", email: "mike.johnson@omnidome.co.za" },
  { id: "u-3", name: "Emily Davis", email: "emily.davis@omnidome.co.za" },
  { id: "u-4", name: "James Wilson", email: "james.wilson@omnidome.co.za" },
  { id: "u-5", name: "Lisa Park", email: "lisa.park@omnidome.co.za" },
]

const AVAILABLE_AGENTS = [
  { id: "customer_facing", name: "DomeBot", icon: "🤖", role: "Customer & Ops", description: "Handles balances, invoices, coverage checks, ticket creation" },
  { id: "executive", name: "InsightDome", icon: "📊", role: "Executive & Finance", description: "MRR, churn, ARPU, executive summaries & pipeline metrics" },
  { id: "retention", name: "ChurnGuard", icon: "🛡️", role: "Retention & Churn", description: "Predicts customer churn risk and retention playbooks" },
  { id: "provisioning", name: "ProvisionBot", icon: "⚡", role: "Provisioning", description: "Onboarding automation, accounts & service provisioning" },
  { id: "support", name: "SupportBot", icon: "🔧", role: "Support Diagnostics", description: "Customer 360° diagnostics and ticket troubleshooting" },
  { id: "assistant", name: "OmniAssist", icon: "✨", role: "Claude Assistant", description: "Versatile assistant: code, documentation, plans into canvas" },
]

const AGENT_ITEMS = [
  ...AVAILABLE_AGENTS.map((a) => ({
    id: `agent-${a.id}`,
    name: a.name,
    role: a.description,
    agent_type: a.id,
    isAgent: true,
    icon: a.icon,
  })),
  {
    id: "agent-insightbot-alias",
    name: "InsightBot",
    role: "Executive briefings & MRR",
    agent_type: "executive",
    isAgent: true,
    icon: "📊",
  },
]

const PLATFORM_COMPONENTS = [
  "sales", "marketing", "crm", "finance", "network", "support",
  "retention", "inventory", "billing", "analytics", "provisioning",
  "compliance", "portal", "call-center", "hr",
]

const CLAUDE_MODELS = [
  { id: "opus-4.8", name: "Opus 4.8", badge: "Most Capable" },
  { id: "claude-3-5-sonnet", name: "Claude 3.5 Sonnet", badge: "Recommended" },
  { id: "qwen-2.5", name: "Qwen 2.5 Coder", badge: "Fast" },
]

function formatInitials(name?: string) {
  if (!name) return "??"
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

interface Artifact {
  id: string
  title: string
  lang: string
  code: string
}

interface Segment {
  type: "text" | "artifact"
  value: string // text content, or artifact id
}

interface Msg {
  id: string
  role: "user" | "assistant"
  content: string
  streaming?: boolean
}

const FENCE = /```(\w+)?\n?([\s\S]*?)```/g

/** Split a message into prose segments + artifact refs, collecting artifacts. */
function parseMessage(msgId: string, content: string): { segments: Segment[]; artifacts: Artifact[] } {
  const segments: Segment[] = []
  const artifacts: Artifact[] = []
  let last = 0
  let idx = 0
  let m: RegExpExecArray | null
  FENCE.lastIndex = 0
  while ((m = FENCE.exec(content)) !== null) {
    if (m.index > last) segments.push({ type: "text", value: content.slice(last, m.index) })
    const lang = (m[1] || "text").toLowerCase()
    const code = m[2] ?? ""
    const id = `${msgId}-art-${idx}`
    artifacts.push({ id, title: `Artifact ${idx + 1}`, lang, code })
    segments.push({ type: "artifact", value: id })
    last = m.index + m[0].length
    idx += 1
  }
  if (last < content.length) segments.push({ type: "text", value: content.slice(last) })
  if (segments.length === 0) segments.push({ type: "text", value: content })
  return { segments, artifacts }
}

export function AgentArtifactChat({
  channelId,
  channelName,
  extraContext,
  teamUsers = DEFAULT_TEAM_USERS,
}: {
  channelId?: string
  channelName?: string
  extraContext?: string
  teamUsers?: { id: string; name: string; email?: string }[]
}) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState(CLAUDE_MODELS[0].id)
  const [selectedAgent, setSelectedAgent] = useState("customer_facing")
  const [bypassPermissions, setBypassPermissions] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [history, setHistory] = useState<{ role: string; content: string }[]>([])
  // Editable artifact store, keyed by artifact id (canvas edits live here).
  const [artifactEdits, setArtifactEdits] = useState<Record<string, string>>({})
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const currentAgent = AVAILABLE_AGENTS.find((a) => a.id === selectedAgent) ?? AVAILABLE_AGENTS[0]

  // ── @mention (team + agents) / /component / #channel autocomplete ──
  const lastToken = input.split(/\s/).pop() ?? ""
  const mentionActive = lastToken.startsWith("@") && lastToken.length >= 1
  const slashActive = lastToken.startsWith("/") && lastToken.length >= 1
  const hashActive = lastToken.startsWith("#") && lastToken.length >= 1

  const mentionQuery = lastToken.slice(1).toLowerCase()
  const mentionMatches = mentionActive
    ? [
        ...AGENT_ITEMS.filter((a) => a.name.toLowerCase().includes(mentionQuery)),
        ...teamUsers.filter((u) => u.name.toLowerCase().includes(mentionQuery)),
      ].slice(0, 8)
    : []

  const slashMatches = slashActive
    ? PLATFORM_COMPONENTS.filter((c) => c.startsWith(lastToken.slice(1).toLowerCase())).slice(0, 8)
    : []

  const hashMatches = hashActive
    ? [
        { id: "c-general", name: "general" },
        { id: "c-sales", name: "sales-team" },
        { id: "c-support", name: "support-tickets" },
        { id: "c-network", name: "network-alerts" },
        { id: "c-marketing", name: "marketing" },
      ].filter((c) => c.name.toLowerCase().includes(lastToken.slice(1).toLowerCase()))
    : []

  const autocompleteOpen =
    (mentionActive && mentionMatches.length > 0) ||
    (slashActive && slashMatches.length > 0) ||
    (hashActive && hashMatches.length > 0)

  const applyAutocomplete = (prefix: "@" | "/" | "#", value: string, agentType?: string) => {
    const idx = input.lastIndexOf(lastToken)
    const next = input.slice(0, idx) + prefix + value + " "
    setInput(next)
    if (agentType) {
      setSelectedAgent(agentType)
    }
    setTimeout(() => inputRef.current?.focus(), 20)
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

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
    return { segmentsByMsg, artifactsById }
  }, [messages])

  // Auto-open the newest artifact as it streams in.
  useEffect(() => {
    const ids = Object.keys(artifactsById)
    if (ids.length && (!activeArtifact || !artifactsById[activeArtifact])) {
      setActiveArtifact(ids[ids.length - 1])
    }
  }, [artifactsById, activeArtifact])

  useEffect(() => {
    if (!channelId) {
      setHistory([])
      return
    }
    let cancelled = false
    fetch(`/api/chat/messages?channel_id=${channelId}`)
      .then((r) => r.json())
      .then((res) => {
        if (cancelled) return
        const msgs = Array.isArray(res?.data) ? res.data : []
        const transcript = msgs
          .slice(-20)
          .map((m: { author_name?: string; content?: string }) => `${m.author_name ?? "?"}: ${m.content || ""}`)
          .filter(Boolean)
          .join("\n")
        const ctx = [
          transcript && `Recent messages in the #${channelName ?? "team"} channel:\n${transcript}`,
          extraContext && extraContext.trim(),
        ]
          .filter(Boolean)
          .join("\n\n")
        setHistory(
          ctx
            ? [
                { role: "user", content: `For context:\n${ctx}` },
                { role: "assistant", content: "Understood — I have the channel and schedule context." },
              ]
            : [],
        )
      })
      .catch(() => {
        if (!cancelled) setHistory([])
      })
    return () => {
      cancelled = true
    }
  }, [channelId, channelName, extraContext])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return
    setError(null)
    setInput("")
    setSending(true)

    const aId = `${Date.now() + 1}`
    setMessages((p) => [
      ...p,
      { id: `${Date.now()}`, role: "user", content: text },
      { id: aId, role: "assistant", content: "", streaming: true },
    ])

    try {
      await invokeAgentAGUI(
        {
          agent_type: selectedAgent,
          message: text,
          context: { channel_id: channelId, channel_name: channelName, history },
          stream_tokens: true,
        },
        (e: AGUIEvent) => {
          if (e.type === "TEXT_MESSAGE_CONTENT") {
            const delta = (e.data?.delta as string) || ""
            if (delta) setMessages((p) => p.map((m) => (m.id === aId ? { ...m, content: m.content + delta } : m)))
          }
        },
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSending(false)
      setMessages((p) => p.map((m) => (m.id === aId ? { ...m, streaming: false } : m)))
    }
  }, [input, sending, channelId, channelName, history, selectedAgent])

  const artifactValue = (a: Artifact) => artifactEdits[a.id] ?? a.code
  const active = activeArtifact ? artifactsById[activeArtifact] : null
  const canvasOpen = Boolean(active)

  const copyActive = async () => {
    if (!active) return
    try {
      await navigator.clipboard.writeText(artifactValue(active))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked — ignore */
    }
  }

  const allArtifacts = Object.values(artifactsById)

  return (
    <div className="flex h-full w-full min-h-0 flex-1 overflow-hidden">
      {/* Chat column */}
      <div className={cn("flex min-w-0 min-h-0 flex-1 flex-col overflow-hidden", canvasOpen ? "w-1/2 flex-none border-r border-border" : "flex-1")}>
        {/* Claude Code Top Status Bar */}
        <div className="flex flex-wrap items-center justify-between border-b border-border bg-secondary/30 px-4 py-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground">omnidome</span>
            <Badge variant="outline" className="font-mono text-[10px] px-1.5 py-0 bg-background/50">
              railway-migration-phase1
            </Badge>
            <span className="font-mono text-[11px] text-emerald-400 font-semibold">+345</span>
            <span className="font-mono text-[11px] text-red-400 font-semibold">-12</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Sparkles className="h-2.5 w-2.5 mr-1" />
              {channelName ? `#${channelName}` : "AI Copilot"}
            </Badge>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" title="Agent Online" />
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
              <Bot className="h-10 w-10 text-cyan-400" />
              <div className="max-w-md">
                Ask an agent about <strong>{channelName ?? "this channel"}</strong>. Ask it to draft a document,
                email, SQL query, or code and it opens in an <strong>editable canvas</strong> beside the chat.
              </div>
            </div>
          )}
          {messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground whitespace-pre-wrap">
                    {m.content}
                  </div>
                </div>
              )
            }
            const segments = segmentsByMsg[m.id] ?? [{ type: "text" as const, value: m.content }]
            return (
              <div key={m.id} className="flex justify-start">
                <div className="max-w-[85%] space-y-2 rounded-lg bg-secondary px-3 py-2 text-sm text-foreground">
                  {m.content === "" && m.streaming && <Loader2 className="h-4 w-4 animate-spin" />}
                  {segments.map((seg, i) => {
                    if (seg.type === "text") {
                      return seg.value.trim() ? (
                        <p key={i} className="whitespace-pre-wrap">
                          {seg.value.trim()}
                        </p>
                      ) : null
                    }
                    const art = artifactsById[seg.value]
                    if (!art) return null
                    return (
                      <button
                        key={i}
                        onClick={() => setActiveArtifact(art.id)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition-colors",
                          activeArtifact === art.id
                            ? "border-primary bg-primary/10"
                            : "border-border bg-background hover:bg-secondary/60",
                        )}
                      >
                        <FileCode2 className="h-4 w-4 text-cyan-400" />
                        <span className="flex-1 truncate font-medium">{art.title}</span>
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                          {art.lang}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
          {error && <div className="text-xs text-red-400">Error: {error}</div>}
          <div ref={endRef} />
        </div>

        {/* Claude Code Style Chat Bar */}
        <div className="border-t border-border bg-card/60 p-3">
          <div className="relative rounded-2xl border border-border/80 bg-secondary/30 p-2 shadow-sm transition-all focus-within:border-primary/50 focus-within:bg-secondary/50">
            {autocompleteOpen && (
              <div className="absolute bottom-full left-0 z-20 mb-2 w-72 overflow-hidden rounded-xl border border-border bg-popover shadow-xl">
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

            {/* Multiline textarea style */}
            <div className="px-1 py-1">
              <textarea
                ref={inputRef as any}
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
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
                      void send()
                    }
                  }
                }}
                placeholder="Ask Claude / Agent anything… Type / for commands, @ for agents & team, # for channels"
                className="w-full resize-none border-0 bg-transparent p-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                disabled={sending}
              />
            </div>

            {/* Bottom Claude Action Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-2 px-1">
              <div className="flex items-center gap-1.5">
                {/* Agent Selector Dropdown (Replaces Bypass permissions) */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-md border border-border/80 bg-secondary/80 px-2.5 py-1 text-xs font-semibold text-foreground hover:bg-secondary hover:border-primary/40 transition-all shadow-sm"
                      title="Select active agent (DomeBot, InsightDome, etc.)"
                    >
                      <span className="text-sm leading-none">{currentAgent.icon}</span>
                      <span className="text-primary font-bold">{currentAgent.name}</span>
                      <ChevronDown className="h-3 w-3 text-muted-foreground ml-0.5" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-64 p-1.5 z-50">
                    <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                      Switch Active Agent
                    </div>
                    {AVAILABLE_AGENTS.map((agent) => (
                      <DropdownMenuItem
                        key={agent.id}
                        onClick={() => setSelectedAgent(agent.id)}
                        className={cn(
                          "flex items-start gap-2.5 px-2 py-1.5 cursor-pointer rounded-md text-xs",
                          selectedAgent === agent.id ? "bg-primary/15 text-primary font-medium" : "text-foreground hover:bg-secondary",
                        )}
                      >
                        <span className="text-base leading-none mt-0.5">{agent.icon}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold">{agent.name}</span>
                            <span className="text-[10px] text-muted-foreground font-mono">{agent.role}</span>
                          </div>
                          <p className="text-[10px] text-muted-foreground truncate mt-0.5">{agent.description}</p>
                        </div>
                        {selectedAgent === agent.id && <Check className="h-3.5 w-3.5 text-primary shrink-0 ml-1 mt-0.5" />}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground" title="Add file attachment">
                  <Plus className="h-4 w-4" />
                </Button>

                <Button
                  variant={isRecording ? "destructive" : "ghost"}
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground"
                  onClick={() => setIsRecording(!isRecording)}
                  title="Voice input"
                >
                  {isRecording ? <MicOff className="h-4 w-4 animate-pulse" /> : <Mic className="h-4 w-4" />}
                </Button>
              </div>

              <div className="flex items-center gap-2">
                {/* Model Selector Dropdown */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-md border border-border bg-secondary/60 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-secondary"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                      <span>{CLAUDE_MODELS.find((m) => m.id === selectedModel)?.name ?? "Opus 4.8"}</span>
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-52">
                    {CLAUDE_MODELS.map((m) => (
                      <DropdownMenuItem
                        key={m.id}
                        onClick={() => setSelectedModel(m.id)}
                        className="flex items-center justify-between text-xs cursor-pointer"
                      >
                        <span className="font-medium">{m.name}</span>
                        <Badge variant="outline" className="text-[10px] px-1 py-0">{m.badge}</Badge>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>

                <Badge variant="secondary" className="h-6 text-[10px] bg-emerald-500/15 text-emerald-400 font-mono">
                  ● Ready
                </Badge>

                <Button
                  size="icon"
                  className="h-8 w-8 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground"
                  onClick={() => void send()}
                  disabled={sending || !input.trim()}
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Artifact canvas */}
      {canvasOpen && active && (
        <div className="flex w-1/2 min-w-0 flex-col bg-background">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <FileCode2 className="h-4 w-4 text-cyan-400" />
            <span className="text-sm font-semibold">{active.title}</span>
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
              {active.lang}
            </span>
            <div className="ml-auto flex items-center gap-1">
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={copyActive} title="Copy">
                {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={() => setActiveArtifact(null)}
                title="Close canvas"
              >
                <PanelRightClose className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {allArtifacts.length > 1 && (
            <div className="flex flex-wrap gap-1 border-b border-border px-3 py-2">
              {allArtifacts.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setActiveArtifact(a.id)}
                  className={cn(
                    "flex items-center gap-1 rounded px-2 py-1 text-xs",
                    a.id === active.id ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
                  )}
                >
                  {a.title}
                  {artifactEdits[a.id] !== undefined && artifactEdits[a.id] !== a.code && (
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400" title="edited" />
                  )}
                </button>
              ))}
            </div>
          )}
          <textarea
            value={artifactValue(active)}
            onChange={(e) => setArtifactEdits((prev) => ({ ...prev, [active.id]: e.target.value }))}
            spellCheck={false}
            className="flex-1 resize-none bg-background p-3 font-mono text-xs text-foreground outline-none"
          />
          <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[11px] text-muted-foreground">
            <span>{artifactValue(active).split("\n").length} lines</span>
            <span>Editable canvas — copy out when ready</span>
          </div>
        </div>
      )}
    </div>
  )
}
