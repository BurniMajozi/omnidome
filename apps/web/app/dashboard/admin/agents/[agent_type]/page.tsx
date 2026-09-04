"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ArrowLeft, Bot, Cpu, Loader2, AlertCircle, MessageSquare, ListOrdered, Activity } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

// ─── Types (mirror backend contracts) ───────────────────────────────────────
// AgentInfo: services/agent_orchestrator/schemas.py (via GET /api/orchestrator/agents list)
// ActionItem: audit_actions rows via GET /api/orchestrator/agents/actions (NEWEST-FIRST, do NOT re-sort)
// ConversationItem: via GET /api/orchestrator/conversations (proxy → /api/conversations)

interface AgentInfo {
  agent_type: string
  description: string
  llm: string
  tools: string[]
}

interface ActionItem {
  id: string
  conversation_id: string
  agent_type: string
  tool_name: string
  tool_input: unknown
  tool_output: unknown
  success: boolean
  created_at: string
}

interface ConversationItem {
  id: string
  agent_type: string
  channel: string
  status: string
  context: unknown
  created_at: string
  updated_at: string
}

// ─── Display-name map (copied from sibling agents/page.tsx) ─────────────────

const DISPLAY_NAMES: Record<string, string> = {
  customer_facing: "DomeBot",
  retention: "ChurnGuard",
  provisioning: "ProvisionBot",
  executive: "InsightBot",
  support: "SupportBot",
}

function displayName(agentType: string): string {
  return DISPLAY_NAMES[agentType] ?? agentType
}

// ─── Loading / error states (copied from sibling agents/page.tsx) ───────────

function TabLoader() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <span className="ml-2 text-sm text-muted-foreground">Loading…</span>
    </div>
  )
}

function TabError({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20">
      <AlertCircle className="h-8 w-8 text-destructive" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function previewJson(value: unknown, maxLen = 160): string {
  let s: string
  try {
    s = typeof value === "string" ? value : (JSON.stringify(value) ?? "null")
  } catch {
    s = String(value)
  }
  if (!s) return "null"
  if (s.length > maxLen) return `${s.slice(0, maxLen)}…`
  return s
}

function getConversationStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  const s = (status ?? "").toLowerCase()
  if (s === "active" || s === "open") return "default"
  if (s === "closed" || s === "resolved" || s === "completed") return "secondary"
  if (s === "failed" || s === "error") return "destructive"
  return "outline"
}

// ─── Action Trail tab ───────────────────────────────────────────────────────

function ActionTrailTab({ agentType }: { agentType: string }) {
  const [items, setItems] = useState<ActionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(
          `/api/orchestrator/agents/actions?agent_type=${encodeURIComponent(agentType)}&limit=200`,
          { cache: "no-store" }
        )
        if (!res.ok) throw new Error(`Failed to load action trail: ${res.status}`)
        const json: unknown = await res.json()
        const arr = (json as { items?: unknown }).items
        if (!Array.isArray(arr)) throw new Error("Unexpected actions response shape")
        if (!cancelled) setItems(arr as ActionItem[])
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load action trail")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [agentType])

  if (loading) return <TabLoader />
  if (error) return <TabError message={error} />

  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        {items.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">No actions recorded for this agent.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Tool / Action</TableHead>
                <TableHead>Success</TableHead>
                <TableHead>Conversation</TableHead>
                <TableHead>Payload</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {formatTime(item.created_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.success ? "outline" : "destructive"} className="font-mono text-[11px]">
                      {item.tool_name}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.success ? "default" : "destructive"}>
                      {item.success ? "ok" : "failed"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <span className="block max-w-[140px] truncate font-mono text-xs text-muted-foreground">
                      {item.conversation_id}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <details>
                      <summary className="cursor-pointer font-mono text-xs text-muted-foreground hover:text-foreground">
                        {previewJson(item.tool_input)}
                      </summary>
                      <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-secondary/50 p-3 text-[11px]">
                        {previewJson(item.tool_input, 2000)}
                        {"\n--- output ---\n"}
                        {previewJson(item.tool_output, 2000)}
                      </pre>
                    </details>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Conversations tab ──────────────────────────────────────────────────────

function ConversationsTab({ agentType }: { agentType: string }) {
  const [items, setItems] = useState<ConversationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch(
          `/api/orchestrator/conversations?agent_type=${encodeURIComponent(agentType)}&page=1&page_size=20`,
          { cache: "no-store" }
        )
        if (!res.ok) throw new Error(`Failed to load conversations: ${res.status}`)
        const json: unknown = await res.json()
        const arr = (json as { items?: unknown }).items
        if (!Array.isArray(arr)) throw new Error("Unexpected conversations response shape")
        if (!cancelled) setItems(arr as ConversationItem[])
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load conversations")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [agentType])

  if (loading) return <TabLoader />
  if (error) return <TabError message={error} />

  return (
    <Card className="border-border bg-card">
      <CardContent className="pt-6">
        {items.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">No conversations for this agent yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {(items ?? []).map((conv) => (
              <li key={conv.id} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="block max-w-[280px] truncate font-mono text-xs text-foreground">{conv.id}</span>
                <div className="flex items-center gap-2">
                  <Badge variant={getConversationStatusVariant(conv.status)}>{conv.status}</Badge>
                  <Badge variant="outline">{conv.channel}</Badge>
                  <span className="text-xs text-muted-foreground">{formatTime(conv.updated_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Deployable chat (Task 8) ────────────────────────────────────────────────

interface ChatDeployment {
  id: string
  tenant_id: string
  agent_type: string
  identifier: string
  display_name: string | null
  is_active: boolean
  has_key: boolean
  created_at: string
  updated_at: string
}

interface ChatReply {
  identifier: string
  conversation_id: string
  message: string
  agent_type: string
}

interface ChatBubble {
  role: "user" | "assistant"
  text: string
}

function suggestedIdentifier(agentType: string): string {
  const base = (agentType ?? "").toLowerCase().replace(/_/g, "-").replace(/[^a-z0-9-]/g, "")
  return `${base}-chat`.replace(/^-+/, "") || "agent-chat"
}

function DeploymentChatTab({ agentType }: { agentType: string }) {
  const [deployments, setDeployments] = useState<ChatDeployment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [identifier, setIdentifier] = useState(suggestedIdentifier(agentType))
  const [displayNameInput, setDisplayNameInput] = useState("")
  const [accessKey, setAccessKey] = useState("")
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatBubble[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [keyInput, setKeyInput] = useState("")
  const [deleting, setDeleting] = useState<string | null>(null)

  const [origin, setOrigin] = useState("")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (typeof window !== "undefined") setOrigin(window.location.origin)
  }, [])

  useEffect(() => {
    setIdentifier(suggestedIdentifier(agentType))
  }, [agentType])

  async function refresh() {
    const res = await fetch("/api/orchestrator/chat-deployments", { cache: "no-store" })
    if (!res.ok) throw new Error(`Failed to load deployments: ${res.status}`)
    const json: unknown = await res.json()
    if (!Array.isArray(json)) throw new Error("Unexpected deployments response shape")
    const mine = (json as ChatDeployment[]).filter((d) => d.agent_type === agentType)
    return mine
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const mine = await refresh()
        if (!cancelled) {
          setDeployments(mine)
          setSelectedId((prev) => {
            if (prev && mine.some((d) => d.identifier === prev)) return prev
            const active = mine.find((d) => d.is_active)
            return active ? active.identifier : null
          })
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load deployments")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentType])

  const selected = deployments.find((d) => d.identifier === selectedId) ?? null

  function selectDeployment(id: string) {
    setSelectedId(id)
    setMessages([])
    setConversationId(null)
    setChatError(null)
    setKeyInput("")
  }

  async function handleCreate() {
    setCreateError(null)
    setCreating(true)
    try {
      const body: { agent_type: string; identifier: string; display_name?: string; access_key?: string } = {
        agent_type: agentType,
        identifier: identifier.trim().toLowerCase(),
      }
      if (displayNameInput.trim()) body.display_name = displayNameInput.trim()
      if (accessKey) body.access_key = accessKey
      const res = await fetch("/api/orchestrator/chat-deployments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        let detail = `Create failed: ${res.status}`
        try {
          const errJson: unknown = await res.json()
          const d = (errJson as { detail?: unknown }).detail
          if (typeof d === "string" && d) detail = d
        } catch {
          /* keep status text */
        }
        throw new Error(detail)
      }
      const mine = await refresh()
      setDeployments(mine)
      const created = (await res.json().catch(() => null)) as ChatDeployment | null
      const createdId =
        created && typeof created.identifier === "string" ? created.identifier : body.identifier
      setSelectedId(createdId)
      setMessages([])
      setConversationId(null)
      setAccessKey("")
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed")
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    setDeleting(id)
    try {
      const res = await fetch(`/api/orchestrator/chat-deployments/${encodeURIComponent(id)}`, {
        method: "DELETE",
        cache: "no-store",
      })
      if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
      const mine = await refresh()
      setDeployments(mine)
      if (selectedId === id) {
        const next = mine.find((d) => d.is_active)
        setSelectedId(next ? next.identifier : null)
        setMessages([])
        setConversationId(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed")
    } finally {
      setDeleting(null)
    }
  }

  async function handleSend() {
    if (!selected || !draft.trim() || sending) return
    setChatError(null)
    const needsKey = selected.has_key && !keyInput
    if (needsKey) {
      setChatError("This deployment requires an access key — enter it above first.")
      return
    }
    const text = draft.trim()
    setDraft("")
    setMessages((prev) => [...prev, { role: "user", text }])
    setSending(true)
    try {
      const body: { message: string; conversation_id?: string; key?: string } = { message: text }
      if (conversationId) body.conversation_id = conversationId
      if (selected.has_key && keyInput) body.key = keyInput
      const res = await fetch(`/api/orchestrator/chat/${encodeURIComponent(selected.identifier)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        let detail = `Chat failed: ${res.status}`
        try {
          const errJson: unknown = await res.json()
          const d = (errJson as { detail?: unknown }).detail
          if (typeof d === "string" && d) detail = d
        } catch {
          /* keep status text */
        }
        throw new Error(detail)
      }
      const reply: unknown = await res.json()
      const r = reply as ChatReply
      if (!r || typeof r.message !== "string") throw new Error("Unexpected chat response shape")
      if (typeof r.conversation_id === "string" && r.conversation_id) setConversationId(r.conversation_id)
      setMessages((prev) => [...prev, { role: "assistant", text: r.message }])
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Chat failed")
    } finally {
      setSending(false)
    }
  }

  async function handleCopySnippet(snippet: string) {
    try {
      await navigator.clipboard.writeText(snippet)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      const ta = document.createElement("textarea")
      ta.value = snippet
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand("copy")
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch {
        /* clipboard unavailable */
      }
      document.body.removeChild(ta)
    }
  }

  if (loading) return <TabLoader />
  if (error && deployments.length === 0) {
    return (
      <div className="space-y-4">
        <TabError message={error} />
        <button
          type="button"
          onClick={() => {
            setError(null)
            setLoading(true)
            refresh()
              .then((mine) => {
                setDeployments(mine)
                setLoading(false)
              })
              .catch((err: unknown) => {
                setError(err instanceof Error ? err.message : "Failed to load deployments")
                setLoading(false)
              })
          }}
          className="text-sm text-muted-foreground underline hover:text-foreground"
        >
          Retry
        </button>
      </div>
    )
  }

  const embedSnippet = selected
    ? `<iframe src="${origin}/dashboard/admin/agents/${encodeURIComponent(agentType)}?tab=chat&deploy=${encodeURIComponent(selected.identifier)}" width="100%" height="600" frameborder="0" title="Chat with ${displayName(selected.display_name ?? selected.identifier)}"></iframe>`
    : ""

  return (
    <div className="space-y-4">
      {/* Deployments list */}
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Chat deployments</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {deployments.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No chat deployments for this agent yet — create one below.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {deployments.map((d) => (
                <li key={d.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <span className="font-mono text-sm text-foreground">{d.identifier}</span>
                    {d.display_name ? (
                      <span className="ml-2 text-sm text-muted-foreground">{d.display_name}</span>
                    ) : null}
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <Badge variant={d.is_active ? "default" : "secondary"}>
                        {d.is_active ? "active" : "inactive"}
                      </Badge>
                      {d.has_key ? <Badge variant="outline">keyed</Badge> : <Badge variant="outline">public</Badge>}
                      <span className="text-xs text-muted-foreground">{formatTime(d.created_at)}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      onClick={() => selectDeployment(d.identifier)}
                      disabled={!d.is_active}
                      className="rounded-md border border-border px-2 py-1 text-xs hover:bg-secondary disabled:opacity-50"
                    >
                      {selectedId === d.identifier ? "Selected" : "Select to chat"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(d.identifier)}
                      disabled={deleting === d.identifier}
                      className="rounded-md border border-destructive/40 px-2 py-1 text-xs text-destructive hover:bg-destructive/10 disabled:opacity-50"
                    >
                      {deleting === d.identifier ? "Deleting…" : "Delete"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Create form */}
      <details className="rounded-lg border border-border bg-card">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium">New deployment</summary>
        <div className="space-y-3 border-t border-border px-4 py-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs font-medium text-muted-foreground">Identifier (lowercase, a-z 0-9 -)</span>
              <input
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value.toLowerCase())}
                placeholder={suggestedIdentifier(agentType)}
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-sm"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-muted-foreground">Display name (optional)</span>
              <input
                value={displayNameInput}
                onChange={(e) => setDisplayNameInput(e.target.value)}
                placeholder={displayName(agentType)}
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              />
            </label>
          </div>
          <label className="block">
            <span className="text-xs font-medium text-muted-foreground">Access key (optional, min 8 chars)</span>
            <input
              type="password"
              value={accessKey}
              onChange={(e) => setAccessKey(e.target.value)}
              placeholder="optional — leave blank for public link"
              className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-sm"
            />
          </label>
          {createError ? <p className="text-xs text-destructive">{createError}</p> : null}
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating || identifier.trim().length < 4}
            className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create deployment"}
          </button>
        </div>
      </details>

      {/* Chat panel */}
      {selected ? (
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span>
                Chat: <span className="font-mono">{selected.identifier}</span>
              </span>
              <button
                type="button"
                onClick={() => {
                  setMessages([])
                  setConversationId(null)
                  setChatError(null)
                }}
                className="rounded-md border border-border px-2 py-1 text-xs font-normal hover:bg-secondary"
              >
                New thread
              </button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {selected.has_key ? (
              <label className="block">
                <span className="text-xs font-medium text-muted-foreground">Access key for this deployment</span>
                <input
                  type="password"
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  placeholder="enter deployment access key"
                  className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 font-mono text-sm"
                />
              </label>
            ) : null}
            <div className="max-h-96 space-y-2 overflow-auto rounded-lg bg-secondary/30 p-3">
              {messages.length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">
                  No messages yet — say hello to {displayName(selected.display_name ?? agentType)}.
                </p>
              ) : (
                messages.map((m, i) => (
                  <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                        m.role === "user" ? "bg-primary text-primary-foreground" : "bg-background text-foreground border border-border"
                      }`}
                    >
                      {m.text}
                    </div>
                  </div>
                ))
              )}
              {sending ? <p className="text-xs text-muted-foreground">Sending…</p> : null}
            </div>
            {chatError ? <p className="text-xs text-destructive">{chatError}</p> : null}
            <div className="flex gap-2">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    handleSend()
                  }
                }}
                placeholder="Type a message…"
                className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              />
              <button
                type="button"
                onClick={handleSend}
                disabled={sending || !draft.trim()}
                className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Embed snippet */}
      {selected ? (
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="text-base">Embed snippet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <pre className="overflow-auto rounded-lg bg-secondary/50 p-3 font-mono text-[11px]">
              {embedSnippet}
            </pre>
            <button
              type="button"
              onClick={() => handleCopySnippet(embedSnippet)}
              className="rounded-md border border-border px-2 py-1 text-xs hover:bg-secondary"
            >
              {copied ? "Copied!" : "Copy snippet"}
            </button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function AgentDetailPage() {
  const params = useParams()
  const agentType = params.agent_type as string

  const [agent, setAgent] = useState<AgentInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // No GET /api/agents/{type} exists — derive config from the registry list.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch("/api/orchestrator/agents", { cache: "no-store" })
        if (!res.ok) throw new Error(`Failed to load agents: ${res.status}`)
        const json: unknown = await res.json()
        if (!Array.isArray(json)) throw new Error("Unexpected agents response shape")
        const found = (json as AgentInfo[]).find((a) => a.agent_type === agentType) ?? null
        if (!cancelled) setAgent(found)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load agent")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    if (agentType) load()
    return () => {
      cancelled = true
    }
  }, [agentType])

  return (
    <div className="space-y-6 p-4 sm:p-6">
      {/* Back link */}
      <Link
        href="/dashboard/admin/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Agents
      </Link>

      {loading ? (
        <TabLoader />
      ) : error ? (
        <TabError message={error} />
      ) : !agent ? (
        <div className="flex flex-col items-center justify-center gap-3 py-20">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm text-muted-foreground">
            Agent not found: <span className="font-mono">{agentType}</span>
          </p>
        </div>
      ) : (
        <>
          {/* Header */}
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Bot className="h-6 w-6" />
              {displayName(agent.agent_type)}
            </h1>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{agent.agent_type}</p>
            <p className="mt-1 text-sm text-muted-foreground">{agent.description}</p>
          </div>

          {/* Config card */}
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Configuration</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-4 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Model</dt>
                  <dd className="mt-1 inline-flex items-center gap-1">
                    <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-mono text-sm">{agent.llm}</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Status</dt>
                  <dd className="mt-1">
                    {/* Backend has no status field yet — static badge until the API exposes one. */}
                    <Badge>active</Badge>
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Tools ({(agent.tools ?? []).length})
                  </dt>
                  <dd className="mt-1 flex flex-wrap gap-1">
                    {(agent.tools ?? []).map((tool, i) => (
                      <Badge key={`${tool}-${i}`} variant="outline" className="font-mono text-[11px]">
                        {tool}
                      </Badge>
                    ))}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Description</dt>
                  <dd className="mt-1 text-sm text-muted-foreground">{agent.description}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {/* Tabs */}
          <Tabs defaultValue="trail">
            <TabsList className="w-full sm:w-auto">
              <TabsTrigger value="trail" className="gap-2">
                <ListOrdered className="h-4 w-4" />
                Action Trail
              </TabsTrigger>
              <TabsTrigger value="conversations" className="gap-2">
                <Activity className="h-4 w-4" />
                Conversations
              </TabsTrigger>
              <TabsTrigger value="chat" className="gap-2">
                <MessageSquare className="h-4 w-4" />
                Chat
              </TabsTrigger>
            </TabsList>

            <div className="mt-4">
              <TabsContent value="trail">
                <ActionTrailTab agentType={agent.agent_type} />
              </TabsContent>
              <TabsContent value="conversations">
                <ConversationsTab agentType={agent.agent_type} />
              </TabsContent>
              <TabsContent value="chat">
                <DeploymentChatTab agentType={agent.agent_type} />
              </TabsContent>
            </div>
          </Tabs>
        </>
      )}
    </div>
  )
}
