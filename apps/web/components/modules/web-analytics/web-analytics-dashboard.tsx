"use client"

import { useEffect, useState, useCallback } from "react"
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"
import {
  Eye, Users, MousePointerClick, Clock, Globe, Smartphone,
  Monitor, Tablet, TrendingUp, TrendingDown, Activity, BarChart3,
  FileText, ArrowUpRight, ArrowDownRight,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { analyticsApi } from "@/lib/analytics/api"
import type {
  OverviewData, TrafficPoint, PageStat, DeviceData, LocationData,
  FormsData, RealtimeData,
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

// --- KPI Card ---
function KPICard({ title, value, subtext, icon, color }: {
  title: string; value: string; subtext?: string; icon: React.ReactNode; color: string
}) {
  return (
    <Card className="border-border bg-card">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="rounded-lg bg-primary/10 p-2" style={{ backgroundColor: `${color}20` }}>{icon}</div>
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

export function WebAnalyticsDashboard() {
  const [days, setDays] = useState(30)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [traffic, setTraffic] = useState<TrafficPoint[]>([])
  const [pages, setPages] = useState<PageStat[]>([])
  const [devices, setDevices] = useState<DeviceData | null>(null)
  const [locations, setLocations] = useState<LocationData | null>(null)
  const [forms, setForms] = useState<FormsData | null>(null)
  const [realtime, setRealtime] = useState<RealtimeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState("overview")

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [ov, tr, pg, dv, loc, fm, rt] = await Promise.all([
        analyticsApi.getOverview(days),
        analyticsApi.getTraffic(days),
        analyticsApi.getPages(days),
        analyticsApi.getDevices(days),
        analyticsApi.getLocations(days),
        analyticsApi.getForms(days),
        analyticsApi.getRealtime(),
      ])
      setOverview(ov)
      setTraffic(tr)
      setPages(pg)
      setDevices(dv)
      setLocations(loc)
      setForms(fm)
      setRealtime(rt)
    } catch (err) {
      console.error("Failed to load analytics:", err)
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { loadData() }, [loadData])

  // Refresh realtime every 30s
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const rt = await analyticsApi.getRealtime()
        setRealtime(rt)
      } catch { /* silent */ }
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Activity className="h-5 w-5 animate-spin" />
          <span>Loading analytics...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Date range selector */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Website Analytics</h2>
          {realtime && (
            <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
              <span className="relative flex h-2 w-2 mr-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              {realtime.active_visitors} active now
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
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
      </div>

      {/* KPI Cards */}
      {overview && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <KPICard
            title="Page Views"
            value={formatNumber(overview.total_pageviews)}
            subtext={`${days} day period`}
            icon={<Eye className="h-5 w-5" />}
            color="#4ade80"
          />
          <KPICard
            title="Unique Visitors"
            value={formatNumber(overview.unique_visitors)}
            subtext="Distinct users"
            icon={<Users className="h-5 w-5" />}
            color="#60a5fa"
          />
          <KPICard
            title="Sessions"
            value={formatNumber(overview.unique_sessions)}
            subtext={`Bounce: ${overview.bounce_rate}%`}
            icon={<MousePointerClick className="h-5 w-5" />}
            color="#a855f7"
          />
          <KPICard
            title="Avg. Session"
            value={formatDuration(overview.avg_session_duration)}
            subtext="Duration"
            icon={<Clock className="h-5 w-5" />}
            color="#f97316"
          />
          <KPICard
            title="Pages / Session"
            value={overview.total_pageviews > 0 && overview.unique_sessions > 0
              ? (overview.total_pageviews / overview.unique_sessions).toFixed(1)
              : "0"
            }
            subtext="Avg. depth"
            icon={<Globe className="h-5 w-5" />}
            color="#14b8a6"
          />
        </div>
      )}

      {/* Tabs for different analytics views */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="overview">Traffic Overview</TabsTrigger>
          <TabsTrigger value="pages">Top Pages</TabsTrigger>
          <TabsTrigger value="devices">Devices & Browsers</TabsTrigger>
          <TabsTrigger value="locations">Locations</TabsTrigger>
          <TabsTrigger value="forms">Forms</TabsTrigger>
        </TabsList>

        {/* --- TRAFFIC OVERVIEW --- */}
        <TabsContent value="overview" className="space-y-6 mt-4">
          {/* Traffic over time */}
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
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
                  <YAxis stroke="#888" fontSize={11} tickFormatter={(v: number) => formatNumber(v)} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                    labelFormatter={(v: string) => v}
                    formatter={(value: number, name: string) => [
                      formatNumber(value),
                      name === "pageviews" ? "Page Views" : name === "unique_visitors" ? "Unique Visitors" : "Sessions",
                    ]}
                  />
                  <Legend />
                  <Area type="monotone" dataKey="pageviews" stroke="#4ade80" fillOpacity={1} fill="url(#colorPV)" name="Page Views" />
                  <Area type="monotone" dataKey="unique_visitors" stroke="#60a5fa" fillOpacity={1} fill="url(#colorUV)" name="Unique Visitors" />
                  <Line type="monotone" dataKey="sessions" stroke="#a855f7" strokeWidth={2} dot={false} name="Sessions" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Realtime active pages */}
          {realtime && realtime.top_pages.length > 0 && (
            <Card className="border-border bg-card">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Activity className="h-4 w-4 text-emerald-400" />
                  Active Pages (last 5 min)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2">
                  {realtime.top_pages.map((p, i) => (
                    <div key={i} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-muted-foreground w-6">#{i + 1}</span>
                        <span className="text-sm text-foreground font-mono">{p.path}</span>
                      </div>
                      <Badge className="bg-emerald-500/20 text-emerald-400">
                        {p.visitors} visitor{p.visitors !== 1 ? "s" : ""}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* --- TOP PAGES --- */}
        <TabsContent value="pages" className="space-y-6 mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-blue-400" />
                Most Visited Pages
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={Math.max(200, pages.length * 35)}>
                <BarChart data={pages} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis type="number" stroke="#888" fontSize={11} tickFormatter={formatNumber} />
                  <YAxis dataKey="title" type="category" stroke="#888" fontSize={11} width={180} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                    formatter={(value: number, name: string) => [
                      formatNumber(value),
                      name === "pageviews" ? "Page Views" : "Unique Visitors",
                    ]}
                  />
                  <Legend />
                  <Bar dataKey="pageviews" fill="#4ade80" name="Page Views" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="unique_visitors" fill="#60a5fa" name="Unique Visitors" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>

              {/* Pages table */}
              <div className="mt-4 overflow-x-auto rounded-lg border border-border">
                <table className="w-full min-w-[600px]">
                  <thead>
                    <tr className="border-b border-border bg-secondary/50">
                      <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">Page</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Views</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Unique</th>
                      <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Avg. Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pages.map((p, i) => (
                      <tr key={i} className="border-b border-border/50 hover:bg-secondary/20">
                        <td className="px-4 py-2 text-sm text-foreground font-mono">{p.path}</td>
                        <td className="px-4 py-2 text-sm text-right text-foreground">{formatNumber(p.pageviews)}</td>
                        <td className="px-4 py-2 text-sm text-right text-muted-foreground">{formatNumber(p.unique_visitors)}</td>
                        <td className="px-4 py-2 text-sm text-right text-muted-foreground">{formatDuration(p.avg_time_on_page)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- DEVICES --- */}
        <TabsContent value="devices" className="space-y-6 mt-4">
          {devices && (
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Device type */}
              <Card className="border-border bg-card">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Smartphone className="h-4 w-4 text-violet-400" />
                    Device Types
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie data={devices.devices} cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={5} dataKey="count" nameKey="device">
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

              {/* Browsers */}
              <Card className="border-border bg-card">
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Monitor className="h-4 w-4 text-blue-400" />
                    Browsers
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={devices.browsers}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis dataKey="browser" stroke="#888" fontSize={11} />
                      <YAxis stroke="#888" fontSize={11} />
                      <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                      <Bar dataKey="count" fill="#60a5fa" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              {/* OS */}
              <Card className="border-border bg-card">
                <CardHeader>
                  <CardTitle className="text-base">Operating Systems</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={devices.os}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis dataKey="os" stroke="#888" fontSize={11} />
                      <YAxis stroke="#888" fontSize={11} />
                      <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                      <Bar dataKey="count" fill="#a855f7" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              {/* Screen sizes */}
              <Card className="border-border bg-card">
                <CardHeader>
                  <CardTitle className="text-base">Screen Resolutions</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[250px] overflow-y-auto">
                    {devices.screens.map((s, i) => {
                      const maxCount = devices.screens[0]?.count || 1
                      const pct = (s.count / maxCount) * 100
                      return (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs font-mono text-muted-foreground w-24">{s.resolution}</span>
                          <div className="flex-1 h-5 bg-secondary/30 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500/70 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-foreground w-12 text-right">{formatNumber(s.count)}</span>
                        </div>
                      )
                    })}
                    {devices.screens.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-8">No screen size data yet</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* --- LOCATIONS --- */}
        <TabsContent value="locations" className="space-y-6 mt-4">
          {locations && (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                {/* Countries */}
                <Card className="border-border bg-card">
                  <CardHeader>
                    <CardTitle className="text-base flex items-center gap-2">
                      <Globe className="h-4 w-4 text-emerald-400" />
                      Countries
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={locations.countries} layout="vertical" margin={{ left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                        <XAxis type="number" stroke="#888" fontSize={11} tickFormatter={formatNumber} />
                        <YAxis dataKey="country" type="category" stroke="#888" fontSize={11} width={100} />
                        <Tooltip
                          contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                          formatter={(value: number) => [formatNumber(value), "Page Views"]}
                        />
                        <Bar dataKey="pageviews" fill="#4ade80" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Cities */}
                <Card className="border-border bg-card">
                  <CardHeader>
                    <CardTitle className="text-base">Top Cities</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="max-h-[320px] space-y-2 overflow-y-auto">
                      {locations.cities.map((c, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 px-3 py-2">
                          <div>
                            <span className="text-sm text-foreground">{c.city}</span>
                            {c.region && <span className="text-xs text-muted-foreground ml-2">{c.region}</span>}
                          </div>
                          <span className="text-xs text-muted-foreground">{formatNumber(c.pageviews)} views</span>
                        </div>
                      ))}
                      {locations.cities.length === 0 && (
                        <p className="text-sm text-muted-foreground text-center py-8">No location data yet</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </TabsContent>

        {/* --- FORMS --- */}
        <TabsContent value="forms" className="space-y-6 mt-4">
          {forms && (
            <>
              {forms.forms.length === 0 ? (
                <Card className="border-border bg-card">
                  <CardContent className="py-12 text-center">
                    <MousePointerClick className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
                    <p className="text-muted-foreground">No form events tracked yet</p>
                    <p className="text-xs text-muted-foreground mt-1">Form tracking is active — data will appear when visitors interact with forms.</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid gap-4">
                  {forms.forms.map((f, i) => (
                    <Card key={i} className="border-border bg-card">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h4 className="font-medium text-foreground">{f.form_name}</h4>
                            <p className="text-xs text-muted-foreground font-mono">{f.path}</p>
                          </div>
                          <Badge className={
                            f.conversion_rate >= 50 ? "bg-emerald-500/20 text-emerald-400" :
                            f.conversion_rate >= 20 ? "bg-amber-500/20 text-amber-400" :
                            "bg-red-500/20 text-red-400"
                          }>
                            {f.conversion_rate}% conversion
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
                          <div className="rounded-lg bg-secondary/30 p-2">
                            <p className="text-lg font-bold text-foreground">{formatNumber(f.views)}</p>
                            <p className="text-xs text-muted-foreground">Views</p>
                          </div>
                          <div className="rounded-lg bg-secondary/30 p-2">
                            <p className="text-lg font-bold text-blue-400">{formatNumber(f.starts)}</p>
                            <p className="text-xs text-muted-foreground">Started</p>
                          </div>
                          <div className="rounded-lg bg-secondary/30 p-2">
                            <p className="text-lg font-bold text-emerald-400">{formatNumber(f.submits)}</p>
                            <p className="text-xs text-muted-foreground">Submitted</p>
                          </div>
                          <div className="rounded-lg bg-secondary/30 p-2">
                            <p className="text-lg font-bold text-red-400">{formatNumber(f.abandons)}</p>
                            <p className="text-xs text-muted-foreground">Abandoned</p>
                          </div>
                          <div className="rounded-lg bg-secondary/30 p-2">
                            <p className="text-lg font-bold text-violet-400">{f.avg_time_to_complete > 0 ? formatDuration(f.avg_time_to_complete) : "—"}</p>
                            <p className="text-xs text-muted-foreground">Avg. Time</p>
                          </div>
                        </div>

                        {/* Funnel bar */}
                        <div className="mt-3">
                          <div className="h-3 w-full rounded-full bg-secondary/30 overflow-hidden flex">
                            {f.submits > 0 && (
                              <div className="h-full bg-emerald-500" style={{ width: `${(f.submits / (f.starts || f.views)) * 100}%` }} />
                            )}
                            {f.abandons > 0 && (
                              <div className="h-full bg-red-500/70" style={{ width: `${(f.abandons / (f.starts || f.views)) * 100}%` }} />
                            )}
                            {f.errors > 0 && (
                              <div className="h-full bg-amber-500/50" style={{ width: `${(f.errors / (f.starts || f.views)) * 100}%` }} />
                            )}
                          </div>
                          <div className="flex justify-between mt-1">
                            <span className="text-xs text-muted-foreground">
                              {f.starts > 0 ? `${((f.submits / f.starts) * 100).toFixed(0)}% completion` : "No data"}
                            </span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
