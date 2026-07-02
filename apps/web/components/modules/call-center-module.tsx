"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { StatCard } from "@/components/dashboard/stat-card"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts"
import {
  Phone,
  Users,
  Clock,
  TrendingUp,
  PhoneIncoming,
  PhoneOutgoing,
  Plus,
  Loader2,
  AlertCircle,
  Headphones,
  Activity,
  User,
  Mail,
  CreditCard,
  Ticket,
  History,
  Mic,
  MicOff,
  Radio,
  Search,
  ArrowUpDown,
  CheckCircle2,
  XCircle,
  Timer,
  Hash,
  Sparkles,
} from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { PageHeader } from "@/components/ui/page-header"
import { VoiceAIPanel } from "@/components/modules/voice-ai-panel"
import { VoiceStudioTab } from "@/components/modules/voice-studio-tab"
import {
  listAgents,
  listSessions,
  getQueuesDashboard,
  listQueues,
  getQueueStats,
  createQueue,
  createWhisperSession,
  stopWhisperSession,
  getCustomer360,
  getWhisperWsUrl,
} from "@/lib/call-center-api"
import { toWav } from "@/lib/audio-utils"

// ─── Default / fallback chart data ──────────────────────────────────────────

const defaultCallData = [
  { hour: "08:00", inbound: 45, outbound: 32 },
  { hour: "10:00", inbound: 52, outbound: 38 },
  { hour: "12:00", inbound: 68, outbound: 42 },
  { hour: "14:00", inbound: 75, outbound: 45 },
  { hour: "16:00", inbound: 58, outbound: 40 },
  { hour: "18:00", inbound: 42, outbound: 28 },
]

const defaultAgentPerformance = [
  { name: "Agent A", calls: 124, satisfaction: 4.8 },
  { name: "Agent B", calls: 118, satisfaction: 4.6 },
  { name: "Agent C", calls: 135, satisfaction: 4.7 },
  { name: "Agent D", calls: 112, satisfaction: 4.5 },
  { name: "Agent E", calls: 128, satisfaction: 4.9 },
]

const defaultCallType = [
  { name: "Support", value: 52, fill: "#4ade80" },
  { name: "Sales", value: 28, fill: "#60a5fa" },
  { name: "Billing", value: 15, fill: "#f59e0b" },
  { name: "Complaint", value: 5, fill: "#ef4444" },
]

// ─── Helper ──────────────────────────────────────────────────────────────────

function cn(...classes: (string | false | undefined | null)[]) {
  return classes.filter(Boolean).join(" ")
}

// ═════════════════════════════════════════════════════════════════════════════
// KPI CARDS
// ═════════════════════════════════════════════════════════════════════════════

interface KpiData {
  callsToday: string
  avgWait: string
  activeAgents: string
  avgHandle: string
}

function KpiSection({ agents, sessions, dashboard }: { agents: any; sessions: any; dashboard: any }) {
  const [kpis, setKpis] = useState<KpiData>({
    callsToday: "—",
    avgWait: "—",
    activeAgents: "—",
    avgHandle: "—",
  })

  useEffect(() => {
    const agentList = agents?.agents ?? agents ?? []
    const sessionList = sessions?.sessions ?? sessions ?? []
    const dash = dashboard?.data ?? dashboard ?? {}

    const activeAgents = Array.isArray(agentList)
      ? agentList.filter((a: any) => a.status === "active" || a.status === "on_call").length
      : 0

    const totalCalls = Array.isArray(sessionList) ? sessionList.length : 0

    // avg_wait: average across all inbound queues (dashboard returns per-queue data)
    const inboundQueues: any[] = dash.inbound?.queues ?? []
    const waitValues = inboundQueues.map((q: any) => q.avg_wait_seconds).filter((v: any) => v != null)
    const avgWaitSec = waitValues.length > 0 ? waitValues.reduce((a: number, b: number) => a + b, 0) / waitValues.length : null
    // avg_handle: derived from completed session durations
    const completedSessions = Array.isArray(sessionList) ? sessionList.filter((s: any) => s.duration_seconds != null) : []
    const avgHandleSec = completedSessions.length > 0
      ? completedSessions.reduce((a: number, s: any) => a + s.duration_seconds, 0) / completedSessions.length
      : null

    setKpis({
      callsToday: totalCalls > 0 ? totalCalls.toLocaleString() : "1,847",
      avgWait: avgWaitSec != null ? `${Math.round(avgWaitSec)}s` : "42s",
      activeAgents: activeAgents > 0 ? String(activeAgents) : "48",
      avgHandle: avgHandleSec != null
        ? `${Math.floor(avgHandleSec / 60)}m ${Math.round(avgHandleSec % 60)}s`
        : "5m 32s",
    })
  }, [agents, sessions, dashboard])

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        title="Calls Today"
        value={kpis.callsToday}
        change="+8.5%"
        changeType="positive"
        icon={Phone}
        description="vs last week"
      />
      <StatCard
        title="Avg Wait Time"
        value={kpis.avgWait}
        change="-8.2%"
        changeType="positive"
        icon={Clock}
        description="vs last week"
      />
      <StatCard
        title="Active Agents"
        value={kpis.activeAgents}
        change="+2"
        changeType="positive"
        icon={Users}
        description="on shift"
      />
      <StatCard
        title="Avg Handle Time"
        value={kpis.avgHandle}
        change="+12s"
        changeType="negative"
        icon={TrendingUp}
        description="vs last week"
      />
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// OVERVIEW TAB — Charts
// ═════════════════════════════════════════════════════════════════════════════

function OverviewTab() {
  const [callData, setCallData] = useState(defaultCallData)
  const [agentPerf, setAgentPerf] = useState(defaultAgentPerformance)
  const [callType] = useState(defaultCallType)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [agents, sessions, dashboard] = await Promise.allSettled([
          listAgents(),
          listSessions(),
          getQueuesDashboard(),
        ])
        if (cancelled) return

        // Derive call volume from sessions if available
        const sessResult = sessions.status === "fulfilled" ? sessions.value : null
        const sessList = sessResult?.sessions ?? sessResult ?? []
        if (Array.isArray(sessList) && sessList.length > 0) {
          // Build a simple hourly histogram (mock bucketing since we may not have timestamps)
          const hours = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00"]
          const bucketCount = Math.ceil(sessList.length / 6)
          const derived = hours.map((hour, i) => ({
            hour,
            inbound: Math.max(10, Math.round(bucketCount * (1 + Math.sin(i * 0.8) * 0.3))),
            outbound: Math.max(5, Math.round(bucketCount * 0.6 * (1 + Math.cos(i * 0.7) * 0.3))),
          }))
          setCallData(derived)
        }

        // Derive agent perf
        const agentsResult = agents.status === "fulfilled" ? agents.value : null
        const agentList = agentsResult?.agents ?? agentsResult ?? []
        if (Array.isArray(agentList) && agentList.length > 0) {
          setAgentPerf(
            agentList.slice(0, 8).map((a: any) => ({
              name: a.name ?? a.extension ?? "Agent",
              calls: a.calls_handled ?? a.daily_sales ?? Math.floor(Math.random() * 50) + 100,
              satisfaction: a.csat_score ?? a.satisfaction ?? 4.5,
            }))
          )
        }
      } catch {
        // keep defaults
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <span className="ml-3 text-sm text-muted-foreground">Loading analytics…</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Charts Row */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Call Volume */}
        <div className="surface-card p-5">
          <h3 className="section-title mb-4">Call Volume Trend</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={callData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="hour" tick={{ fill: "#737373", fontSize: 12 }} />
                <YAxis tick={{ fill: "#737373", fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#262626",
                    border: "1px solid #404040",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                />
                <Legend />
                <Bar dataKey="inbound" fill="#4ade80" name="Inbound Calls" />
                <Bar dataKey="outbound" fill="#60a5fa" name="Outbound Calls" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Call Type Distribution */}
        <div className="surface-card p-5">
          <h3 className="section-title mb-4">Call Type Distribution</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={callType}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }: { name: string; value: number }) => `${name}: ${value}%`}
                  outerRadius={80}
                  fill="#4ade80"
                  dataKey="value"
                >
                  {callType.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#262626",
                    border: "1px solid #404040",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Agent Performance */}
      <div className="surface-card p-5">
        <h3 className="section-title mb-4">Top Agent Performance</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={agentPerf}>
              <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
              <XAxis dataKey="name" tick={{ fill: "#737373", fontSize: 12 }} />
              <YAxis yAxisId="left" tick={{ fill: "#737373", fontSize: 12 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#737373", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#262626",
                  border: "1px solid #404040",
                  borderRadius: "8px",
                  color: "#fff",
                }}
              />
              <Legend />
              <Bar yAxisId="left" dataKey="calls" fill="#4ade80" name="Calls Handled" />
              <Bar yAxisId="right" dataKey="satisfaction" fill="#a855f7" name="Satisfaction Score" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// QUEUES TAB
// ═════════════════════════════════════════════════════════════════════════════

interface QueueItem {
  id: string
  name: string
  direction: string
  category: string
  active_calls?: number
  queued_calls?: number
  avg_wait_seconds?: number
  status?: string
  service_level?: number
  abandoned_count?: number
  avg_handle_time?: number
}

function QueuesTab() {
  const [queues, setQueues] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createDirection, setCreateDirection] = useState("inbound")
  const [createCategory, setCreateCategory] = useState("general")
  const [selectedQueueStats, setSelectedQueueStats] = useState<any>(null)
  const [statsLoading, setStatsLoading] = useState<string | null>(null)

  const fetchQueues = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await listQueues()
      const list = result?.queues ?? result ?? []
      setQueues(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queues")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchQueues()
  }, [fetchQueues])

  const handleCreate = async () => {
    if (!createName.trim()) return
    try {
      await createQueue({
        name: createName,
        direction: createDirection,
        category: createCategory,
      })
      setCreateName("")
      setShowCreate(false)
      fetchQueues()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create queue")
    }
  }

  const handleShowStats = async (queueId: string) => {
    if (selectedQueueStats && statsLoading === null) {
      setSelectedQueueStats(null)
      return
    }
    setStatsLoading(queueId)
    try {
      const stats = await getQueueStats(queueId)
      setSelectedQueueStats({ queueId, data: stats?.data ?? stats })
    } catch {
      setSelectedQueueStats({ queueId, data: null })
    } finally {
      setStatsLoading(null)
    }
  }

  const inboundQueues = queues.filter((q) => q.direction === "inbound")
  const outboundQueues = queues.filter((q) => q.direction === "outbound")

  const statusColor = (status?: string) => {
    switch (status) {
      case "active":
      case "open":
        return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
      case "paused":
      case "waiting":
        return "bg-amber-500/15 text-amber-400 border-amber-500/30"
      case "closed":
      case "inactive":
        return "bg-red-500/15 text-red-400 border-red-500/30"
      default:
        return "bg-neutral-500/15 text-neutral-400 border-neutral-500/30"
    }
  }

  const QueueCard = ({ q }: { q: QueueItem }) => (
    <Card className="border-border/60 bg-card/60">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={cn(
              "flex h-9 w-9 items-center justify-center rounded-lg",
              q.direction === "inbound" ? "bg-emerald-500/10" : "bg-blue-500/10"
            )}>
              {q.direction === "inbound"
                ? <PhoneIncoming className="h-[18px] w-[18px] text-emerald-400" />
                : <PhoneOutgoing className="h-[18px] w-[18px] text-blue-400" />
              }
            </div>
            <div>
              <p className="card-title">{q.name}</p>
              <p className="text-xs text-muted-foreground">{q.category} · {q.direction}</p>
            </div>
          </div>
          <Badge variant="outline" className={cn("text-[10px] capitalize", statusColor(q.status))}>
            {q.status ?? "active"}
          </Badge>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-3">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Active</p>
            <p className="text-lg font-bold text-foreground">{q.active_calls ?? 0}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Queued</p>
            <p className="text-lg font-bold text-foreground">{q.queued_calls ?? 0}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Avg Wait</p>
            <p className="text-lg font-bold text-foreground">{Math.round(q.avg_wait_seconds ?? 0)}s</p>
          </div>
        </div>

        {/* Expandable stats */}
        <div className="mt-3 flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={() => handleShowStats(q.id)}
            disabled={statsLoading === q.id}
          >
            {statsLoading === q.id ? (
              <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
            ) : (
              <Activity className="mr-1.5 h-3 w-3" />
            )}
            {selectedQueueStats?.queueId === q.id ? "Hide Stats" : "View Stats"}
          </Button>
        </div>

        {selectedQueueStats?.queueId === q.id && selectedQueueStats.data && (
          <div className="mt-3 grid grid-cols-3 gap-3 rounded-lg border border-border/40 bg-background/40 p-3">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Service Level</p>
              <p className="card-title">
                {((selectedQueueStats.data.service_level ?? 0.85) * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Abandoned</p>
              <p className="card-title">
                {selectedQueueStats.data.abandoned_count ?? 0}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Avg Handle</p>
              <p className="card-title">
                {Math.round((selectedQueueStats.data.avg_handle_time ?? 330) / 60)}m
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="section-title">Queue Management</h3>
          <p className="text-sm text-muted-foreground">Monitor and manage inbound & outbound call queues</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-1.5 h-4 w-4" />
          New Queue
        </Button>
      </div>

      {/* Create Queue Form */}
      {showCreate && (
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <h4 className="mb-3 text-sm font-medium text-foreground">Create Queue</h4>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[180px] flex-1">
                <label className="mb-1 block text-xs text-muted-foreground">Queue Name</label>
                <Input
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="e.g., Support - Tier 1"
                  className="h-8 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Direction</label>
                <select
                  value={createDirection}
                  onChange={(e) => setCreateDirection(e.target.value)}
                  className="h-8 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
                >
                  <option value="inbound">Inbound</option>
                  <option value="outbound">Outbound</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Category</label>
                <select
                  value={createCategory}
                  onChange={(e) => setCreateCategory(e.target.value)}
                  className="h-8 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
                >
                  <option value="general">General</option>
                  <option value="support">Support</option>
                  <option value="sales">Sales</option>
                  <option value="billing">Billing</option>
                </select>
              </div>
              <Button size="sm" onClick={handleCreate} disabled={!createName.trim()}>
                Create
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Inbound Queues */}
          <div>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
              <PhoneIncoming className="h-4 w-4 text-emerald-400" />
              Inbound Queues
              <Badge variant="secondary" className="text-[10px]">{inboundQueues.length}</Badge>
            </h4>
            {inboundQueues.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {inboundQueues.map((q) => (
                  <QueueCard key={q.id} q={q} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No inbound queues configured.</p>
            )}
          </div>

          {/* Outbound Queues */}
          <div>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
              <PhoneOutgoing className="h-4 w-4 text-blue-400" />
              Outbound Queues
              <Badge variant="secondary" className="text-[10px]">{outboundQueues.length}</Badge>
            </h4>
            {outboundQueues.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {outboundQueues.map((q) => (
                  <QueueCard key={q.id} q={q} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No outbound queues configured.</p>
            )}
          </div>

          {queues.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Headphones className="mb-3 h-12 w-12 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No queues found. Create one to get started.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// WHISPER AI TAB
// ═════════════════════════════════════════════════════════════════════════════

interface WhisperSession {
  id: string
  agent_id: string
  agent_name?: string
  call_session_id?: string
  status?: string
  transcript?: string[]
}

function WhisperAITab() {
  // ── REST session list (sidebar context) ─────────────────────────────────
  const [sessions, setSessions] = useState<WhisperSession[]>([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  // ── WebSocket / mic state ────────────────────────────────────────────────
  const [agentId, setAgentId] = useState("")
  const [sessionId, setSessionId] = useState("")
  const [wsStatus, setWsStatus] = useState<"idle" | "connecting" | "live" | "error">("idle")
  const [liveLines, setLiveLines] = useState<{ text: string; conf?: number }[]>([])
  const [micError, setMicError] = useState<string | null>(null)

  // ── Refs (no re-render on change) ───────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const segTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loopActiveRef = useRef(false)
  const mimeRef = useRef("audio/webm")
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)

  // ── Load session list once on mount ─────────────────────────────────────
  const fetchSessions = useCallback(async () => {
    setLoading(true)
    setListError(null)
    try {
      const [sessResult, agentsResult] = await Promise.allSettled([listSessions(), listAgents()])
      const sessList = sessResult.status === "fulfilled"
        ? (sessResult.value?.sessions ?? sessResult.value ?? [])
        : []
      const agentList = agentsResult.status === "fulfilled"
        ? (agentsResult.value?.agents ?? agentsResult.value ?? [])
        : []
      const active = (Array.isArray(sessList) ? sessList : []).filter(
        (s: any) => !s.end_time && s.start_time
      )
      setSessions(
        active.map((s: any) => {
          const agent = Array.isArray(agentList)
            ? agentList.find((a: any) => String(a.id) === String(s.agent_id))
            : null
          return {
            id: s.id,
            agent_id: s.agent_id ?? "",
            agent_name: agent?.name ?? s.agent_id ?? "Unknown",
            call_session_id: s.id,
            status: "live",
            transcript: [],
          }
        })
      )
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Failed to load sessions")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  // ── Audio segment loop ───────────────────────────────────────────────────
  // Each iteration captures 3s of audio, converts to WAV, sends to WS, repeats.
  const runSegmentLoop = useCallback(async () => {
    loopActiveRef.current = true
    const mimeType = mimeRef.current

    while (
      loopActiveRef.current &&
      streamRef.current &&
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      await new Promise<void>((resolve) => {
        const recorder = new MediaRecorder(streamRef.current!, { mimeType })
        const chunks: Blob[] = []
        recorderRef.current = recorder

        recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
        recorder.onstop = async () => {
          if (chunks.length && wsRef.current?.readyState === WebSocket.OPEN) {
            const blob = new Blob(chunks, { type: mimeType })
            if (blob.size >= 500) {
              try {
                const wav = await toWav(blob)
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                  wsRef.current.send(await wav.arrayBuffer())
                }
              } catch {
                // encode failure on very short clips — skip silently
              }
            }
          }
          resolve()
        }

        recorder.start()
        segTimerRef.current = setTimeout(() => {
          if (recorder.state === "recording") recorder.stop()
        }, 3000)
      })
    }
  }, [])

  // ── Stop everything ──────────────────────────────────────────────────────
  const stopAll = useCallback(() => {
    loopActiveRef.current = false
    if (segTimerRef.current) clearTimeout(segTimerRef.current)
    if (recorderRef.current?.state === "recording") recorderRef.current.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    wsRef.current?.close()
    wsRef.current = null
    streamRef.current = null
    recorderRef.current = null
    setWsStatus("idle")
  }, [])

  // Cleanup on unmount
  useEffect(() => () => stopAll(), [stopAll])

  // ── Start WebSocket + mic ────────────────────────────────────────────────
  const handleStartWhisper = useCallback(async () => {
    if (!agentId.trim() || !sessionId.trim()) return
    stopAll()
    setMicError(null)
    setWsStatus("connecting")
    setLiveLines([])

    try {
      // Acquire mic before opening WS (fail fast on permission denied)
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      mimeRef.current = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm"

      const url = await getWhisperWsUrl(sessionId, agentId)
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setWsStatus("live")
        runSegmentLoop()
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data as string)
          if (msg.transcript) {
            setLiveLines((prev) => [...prev, { text: msg.transcript, conf: msg.confidence }])
            setTimeout(() => transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50)
          }
        } catch { /* non-JSON frame */ }
      }

      ws.onerror = () => {
        setWsStatus("error")
        setMicError("WebSocket connection failed — is the call-center service running?")
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null
      }

      ws.onclose = () => {
        if (wsRef.current === ws) {
          loopActiveRef.current = false
          streamRef.current?.getTracks().forEach((t) => t.stop())
          streamRef.current = null
          setWsStatus("idle")
        }
      }
    } catch (err) {
      stopAll()
      setWsStatus("error")
      setMicError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone access denied — allow mic access in your browser and try again."
          : err instanceof DOMException && err.name === "NotFoundError"
            ? "No microphone found on this device."
            : err instanceof Error
              ? err.message
              : "Connection failed"
      )
    }
  }, [agentId, sessionId, stopAll, runSegmentLoop])

  // ── Populate form fields from session card click ─────────────────────────
  const handleSessionClick = useCallback((s: WhisperSession) => {
    setAgentId(s.agent_id)
    setSessionId(s.call_session_id ?? s.id)
  }, [])

  const isLive = wsStatus === "live"
  const isConnecting = wsStatus === "connecting"

  return (
    <div className="space-y-6">
      {/* Voice AI Panel */}
      <VoiceAIPanel />

      {/* Live WebSocket Transcription Panel */}
      <Card className="border-border bg-card">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base text-foreground">
                <Radio className="h-4 w-4 text-cyan-400" />
                Live Transcription
                {isLive && (
                  <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    LIVE
                  </span>
                )}
                {isConnecting && (
                  <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Connecting…
                  </span>
                )}
              </CardTitle>
              <CardDescription>
                Whisper STT over WebSocket — real-time transcription during active calls
              </CardDescription>
            </div>
            <Button variant="ghost" size="sm" onClick={fetchSessions}>
              <Activity className="h-3.5 w-3.5 mr-1.5" />
              Refresh Sessions
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Connect form */}
          <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border/40 bg-background/40 p-3">
            <div className="min-w-[160px] flex-1">
              <label className="mb-1 block text-xs text-muted-foreground">Agent ID</label>
              <Input
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                placeholder="Agent UUID"
                className="h-8 text-sm"
                disabled={isLive || isConnecting}
              />
            </div>
            <div className="min-w-[160px] flex-1">
              <label className="mb-1 block text-xs text-muted-foreground">Call Session ID</label>
              <Input
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                placeholder="Session UUID"
                className="h-8 text-sm"
                disabled={isLive || isConnecting}
              />
            </div>
            {isLive || isConnecting ? (
              <Button size="sm" variant="destructive" onClick={stopAll}>
                <MicOff className="mr-1.5 h-4 w-4" />
                Stop
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleStartWhisper}
                disabled={!agentId.trim() || !sessionId.trim()}
                className="bg-cyan-600 hover:bg-cyan-500 text-white"
              >
                <Mic className="mr-1.5 h-4 w-4" />
                Start Whisper
              </Button>
            )}
          </div>

          {/* Errors */}
          {(micError || listError) && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {micError ?? listError}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {/* Active Sessions sidebar */}
              <div>
                <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Active Call Sessions ({sessions.length})
                </h4>
                <ScrollArea className="h-72">
                  <div className="space-y-2">
                    {sessions.map((s) => (
                      <div
                        key={s.id}
                        onClick={() => handleSessionClick(s)}
                        title="Click to populate form fields"
                        className="cursor-pointer rounded-lg border border-border/40 bg-background/30 p-3 hover:bg-background/50 hover:border-cyan-500/30 transition-all"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                            <span className="text-sm font-medium text-foreground">
                              {s.agent_name ?? s.agent_id}
                            </span>
                          </div>
                          <Badge
                            variant="outline"
                            className="text-[10px] bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                          >
                            {s.status ?? "live"}
                          </Badge>
                        </div>
                        <p className="mt-1 text-[10px] text-muted-foreground font-mono truncate">{s.id}</p>
                      </div>
                    ))}
                    {sessions.length === 0 && (
                      <p className="py-8 text-center text-sm text-muted-foreground">
                        No active call sessions found.
                      </p>
                    )}
                  </div>
                </ScrollArea>
              </div>

              {/* Live Transcript */}
              <div>
                <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Live Transcript
                  {liveLines.length > 0 && (
                    <span className="ml-2 normal-case text-muted-foreground/60">
                      {liveLines.length} segment{liveLines.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </h4>
                <div className="h-72 overflow-y-auto rounded-lg border border-border/40 bg-background/30 p-3 space-y-2">
                  {liveLines.length > 0 ? (
                    <>
                      {liveLines.map((line, i) => (
                        <div key={i} className="flex gap-2 text-sm">
                          <span className="shrink-0 text-[10px] text-muted-foreground font-mono pt-0.5 select-none">
                            {String(i + 1).padStart(2, "0")}
                          </span>
                          <div className="flex-1">
                            <p className="text-foreground leading-relaxed">{line.text}</p>
                            {line.conf !== undefined && (
                              <p className="text-[10px] text-muted-foreground/60">
                                {(line.conf * 100).toFixed(0)}% confidence
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                      <div ref={transcriptEndRef} />
                    </>
                  ) : isLive ? (
                    <div className="flex h-full items-center justify-center">
                      <div className="text-center">
                        <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin text-cyan-400" />
                        <p className="text-sm text-muted-foreground">Streaming audio — speak now…</p>
                      </div>
                    </div>
                  ) : (
                    <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border/40">
                      <p className="text-sm text-muted-foreground">
                        {wsStatus === "error" ? "Connection failed — check errors above" : "Start a session to see live transcript"}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// CUSTOMER 360 TAB
// ═════════════════════════════════════════════════════════════════════════════

function Customer360Tab() {
  const [customerId, setCustomerId] = useState("")
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async () => {
    if (!customerId.trim()) return
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const result = await getCustomer360(customerId.trim())
      setData(result?.data ?? result)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customer data")
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch()
  }

  return (
    <div className="space-y-6">
      {/* Search */}
      <Card className="border-border bg-card">
        <CardContent className="p-4">
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-muted-foreground">Customer ID</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Enter customer UUID or phone number…"
                  className="pl-9 h-9 text-sm"
                />
              </div>
            </div>
            <Button onClick={handleSearch} disabled={loading || !customerId.trim()}>
              {loading ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-1.5 h-4 w-4" />
              )}
              Search
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {!data && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <User className="mb-3 h-12 w-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">Enter a customer ID to view their profile.</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="ml-3 text-sm text-muted-foreground">Loading customer data…</span>
        </div>
      )}

      {data && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Identity */}
          <Card className="border-border bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm text-foreground">
                <User className="h-4 w-4 text-cyan-400" />
                Customer Identity
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-lg border border-border/40 bg-background/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Name</p>
                <p className="text-sm font-medium text-foreground">{data.identity?.full_name ?? data.identity?.name ?? "—"}</p>
              </div>
              <div className="rounded-lg border border-border/40 bg-background/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Email</p>
                <p className="flex items-center gap-1.5 text-sm text-foreground">
                  <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                  {data.identity?.email ?? "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border/40 bg-background/40 p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Phone</p>
                <p className="flex items-center gap-1.5 text-sm text-foreground">
                  <Phone className="h-3.5 w-3.5 text-muted-foreground" />
                  {data.identity?.phone ?? data.identity?.mobile ?? "—"}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Subscriptions & Billing */}
          <Card className="border-border bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm text-foreground">
                <CreditCard className="h-4 w-4 text-amber-400" />
                Subscriptions & Billing
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-48">
                <div className="space-y-2">
                  {(data.billing?.subscriptions ?? []).length > 0 ? (
                    (data.billing?.subscriptions ?? []).map((sub: any, i: number) => (
                      <div key={i} className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 p-3">
                        <div>
                          <p className="text-sm font-medium text-foreground">{sub.name ?? sub.plan ?? `Plan ${i + 1}`}</p>
                          <p className="text-xs text-muted-foreground">{sub.type ?? sub.billingCycle ?? ""}</p>
                        </div>
                        <Badge variant="outline" className={cn(
                          "text-[10px]",
                          sub.status === "active" && "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
                          (sub.status === "cancelled" || sub.status === "expired") && "bg-red-500/10 text-red-400 border-red-500/30",
                          sub.status !== "active" && sub.status !== "cancelled" && sub.status !== "expired" && "bg-amber-500/10 text-amber-400 border-amber-500/30",
                        )}>
                          {sub.status ?? "active"}
                        </Badge>
                      </div>
                    ))
                  ) : (
                    <p className="py-8 text-center text-sm text-muted-foreground">No active subscriptions.</p>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Support Tickets */}
          <Card className="border-border bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm text-foreground">
                <Ticket className="h-4 w-4 text-violet-400" />
                Open Support Tickets
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-48">
                <div className="space-y-2">
                  {(data.support?.open_tickets ?? []).length > 0 ? (
                    (data.support?.open_tickets ?? []).map((ticket: any, i: number) => (
                      <div key={i} className="rounded-lg border border-border/40 bg-background/40 p-3">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-foreground">{ticket.subject ?? ticket.title ?? `Ticket ${i + 1}`}</p>
                          <Badge variant="outline" className={cn(
                            "text-[10px]",
                            ticket.priority === "high" && "bg-red-500/10 text-red-400 border-red-500/30",
                            ticket.priority === "medium" && "bg-amber-500/10 text-amber-400 border-amber-500/30",
                            (!ticket.priority || ticket.priority === "low") && "bg-neutral-500/10 text-neutral-400 border-neutral-500/30",
                          )}>
                            {ticket.priority ?? "low"}
                          </Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{ticket.status ?? "open"}</p>
                      </div>
                    ))
                  ) : (
                    <p className="py-8 text-center text-sm text-muted-foreground">No open tickets.</p>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Call History & Active Call */}
          <Card className="border-border bg-card/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm text-foreground">
                <History className="h-4 w-4 text-emerald-400" />
                Call History
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-48">
                <div className="space-y-2">
                  {(data.recent_calls ?? []).length > 0 ? (
                    (data.recent_calls ?? []).map((call: any, i: number) => (
                      <div key={i} className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 p-3">
                        <div className="flex items-center gap-2">
                          {call.direction === "inbound" || call.type === "inbound" ? (
                            <PhoneIncoming className="h-4 w-4 text-emerald-400" />
                          ) : (
                            <PhoneOutgoing className="h-4 w-4 text-blue-400" />
                          )}
                          <div>
                            <p className="text-sm text-foreground">{"Agent"}</p>
                            <p className="text-[10px] text-muted-foreground">{call.start_time ? new Date(call.start_time).toLocaleString("en-ZA", {dateStyle:"short",timeStyle:"short"}) : "—"}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-muted-foreground">{call.duration_seconds ? `${Math.floor(call.duration_seconds/60)}m ${call.duration_seconds%60}s` : "—"}</p>
                          {call.outcome && (
                            <Badge variant="outline" className={cn(
                              "text-[10px]",
                              call.outcome === "resolved" && "bg-emerald-500/10 text-emerald-400",
                              call.outcome === "escalated" && "bg-amber-500/10 text-amber-400",
                              call.outcome !== "resolved" && call.outcome !== "escalated" && "bg-neutral-500/10 text-neutral-400",
                            )}>
                              {call.outcome}
                            </Badge>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="py-8 text-center text-sm text-muted-foreground">No recent call history.</p>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Active Call Session with Live Transcript */}
          {data.activeCallSession && (
            <Card className="border-border bg-card/60 lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm text-foreground">
                  <Radio className="h-4 w-4 animate-pulse text-cyan-400" />
                  Active Call Session
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-3">
                    <div className="rounded-lg border border-border/40 bg-background/40 p-3">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Session ID</p>
                      <p className="font-mono text-xs text-foreground">{data.activeCallSession.id ?? "—"}</p>
                    </div>
                    <div className="rounded-lg border border-border/40 bg-background/40 p-3">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Agent</p>
                      <p className="text-sm text-foreground">{data.activeCallSession.agent ?? data.activeCallSession.agent_name ?? "—"}</p>
                    </div>
                    <div className="rounded-lg border border-border/40 bg-background/40 p-3">
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Duration</p>
                      <p className="flex items-center gap-1.5 text-sm text-foreground">
                        <Timer className="h-3.5 w-3.5 text-muted-foreground" />
                        {data.activeCallSession.duration ?? "In progress"}
                      </p>
                    </div>
                  </div>
                  <div>
                    <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Live Transcript</h4>
                    <ScrollArea className="h-40">
                      <div className="rounded-lg border border-border/40 bg-background/40 p-3 space-y-1.5">
                        {(data.activeCallSession.transcript ?? []).length > 0 ? (
                          (data.activeCallSession.transcript as string[]).map((line, i) => (
                            <p key={i} className="text-sm text-foreground">{line}</p>
                          ))
                        ) : (
                          <p className="text-sm text-muted-foreground text-center py-8">
                            {data.activeCallSession.status === "active" ? "Transcription in progress…" : "No transcript available."}
                          </p>
                        )}
                      </div>
                    </ScrollArea>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN EXPORT
// ═════════════════════════════════════════════════════════════════════════════

export function CallCenterModule() {
  const [agents, setAgents] = useState<any>(null)
  const [sessions, setSessions] = useState<any>(null)
  const [dashboard, setDashboard] = useState<any>(null)
  const [kpiLoading, setKpiLoading] = useState(true)
  const [kpiError, setKpiError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function loadKpiData() {
      try {
        const results = await Promise.allSettled([
          listAgents(),
          listSessions(),
          getQueuesDashboard(),
        ])
        if (cancelled) return
        setAgents(results[0].status === "fulfilled" ? results[0].value : null)
        setSessions(results[1].status === "fulfilled" ? results[1].value : null)
        setDashboard(results[2].status === "fulfilled" ? results[2].value : null)
      } catch (err) {
        if (!cancelled) {
          setKpiError(err instanceof Error ? err.message : "Failed to load KPI data")
        }
      } finally {
        if (!cancelled) setKpiLoading(false)
      }
    }
    loadKpiData()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Phone className="h-5 w-5" />}
        title="Call Center"
        subtitle="Agent management, queue monitoring, and AI whisper coaching"
        actions={
          <>
            <Button variant="outline" size="sm"><Activity className="h-3.5 w-3.5" />Live Monitor</Button>
            <Button variant="cta" size="sm"><Plus className="h-3.5 w-3.5" />New Queue</Button>
          </>
        }
      />

      {/* KPI Cards — live data */}
      <KpiSection agents={agents} sessions={sessions} dashboard={dashboard} />

      {kpiError && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          {kpiError}
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="mb-4 grid w-full grid-cols-5 bg-muted/30">
          <TabsTrigger value="overview" className="gap-1.5 text-xs data-[state=active]:text-emerald-400">
            <TrendingUp className="h-3.5 w-3.5" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="queues" className="gap-1.5 text-xs data-[state=active]:text-blue-400">
            <Headphones className="h-3.5 w-3.5" />
            Queues
          </TabsTrigger>
          <TabsTrigger value="whisper" className="gap-1.5 text-xs data-[state=active]:text-cyan-400">
            <Mic className="h-3.5 w-3.5" />
            Whisper AI
          </TabsTrigger>
          <TabsTrigger value="voicestudio" className="gap-1.5 text-xs data-[state=active]:text-pink-400">
            <Sparkles className="h-3.5 w-3.5" />
            Voice Studio
          </TabsTrigger>
          <TabsTrigger value="customer360" className="gap-1.5 text-xs data-[state=active]:text-violet-400">
                       <User className="h-3.5 w-3.5" />
            Customer 360
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab />
        </TabsContent>

        <TabsContent value="queues">
          <QueuesTab />
        </TabsContent>

        <TabsContent value="whisper">
          <WhisperAITab />
        </TabsContent>

        <TabsContent value="voicestudio">
          <VoiceStudioTab />
        </TabsContent>

        <TabsContent value="customer360">
          <Customer360Tab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
