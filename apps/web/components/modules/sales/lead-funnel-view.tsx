"use client"

import { useCallback, useEffect, useState, useMemo } from "react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from "recharts"
import {
  Filter,
  RefreshCw,
  TrendingUp,
  Target,
  Users,
  DollarSign,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Megaphone,
  Mail,
  PhoneCall,
  PhoneOutgoing,
  Globe,
  MapPin,
  Store,
  Building2,
  FileText,
  Activity,
  Layers,
  ChevronRight,
  ShieldAlert,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  salesApi,
  type ChannelFunnelItem,
  type FunnelStageItem,
  type LeadFunnelResponse,
  SALES_CHANNELS,
} from "@/lib/sales-api"

interface LeadFunnelViewProps {
  onSelectChannelFilter?: (channel: string) => void
  onNavigateToLeads?: (channel?: string, stage?: string) => void
}

const zar = (n: number | string | undefined | null) => {
  const num = typeof n === "number" ? n : Number(n) || 0
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    maximumFractionDigits: 0,
  }).format(num)
}

const CHANNEL_METADATA: Record<
  string,
  { label: string; icon: any; color: string; desc: string }
> = {
  MARKETING: {
    label: "Marketing Campaigns",
    icon: Megaphone,
    color: "#e03131",
    desc: "Digital ads, campaign forms & social lead warming",
  },
  INBOUND_EMAIL: {
    label: "Inbound Email",
    icon: Mail,
    color: "#60a5fa",
    desc: "Direct inbound quotes and email inquiries",
  },
  CALL_CENTER_INBOUND: {
    label: "Call Center Inbound",
    icon: PhoneCall,
    color: "#34d399",
    desc: "Hotline calls & incoming telephony leads",
  },
  CALL_CENTER_OUTBOUND: {
    label: "Call Center Outbound",
    icon: PhoneOutgoing,
    color: "#fbbf24",
    desc: "Telesales campaigns & cold outbound outreach",
  },
  PORTAL_WEBSITE: {
    label: "Portal & Website",
    icon: Globe,
    color: "#a78bfa",
    desc: "Self-service web checkout & online coverage checks",
  },
  FIELD_SALES: {
    label: "Field Sales Team",
    icon: MapPin,
    color: "#f87171",
    desc: "Door-to-door agents & territory walk visits",
  },
  WALK_IN: {
    label: "Walk-in Branch",
    icon: Store,
    color: "#38bdf8",
    desc: "Physical customer service & retail stores",
  },
  REFERRAL: {
    label: "Partner Referral",
    icon: Users,
    color: "#ec4899",
    desc: "Affiliate & agent referral network",
  },
  COMPANY_SEARCH: {
    label: "Company Search",
    icon: Building2,
    color: "#14b8a6",
    desc: "Area business directory & OpenStreetMap B2B leads",
  },
  TENDER: {
    label: "Tenders & RFQs",
    icon: FileText,
    color: "#f59e0b",
    desc: "Public sector & enterprise tenders scanned via Firecrawl",
  },
  OTHER: {
    label: "Direct / Other",
    icon: Layers,
    color: "#94a3b8",
    desc: "Direct entries and unclassified sources",
  },
}

const STAGE_COLORS: Record<string, string> = {
  NEW: "#3b82f6",
  CONTACTED: "#06b6d4",
  QUALIFIED: "#f59e0b",
  Prospecting: "#8b5cf6",
  Proposal: "#ec4899",
  Negotiation: "#f97316",
  "Closed Won": "#10b981",
  "Closed Lost": "#ef4444",
}

export function LeadFunnelView({
  onSelectChannelFilter,
  onNavigateToLeads,
}: LeadFunnelViewProps) {
  const [data, setData] = useState<LeadFunnelResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedChannel, setSelectedChannel] = useState<string>("all")
  const [days, setDays] = useState<number | undefined>(undefined)

  const loadFunnel = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await salesApi.getLeadFunnel({
        days,
        channel: selectedChannel === "all" ? undefined : selectedChannel,
      })
      setData(res)
    } catch (err: any) {
      setError(err?.message || "Failed to load lead funnel")
    } finally {
      setLoading(false)
    }
  }, [days, selectedChannel])

  useEffect(() => {
    loadFunnel()
  }, [loadFunnel])

  // Active channels that have leads
  const activeChannels = useMemo(() => {
    if (!data?.channels) return []
    return data.channels.filter((c) => c.total_leads > 0)
  }, [data])

  // Stacked chart data per channel
  const channelChartData = useMemo(() => {
    if (!data?.channels) return []
    return data.channels
      .filter((c) => c.total_leads > 0)
      .slice(0, 8)
      .map((c) => ({
        name: c.channel_label || c.channel,
        channel: c.channel,
        total: c.total_leads,
        won: c.won_count,
        lost: c.lost_count,
        pipeline: Math.max(0, c.total_leads - c.won_count - c.lost_count),
        conversion: c.conversion_rate,
        revenue: Number(c.won_value_zar) || 0,
        color: CHANNEL_METADATA[c.channel]?.color || "#94a3b8",
      }))
  }, [data])

  return (
    <div className="space-y-6">
      {/* ── Top Bar with Controls ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-border/60 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-foreground tracking-tight">
                Lead Funnel by Channel
              </h2>
              <p className="text-xs text-muted-foreground">
                Attribution & conversion tracking across Call Center, Marketing, Field Sales, Portal, and B2B sources
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center flex-wrap gap-2">
          {/* Channel selector */}
          <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-lg text-xs">
            <span className="text-muted-foreground px-2 flex items-center gap-1 font-medium">
              <Filter className="h-3 w-3" /> Channel:
            </span>
            <select
              value={selectedChannel}
              onChange={(e) => {
                setSelectedChannel(e.target.value)
                if (onSelectChannelFilter && e.target.value !== "all") {
                  onSelectChannelFilter(e.target.value)
                }
              }}
              className="bg-background text-foreground text-xs rounded-md px-2 py-1 border border-border focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="all">All Channels</option>
              {SALES_CHANNELS.map((ch: any) => {
                const id = typeof ch === "string" ? ch : ch.id
                const label = typeof ch === "string" ? (CHANNEL_METADATA[ch]?.label || ch) : ch.label
                return (
                  <option key={id} value={id}>
                    {label}
                  </option>
                )
              })}
            </select>
          </div>

          {/* Time range buttons */}
          <div className="flex items-center bg-muted/60 p-0.5 rounded-lg text-xs">
            {[
              { label: "All Time", value: undefined },
              { label: "30d", value: 30 },
              { label: "90d", value: 90 },
              { label: "1y", value: 365 },
            ].map((t) => (
              <button
                key={t.label}
                onClick={() => setDays(t.value)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                  days === t.value
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={loadFunnel}
            disabled={loading}
            className="h-8 gap-1 text-xs"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 text-xs flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ── KPI Highlight Cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Total Inbound Leads
              <Users className="h-3.5 w-3.5 text-blue-400" />
            </p>
            <p className="text-2xl font-bold text-foreground mt-1">
              {data?.totals?.total_leads ?? 0}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Across all channels
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Closed Won Deals
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            </p>
            <p className="text-2xl font-bold text-emerald-400 mt-1">
              {data?.totals?.won_leads ?? 0}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Active converted clients
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Conversion Rate
              <TrendingUp className="h-3.5 w-3.5 text-amber-400" />
            </p>
            <p className="text-2xl font-bold text-amber-400 mt-1">
              {data?.totals?.conversion_rate ?? 0}%
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Won / Total Leads
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Pipeline Value
              <DollarSign className="h-3.5 w-3.5 text-purple-400" />
            </p>
            <p className="text-xl font-bold text-foreground mt-1 truncate">
              {zar(data?.totals?.total_pipeline_value_zar ?? 0)}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Total open opportunities
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Won Revenue
              <DollarSign className="h-3.5 w-3.5 text-emerald-400" />
            </p>
            <p className="text-xl font-bold text-emerald-400 mt-1 truncate">
              {zar(data?.totals?.won_value_zar ?? 0)}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Realized deal contract value
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Top Channel
              <Target className="h-3.5 w-3.5 text-cyan-400" />
            </p>
            <p className="text-sm font-bold text-foreground mt-2 truncate">
              {data?.totals?.top_performing_channel ?? "—"}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              By lead volume & closed deals
            </p>
          </CardContent>
        </Card>
      </div>

      {/* ── Main Stage Funnel Horizontal Cascade ── */}
      <Card className="border-border bg-card shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Layers className="h-4 w-4 text-primary" />
                Cross-Channel Funnel Progression
              </CardTitle>
              <CardDescription className="text-xs">
                Stage progression from initial capture through qualification, quoting, and deal closing
              </CardDescription>
            </div>
            {onNavigateToLeads && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onNavigateToLeads()}
                className="text-xs text-primary hover:text-primary/80 h-7"
              >
                Manage Leads &rarr;
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 pt-2">
            {data?.overall_funnel?.map((st, idx) => {
              const color = STAGE_COLORS[st.stage] || "#94a3b8"
              const isWon = st.stage === "Closed Won"
              const isLost = st.stage === "Closed Lost"
              const valNum = Number(st.value_zar) || 0

              return (
                <div
                  key={st.stage}
                  onClick={() => onNavigateToLeads && onNavigateToLeads(undefined, st.stage)}
                  className={`group relative flex flex-col p-3 rounded-xl border border-border/80 bg-secondary/30 hover:border-primary/50 hover:bg-secondary/60 transition-all cursor-pointer ${
                    isWon ? "border-emerald-500/30 bg-emerald-500/5" : ""
                  } ${isLost ? "border-red-500/30 bg-red-500/5 opacity-80" : ""}`}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-[10px] font-mono text-muted-foreground">
                      {st.pct_of_total}%
                    </span>
                  </div>

                  <p className="mt-2 text-xs font-semibold text-foreground truncate" title={st.stage}>
                    {st.stage}
                  </p>

                  <p className="text-lg font-bold font-mono mt-1" style={{ color }}>
                    {st.count}
                  </p>

                  {valNum > 0 && (
                    <p className="text-[10px] font-mono text-muted-foreground mt-1 truncate">
                      {zar(valNum)}
                    </p>
                  )}

                  {data?.overall_funnel && idx < (data.overall_funnel.length - 1) && !isLost && (
                    <div className="hidden lg:block absolute -right-2 top-1/2 -translate-y-1/2 z-10">
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/40" />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── Channel Comparison Grid & Detailed Breakdown ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Channel Volume Bar Chart */}
        <Card className="border-border bg-card lg:col-span-2 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span>Channel Lead Volume & Won Performance</span>
              <Badge variant="outline" className="text-xs font-mono">
                {activeChannels.length} active channels
              </Badge>
            </CardTitle>
            <CardDescription className="text-xs">
              Comparing incoming leads, active deals, and closed won wins per acquisition channel
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-72 w-full pt-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={channelChartData}
                  margin={{ top: 10, right: 10, left: 0, bottom: 25 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "#a1a1aa", fontSize: 11 }}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#18181b",
                      border: "1px solid #3f3f46",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                    }}
                    formatter={(val: number, name: string) => [
                      name === "revenue" ? zar(val) : val,
                      name === "won"
                        ? "Closed Won"
                        : name === "pipeline"
                        ? "In Pipeline"
                        : name === "total"
                        ? "Total Leads"
                        : name,
                    ]}
                  />
                  <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                  <Bar dataKey="won" name="Closed Won" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="pipeline" name="In Pipeline" stackId="a" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Lead Share by Channel Donut */}
        <Card className="border-border bg-card shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Channel Volume Share</CardTitle>
            <CardDescription className="text-xs">
              Lead distribution percentage across active channels
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={channelChartData}
                    dataKey="total"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={80}
                    paddingAngle={3}
                  >
                    {channelChartData.map((entry, index) => (
                      <Cell key={`slice-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#18181b",
                      border: "1px solid #3f3f46",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                    }}
                    formatter={(val: number) => [`${val} Leads`, "Volume"]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-1.5 pt-3 border-t border-border/60">
              {channelChartData.slice(0, 5).map((ch) => (
                <div key={ch.channel} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full shrink-0"
                      style={{ backgroundColor: ch.color }}
                    />
                    <span className="text-muted-foreground truncate max-w-[130px]">
                      {ch.name}
                    </span>
                  </div>
                  <span className="font-mono font-medium text-foreground">
                    {ch.total} leads ({ch.conversion}%)
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Channel Deep-Dive Cards ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Target className="h-4 w-4 text-emerald-400" />
            Performance by Acquisition Channel
          </h3>
          <span className="text-xs text-muted-foreground">
            Click any channel to pre-filter sales records
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data?.channels.map((ch) => {
            const meta = CHANNEL_METADATA[ch.channel] || {
              label: ch.channel_label,
              icon: Layers,
              color: "#94a3b8",
              desc: "Channel leads",
            }
            const Icon = meta.icon

            return (
              <div
                key={ch.channel}
                onClick={() => {
                  setSelectedChannel(ch.channel)
                  if (onSelectChannelFilter) onSelectChannelFilter(ch.channel)
                }}
                className={`p-4 rounded-xl border border-border bg-card hover:border-primary/50 transition-all cursor-pointer ${
                  selectedChannel === ch.channel
                    ? "ring-2 ring-primary/40 border-primary"
                    : ""
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2.5">
                    <div
                      className="p-2 rounded-lg"
                      style={{
                        backgroundColor: `${meta.color}15`,
                        color: meta.color,
                      }}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-foreground">
                        {meta.label}
                      </h4>
                      <p className="text-[10px] text-muted-foreground line-clamp-1">
                        {meta.desc}
                      </p>
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className="text-[10px] font-mono"
                    style={{ borderColor: `${meta.color}40`, color: meta.color }}
                  >
                    {ch.conversion_rate}% Win
                  </Badge>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 py-2 border-y border-border/40 text-center">
                  <div>
                    <span className="text-[10px] text-muted-foreground block">Leads</span>
                    <span className="text-sm font-bold font-mono text-foreground">
                      {ch.total_leads}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-muted-foreground block">Won Deals</span>
                    <span className="text-sm font-bold font-mono text-emerald-400">
                      {ch.won_count}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-muted-foreground block">Won Revenue</span>
                    <span className="text-xs font-bold font-mono text-foreground truncate block">
                      {zar(ch.won_value_zar)}
                    </span>
                  </div>
                </div>

                <div className="mt-2.5 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>Open Pipeline:</span>
                  <span className="font-mono font-medium text-foreground">
                    {zar(ch.total_pipeline_value_zar)}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
