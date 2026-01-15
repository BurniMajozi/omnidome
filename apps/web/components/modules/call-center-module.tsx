"use client"

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
import { Phone, Users, Clock, TrendingUp } from "lucide-react"

const callData = [
  { hour: "08:00", inbound: 45, outbound: 32 },
  { hour: "10:00", inbound: 52, outbound: 38 },
  { hour: "12:00", inbound: 68, outbound: 42 },
  { hour: "14:00", inbound: 75, outbound: 45 },
  { hour: "16:00", inbound: 58, outbound: 40 },
  { hour: "18:00", inbound: 42, outbound: 28 },
]

const agentPerformance = [
  { name: "Agent A", calls: 124, satisfaction: 4.8 },
  { name: "Agent B", calls: 118, satisfaction: 4.6 },
  { name: "Agent C", calls: 135, satisfaction: 4.7 },
  { name: "Agent D", calls: 112, satisfaction: 4.5 },
  { name: "Agent E", calls: 128, satisfaction: 4.9 },
]

const callType = [
  { name: "Support", value: 52, fill: "#4ade80" },
  { name: "Sales", value: 28, fill: "#60a5fa" },
  { name: "Billing", value: 15, fill: "#f59e0b" },
  { name: "Complaint", value: 5, fill: "#ef4444" },
]

export function CallCenterModule() {
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Calls Today"
          value="1,847"
          change="+8.5%"
          changeType="positive"
          icon={Phone}
          description="vs last week"
        />
        <StatCard
          title="Avg Wait Time"
          value="42s"
          change="-8.2%"
          changeType="positive"
          icon={Clock}
          description="vs last week"
        />
        <StatCard
          title="Active Agents"
          value="48"
          change="+2"
          changeType="positive"
          icon={Users}
          description="on shift"
        />
        <StatCard
          title="Avg Handle Time"
          value="5m 32s"
          change="+12s"
          changeType="negative"
          icon={TrendingUp}
          description="vs last week"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Call Volume */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Call Volume Trend</h3>
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
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Call Type Distribution</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={callType}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}%`}
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
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Top Agent Performance</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={agentPerformance}>
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
