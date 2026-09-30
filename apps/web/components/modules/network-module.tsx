"use client"

import { StatCard } from "@/components/dashboard/stat-card"
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts"
import { Wifi, Activity, AlertTriangle, Zap, RefreshCw } from "lucide-react"
import { PageHeader } from "@/components/ui/page-header"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { tileLabel, type Loadable } from "@/lib/service-state"
import { loadNetworkBreaches, loadNetworkDevices, loadNetworkMetrics, useOps } from "@/lib/ops-api"
import {
  allSettled,
  dataOr,
  fmtInt,
  latestAverage,
  metricByHour,
  networkDeviceStats,
  pct,
  type NetworkDeviceRow,
  type NetworkMetricRow,
} from "@/lib/ops-derive"

/**
 * Network Operations. Read from the Network service (devices, performance
 * metrics, SLA breaches). If that service is not running the whole module says
 * so; when it runs but has ingested nothing, sections say "No data yet".
 */

const tooltipStyle = {
  backgroundColor: "#262626",
  border: "1px solid #404040",
  borderRadius: "8px",
  color: "#fff",
}

const tile = (l: Loadable<unknown>, value: () => string) => (l.state === "ready" ? value() : (tileLabel(l) ?? "—"))

export function NetworkModule() {
  const devices = useOps(loadNetworkDevices)
  const metrics = useOps(loadNetworkMetrics)
  const breaches = useOps(loadNetworkBreaches)

  const reloadAll = () => {
    devices.reload()
    metrics.reload()
    breaches.reload()
  }

  const loading = !allSettled(devices.value, metrics.value, breaches.value)
  const deviceRows: NetworkDeviceRow[] = devices.value.state === "ready" ? devices.value.data.rows : []
  const deviceTotal = devices.value.state === "ready" ? devices.value.data.total : 0
  const metricRows: NetworkMetricRow[] = dataOr(metrics.value, [] as NetworkMetricRow[])
  const breachRows: Array<{ severity: string }> = dataOr(breaches.value, [] as Array<{ severity: string }>)

  const stats = networkDeviceStats(deviceRows)
  const latencyAvg = latestAverage(metricRows, "latency_ms")
  const bandwidth = metricByHour(metricRows, "download_mbps")
  const latency = metricByHour(metricRows, "latency_ms")
  const perf = bandwidth.map((b, i) => ({ hour: b.hour, bandwidth: b.value, latency: latency[i].value }))
  const hasPerf = perf.some((p) => p.bandwidth !== null || p.latency !== null)
  const critical = breachRows.filter((b) => b.severity === "critical" || b.severity === "emergency").length

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Wifi className="h-5 w-5" />}
        title="Network Operations"
        subtitle="Infrastructure monitoring, node health, and bandwidth analytics"
        actions={
          <Button variant="cta" size="sm" onClick={reloadAll}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />

      {/* Whole service unreachable: say it once, prominently */}
      {!loading && devices.value.state !== "ready" && (
        <NotConnected loadable={devices.value} service="Network" onRetry={reloadAll} />
      )}

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Network Devices"
          value={loading ? "…" : tile(devices.value, () => fmtInt(deviceTotal))}
          change=""
          changeType="neutral"
          icon={Activity}
          description="registered"
        />
        <StatCard
          title="Active Devices"
          value={loading ? "…" : tile(devices.value, () => (stats.total ? `${fmtInt(stats.active)} (${pct(stats.active, stats.total)})` : "No data yet"))}
          change=""
          changeType="neutral"
          icon={Wifi}
          description="status active"
        />
        <StatCard
          title="Avg Latency"
          value={loading ? "…" : tile(metrics.value, () => (latencyAvg === null ? "No data yet" : `${latencyAvg.toFixed(1)}ms`))}
          change=""
          changeType="neutral"
          icon={Zap}
          description="collected samples"
        />
        <StatCard
          title="Critical SLA Breaches"
          value={loading ? "…" : tile(breaches.value, () => fmtInt(critical))}
          change=""
          changeType="neutral"
          icon={AlertTriangle}
          description="open"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="surface-card p-5">
          <h3 className="section-title mb-4">Bandwidth Usage & Latency (24h)</h3>
          {metrics.value.state !== "ready" ? (
            <NotConnected loadable={metrics.value} service="Network metrics" onRetry={metrics.reload} />
          ) : !hasPerf ? (
            <NoDataYet message="No performance metrics ingested yet" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={perf}>
                  <defs>
                    <linearGradient id="colorBandwidth" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                  <XAxis dataKey="hour" interval={3} tick={{ fill: "#737373", fontSize: 12 }} />
                  <YAxis yAxisId="left" tick={{ fill: "#737373", fontSize: 12 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fill: "#737373", fontSize: 12 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend />
                  <Area yAxisId="left" type="monotone" dataKey="bandwidth" stroke="#4ade80" fillOpacity={1} fill="url(#colorBandwidth)" name="Download (Mbps)" connectNulls />
                  <Line yAxisId="right" type="monotone" dataKey="latency" stroke="#60a5fa" strokeWidth={2} name="Latency (ms)" connectNulls />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="surface-card p-5">
          <h3 className="section-title mb-4">Devices by Type</h3>
          {devices.value.state !== "ready" ? (
            <NotConnected loadable={devices.value} service="Network" onRetry={devices.reload} />
          ) : stats.byType.length === 0 ? (
            <NoDataYet message="No network devices registered yet" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.byType}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                  <XAxis dataKey="type" tick={{ fill: "#737373", fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fill: "#737373", fontSize: 12 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend />
                  <Bar dataKey="count" fill="#60a5fa" name="Registered" />
                  <Bar dataKey="active" fill="#4ade80" name="Active" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      <div className="surface-card p-5">
        <h3 className="section-title mb-4">24-Hour Network Performance</h3>
        {metrics.value.state !== "ready" ? (
          <NotConnected loadable={metrics.value} service="Network metrics" onRetry={metrics.reload} />
        ) : !hasPerf ? (
          <NoDataYet message="No performance metrics ingested yet" />
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={perf}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="hour" interval={3} tick={{ fill: "#737373", fontSize: 12 }} />
                <YAxis tick={{ fill: "#737373", fontSize: 12 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend />
                <Line type="monotone" dataKey="bandwidth" stroke="#4ade80" strokeWidth={2} name="Download (Mbps)" connectNulls />
                <Line type="monotone" dataKey="latency" stroke="#ef4444" strokeWidth={2} name="Latency (ms)" connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
