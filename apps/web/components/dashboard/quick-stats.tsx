"use client"

import { useState, useEffect, useMemo } from "react"
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import {
  DollarSign,
  Briefcase,
  Layers,
  ArrowUpRight,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { getCorporateSalesSnapshot, type CorporateSalesSnapshot } from "@/lib/hr-api"
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"
import {
  bucketWonDeals,
  dealTotals,
  fmtZarCompact,
  sumBuckets,
  type DealRow,
} from "@/lib/overview-derive"

type MetricView = "revenue" | "deals" | "pipeline"
type TimeRange = "7D" | "30D" | "90D" | "1Y"

export function QuickStats({ deals, onRetry }: { deals: Loadable<DealRow[]>; onRetry?: () => void }) {
  const [metricView, setMetricView] = useState<MetricView>("revenue")
  const [timeRange, setTimeRange] = useState<TimeRange>("30D")
  const [corpSales, setCorpSales] = useState<CorporateSalesSnapshot | null>(null)
  const [corpSalesLoading, setCorpSalesLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getCorporateSalesSnapshot()
      .then((snap) => { if (!cancelled) setCorpSales(snap) })
      .catch(() => { if (!cancelled) setCorpSales(null) })
      .finally(() => { if (!cancelled) setCorpSalesLoading(false) })
    return () => { cancelled = true }
  }, [])

  const fmtCorpZar = (v: number | null | undefined) =>
    v === null || v === undefined ? "Not connected" : `R ${Math.round(v).toLocaleString("en-ZA")}`

  const rows: DealRow[] = deals.state === "ready" && Array.isArray(deals.data) ? deals.data : []
  const ready = deals.state === "ready"

  // Won revenue / deals bucketed by real close dates for the selected range.
  const chartData = useMemo(
    () => bucketWonDeals(rows, timeRange).map((b) => ({ month: b.label, revenue: b.revenue, deals: b.deals })),
    [rows, timeRange],
  )
  const period = useMemo(() => sumBuckets(chartData), [chartData])
  const totals = useMemo(() => dealTotals(rows), [rows])

  // Open pipeline by stage, from the same real deals.
  const pipelineByStage = useMemo(() => {
    const m = new Map<string, { month: string; revenue: number; deals: number }>()
    for (const d of rows) {
      const st = (d.status ?? "").toUpperCase()
      if (st === "WON" || st === "LOST") continue
      const key = d.stage_name || "Unstaged"
      const cur = m.get(key) ?? { month: key, revenue: 0, deals: 0 }
      cur.revenue += Number.parseFloat(String(d.value_zar ?? 0)) || 0
      cur.deals += 1
      m.set(key, cur)
    }
    return [...m.values()]
  }, [rows])

  const tileValue = (fmt: () => string) =>
    deals.state === "loading" ? (
      <span className="inline-block h-8 w-28 animate-pulse rounded bg-muted align-middle" aria-label="Loading" />
    ) : ready ? (
      fmt()
    ) : (
      <span className="text-sm font-medium text-muted-foreground">
        {deals.state === "unreachable" ? "Service not running" : deals.state === "denied" ? "Not permitted" : "Error loading"}
      </span>
    )

  const hasChartData =
    metricView === "pipeline" ? pipelineByStage.length > 0 : chartData.some((b) => b.revenue > 0 || b.deals > 0)

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm transition-all">
      {/* Header & Live Status */}
      <div className="flex flex-col gap-4 border-b border-border/60 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className={`flex h-2.5 w-2.5 rounded-full ${ready ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/40"}`} />
            <h3 className="text-lg font-bold tracking-tight text-foreground sm:text-xl">
              Sales & Revenue Performance
            </h3>
            {ready && (
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-400">
                Live data
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground sm:text-sm">
            Won revenue and deal volume by close date, and open pipeline by stage, from the sales service.
          </p>
        </div>

        {/* Action controls & Time Range Filter */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Time range buttons */}
          <div className="flex rounded-lg border border-border bg-secondary/30 p-0.5 text-xs font-medium">
            {(["7D", "30D", "90D", "1Y"] as TimeRange[]).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`rounded-md px-2.5 py-1 transition-all cursor-pointer ${
                  timeRange === range
                    ? "bg-primary text-primary-foreground font-semibold shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {range}
              </button>
            ))}
          </div>

          {/* Refresh button */}
          <button
            onClick={onRetry}
            disabled={deals.state === "loading"}
            className="flex items-center gap-1.5 rounded-lg border border-border bg-secondary/20 px-2.5 py-1 text-xs font-medium text-muted-foreground transition hover:bg-secondary/40 hover:text-foreground cursor-pointer"
            title="Refresh live sales metrics"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${deals.state === "loading" ? "animate-spin text-primary" : ""}`} />
            <span className="hidden sm:inline">Sync</span>
          </button>
        </div>
      </div>

      {/* KPI vs Budget Shared Alignment Banner */}
      <div className="mt-4 p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-400 shrink-0">
            <Target className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground">Corporate Sales KPI vs Target Budget</span>
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px]">
                {corpSalesLoading
                  ? "Loading..."
                  : corpSales?.achievementPct != null
                    ? `${corpSales.achievementPct.toFixed(1)}% of ${fmtCorpZar(corpSales.budget)} Target`
                    : "Not connected"}
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              Actual: <b className="text-foreground">{corpSalesLoading ? "Loading..." : fmtCorpZar(corpSales?.actual)}</b> • Target Budget: <b className="text-foreground">{corpSalesLoading ? "Loading..." : fmtCorpZar(corpSales?.budget)}</b>
            </p>
          </div>
        </div>
        <a
          href="#talent"
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline shrink-0"
        >
          <span>Performance & Objectives</span>
          <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      </div>

      {/* Metric Switcher Cards (CX Interactive Tabs) */}
      <div className="my-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {/* Card 1: Revenue */}
        <button
          type="button"
          onClick={() => setMetricView("revenue")}
          className={`group relative flex flex-col justify-between rounded-xl border p-4 text-left transition-all cursor-pointer ${
            metricView === "revenue"
              ? "border-primary bg-primary/10 shadow-md shadow-primary/10 ring-1 ring-primary/40"
              : "border-border bg-secondary/15 hover:border-border/80 hover:bg-secondary/25"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Won Revenue (period)
            </span>
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                metricView === "revenue" ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
              }`}
            >
              <DollarSign className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold tracking-tight text-foreground">
              {tileValue(() => fmtZarCompact(period.revenue))}
            </span>
            {ready && (
              <div className="mt-1 text-xs font-medium text-muted-foreground">
                {totals.wonValue > 0 ? `${fmtZarCompact(totals.wonValue)} won all-time` : "No won deals yet"}
              </div>
            )}
          </div>
        </button>

        {/* Card 2: Closed Deals */}
        <button
          type="button"
          onClick={() => setMetricView("deals")}
          className={`group relative flex flex-col justify-between rounded-xl border p-4 text-left transition-all cursor-pointer ${
            metricView === "deals"
              ? "border-primary bg-primary/10 shadow-md shadow-primary/10 ring-1 ring-primary/40"
              : "border-border bg-secondary/15 hover:border-border/80 hover:bg-secondary/25"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Deals Converted
            </span>
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                metricView === "deals" ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
              }`}
            >
              <Briefcase className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold tracking-tight text-foreground">
              {tileValue(() => `${period.deals} Deals`)}
            </span>
            {ready && (
              <div className="mt-1 text-xs font-medium text-muted-foreground">
                {totals.winRate === null ? "Win rate: no closed deals yet" : `${(totals.winRate * 100).toFixed(0)}% win rate (${totals.won} won, ${totals.lost} lost)`}
              </div>
            )}
          </div>
        </button>

        {/* Card 3: Active Pipeline */}
        <button
          type="button"
          onClick={() => setMetricView("pipeline")}
          className={`group relative flex flex-col justify-between rounded-xl border p-4 text-left transition-all cursor-pointer ${
            metricView === "pipeline"
              ? "border-primary bg-primary/10 shadow-md shadow-primary/10 ring-1 ring-primary/40"
              : "border-border bg-secondary/15 hover:border-border/80 hover:bg-secondary/25"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Active Pipeline
            </span>
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                metricView === "pipeline" ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
              }`}
            >
              <Layers className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-bold tracking-tight text-foreground">
              {tileValue(() => fmtZarCompact(totals.openValue))}
            </span>
            {ready && (
              <div className="mt-1 flex items-center gap-1 text-xs font-medium text-blue-400">
                <Sparkles className="h-3.5 w-3.5" />
                <span>{`${totals.open} open deal${totals.open === 1 ? "" : "s"}`}</span>
              </div>
            )}
          </div>
        </button>
      </div>

      {/* Main Interactive Graph */}
      {!ready ? (
        <NotConnected loadable={deals} service="The sales service" onRetry={onRetry} className="h-64 sm:h-80" />
      ) : !hasChartData ? (
        <div className="flex h-64 w-full items-center justify-center rounded-lg border border-dashed border-border bg-secondary/20 text-sm text-muted-foreground sm:h-80">
          {metricView === "pipeline" ? "No open deals yet" : "No won deals in this period"}
        </div>
      ) : (
      <div className="h-64 w-full sm:h-80">
        <ResponsiveContainer width="100%" height="100%">
          {metricView === "revenue" ? (
            <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
              <defs>
                <linearGradient id="colorSalesRevenue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#818cf8" stopOpacity={0.45} />
                  <stop offset="95%" stopColor="#818cf8" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2e384d" vertical={false} />
              <XAxis
                dataKey="month"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                tickFormatter={(v) => `R${v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                  color: "#f8fafc",
                  boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)",
                }}
                formatter={(val: any) => [
                  `R ${Number(val).toLocaleString()}`,
                  "Won Revenue",
                ]}
              />
              <Area
                type="monotone"
                dataKey="revenue"
                name="revenue"
                stroke="#6366f1"
                strokeWidth={3}
                fillOpacity={1}
                fill="url(#colorSalesRevenue)"
              />
            </AreaChart>
          ) : metricView === "deals" ? (
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2e384d" vertical={false} />
              <XAxis
                dataKey="month"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                  color: "#f8fafc",
                }}
                formatter={(val: any) => [`${val} Deals Won`, "Volume"]}
              />
              <Bar
                dataKey="deals"
                name="Deals"
                fill="#38bdf8"
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          ) : (
            <BarChart
              data={pipelineByStage}
              margin={{ top: 10, right: 10, left: -15, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2e384d" vertical={false} />
              <XAxis
                dataKey="month"
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#94a3b8", fontSize: 12 }}
                tickFormatter={(v) => fmtZarCompact(Number(v))}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "10px",
                  color: "#f8fafc",
                }}
                formatter={(val: any) => [`R ${Number(val).toLocaleString()}`, "Pipeline Value"]}
              />
              <Bar
                dataKey="revenue"
                name="Pipeline ZAR"
                fill="#a855f7"
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      )}

      {/* Data source footer */}
      <div className="mt-4 flex flex-col justify-between gap-2 border-t border-border/50 pt-3 text-xs text-muted-foreground sm:flex-row sm:items-center">
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground">Data source:</span>
          <span>
            {ready
              ? `Sales service (${totals.count} deal${totals.count === 1 ? "" : "s"})`
              : deals.state === "loading"
                ? "Loading…"
                : "Sales service unavailable"}
          </span>
        </div>
        {metricView === "revenue" && ready && (
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-primary" />
            <span>Won revenue by close date</span>
          </span>
        )}
      </div>
    </div>
  )
}
