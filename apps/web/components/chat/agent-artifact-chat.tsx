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
import { Bot, Send, Loader2, FileCode2, Copy, Check, PanelRightClose, X, Hash } from "lucide-react"
import { invokeAgentAGUI, type AGUIEvent } from "@/lib/orchestrator-api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"

const DEFAULT_TEAM_USERS = [
  { id: "u-1", name: "Sarah Chen", email: "sarah.chen@omnidome.co.za" },
  { id: "u-2", name: "Mike Johnson", email: "mike.johnson@omnidome.co.za" },
  { id: "u-3", name: "Emily Davis", email: "emily.davis@omnidome.co.za" },
  { id: "u-4", name: "James Wilson", email: "james.wilson@omnidome.co.za" },
  { id: "u-5", name: "Lisa Park", email: "lisa.park@omnidome.co.za" },
]

const PLATFORM_COMPONENTS = [
  "sales", "marketing", "crm", "finance", "network", "support",
  "retention", "inventory", "billing", "analytics", "provisioning",
  "compliance", "portal", "call-center", "hr",
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
  const [history, setHistory] = useState<{ role: string; content: string }[]>([])
  // Editable artifact store, keyed by artifact id (canvas edits live here).
  const [artifactEdits, setArtifactEdits] = useState<Record<string, string>>({})
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // ── @mention / /component autocomplete ──
  const lastToken = input.split(/\s/).pop() ?? ""
  const mentionActive = lastToken.startsWith("@") && lastToken.length >= 1
  const slashActive = lastToken.startsWith("/") && lastToken.length >= 1
  const mentionMatches = mentionActive
    ? teamUsers.filter((u) => u.name.toLowerCase().includes(lastToken.slice(1).toLowerCase())).slice(0, 6)
    : []
  const slashMatches = slashActive
    ? PLATFORM_COMPONENTS.filter((c) => c.startsWith(lastToken.slice(1).toLowerCase())).slice(0, 8)
    : []
  const autocompleteOpen = (mentionActive && mentionMatches.length > 0) || (slashActive && slashMatches.length > 0)

  const applyAutocomplete = (prefix: "@" | "/", value: string) => {
    const idx = input.lastIndexOf(lastToken)
    const next = input.slice(0, idx) + prefix + value + " "
    setInput(next)
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
          agent_type: "assistant",
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
  }, [input, sending, channelId, channelName, history])

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
        <div className="border-t border-border p-3">
          <div className="relative flex items-center gap-2">
            {autocompleteOpen && (
              <div className="absolute bottom-full left-0 z-20 mb-2 w-64 overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
                {mentionActive
                  ? mentionMatches.map((u) => (
                      <button
                        key={u.id}
                        type="button"
                        onClick={() => applyAutocomplete("@", u.name.replace(/\s+/g, ""))}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-secondary"
                      >
                        <Avatar className="h-6 w-6">
                          <AvatarFallback className="bg-primary/20 text-primary text-[10px]">
                            {formatInitials(u.name)}
                          </AvatarFallback>
                        </Avatar>
                        <span className="truncate">{u.name}</span>
                      </button>
                    ))
                  : slashMatches.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => applyAutocomplete("/", c)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm capitalize hover:bg-secondary"
                      >
                        <Hash className="h-4 w-4 text-muted-foreground" />
                        {c}
                      </button>
                    ))}
              </div>
            )}
            <Input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  if (autocompleteOpen) {
                    if (mentionActive && mentionMatches[0]) {
                      applyAutocomplete("@", mentionMatches[0].name.replace(/\s+/g, ""))
                    } else if (slashActive && slashMatches[0]) {
                      applyAutocomplete("/", slashMatches[0])
                    }
                  } else {
                    void send()
                  }
                }
              }}
              placeholder="Ask the agent to draft something… (use @ for team, / for components)"
              disabled={sending}
            />
            <Button size="icon" onClick={() => void send()} disabled={sending || !input.trim()}>
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
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
