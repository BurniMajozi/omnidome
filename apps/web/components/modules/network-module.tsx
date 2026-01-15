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
import { Wifi, Activity, AlertTriangle, Zap } from "lucide-react"

const networkMetrics = [
  { time: "00:00", bandwidth: 65, latency: 2.1 },
  { time: "04:00", bandwidth: 52, latency: 1.8 },
  { time: "08:00", bandwidth: 78, latency: 2.4 },
  { time: "12:00", bandwidth: 88, latency: 2.8 },
  { time: "16:00", bandwidth: 92, latency: 3.2 },
  { time: "20:00", bandwidth: 85, latency: 2.9 },
  { time: "24:00", bandwidth: 70, latency: 2.3 },
]

const nodeStatus = [
  { node: "North Zone", status: 287, utilization: 72 },
  { node: "South Zone", status: 264, utilization: 68 },
  { node: "East Zone", status: 298, utilization: 75 },
  { node: "West Zone", status: 271, utilization: 70 },
  { node: "Central Hub", status: 127, utilization: 82 },
]

export function NetworkModule() {
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Network Uptime"
          value="99.97%"
          change="+0.02%"
          changeType="positive"
          icon={Wifi}
          description="this month"
        />
        <StatCard
          title="Active Nodes"
          value="1,247"
          change="+3.2%"
          changeType="positive"
          icon={Activity}
          description="vs last month"
        />
        <StatCard
          title="Avg Latency"
          value="2.6ms"
          change="-0.3ms"
          changeType="positive"
          icon={Zap}
          description="vs last week"
        />
        <StatCard
          title="Critical Alerts"
          value="2"
          change="-45%"
          changeType="positive"
          icon={AlertTriangle}
          description="vs last month"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Bandwidth & Latency */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Bandwidth Usage & Latency</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={networkMetrics}>
                <defs>
                  <linearGradient id="colorBandwidth" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#4ade80" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="time" tick={{ fill: "#737373", fontSize: 12 }} />
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
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="bandwidth"
                  stroke="#4ade80"
                  fillOpacity={1}
                  fill="url(#colorBandwidth)"
                  name="Bandwidth (%)"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="latency"
                  stroke="#60a5fa"
                  strokeWidth={2}
                  name="Latency (ms)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Node Status */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Node Status by Zone</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={nodeStatus}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="node" tick={{ fill: "#737373", fontSize: 12 }} />
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
                <Bar dataKey="status" fill="#4ade80" name="Active Nodes" />
                <Bar dataKey="utilization" fill="#60a5fa" name="Utilization (%)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Network Performance */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">24-Hour Network Performance</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={networkMetrics}>
              <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
              <XAxis dataKey="time" tick={{ fill: "#737373", fontSize: 12 }} />
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
              <Line type="monotone" dataKey="bandwidth" stroke="#4ade80" strokeWidth={2} name="Bandwidth %" />
              <Line type="monotone" dataKey="latency" stroke="#ef4444" strokeWidth={2} name="Latency (ms)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
