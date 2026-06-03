"use client"

import { useState, useCallback, useEffect } from "react"
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"
import {
  Eye, Users, MousePointerClick, Clock, Globe, Smartphone,
  Monitor, Tablet, TrendingUp, TrendingDown, Activity, BarChart3,
  FileText, Save, Trash2, Edit3, Plus, Layout, Settings,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { analyticsApi } from "@/lib/analytics/api"
import type {
  OverviewData, TrafficPoint, PageStat, DeviceData,
} from "@/lib/analytics/api"

const COLORS = ["#4ade80", "#60a5fa", "#a855f7", "#f97316", "#ef4444", "#14b8a6", "#eab308", "#ec4899"]

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

function formatNumber(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return n.toLocaleString()
}

// ── Types ─────────────────────────────────────────────────────────────

interface DashboardWidget {
  id: string
  type: "kpi" | "traffic" | "pages" | "devices" | "trend" | "custom"
  title: string
  visible: boolean
}

interface SavedDashboard {
  id: string
  name: string
  widgets: DashboardWidget[]
  dateRange: number
  createdAt: string
}

const DEFAULT_WIDGETS: DashboardWidget[] = [
  { id: "kpi-overview", type: "kpi", title: "Key Metrics", visible: true },
  { id: "traffic-chart", type: "traffic", title: "Traffic Over Time", visible: true },
  { id: "top-pages", type: "pages", title: "Top Pages", visible: true },
  { id: "device-breakdown", type: "devices", title: "Devices & Browsers", visible: true },
  { id: "trend-chart", type: "trend", title: "Engagement Trend", visible: true },
]

// ── Main Component ───────────────────────────────────────────────────

export function WebAnalyticsCustomDashboard() {
  const [days, setDays] = useState(30)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [traffic, setTraffic] = useState<TrafficPoint[]>([])
  const [pages, setPages] = useState<PageStat[]>([])
  const [devices, setDevices] = useState<DeviceData | null>(null)
  const [loading, setLoading] = useState(true)

  // Dashboard customization state
  const [widgets, setWidgets] = useState<DashboardWidget[]>(DEFAULT_WIDGETS)
  const [savedDashboards, setSavedDashboards] = useState<SavedDashboard[]>([])
  const [showCustomize, setShowCustomize] = useState(false)
  const [newDashboardName, setNewDashboardName] = useState("")
  const [editingWidget, setEditingWidget] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [ov, tr, pg, dv] = await Promise.all([
        analyticsApi.getOverview(days),
        analyticsApi.getTraffic(days),
        analyticsApi.getPages(days),
        analyticsApi.getDevices(days),
      ])
      setOverview(ov)
      setTraffic(tr)
      setPages(pg)
      setDevices(dv)
    } catch (err) {
      console.error("Failed to load analytics:", err)
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { loadData() }, [loadData])

  // Load saved dashboards from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("omnidome-dashboards")
      if (saved) setSavedDashboards(JSON.parse(saved))
    } catch { /* ignore */ }
  }, [])

  const saveDashboard = useCallback(() => {
    if (!newDashboardName.trim()) return
    const dashboard: SavedDashboard = {
      id: `dash-${Date.now()}`,
      name: newDashboardName.trim(),
      widgets: [...widgets],
      dateRange: days,
      createdAt: new Date().toISOString(),
    }
    const updated = [...savedDashboards, dashboard]
    setSavedDashboards(updated)
    localStorage.setItem("omnidome-dashboards", JSON.stringify(updated))
    setNewDashboardName("")
  }, [newDashboardName, widgets, days, savedDashboards])

  const loadDashboard = useCallback((dashboard: SavedDashboard) => {
    setWidgets(dashboard.widgets)
    setDays(dashboard.dateRange)
    setShowCustomize(false)
  }, [])

  const deleteDashboard = useCallback((id: string) => {
    const updated = savedDashboards.filter((d) => d.id !== id)
    setSavedDashboards(updated)
    localStorage.setItem("omnidome-dashboards", JSON.stringify(updated))
  }, [savedDashboards])

  const toggleWidget = useCallback((widgetId: string) => {
    setWidgets((prev) =>
      prev.map((w) => (w.id === widgetId ? { ...w, visible: !w.visible } : w))
    )
  }, [])

  const visibleWidgets = widgets.filter((w) => w.visible)

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Activity className="h-5 w-5 animate-spin" />
          <span>Loading dashboards...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layout className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Custom Dashboards</h2>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {[7, 14, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1 text-xs rounded-md transition-colors ${
                  days === d
                    ? "bg-primary text-primary-foreground"
                    : "bg-secondary text-muted-foreground hover:text-foreground"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <Dialog open={showCustomize} onOpenChange={setShowCustomize}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Settings className="mr-2 h-4 w-4" />
                Customize
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Customize Dashboard</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                {/* Widget toggles */}
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">Visible Widgets</Label>
                  {widgets.map((widget) => (
                    <div key={widget.id} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={widget.visible}
                          onChange={() => toggleWidget(widget.id)}
                          className="h-4 w-4 rounded border-border"
                        />
                        <span className="text-sm text-foreground">{widget.title}</span>
                      </div>
                      <Badge variant="outline" className="text-[10px]">{widget.type}</Badge>
                    </div>
                  ))}
                </div>

                {/* Save dashboard */}
                <div className="border-t border-border pt-4">
                  <Label className="text-xs text-muted-foreground">Save as Dashboard</Label>
                  <div className="flex gap-2 mt-1">
                    <Input
                      placeholder="Dashboard name..."
                      value={newDashboardName}
                      onChange={(e) => setNewDashboardName(e.target.value)}
                    />
                    <Button size="sm" onClick={saveDashboard} disabled={!newDashboardName.trim()}>
                      <Save className="mr-1.5 h-3.5 w-3.5" /> Save
                    </Button>
                  </div>
                </div>

                {/* Saved dashboards */}
                {savedDashboards.length > 0 && (
                  <div className="border-t border-border pt-4">
                    <Label className="text-xs text-muted-foreground">Saved Dashboards</Label>
                    <div className="space-y-2 mt-1">
                      {savedDashboards.map((dash) => (
                        <div key={dash.id} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 px-3 py-2">
                          <div>
                            <span className="text-sm text-foreground">{dash.name}</span>
                            <span className="text-xs text-muted-foreground ml-2">{dash.dateRange}d range</span>
                          </div>
                          <div className="flex gap-1">
                            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => loadDashboard(dash)}>
                              Load
                            </Button>
                            <Button variant="ghost" size="sm" className="h-7 px-2 text-red-400" onClick={() => deleteDashboard(dash.id)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Widgets grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* KPI Overview */}
        {visibleWidgets.find((w) => w.type === "kpi") && overview && (
          <Card className="border-border bg-card lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-emerald-400" />
                Key Metrics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                {[
                  { title: "Page Views", value: formatNumber(overview.total_pageviews), icon: <Eye className="h-5 w-5" />, color: "#4ade80" },
                  { title: "Unique Visitors", value: formatNumber(overview.unique_visitors), icon: <Users className="h-5 w-5" />, color: "#60a5fa" },
                  { title: "Sessions", value: formatNumber(overview.unique_sessions), icon: <MousePointerClick className="h-5 w-5" />, color: "#a855f7" },
                  { title: "Avg. Session", value: formatDuration(overview.avg_session_duration), icon: <Clock className="h-5 w-5" />, color: "#f97316" },
                  { title: "Bounce Rate", value: `${overview.bounce_rate}%`, icon: <TrendingDown className="h-5 w-5" />, color: "#ef4444" },
                ].map((kpi, i) => (
                  <div key={i} className="rounded-lg border border-border bg-secondary/30 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">{kpi.title}</span>
                      <div className="rounded-lg p-1.5" style={{ backgroundColor: `${kpi.color}20`, color: kpi.color }}>
                        {kpi.icon}
                      </div>
                    </div>
                    <p className="mt-2 text-xl font-bold text-foreground">{kpi.value}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Traffic over time */}
        {visibleWidgets.find((w) => w.type === "traffic") && (
          <Card className="border-border bg-card lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-emerald-400" />
                Traffic Over Time
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={traffic}>
                  <defs>
                    <linearGradient id="colorPV" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorUV" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="date" stroke="#888" fontSize={11} tickFormatter={(v: string) => v?.slice(5, 10) || ""} />
                  <YAxis stroke="#888" fontSize={11} tickFormatter={formatNumber} />
                  <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                  <Legend />
                  <Area type="monotone" dataKey="pageviews" stroke="#4ade80" fill="url(#colorPV)" name="Page Views" />
                  <Area type="monotone" dataKey="unique_visitors" stroke="#60a5fa" fill="url(#colorUV)" name="Unique Visitors" />
                  <Line type="monotone" dataKey="sessions" stroke="#a855f7" strokeWidth={2} dot={false} name="Sessions" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Top pages */}
        {visibleWidgets.find((w) => w.type === "pages") && (
          <Card className="border-border bg-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="h-4 w-4 text-blue-400" />
                Top Pages
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {pages.slice(0, 10).map((p, i) => {
                  const maxPV = pages[0]?.pageviews || 1
                  const pct = (p.pageviews / maxPV) * 100
                  return (
                    <div key={i} className="flex items-center gap-3">
                      <span className="text-xs font-mono text-muted-foreground w-6">#{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-foreground truncate">{p.path}</span>
                          <span className="text-xs text-muted-foreground ml-2">{formatNumber(p.pageviews)}</span>
                        </div>
                        <div className="mt-1 h-1.5 bg-secondary/30 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500/70 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    </div>
                  )
                })}
                {pages.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">No page data yet</p>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Devices */}
        {visibleWidgets.find((w) => w.type === "devices") && devices && (
          <Card className="border-border bg-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Smartphone className="h-4 w-4 text-violet-400" />
                Device Types
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={devices.devices} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={5} dataKey="count" nameKey="device">
                    {devices.devices.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}

        {/* Engagement trend — uses page load data */}
        {visibleWidgets.find((w) => w.type === "trend") && (
          <Card className="border-border bg-card lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Activity className="h-4 w-4 text-amber-400" />
                Engagement Overview
              </CardTitle>
              <CardDescription className="text-xs">Pages per session and average session depth</CardDescription>
            </CardHeader>
            <CardContent>
              {overview && (
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="rounded-lg border border-border bg-secondary/30 p-4 text-center">
                    <p className="text-xs text-muted-foreground">Pages / Session</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">
                      {overview.total_pageviews > 0 && overview.unique_sessions > 0
                        ? (overview.total_pageviews / overview.unique_sessions).toFixed(1)
                        : "0"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border bg-secondary/30 p-4 text-center">
                    <p className="text-xs text-muted-foreground">Avg. Session Duration</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">{formatDuration(overview.avg_session_duration)}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-secondary/30 p-4 text-center">
                    <p className="text-xs text-muted-foreground">Bounce Rate</p>
                    <p className="mt-1 text-2xl font-bold text-foreground">{overview.bounce_rate}%</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
