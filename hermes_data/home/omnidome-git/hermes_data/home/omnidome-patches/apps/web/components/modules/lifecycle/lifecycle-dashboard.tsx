"use client"

import { useEffect, useState, useCallback } from "react"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area,
} from "recharts"
import {
  Users, TrendingUp, TrendingDown, AlertTriangle, DollarSign,
  ArrowRight, Filter, Activity, Target, RefreshCw, ChevronRight,
  UserPlus, UserMinus, Zap,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { lifecycleApi } from "@/lib/lifecycle-api"
import type {
  DashboardData, CustomerLifecycle, LifecycleEvent, LifecycleStage, FunnelData,
} from "@/lib/lifecycle-api"

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

const TENANT_ID = "00000000-0000-0000-0000-000000000001" // TODO: from auth context

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
  const [tab, setTab] = useState("overview")
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [lifecycles, setLifecycles] = useState<CustomerLifecycle[]>([])
  const [events, setEvents] = useState<LifecycleEvent[]>([])
  const [stages, setStages] = useState<LifecycleStage[]>([])
  const [loading, setLoading] = useState(true)
  const [filterStage, setFilterStage] = useState<string>("all")
  const [days, setDays] = useState(30)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [dashData, lcData, evData, stData] = await Promise.all([
        lifecycleApi.getDashboard(TENANT_ID, days),
        lifecycleApi.listLifecycles(TENANT_ID, {
          stage: filterStage === "all" ? undefined : filterStage,
          page_size: 50,
        }),
        lifecycleApi.listEvents(TENANT_ID, undefined, 20),
        lifecycleApi.ensureStages(TENANT_ID),
      ])
      setDashboard(dashData)
      setLifecycles(lcData.lifecycles || [])
      setEvents(evData.events || [])
      setStages(stData.stages || [])
    } catch (err) {
      console.error("Failed to load lifecycle data:", err)
    } finally {
      setLoading(false)
    }
  }, [days, filterStage])

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
            value={`${Object.values(dashboard.stages).reduce((s, d) => s + d.avg_health * d.count, 0) / Math.max(1, Object.values(dashboard.stages).reduce((s, d) => s + d.count, 0)).toFixed(0)}%`}
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
          {/* Visual stage pipeline */}
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="h-4 w-4 text-primary" />
                Lifecycle Funnel
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {stageList.filter(s => {
                  if (!dashboard) return true
                  const data = dashboard.stages[s]
                  return !data || data.count > 0 || s === "Active"
                }).map((stageName) => {
                  const data = dashboard?.stages[stageName]
                  const count = data?.count || 0
                  const mrr = data?.mrr || 0
                  const color = STAGE_COLORS[stageName] || "#888"

                  return (
                    <div
                      key={stageName}
                      className="flex flex-col items-center rounded-xl border border-border bg-secondary/30 p-3 min-w-[100px]"
                      style={{ borderColor: `${color}40` }}
                    >
                      <div className="h-3 w-3 rounded-full mb-2" style={{ backgroundColor: color }} />
                      <p className="text-sm font-medium text-foreground">{stageName}</p>
                      <p className="text-lg font-bold" style={{ color }}>{count}</p>
                      <p className="text-xs text-muted-foreground">{formatZAR(mrr)}</p>
                      <Badge
                        variant="outline"
                        className="mt-1 text-xs"
                        style={{ borderColor: `${color}60`, color }}
                      >
                        {data ? `${data.avg_health.toFixed(0)}% health` : "—"}
                      </Badge>
                    </div>
                  )
                })}
              </div>

              {/* Stage connection arrows */}
              <div className="flex justify-center mt-4">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <UserPlus className="h-3 w-3" />
                  <span>Acquisition</span>
                  <ArrowRight className="h-3 w-3 mx-1" />
                  <TrendingUp className="h-3 w-3" />
                  <span>Conversion</span>
                  <ArrowRight className="h-3 w-3 mx-1" />
                  <Users className="h-3 w-3" />
                  <span>Retention</span>
                  <ArrowRight className="h-3 w-3 mx-1" />
                  <AlertTriangle className="h-3 w-3" />
                  <span>Risk</span>
                  <ArrowRight className="h-3 w-3 mx-1" />
                  <UserMinus className="h-3 w-3" />
                  <span>Churn</span>
                </div>
              </div>
            </CardContent>
          </Card>
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
