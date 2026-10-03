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
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import {
  aggregateFunnel, clampPct, funnelKey, funnelTier, pipelineValueFigure, sumStageMap, tierConversion, visibleChannels,
  type FunnelStageIn, type FunnelTier,
} from "@/lib/sales-derive"
import {
  salesApi,
  isSalesUnreachable,
  SalesApiError,
  type ChannelFunnelItem,
  type FunnelStageItem,
  type LeadFunnelResponse,
  SALES_CHANNELS,
} from "@/lib/sales-api"
import { TraditionalFunnel, type FunnelTierData } from "./traditional-funnel"

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
    desc: "Public sector & enterprise tenders scanned via Domecrawl",
  },
  OTHER: {
    label: "Direct / Other",
    icon: Layers,
    color: "#94a3b8",
    desc: "Direct entries and unclassified sources",
  },
}

// Keyed by funnelKey() (upper case, single spaces) so 'Qualified' and 'QUALIFIED' are the same stage.
const STAGE_COLORS: Record<string, string> = {
  NEW: "#3b82f6",
  CONTACTED: "#06b6d4",
  QUALIFIED: "#f59e0b",
  PROSPECTING: "#8b5cf6",
  CONVERTED: "#8b5cf6",
  PROPOSAL: "#ec4899",
  NEGOTIATION: "#f97316",
  "CLOSED WON": "#10b981",
  WON: "#10b981",
  "CLOSED LOST": "#ef4444",
  LOST: "#ef4444",
  DISQUALIFIED: "#ef4444",
}

const STAGE_LABELS: Record<string, string> = {
  NEW: "New",
  CONTACTED: "Contacted",
  QUALIFIED: "Qualified",
  CONVERTED: "In pipeline",
  DISQUALIFIED: "Disqualified",
  WON: "Closed Won",
  LOST: "Closed Lost",
}
const stageLabel = (stage: string) => STAGE_LABELS[funnelKey(stage)] ?? stage

const CHANNEL_CHART_MAX = 8

export function LeadFunnelView({
  onSelectChannelFilter,
  onNavigateToLeads,
}: LeadFunnelViewProps) {
  const [data, setData] = useState<LeadFunnelResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadFail, setLoadFail] = useState<Loadable<never> | null>(null)
  const [showAllChannels, setShowAllChannels] = useState(false)
  const [selectedChannel, setSelectedChannel] = useState<string>("all")
  const [days, setDays] = useState<number | undefined>(undefined)

  const loadFunnel = useCallback(async () => {
    try {
      setLoading(true)
      setLoadFail(null)
      const res = await salesApi.getLeadFunnel({
        days,
        channel: selectedChannel === "all" ? undefined : selectedChannel,
      })
      setData(res)
    } catch (err: any) {
      setData(null)
      setLoadFail(
        isSalesUnreachable(err)
          ? { state: "unreachable", status: err instanceof SalesApiError ? err.status : null }
          : err instanceof SalesApiError && (err.status === 401 || err.status === 403)
            ? { state: "denied", status: err.status }
            : { state: "error", status: err instanceof SalesApiError ? err.status : null, message: err?.message || "Failed to load lead funnel" },
      )
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

  // Stacked chart data per channel: first 8 until the user expands (never cut silently).
  const allChannelChartData = useMemo(() => {
    if (!data?.channels) return []
    return data.channels
      .filter((c) => c.total_leads > 0)
      .map((c) => ({
        name: c.channel_label || c.channel,
        channel: c.channel,
        total: c.total_leads,
        won: c.won_count,
        lost: c.lost_count,
        pipeline: Math.max(0, c.total_leads - c.won_count - c.lost_count),
        conversion: clampPct(c.conversion_rate),
        revenue: Number(c.won_value_zar) || 0,
        color: CHANNEL_METADATA[c.channel]?.color || "#94a3b8",
      }))
  }, [data])
  const chartChannels = visibleChannels(allChannelChartData, CHANNEL_CHART_MAX, showAllChannels)
  const channelChartData = chartChannels.shown

  // Every bucket the API returned, merged case-insensitively, plus whatever is not accounted for.
  const funnelAgg = useMemo(
    () => aggregateFunnel((data?.overall_funnel ?? []) as FunnelStageIn[], Number(data?.totals?.total_leads) || 0),
    [data],
  )
  const pipelineFigure = useMemo(() => pipelineValueFigure(data?.totals as Record<string, unknown> | undefined), [data])

  // Traditional Inverted Funnel Tiers (Top leads -> Mid pipeline -> Closing -> Won)
  const funnelTiers: FunnelTierData[] = useMemo(() => {
    if (!data) return []

    const total = Number(data.totals?.total_leads) || 0
    const { tiers } = funnelAgg
    const pctOf = (n: number) => (total > 0 ? clampPct((n / total) * 100) : 0)
    const wonCount = Number(data.totals?.won_leads) || tiers.won.count

    const getChannelSegmentsFor = (tier: "top" | "mid" | "closing" | "won", tierTotal: number) => {
      if (!data.channels) return []
      return data.channels
        .map((ch) => {
          const chCount = sumStageMap(ch.stage_counts, tier)
          const meta = CHANNEL_METADATA[ch.channel] || {
            label: ch.channel_label,
            color: "#94a3b8",
          }
          return {
            channel: ch.channel,
            label: meta.label,
            count: chCount,
            color: meta.color,
            pctOfTier: tierTotal > 0 ? Math.round((chCount / tierTotal) * 100) : 0,
          }
        })
        .filter((seg) => seg.count > 0)
        .sort((a, b) => b.count - a.count)
    }

    const conv = (cur: FunnelTier, prev: FunnelTier) => {
      const c = tierConversion(tiers[cur], tiers[prev])
      return c === null ? undefined : c
    }

    return [
      {
        id: "top-tier",
        name: "Top of Funnel: Captured Inbound Leads",
        stageCategory: "top",
        count: tiers.top.count,
        valueZar: tiers.top.value,
        pctOfTotal: pctOf(tiers.top.count),
        description: "Raw prospects sitting in New or Contacted stages awaiting discovery and warming",
        channels: getChannelSegmentsFor("top", tiers.top.count),
      },
      {
        id: "mid-tier",
        name: "Mid Funnel: Qualified Pipeline in Progress",
        stageCategory: "mid",
        count: tiers.mid.count,
        valueZar: tiers.mid.value,
        pctOfTotal: pctOf(tiers.mid.count),
        conversionFromPrev: conv("mid", "top"),
        description: "Qualified opportunities being actively worked on by field agents and telesales",
        channels: getChannelSegmentsFor("mid", tiers.mid.count),
      },
      {
        id: "closing-tier",
        name: "Decision Stage: Proposals & Negotiations",
        stageCategory: "closing",
        count: tiers.closing.count,
        valueZar: tiers.closing.value,
        pctOfTotal: pctOf(tiers.closing.count),
        conversionFromPrev: conv("closing", "mid"),
        description: "Formal packages quoted, SLA evaluations, and pricing terms under review",
        channels: getChannelSegmentsFor("closing", tiers.closing.count),
      },
      {
        id: "won-tier",
        name: "Bottom of Funnel: Closed Won & Subscribed",
        stageCategory: "won",
        count: wonCount,
        valueZar: Number(data.totals?.won_value_zar) || tiers.won.value,
        pctOfTotal: pctOf(wonCount),
        conversionFromPrev: conv("won", "closing") ?? conv("won", "mid"),
        description: "Signed contracts provisioned as live active subscribers",
        channels: getChannelSegmentsFor("won", wonCount),
      },
    ]
  }, [data, funnelAgg])

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

      {!data && (
        <NotConnected
          loadable={loading && !loadFail ? { state: "loading" } : (loadFail ?? { state: "loading" })}
          service="The sales service"
          onRetry={loadFunnel}
          className="min-h-48"
        />
      )}

      {data && (<>
      {funnelAgg.unaccounted > 0 && (
        <div className="p-3 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-400 text-xs flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span>
            {funnelAgg.unaccounted} of {data.totals?.total_leads} leads are not in any stage bucket below (shown as Other / unmapped).
          </span>
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
              {clampPct(Number(data?.totals?.conversion_rate))}%
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              Won / Total Leads
            </p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card shadow-sm">
          <CardContent className="p-4">
            <p className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
              Open Pipeline
              <DollarSign className="h-3.5 w-3.5 text-purple-400" />
            </p>
            <p className="text-xl font-bold text-foreground mt-1 truncate">
              {zar(pipelineFigure.value)}
            </p>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {pipelineFigure.label}
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
            {[...funnelAgg.merged, ...(funnelAgg.unaccounted > 0 ? [{ stage: "Other / unmapped", count: funnelAgg.unaccounted, value_zar: 0 } as FunnelStageIn] : [])].map((st, idx, all) => {
              const key = funnelKey(st.stage)
              const tier = funnelTier(st.stage)
              const color = STAGE_COLORS[key] || "#94a3b8"
              const isWon = tier === "won"
              const isLost = tier === "lost"
              const valNum = Number(st.value_zar) || 0
              const totalLeads = Number(data?.totals?.total_leads) || 0
              const pct = totalLeads > 0 ? clampPct((st.count / totalLeads) * 100) : 0

              return (
                <div
                  key={key}
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
                      {pct}%
                    </span>
                  </div>

                  <p className="mt-2 text-xs font-semibold text-foreground truncate" title={stageLabel(st.stage)}>
                    {stageLabel(st.stage)}
                  </p>

                  <p className="text-lg font-bold font-mono mt-1" style={{ color }}>
                    {st.count}
                  </p>

                  {valNum > 0 && (
                    <p className="text-[10px] font-mono text-muted-foreground mt-1 truncate">
                      {zar(valNum)}
                    </p>
                  )}

                  {idx < all.length - 1 && !isLost && (
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

      {/* ── Visual Traditional Pipeline Funnel (Inverted Trapezoid Stages) ── */}
      <Card className="border-border bg-card shadow-sm">
        <CardHeader className="pb-2">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base font-bold text-foreground flex items-center gap-2">
                <Target className="h-5 w-5 text-emerald-400" />
                Pipeline Conversion Funnel
              </CardTitle>
              <CardDescription className="text-xs">
                Visual progression from initial inbound leads &rarr; active pipeline &rarr; closed won deals by channel attribution
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs font-mono border-emerald-500/30 text-emerald-400">
                {data?.totals?.total_leads ?? 0} Inbound Leads
              </Badge>
              <Badge variant="outline" className="text-xs font-mono border-purple-500/30 text-purple-400">
                {zar(pipelineFigure.value)} Open pipeline
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-2">
          <TraditionalFunnel
            tiers={funnelTiers}
            totalLeads={data?.totals?.total_leads ?? 0}
            totalPipelineZar={pipelineFigure.value}
            wonLeads={data?.totals?.won_leads ?? 0}
            wonRevenueZar={Number(data?.totals?.won_value_zar) || 0}
            onSelectChannel={(ch) => setSelectedChannel(ch)}
            onSelectTier={(tierId) => {
              if (onNavigateToLeads) onNavigateToLeads()
            }}
          />
        </CardContent>
      </Card>

      {/* ── Channel Lead Volume & Won Performance Bar Chart ── */}
      <Card className="border-border bg-card shadow-sm">
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
          {chartChannels.hidden > 0 && (
            <p className="text-xs text-muted-foreground">
              Showing {channelChartData.length} of {allChannelChartData.length} channels.{" "}
              <button type="button" className="text-primary underline" onClick={() => setShowAllChannels(true)}>
                Show {chartChannels.hidden} more
              </button>
            </p>
          )}
          {showAllChannels && allChannelChartData.length > CHANNEL_CHART_MAX && (
            <p className="text-xs text-muted-foreground">
              Showing all {allChannelChartData.length} channels.{" "}
              <button type="button" className="text-primary underline" onClick={() => setShowAllChannels(false)}>
                Show fewer
              </button>
            </p>
          )}
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
          {(data?.channels ?? []).map((ch) => {
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
                    {clampPct(ch.conversion_rate)}% Win
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
      </>)}
    </div>
  )
}
