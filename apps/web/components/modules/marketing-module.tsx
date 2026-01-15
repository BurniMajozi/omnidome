"use client"

import { StatCard } from "@/components/dashboard/stat-card"
import {
  LineChart,
  Line,
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
import { Megaphone, TrendingUp, Target, Eye } from "lucide-react"

const campaignPerformance = [
  { month: "Jan", impressions: 45000, clicks: 2800, conversions: 280 },
  { month: "Feb", impressions: 52000, clicks: 3200, conversions: 340 },
  { month: "Mar", impressions: 48000, clicks: 3100, conversions: 310 },
  { month: "Apr", impressions: 61000, clicks: 4100, conversions: 450 },
  { month: "May", impressions: 58000, clicks: 3900, conversions: 420 },
  { month: "Jun", impressions: 72000, clicks: 5200, conversions: 620 },
]

const channelData = [
  { name: "Email", value: 32, fill: "#4ade80" },
  { name: "Social Media", value: 28, fill: "#60a5fa" },
  { name: "Search", value: 22, fill: "#a855f7" },
  { name: "Display", value: 18, fill: "#f59e0b" },
]

const campaignROI = [
  { campaign: "Summer Promo", roi: 3.2 },
  { campaign: "Back to School", roi: 2.8 },
  { campaign: "Holiday Sale", roi: 4.1 },
  { campaign: "Black Friday", roi: 5.2 },
  { campaign: "New Year", roi: 2.4 },
]

export function MarketingModule() {
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Active Campaigns"
          value="12"
          change="+3"
          changeType="positive"
          icon={Megaphone}
          description="this month"
        />
        <StatCard
          title="Total Impressions"
          value="2.4M"
          change="+24%"
          changeType="positive"
          icon={Eye}
          description="vs last month"
        />
        <StatCard
          title="Conversion Rate"
          value="3.2%"
          change="+0.8%"
          changeType="positive"
          icon={Target}
          description="vs last month"
        />
        <StatCard
          title="Marketing ROI"
          value="3.8x"
          change="+0.6x"
          changeType="positive"
          icon={TrendingUp}
          description="vs last quarter"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Campaign Performance */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Campaign Performance Trend</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={campaignPerformance}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
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
                <Line type="monotone" dataKey="impressions" stroke="#4ade80" strokeWidth={2} name="Impressions" />
                <Line type="monotone" dataKey="conversions" stroke="#60a5fa" strokeWidth={2} name="Conversions" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Channel Distribution */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Traffic by Channel</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={channelData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}%`}
                  outerRadius={80}
                  fill="#4ade80"
                  dataKey="value"
                >
                  {channelData.map((entry, index) => (
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

      {/* Campaign ROI */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Campaign ROI Comparison</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={campaignROI}>
              <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
              <XAxis dataKey="campaign" tick={{ fill: "#737373", fontSize: 12 }} />
              <YAxis
                label={{ value: "ROI Multiplier", angle: -90, position: "insideLeft" }}
                tick={{ fill: "#737373", fontSize: 12 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#262626",
                  border: "1px solid #404040",
                  borderRadius: "8px",
                  color: "#fff",
                }}
              />
              <Bar dataKey="roi" fill="#a855f7" name="ROI Multiplier" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
