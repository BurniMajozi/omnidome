"use client"

import { useEffect, useState, useCallback, useMemo } from "react"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area,
} from "recharts"
import {
  Users, TrendingUp, TrendingDown, AlertTriangle, DollarSign,
  ArrowRight, Filter, Activity, Target, RefreshCw, ChevronRight,
  UserPlus, UserMinus, Zap, Layers, CheckCircle2,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { lifecycleApi } from "@/lib/lifecycle-api"
import type {
  DashboardData, CustomerLifecycle, LifecycleEvent, LifecycleStage, FunnelData,
} from "@/lib/lifecycle-api"
import { salesApi, type LeadFunnelResponse } from "@/lib/sales-api"
import { TraditionalFunnel, type FunnelTierData } from "@/components/modules/sales/traditional-funnel"
import { supabase, getSessionSafe } from "@/lib/supabase/client"

const COLORS = ["#4ade80", "#60a5fa", "#a855f7", "#f97316", "#ef4444", "#14b8a6", "#eab308", "#ec4899", "#8b5cf6"]

const STAGE_COLORS: Record<string, string> = {
  "Lead": "#94a3b8",
  "Qualified": "#60a5fa",
  "Proposal": "#a855f7",
  "Converted": "#4ade80",
  "Onboarding": "#38bdf8",
  "Active": "#4ade80",
  "At Risk": "#f97316",
  "Churned": "#ef4444",
  "Reactivated": "#14b8a6",
}

const CHANNEL_COLORS: Record<string, string> = {
  MARKETING: "#e03131",
  INBOUND_EMAIL: "#60a5fa",
  CALL_CENTER_INBOUND: "#34d399",
  CALL_CENTER_OUTBOUND: "#fbbf24",
  PORTAL_WEBSITE: "#a78bfa",
  FIELD_SALES: "#f87171",
  WALK_IN: "#38bdf8",
  REFERRAL: "#ec4899",
  COMPANY_SEARCH: "#14b8a6",
  TENDER: "#f59e0b",
  OTHER: "#94a3b8",
}

const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"

function formatZAR(n: number): string {
  return `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

// ---------------------------------------------------------------------------
// KPICard
// ---------------------------------------------------------------------------
function KPICard({ title, value, subtext, icon, color }: {
  title: string; value: string; subtext?: string; icon: React.ReactNode; color: string
}) {
  return (
    <Card className="border-border bg-card">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="rounded-lg p-2" style={{ backgroundColor: `${color}20` }}>{icon}</div>
        </div>
        <div className="mt-3">
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold text-foreground">{value}</p>
          {subtext && <p className="text-xs text-muted-foreground mt-1">{subtext}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------
export function LifecycleDashboard() {
  const [tenantId, setTenantId] = useState(FALLBACK_TENANT_ID)
  const [tab, setTab] = useState("overview")
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [lifecycles, setLifecycles] = useState<CustomerLifecycle[]>([])
  const [events, setEvents] = useState<LifecycleEvent[]>([])
  const [stages, setStages] = useState<LifecycleStage[]>([])
  const [salesFunnel, setSalesFunnel] = useState<LeadFunnelResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [filterStage, setFilterStage] = useState<string>("all")
  const [days, setDays] = useState(30)

  // Resolve tenant ID from Supabase session (falls back to dev default)
  useEffect(() => {
    const resolve = (session: Parameters<Parameters<typeof supabase.auth.onAuthStateChange>[0]>[1]) => {
      setTenantId(
        session?.user?.user_metadata?.tenant_id ??
        session?.user?.app_metadata?.tenant_id ??
        FALLBACK_TENANT_ID
      )
    }
    getSessionSafe().then(({ data }) => resolve(data.session))
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => resolve(session))
    return () => listener.subscription.unsubscribe()
  }, [])

  const loadData = useCallback(async () => {
    const safe = <T,>(p: Promise<T>) => p.catch((): null => null)
    setLoading(true)
    const [dashData, lcData, evData, stData, funnelData] = await Promise.all([
      safe(lifecycleApi.getDashboard(tenantId, days)),
      safe(lifecycleApi.listLifecycles(tenantId, {
        stage: filterStage === "all" ? undefined : filterStage,
        page_size: 50,
      })),
      safe(lifecycleApi.listEvents(tenantId, undefined, 20)),
      safe(lifecycleApi.ensureStages(tenantId)),
      safe(salesApi.getLeadFunnel({ days })),
    ])
    if (dashData) setDashboard(dashData)
    setLifecycles(lcData?.lifecycles ?? [])
    setEvents(evData?.events ?? [])
    setStages(stData?.stages ?? [])
    if (funnelData) setSalesFunnel(funnelData)
    setLoading(false)
  }, [tenantId, days, filterStage])

  useEffect(() => { loadData() }, [loadData])

  if (loading && !dashboard) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Activity className="h-5 w-5 animate-spin" />
          <span>Loading lifecycle data...</span>
        </div>
      </div>
    )
  }

  // Prepare chart data
  const stageChartData = dashboard ? Object.entries(dashboard.stages).map(([name, data]) => ({
    name,
    count: data.count,
    mrr: data.mrr,
    fill: STAGE_COLORS[name] || "#888",
  })) : []

  const riskData = dashboard ? [
    { name: "Active", value: (dashboard.revenue.active_customers || 0) - (dashboard.risk.at_risk_count || 0), fill: "#4ade80" },
    { name: "At Risk", value: dashboard.risk.at_risk_count || 0, fill: "#f97316" },
  ] : []

  // Traditional Inverted Funnel Tiers (Top leads -> Mid pipeline -> Closing -> Won)
  const funnelTiers: FunnelTierData[] = useMemo(() => {
    // If salesFunnel data is available, compute tiers matching channels
    if (salesFunnel && salesFunnel.overall_funnel && salesFunnel.overall_funnel.length > 0) {
      const stages = salesFunnel.overall_funnel
      const countFor = (stageNames: string[]) =>
        stages
          .filter((s) => stageNames.includes(s.stage))
          .reduce((sum, s) => sum + s.count, 0)

      const valFor = (stageNames: string[]) =>
        stages
          .filter((s) => stageNames.includes(s.stage))
          .reduce((sum, s) => sum + (Number(s.value_zar) || 0), 0)

      const topCount = countFor(["NEW", "CONTACTED"])
      const midCount = countFor(["QUALIFIED", "Prospecting"])
      const closeCount = countFor(["Proposal", "Negotiation"])
      const wonCount = Math.max(
        salesFunnel.totals?.won_leads || countFor(["Closed Won"]),
        dashboard?.revenue?.active_customers || 0
      )
      const wonVal = Math.max(
        Number(salesFunnel.totals?.won_value_zar) || 0,
        dashboard?.revenue?.total_mrr ? dashboard.revenue.total_mrr * 12 : 0
      )

      const total = topCount + midCount + closeCount + wonCount || 1

      const getChannelSegmentsFor = (stageNames: string[], tierTotal: number) => {
        if (!salesFunnel.channels) return []
        return salesFunnel.channels
          .map((ch) => {
            const chCount = stageNames.reduce(
              (sum, st) => sum + (ch.stage_counts?.[st] || 0),
              0
            )
            const color = CHANNEL_COLORS[ch.channel] || "#94a3b8"
            return {
              channel: ch.channel,
              label: ch.channel_label || ch.channel,
              count: chCount,
              color,
              pctOfTier: tierTotal > 0 ? Math.round((chCount / tierTotal) * 100) : 0,
            }
          })
          .filter((seg) => seg.count > 0)
          .sort((a, b) => b.count - a.count)
      }

      return [
        {
          id: "top-tier",
          name: "Top of Funnel: Captured Inbound Leads",
          stageCategory: "top",
          count: topCount,
          valueZar: valFor(["NEW", "CONTACTED"]),
          pctOfTotal: Math.round((topCount / total) * 100),
          description: "Raw prospects sitting in NEW or Contacted stages awaiting discovery and warming",
          channels: getChannelSegmentsFor(["NEW", "CONTACTED"], topCount),
        },
        {
          id: "mid-tier",
          name: "Mid Funnel: Qualified Pipeline in Progress",
          stageCategory: "mid",
          count: midCount,
          valueZar: valFor(["QUALIFIED", "Prospecting"]),
          pctOfTotal: Math.round((midCount / total) * 100),
          conversionFromPrev: topCount > 0 ? Math.round((midCount / topCount) * 100) : 0,
          description: "Qualified opportunities being actively worked on by field agents and telesales",
          channels: getChannelSegmentsFor(["QUALIFIED", "Prospecting"], midCount),
        },
        {
          id: "closing-tier",
          name: "Decision Stage: Proposals & Negotiations",
          stageCategory: "closing",
          count: closeCount,
          valueZar: valFor(["Proposal", "Negotiation"]),
          pctOfTotal: Math.round((closeCount / total) * 100),
          conversionFromPrev: midCount > 0 ? Math.round((closeCount / midCount) * 100) : 0,
          description: "Formal packages quoted, SLA evaluations, and pricing terms under review",
          channels: getChannelSegmentsFor(["Proposal", "Negotiation"], closeCount),
        },
        {
          id: "won-tier",
          name: "Bottom of Funnel: Won & Active Subscribers",
          stageCategory: "won",
          count: wonCount,
          valueZar: wonVal,
          pctOfTotal: Math.round((wonCount / total) * 100),
          conversionFromPrev: closeCount > 0 ? Math.round((wonCount / closeCount) * 100) : (total > 0 ? Math.round((wonCount / total) * 100) : 0),
          description: "Signed contracts provisioned as live active subscribers",
          channels: getChannelSegmentsFor(["Closed Won"], wonCount),
        },
      ]
    }

    // Fallback: build tiers from dashboard.stages
    const leadCount = dashboard?.stages?.Lead?.count || 0
    const qualCount = dashboard?.stages?.Qualified?.count || 0
    const propCount = dashboard?.stages?.Proposal?.count || 0
    const activeCount = (dashboard?.stages?.Active?.count || 0) + (dashboard?.stages?.Converted?.count || 0)
    const total = leadCount + qualCount + propCount + activeCount || 1

    return [
      {
        id: "top-tier",
        name: "Top of Funnel: Captured Inbound Leads",
        stageCategory: "top",
        count: leadCount,
        valueZar: dashboard?.stages?.Lead?.mrr || 0,
        pctOfTotal: Math.round((leadCount / total) * 100),
        description: "Prospects entered through campaigns, inbound, referral & partners",
        channels: [],
      },
      {
        id: "mid-tier",
        name: "Mid Funnel: Qualified Pipeline in Progress",
        stageCategory: "mid",
        count: qualCount,
        valueZar: dashboard?.stages?.Qualified?.mrr || 0,
        pctOfTotal: Math.round((qualCount / total) * 100),
        conversionFromPrev: leadCount > 0 ? Math.round((qualCount / leadCount) * 100) : 0,
        description: "Opportunities with verified coverage, budget, and authority",
        channels: [],
      },
      {
        id: "closing-tier",
        name: "Decision Stage: Proposals & Pricing",
        stageCategory: "closing",
        count: propCount,
        valueZar: dashboard?.stages?.Proposal?.mrr || 0,
        pctOfTotal: Math.round((propCount / total) * 100),
        conversionFromPrev: qualCount > 0 ? Math.round((propCount / qualCount) * 100) : 0,
        description: "Formal proposals out with prospective clients",
        channels: [],
      },
      {
        id: "won-tier",
        name: "Bottom of Funnel: Active Subscribers",
        stageCategory: "won",
        count: activeCount,
        valueZar: dashboard?.revenue?.total_mrr || 0,
        pctOfTotal: Math.round((activeCount / total) * 100),
        conversionFromPrev: propCount > 0 ? Math.round((activeCount / propCount) * 100) : 0,
        description: "Active subscribers deployed and generating MRR",
        channels: [],
      },
    ]
  }, [salesFunnel, dashboard])

  const stageList = [
    "Lead", "Qualified", "Proposal", "Converted", "Onboarding",
    "Active", "At Risk", "Churned", "Reactivated",
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Customer Lifecycle Pipeline</h2>
          <Badge variant="outline" className="text-xs">
            Lead → Active → Churn
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-2.5 py-0.5 text-xs rounded-md transition-colors ${
                  days === d
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-muted-foreground hover:text-foreground"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={loadData}>
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      {dashboard && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <KPICard
            title="Active Customers"
            value={String(dashboard.revenue.active_customers || 0)}
            subtext="Non-churned"
            icon={<Users className="h-5 w-5" />}
            color="#4ade80"
          />
          <KPICard
            title="Total MRR"
            value={formatZAR(dashboard.revenue.total_mrr)}
            subtext="Monthly recurring"
            icon={<DollarSign className="h-5 w-5" />}
            color="#60a5fa"
          />
          <KPICard
            title="At Risk"
            value={String(dashboard.risk.at_risk_count || 0)}
            subtext={`Avg churn prob: ${(dashboard.risk.avg_churn_probability * 100).toFixed(0)}%`}
            icon={<AlertTriangle className="h-5 w-5" />}
            color="#f97316"
          />
          <KPICard
            title="Total Events"
            value={String(events.length)}
            subtext="Recent transitions"
            icon={<Activity className="h-5 w-5" />}
            color="#a855f7"
          />
          <KPICard
            title="Avg Health"
            value={`${(Object.values(dashboard.stages).reduce((s, d) => s + d.avg_health * d.count, 0) / Math.max(1, Object.values(dashboard.stages).reduce((s, d) => s + d.count, 0))).toFixed(0)}%`}
            subtext="Across all stages"
            icon={<Zap className="h-5 w-5" />}
            color="#14b8a6"
          />
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="funnel">Funnel</TabsTrigger>
          <TabsTrigger value="customers">Customers</TabsTrigger>
          <TabsTrigger value="events">Activity Feed</TabsTrigger>
        </TabsList>

        {/* --- OVERVIEW TAB --- */}
        <TabsContent value="overview" className="space-y-6 mt-4">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Stage Distribution */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Users className="h-4 w-4 text-blue-400" />
                  Customers by Stage
                </CardTitle>
              </CardHeader>
              <CardContent>
                {stageChartData.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">No data yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={stageChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis dataKey="name" stroke="#888" fontSize={10} />
                      <YAxis stroke="#888" fontSize={10} />
                      <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {stageChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Risk Distribution */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                  Risk Distribution
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={riskData}
                      cx="50%" cy="50%"
                      innerRadius={50} outerRadius={90}
                      paddingAngle={5}
                      dataKey="value"
                      label={({ name, value }) => `${name}: ${value}`}
                    >
                      {riskData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* MRR by Stage */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <DollarSign className="h-4 w-4 text-emerald-400" />
                  MRR by Stage
                </CardTitle>
              </CardHeader>
              <CardContent>
                {stageChartData.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">No data yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={stageChartData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis type="number" stroke="#888" fontSize={10} tickFormatter={(v) => `R${(v/1000).toFixed(0)}K`} />
                      <YAxis dataKey="name" type="category" stroke="#888" fontSize={10} width={80} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                        formatter={(value: number) => [formatZAR(value), "MRR"]}
                      />
                      <Bar dataKey="mrr" radius={[0, 4, 4, 0]}>
                        {stageChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Recent Activity */}
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Activity className="h-4 w-4 text-violet-400" />
                  Recent Transitions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="max-h-[280px] space-y-2 overflow-y-auto">
                  {events.slice(0, 10).map((ev) => (
                    <div key={ev.id} className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-2.5">
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/20">
                        {ev.to_stage === "Churned" ? (
                          <UserMinus className="h-3 w-3 text-red-400" />
                        ) : ev.to_stage === "Converted" ? (
                          <UserPlus className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <ChevronRight className="h-3 w-3 text-blue-400" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-foreground truncate">
                          {ev.from_stage ? `${ev.from_stage} → ` : ""}{ev.to_stage}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {ev.trigger_source} {ev.reason ? `• ${ev.reason}` : ""}
                        </p>
                      </div>
                      {ev.created_at && (
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {new Date(ev.created_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short" })}
                        </span>
                      )}
                    </div>
                  ))}
                  {events.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-8">No transitions yet</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* --- FUNNEL TAB --- */}
        <TabsContent value="funnel" className="space-y-6 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* ── Left Side: Customer Lifecycle Progression & Journey Graph (6 cols) ── */}
            <div className="lg:col-span-6 space-y-4">
              <Card className="border-border bg-card shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base font-bold flex items-center gap-2">
                        <Target className="h-5 w-5 text-primary" />
                        Customer Lifecycle Journey
                      </CardTitle>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Progression from acquisition &rarr; conversion &rarr; retention &rarr; risk management
                      </p>
                    </div>
                    <Badge variant="outline" className="text-xs font-mono border-emerald-500/30 text-emerald-400">
                      {dashboard?.revenue?.active_customers ?? 0} Live Subscribers
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Journey Phase Flow Header */}
                  <div className="p-3 rounded-xl border border-border/80 bg-secondary/20">
                    <div className="flex items-center justify-between gap-1 overflow-x-auto text-[11px] font-medium text-muted-foreground pb-1">
                      <div className="flex items-center gap-1 text-blue-400 shrink-0">
                        <UserPlus className="h-3.5 w-3.5" />
                        <span>Acquisition</span>
                      </div>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                      <div className="flex items-center gap-1 text-purple-400 shrink-0">
                        <TrendingUp className="h-3.5 w-3.5" />
                        <span>Conversion</span>
                      </div>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                      <div className="flex items-center gap-1 text-emerald-400 shrink-0">
                        <Users className="h-3.5 w-3.5" />
                        <span>Retention</span>
                      </div>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                      <div className="flex items-center gap-1 text-amber-400 shrink-0">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        <span>Risk</span>
                      </div>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/60 shrink-0" />
                      <div className="flex items-center gap-1 text-red-400 shrink-0">
                        <UserMinus className="h-3.5 w-3.5" />
                        <span>Churn</span>
                      </div>
                    </div>
                  </div>

                  {/* Lifecycle Phase Milestones */}
                  <div className="space-y-2.5">
                    {/* Phase 1: Acquisition */}
                    <div className="p-3 rounded-xl border border-blue-500/20 bg-blue-950/10 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-blue-500/20 flex items-center justify-center text-blue-400 font-bold text-xs">
                          1
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            Acquisition Phase
                            <Badge variant="outline" className="text-[10px] border-blue-500/30 text-blue-400">
                              Lead & Qualified
                            </Badge>
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Capturing inbound interest, discovery calls & qualification
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-base font-bold text-blue-400 font-mono">
                          {(dashboard?.stages?.Lead?.count || 0) + (dashboard?.stages?.Qualified?.count || 0)} accounts
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {formatZAR((dashboard?.stages?.Lead?.mrr || 0) + (dashboard?.stages?.Qualified?.mrr || 0))} pipeline
                        </p>
                      </div>
                    </div>

                    {/* Phase 2: Conversion */}
                    <div className="p-3 rounded-xl border border-purple-500/20 bg-purple-950/10 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400 font-bold text-xs">
                          2
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            Conversion Phase
                            <Badge variant="outline" className="text-[10px] border-purple-500/30 text-purple-400">
                              Proposal & Converted
                            </Badge>
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Formal pricing proposals, negotiation & agreement sign-off
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-base font-bold text-purple-400 font-mono">
                          {(dashboard?.stages?.Proposal?.count || 0) + (dashboard?.stages?.Converted?.count || 0)} accounts
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {formatZAR(dashboard?.stages?.Proposal?.mrr || 0)} value
                        </p>
                      </div>
                    </div>

                    {/* Phase 3: Retention & Service Delivery */}
                    <div className="p-3 rounded-xl border border-emerald-500/20 bg-emerald-950/10 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold text-xs">
                          3
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            Retention & Value Phase
                            <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-400">
                              Active & Onboarding
                            </Badge>
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Live operational billing, continuous SLA & high health
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-base font-bold text-emerald-400 font-mono">
                          {dashboard?.revenue?.active_customers ?? (dashboard?.stages?.Active?.count || 0)} active
                        </p>
                        <p className="text-[10px] text-emerald-400/80 font-medium">
                          {formatZAR(dashboard?.revenue?.total_mrr || 0)} MRR
                        </p>
                      </div>
                    </div>

                    {/* Phase 4: Risk Mitigation */}
                    <div className="p-3 rounded-xl border border-amber-500/20 bg-amber-950/10 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-lg bg-amber-500/20 flex items-center justify-center text-amber-400 font-bold text-xs">
                          4
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                            Risk Assessment
                            <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-400">
                              At Risk Monitoring
                            </Badge>
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Early churn signals, ticket escalations & intervention
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-base font-bold text-amber-400 font-mono">
                          {dashboard?.risk?.at_risk_count || 0} at risk
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {((dashboard?.risk?.avg_churn_probability || 0) * 100).toFixed(0)}% avg churn prob
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Individual Stage Grid */}
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-2">Stage Breakdown</p>
                    <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                      {stageList.map((stageName) => {
                        const data = dashboard?.stages[stageName]
                        const count = data?.count || 0
                        const mrr = data?.mrr || 0
                        const color = STAGE_COLORS[stageName] || "#888"

                        return (
                          <div
                            key={stageName}
                            className="flex flex-col items-center rounded-xl border border-border bg-secondary/30 p-2.5 text-center transition-all hover:bg-secondary/50"
                            style={{ borderColor: `${color}35` }}
                          >
                            <div className="h-2 w-2 rounded-full mb-1" style={{ backgroundColor: color }} />
                            <p className="text-[11px] font-medium text-foreground truncate w-full">{stageName}</p>
                            <p className="text-base font-bold font-mono" style={{ color }}>{count}</p>
                            {mrr > 0 ? (
                              <p className="text-[10px] text-muted-foreground font-mono">{formatZAR(mrr)}</p>
                            ) : (
                              <p className="text-[10px] text-muted-foreground/60">—</p>
                            )}
                            <Badge
                              variant="outline"
                              className="mt-1 text-[9px] px-1 py-0"
                              style={{ borderColor: `${color}50`, color }}
                            >
                              {data ? `${data.avg_health.toFixed(0)}%` : "—"}
                            </Badge>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* ── Right Side: Traditional Inverted Funnel (6 cols) ── */}
            <div className="lg:col-span-6 space-y-4">
              <Card className="border-border bg-card shadow-sm">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base font-bold flex items-center gap-2">
                        <Layers className="h-5 w-5 text-emerald-400" />
                        Pipeline & Deal Funnel
                      </CardTitle>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Traditional inverted funnel: Inbound leads &rarr; active pipeline &rarr; closed won subscribers
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge variant="outline" className="text-xs font-mono border-emerald-500/30 text-emerald-400">
                        {salesFunnel?.totals?.total_leads ?? (dashboard ? Object.values(dashboard.stages).reduce((s, d) => s + d.count, 0) : 36)} Leads
                      </Badge>
                      <Badge variant="outline" className="text-xs font-mono border-purple-500/30 text-purple-400">
                        {formatZAR(Number(salesFunnel?.totals?.total_pipeline_value_zar) || (dashboard?.stages?.Qualified?.mrr || 0) + (dashboard?.stages?.Proposal?.mrr || 0))} Pipeline
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-2">
                  <TraditionalFunnel
                    tiers={funnelTiers}
                    totalLeads={salesFunnel?.totals?.total_leads ?? (dashboard ? Object.values(dashboard.stages).reduce((s, d) => s + d.count, 0) : 36)}
                    totalPipelineZar={Number(salesFunnel?.totals?.total_pipeline_value_zar) || (dashboard?.stages?.Qualified?.mrr || 0) + (dashboard?.stages?.Proposal?.mrr || 0)}
                    wonLeads={Math.max(salesFunnel?.totals?.won_leads || 0, dashboard?.revenue?.active_customers || 0)}
                    wonRevenueZar={Math.max(Number(salesFunnel?.totals?.won_value_zar) || 0, dashboard?.revenue?.total_mrr || 0)}
                  />
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* --- CUSTOMERS TAB --- */}
        <TabsContent value="customers" className="space-y-4 mt-4">
          {/* Stage filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Filter:</span>
            <button
              onClick={() => setFilterStage("all")}
              className={`px-2 py-0.5 text-xs rounded-md ${filterStage === "all" ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"}`}
            >
              All
            </button>
            {stageList.map((s) => (
              <button
                key={s}
                onClick={() => setFilterStage(s)}
                className={`px-2 py-0.5 text-xs rounded-md ${filterStage === s ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground"}`}
                style={filterStage === s ? { backgroundColor: STAGE_COLORS[s] } : {}}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Customer list */}
          <Card className="border-border bg-card">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[800px] text-sm">
                  <thead>
                    <tr className="border-b border-border bg-secondary/50">
                      <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Customer</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Stage</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Health</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">MRR</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Plan</th>
                      <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Risk</th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lifecycles.map((lc) => (
                      <tr key={lc.id} className="border-b border-border/50 hover:bg-secondary/20">
                        <td className="px-3 py-2 text-foreground font-mono text-xs">{lc.customer_id.slice(0, 8)}...</td>
                        <td className="px-3 py-2">
                          <Badge
                            className="text-xs"
                            style={{
                              backgroundColor: `${STAGE_COLORS[lc.current_stage] || "#888"}20`,
                              color: STAGE_COLORS[lc.current_stage] || "#888",
                              borderColor: `${STAGE_COLORS[lc.current_stage] || "#888"}40`,
                            }}
                          >
                            {lc.current_stage}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Badge className={`text-xs ${
                            lc.health_score >= 70 ? "bg-emerald-500/20 text-emerald-400" :
                            lc.health_score >= 40 ? "bg-amber-500/20 text-amber-400" :
                            "bg-red-500/20 text-red-400"
                          }`}>
                            {lc.health_score}%
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right text-foreground">{formatZAR(lc.monthly_recurring_revenue)}</td>
                        <td className="px-3 py-2 text-muted-foreground text-xs">{lc.current_plan || "—"}</td>
                        <td className="px-3 py-2">
                          {lc.is_at_risk ? (
                            <Badge className="bg-red-500/20 text-red-400 text-xs">
                              {lc.churn_probability ? `${(lc.churn_probability * 100).toFixed(0)}%` : "High"}
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                          {lc.updated_at ? new Date(lc.updated_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short" }) : "—"}
                        </td>
                      </tr>
                    ))}
                    {lifecycles.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                          No lifecycle records yet. They&apos;re created when deals close or customers transition.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- ACTIVITY TAB --- */}
        <TabsContent value="events" className="space-y-4 mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Lifecycle Activity Feed</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-[500px] space-y-2 overflow-y-auto">
                {events.map((ev) => (
                  <div key={ev.id} className="flex items-start gap-3 rounded-lg border border-border bg-secondary/30 p-3">
                    <div className={`flex h-8 w-8 items-center justify-center rounded-full ${
                      ev.to_stage === "Churned" ? "bg-red-500/20" :
                      ev.to_stage === "Converted" ? "bg-emerald-500/20" :
                      ev.to_stage === "At Risk" ? "bg-amber-500/20" :
                      "bg-blue-500/20"
                    }`}>
                      {ev.to_stage === "Churned" ? (
                        <UserMinus className="h-4 w-4 text-red-400" />
                      ) : ev.to_stage === "Converted" ? (
                        <UserPlus className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-blue-400" />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">
                          {ev.from_stage ? `${ev.from_stage} → ` : ""}{ev.to_stage}
                        </span>
                        <Badge variant="outline" className="text-xs">{ev.trigger_source}</Badge>
                      </div>
                      {ev.reason && <p className="text-xs text-muted-foreground mt-0.5">{ev.reason}</p>}
                      <p className="text-xs text-muted-foreground mt-1">
                        Customer: {ev.customer_id.slice(0, 8)}...
                        {ev.created_at && ` • ${new Date(ev.created_at).toLocaleString("en-ZA")}`}
                      </p>
                    </div>
                  </div>
                ))}
                {events.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">No activity yet</p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
