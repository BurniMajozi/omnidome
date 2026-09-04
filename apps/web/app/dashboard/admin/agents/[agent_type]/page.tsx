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
// ActionItem: audit_actions rows via GET /api/orchestrator/actions (NEWEST-FIRST, do NOT re-sort)
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
    s = typeof value === "string" ? value : JSON.stringify(value)
  } catch {
    s = String(value)
  }
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
                <Card className="border-border bg-card">
                  <CardContent className="py-10 text-center">
                    <MessageSquare className="mx-auto h-8 w-8 text-muted-foreground" />
                    <p className="mt-3 text-sm text-muted-foreground">
                      Embedded chat lands here in Task 8 — mount point reserved.
                    </p>
                  </CardContent>
                </Card>
              </TabsContent>
            </div>
          </Tabs>
        </>
      )}
    </div>
  )
}
