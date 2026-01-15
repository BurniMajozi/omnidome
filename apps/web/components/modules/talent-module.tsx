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
import { UserCog, TrendingUp, Users, Target } from "lucide-react"

const employeeGrowth = [
  { month: "Jan", employees: 215, hired: 8, separated: 2 },
  { month: "Feb", employees: 220, hired: 6, separated: 1 },
  { month: "Mar", employees: 225, hired: 7, separated: 2 },
  { month: "Apr", employees: 232, hired: 9, separated: 2 },
  { month: "May", employees: 240, hired: 10, separated: 2 },
  { month: "Jun", employees: 248, hired: 12, separated: 4 },
]

const departmentStaff = [
  { department: "Sales", count: 48 },
  { department: "Service", count: 52 },
  { department: "Network", count: 38 },
  { department: "Marketing", count: 22 },
  { department: "HR", count: 18 },
  { department: "Admin", count: 70 },
]

const turnoverData = [
  { name: "Sales", value: 8, fill: "#ef4444" },
  { name: "Service", value: 5, fill: "#f97316" },
  { name: "Network", value: 3, fill: "#eab308" },
  { name: "Admin", value: 4, fill: "#4ade80" },
]

export function TalentModule() {
  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Employees"
          value="248"
          change="+3.3%"
          changeType="positive"
          icon={UserCog}
          description="vs last month"
        />
        <StatCard
          title="Open Positions"
          value="14"
          change="+2"
          changeType="negative"
          icon={Target}
          description="vs last month"
        />
        <StatCard
          title="Avg Employee Rating"
          value="4.2/5"
          change="+0.2"
          changeType="positive"
          icon={TrendingUp}
          description="engagement score"
        />
        <StatCard
          title="Turnover Rate"
          value="6.4%"
          change="-1.2%"
          changeType="positive"
          icon={Users}
          description="annualized"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Employee Growth */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Employee Growth & Turnover</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={employeeGrowth}>
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
                <Bar dataKey="hired" fill="#4ade80" name="Hired" />
                <Bar dataKey="separated" fill="#ef4444" name="Separated" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Department Staffing */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Headcount by Department</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={departmentStaff} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis type="number" tick={{ fill: "#737373", fontSize: 12 }} />
                <YAxis type="category" dataKey="department" tick={{ fill: "#737373", fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#262626",
                    border: "1px solid #404040",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                />
                <Bar dataKey="count" fill="#60a5fa" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Turnover by Department */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Turnover by Department</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={turnoverData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value }) => `${name}: ${value}`}
                outerRadius={80}
                fill="#4ade80"
                dataKey="value"
              >
                {turnoverData.map((entry, index) => (
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
  )
}
