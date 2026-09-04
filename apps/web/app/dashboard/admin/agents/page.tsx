"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Bot, Cpu, Loader2, AlertCircle, Wrench } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

// ─── Types (mirror backend AgentInfo in services/agent_orchestrator/schemas.py) ──

interface AgentInfo {
  agent_type: string
  description: string
  llm: string
  tools: string[]
}

// ─── Display-name map ────────────────────────────────────────────────────────

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

// ─── Loading / error states (same style as customer-360) ────────────────────

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

// ─── Page ────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch("/api/orchestrator/agents", { cache: "no-store" })
        if (!res.ok) throw new Error(`Failed to load agents: ${res.status}`)
        const json: unknown = await res.json()
        if (!Array.isArray(json)) throw new Error("Unexpected agents response shape")
        if (!cancelled) setAgents(json as AgentInfo[])
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load agents")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="space-y-6 p-4 sm:p-6">
      {/* Back link */}
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Link>

      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Bot className="h-6 w-6" />
          Agent Manager
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Registry of autonomous agents served by the orchestrator.
        </p>
      </div>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Agents ({loading ? "…" : agents.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <TabLoader />
          ) : error ? (
            <TabError message={error} />
          ) : agents.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No agents registered.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Tools</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {agents.map((agent) => (
                  <TableRow key={agent.agent_type}>
                    <TableCell>
                      <Link
                        href={`/dashboard/admin/agents/${encodeURIComponent(agent.agent_type)}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {displayName(agent.agent_type)}
                      </Link>
                      <div className="font-mono text-xs text-muted-foreground">
                        {agent.agent_type}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-md text-sm text-muted-foreground">
                      {agent.description}
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1 text-sm">
                        <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="font-mono text-xs">{agent.llm}</span>
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1 text-sm">
                        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
                        {(agent.tools ?? []).length}
                      </span>
                      {(agent.tools ?? []).length > 0 && (
                        <div className="mt-1 flex max-w-xs flex-wrap gap-1">
                          {(agent.tools ?? []).map((tool, i) => (
                            <Badge key={`${tool}-${i}`} variant="outline" className="font-mono text-[11px]">
                              {tool}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge>active</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
