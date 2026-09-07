"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Bot, Cpu, Loader2, AlertCircle, Wrench, MessageSquare, ExternalLink, ShieldCheck, Zap } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

// ─── Types (mirror backend AgentInfo in services/agent_orchestrator/schemas.py) ──

interface AgentInfo {
  agent_type: string
  description: string
  llm: string
  tools: string[]
}

// ─── Display-name map ────────────────────────────────────────────────────────

const AGENT_METADATA: Record<string, { name: string; role: string; color: string; badge: string }> = {
  customer_facing: {
    name: "DomeBot",
    role: "Front-Office Omnichannel Assistant",
    color: "from-blue-500/20 to-indigo-500/10 border-blue-500/30",
    badge: "Omnichannel / Support",
  },
  retention: {
    name: "ChurnGuard",
    role: "Retention & Churn Risk Predictor",
    color: "from-amber-500/20 to-orange-500/10 border-amber-500/30",
    badge: "Risk Mitigation",
  },
  provisioning: {
    name: "ProvisionBot",
    role: "Infrastructure & Fleet Orchestrator",
    color: "from-emerald-500/20 to-teal-500/10 border-emerald-500/30",
    badge: "Infrastructure",
  },
  executive: {
    name: "InsightBot",
    role: "Executive Strategy & Synthesis Engine",
    color: "from-purple-500/20 to-pink-500/10 border-purple-500/30",
    badge: "Analytics / C-Suite",
  },
  support: {
    name: "SupportBot",
    role: "Deep Technical Escalation Specialist",
    color: "from-cyan-500/20 to-blue-500/10 border-cyan-500/30",
    badge: "Diagnostics",
  },
}

function getAgentMeta(agentType: string) {
  return AGENT_METADATA[agentType] ?? {
    name: agentType,
    role: "Autonomous Subsystem Specialist",
    color: "from-secondary/40 to-muted/20 border-border",
    badge: "Specialist",
  }
}

// ─── Loading / error states ─────────────────────────────────────────────────

function TabLoader() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <span className="ml-2 text-sm text-muted-foreground">Loading registered agents…</span>
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
  const [searchQuery, setSearchQuery] = useState("")

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

  const filteredAgents = agents.filter((agent) => {
    const meta = getAgentMeta(agent.agent_type)
    const match =
      agent.agent_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      meta.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase())
    return match
  })

  return (
    <div className="space-y-6 p-4 sm:p-6">
      {/* Top Breadcrumb / Back Link */}
      <div className="flex items-center justify-between">
        <Link
          href="/dashboard/admin"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Admin Console
        </Link>
        <Badge variant="outline" className="gap-1 border-primary/30 text-primary">
          <ShieldCheck className="h-3 w-3" />
          Multi-Agent Runtime Active
        </Badge>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2.5 text-2xl font-bold tracking-tight text-foreground">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <Bot className="h-6 w-6" />
            </div>
            Agent Manager
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Orchestrated fleet of specialized autonomous agents, tool bindings, and operational telemetry.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search agents or capabilities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-9 w-64 rounded-lg border border-border bg-background px-3 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {loading ? (
        <TabLoader />
      ) : error ? (
        <TabError message={error} />
      ) : filteredAgents.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-12 text-center">
          <Bot className="mx-auto h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm font-medium text-foreground">No agents found</p>
          <p className="text-xs text-muted-foreground mt-1">
            Try adjusting your search filter or verify orchestrator agent registration.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredAgents.map((agent) => {
            const meta = getAgentMeta(agent.agent_type)
            return (
              <Card
                key={agent.agent_type}
                className={`relative flex flex-col justify-between overflow-hidden border bg-gradient-to-b ${meta.color} transition-all hover:shadow-md hover:border-primary/50`}
              >
                <div>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="h-10 w-10 rounded-xl bg-background/80 border border-border/80 flex items-center justify-center shadow-sm text-primary">
                          <Bot className="h-5 w-5" />
                        </div>
                        <div>
                          <CardTitle className="text-base font-bold text-foreground">
                            {meta.name}
                          </CardTitle>
                          <div className="font-mono text-[11px] text-muted-foreground">
                            {agent.agent_type}
                          </div>
                        </div>
                      </div>
                      <Badge variant="outline" className="text-[10px] bg-background/60 font-normal">
                        {meta.badge}
                      </Badge>
                    </div>
                    <CardDescription className="text-xs text-muted-foreground line-clamp-2 mt-2 leading-relaxed">
                      {agent.description}
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="space-y-3 pb-3">
                    {/* Model Spec */}
                    <div className="flex items-center justify-between rounded-lg bg-background/60 border border-border/60 p-2 text-xs">
                      <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                        <Cpu className="h-3.5 w-3.5 text-primary" />
                        Model Engine
                      </span>
                      <span className="font-mono font-medium text-foreground text-[11px]">
                        {agent.llm}
                      </span>
                    </div>

                    {/* Tools / Capabilities */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                          <Wrench className="h-3.5 w-3.5 text-amber-500" />
                          Tool Bindings
                        </span>
                        <span className="font-mono text-[11px] font-semibold text-foreground">
                          {(agent.tools ?? []).length} registered
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1 max-h-16 overflow-y-auto pr-0.5">
                        {(agent.tools ?? []).length > 0 ? (
                          agent.tools.map((tool, idx) => (
                            <Badge
                              key={`${tool}-${idx}`}
                              variant="secondary"
                              className="font-mono text-[10px] px-1.5 py-0 bg-background/80 border border-border/50 text-foreground"
                            >
                              {tool}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-[11px] text-muted-foreground italic">
                            No custom tools attached
                          </span>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </div>

                {/* Card Actions Footer */}
                <div className="border-t border-border/70 bg-background/40 p-3 flex items-center justify-between gap-2 mt-auto">
                  <Link
                    href={`/dashboard/communication?agent=${encodeURIComponent(agent.agent_type)}`}
                    className="flex-1"
                  >
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full h-8 text-xs gap-1 bg-background hover:bg-muted"
                    >
                      <MessageSquare className="h-3.5 w-3.5 text-primary" />
                      Chat & Test
                    </Button>
                  </Link>

                  <Link
                    href={`/dashboard/admin/agents/${encodeURIComponent(agent.agent_type)}`}
                    className="flex-1"
                  >
                    <Button
                      size="sm"
                      className="w-full h-8 text-xs gap-1 bg-primary text-primary-foreground shadow-sm"
                    >
                      <Zap className="h-3.5 w-3.5" />
                      Manage & Audit
                      <ExternalLink className="h-3 w-3 ml-0.5 opacity-70" />
                    </Button>
                  </Link>
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
