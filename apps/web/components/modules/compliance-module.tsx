"use client"

import { StatCard } from "@/components/dashboard/stat-card"
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts"
import { ShieldCheck, AlertTriangle, CheckCircle, Zap } from "lucide-react"

const complianceScore = [
  { month: "Jan", score: 88 },
  { month: "Feb", score: 90 },
  { month: "Mar", score: 91 },
  { month: "Apr", score: 93 },
  { month: "May", score: 94 },
  { month: "Jun", score: 94 },
]

const riskAssessment = [
  { name: "Critical", value: 1, fill: "#ef4444" },
  { name: "High", value: 3, fill: "#f97316" },
  { name: "Medium", value: 6, fill: "#eab308" },
  { name: "Low", value: 15, fill: "#4ade80" },
]

const complianceFramework = [
  { framework: "GDPR", compliance: 95 },
  { framework: "CCPA", compliance: 92 },
  { framework: "HIPAA", compliance: 89 },
  { framework: "SOC 2", compliance: 96 },
  { framework: "ISO 27001", compliance: 90 },
]

export function ComplianceModule() {
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Compliance Score"
          value="94%"
          change="+2%"
          changeType="positive"
          icon={ShieldCheck}
          description="vs last month"
        />
        <StatCard
          title="Open Issues"
          value="7"
          change="-3"
          changeType="positive"
          icon={AlertTriangle}
          description="vs last month"
        />
        <StatCard
          title="Audit Status"
          value="Passed"
          change="Latest audit"
          changeType="positive"
          icon={CheckCircle}
          description="2 weeks ago"
        />
        <StatCard
          title="Remediation Rate"
          value="89%"
          change="+5%"
          changeType="positive"
          icon={Zap}
          description="vs last month"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Compliance Score Trend */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Compliance Score Trend</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={complianceScore}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                <YAxis domain={[80, 100]} tick={{ fill: "#737373", fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#262626",
                    border: "1px solid #404040",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                />
                <Line type="monotone" dataKey="score" stroke="#4ade80" strokeWidth={2} name="Score %" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Risk Assessment */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Risk Assessment</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={riskAssessment}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}`}
                  outerRadius={80}
                  fill="#4ade80"
                  dataKey="value"
                >
                  {riskAssessment.map((entry, index) => (
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

      {/* Compliance Framework Status */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Regulatory Framework Compliance</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={complianceFramework}>
              <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
              <XAxis dataKey="framework" tick={{ fill: "#737373", fontSize: 12 }} />
              <YAxis domain={[0, 100]} tick={{ fill: "#737373", fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#262626",
                  border: "1px solid #404040",
                  borderRadius: "8px",
                  color: "#fff",
                }}
              />
              <Bar dataKey="compliance" fill="#4ade80" name="Compliance %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
