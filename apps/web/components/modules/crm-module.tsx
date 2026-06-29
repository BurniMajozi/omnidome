"use client"

import { useEffect, useState } from "react"
import { ModuleLayout } from "./module-layout"
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
import { Users, UserCheck, UserPlus, TrendingUp } from "lucide-react"
import {
  getActivities,
  getDashboardSummary,
  getInsights,
  getTasks,
  listCustomers,
  type Activity,
  type AiRecommendation,
  type CrmTask,
  type DashboardSummary,
  type Issue,
} from "@/lib/crm-api"

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const crmKpiIconMap: Record<string, JSX.Element> = {
  customers: <Users className="h-5 w-5 text-emerald-400" />,
  leads: <UserPlus className="h-5 w-5 text-blue-400" />,
  conversion: <UserCheck className="h-5 w-5 text-amber-400" />,
  revenue: <TrendingUp className="h-5 w-5 text-purple-400" />,
}

const tableColumns = [
  { key: "customer", label: "Customer Name" },
  { key: "type", label: "Type" },
  { key: "status", label: "Status" },
  { key: "revenue", label: "Monthly Revenue" },
  { key: "since", label: "Customer Since" },
  { key: "health", label: "Health Score" },
]

export function CrmModule() {
  const [summaryData, setSummaryData] = useState<DashboardSummary | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [tasks, setTasks] = useState<CrmTask[]>([])
  const [aiRecommendations, setAiRecommendations] = useState<AiRecommendation[]>([])
  const [issues, setIssues] = useState<Issue[]>([])
  const [tableData, setTableData] = useState<Record<string, unknown>[]>([])

  useEffect(() => {
    let cancelled = false

    async function load() {
      const [summary, activityFeed, taskList, insights, customers] = await Promise.all([
        getDashboardSummary(),
        getActivities(),
        getTasks(),
        getInsights(),
        listCustomers(5),
      ])
      if (cancelled) return
      setSummaryData(summary)
      setActivities(activityFeed)
      setTasks(taskList)
      setAiRecommendations(insights.aiRecommendations)
      setIssues(insights.issues)
      setTableData(
        customers.map((c) => ({
          id: c.id,
          customer: `${c.first_name} ${c.last_name}`,
          type: c.customer_type,
          status: c.status,
          revenue: formatCurrency(c.mrr),
          since: c.created_at?.slice(0, 10) ?? "",
          health: c.health,
        }))
      )
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const flashcardKPIsWithIcons = (summaryData?.flashcardKPIs ?? []).map((kpi) => ({
    ...kpi,
    icon: crmKpiIconMap[kpi.iconKey] ?? null,
  }))

  const summary = summaryData
    ? `${summaryData.totalCustomers} customers, ${summaryData.activeLeads} active leads, and a ${summaryData.conversionRate}% lead conversion rate. Average revenue per customer is ${formatCurrency(summaryData.avgRevenuePerCustomer)}.`
    : "Loading CRM summary..."

  return (
    <ModuleLayout
      title="CRM"
        icon={<Users className="h-5 w-5" />}
        subtitle="Customer relationships, pipeline health, and churn analytics"
      flashcardKPIs={flashcardKPIsWithIcons}
      activities={activities}
      issues={issues}
      summary={summary}
      tasks={tasks}
      aiRecommendations={aiRecommendations}
      tableData={tableData}
      tableColumns={tableColumns}
    >
      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Customer Growth & Churn */}
        <div className="surface-card p-5">
          <h3 className="section-title mb-4">Customer Growth & Churn</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={summaryData?.customerData ?? []}>
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
                <Line type="monotone" dataKey="customers" stroke="#4ade80" strokeWidth={2} name="Total Customers" />
                <Line type="monotone" dataKey="churn" stroke="#ef4444" strokeWidth={2} name="Churn" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Lead Generation & Conversion */}
        <div className="surface-card p-5">
          <h3 className="section-title mb-4">Lead Generation & Conversion</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summaryData?.leadData ?? []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="week" tick={{ fill: "#737373", fontSize: 12 }} />
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
                <Bar dataKey="leads" fill="#60a5fa" name="New Leads" />
                <Bar dataKey="converted" fill="#4ade80" name="Converted" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Customer Growth Trend */}
      <div className="surface-card p-5">
        <h3 className="section-title mb-4">Customer Base Trend</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={summaryData?.customerData ?? []}>
              <defs>
                <linearGradient id="colorEngagement" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                </linearGradient>
              </defs>
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
              <Area type="monotone" dataKey="customers" stroke="#60a5fa" fillOpacity={1} fill="url(#colorEngagement)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </ModuleLayout>
  )
}
