"use client"

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

const customerData = [
  { month: "Jan", customers: 10200, churn: 45 },
  { month: "Feb", customers: 10850, churn: 38 },
  { month: "Mar", customers: 11200, churn: 42 },
  { month: "Apr", customers: 11950, churn: 35 },
  { month: "May", customers: 12400, churn: 32 },
  { month: "Jun", customers: 12847, churn: 28 },
]

const leadData = [
  { week: "Week 1", leads: 85, converted: 12 },
  { week: "Week 2", leads: 92, converted: 16 },
  { week: "Week 3", leads: 78, converted: 11 },
  { week: "Week 4", leads: 105, converted: 18 },
]

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const flashcardKPIs = [
  {
    id: "1",
    title: "Total Customers",
    value: "12,847",
    change: "+5.2%",
    changeType: "positive" as const,
    icon: <Users className="h-5 w-5 text-emerald-400" />,
    backTitle: "Customer Segments",
    backDetails: [
      { label: "Enterprise", value: "1,245" },
      { label: "SMB", value: "4,892" },
      { label: "Residential", value: "6,710" },
    ],
    backInsight: "Enterprise segment growing 15% faster",
  },
  {
    id: "2",
    title: "Active Leads",
    value: "342",
    change: "+14.8%",
    changeType: "positive" as const,
    icon: <UserPlus className="h-5 w-5 text-blue-400" />,
    backTitle: "Lead Sources",
    backDetails: [
      { label: "Website", value: "142" },
      { label: "Referrals", value: "98" },
      { label: "Field Sales", value: "102" },
    ],
    backInsight: "Referrals have highest conversion at 32%",
  },
  {
    id: "3",
    title: "Conversion Rate",
    value: "15.7%",
    change: "+2.3%",
    changeType: "positive" as const,
    icon: <UserCheck className="h-5 w-5 text-amber-400" />,
    backTitle: "Conversion by Channel",
    backDetails: [
      { label: "Direct Sales", value: "24.5%" },
      { label: "Online", value: "12.8%" },
      { label: "Partners", value: "18.2%" },
    ],
    backInsight: "Direct sales conversion up 5% this month",
  },
  {
    id: "4",
    title: "Customer Lifetime Value",
    value: formatCurrency(42500),
    change: "+8.9%",
    changeType: "positive" as const,
    icon: <TrendingUp className="h-5 w-5 text-purple-400" />,
    backTitle: "CLV by Segment",
    backDetails: [
      { label: "Enterprise", value: formatCurrency(185000) },
      { label: "SMB", value: formatCurrency(48000) },
      { label: "Residential", value: formatCurrency(12500) },
    ],
    backInsight: "Enterprise CLV increased 12% YoY",
  },
]

const activities = [
  {
    id: "1",
    user: "Emily Davis",
    action: "converted lead",
    target: "Acme Corp",
    time: "5 minutes ago",
    type: "create" as const,
  },
  {
    id: "2",
    user: "James Wilson",
    action: "updated profile for",
    target: "John Doe",
    time: "20 minutes ago",
    type: "update" as const,
  },
  {
    id: "3",
    user: "Maria Garcia",
    action: "logged call with",
    target: "Tech Solutions",
    time: "1 hour ago",
    type: "comment" as const,
  },
  {
    id: "4",
    user: "Robert Lee",
    action: "assigned lead to",
    target: "Sales Team A",
    time: "2 hours ago",
    type: "assign" as const,
  },
  {
    id: "5",
    user: "Anna Kim",
    action: "sent campaign to",
    target: "Q1 Prospects",
    time: "3 hours ago",
    type: "create" as const,
  },
]

const issues = [
  {
    id: "1",
    title: "Duplicate customer records detected",
    severity: "high" as const,
    status: "open" as const,
    assignee: "Emily Davis",
    time: "1 hour ago",
  },
  {
    id: "2",
    title: "Email bounce rate increased",
    severity: "medium" as const,
    status: "in-progress" as const,
    assignee: "James Wilson",
    time: "3 hours ago",
  },
  {
    id: "3",
    title: "Customer data sync failed",
    severity: "critical" as const,
    status: "open" as const,
    assignee: "IT Support",
    time: "4 hours ago",
  },
  {
    id: "4",
    title: "Lead scoring model needs update",
    severity: "low" as const,
    status: "resolved" as const,
    assignee: "Maria Garcia",
    time: "Yesterday",
  },
]

const summary = `Customer base has grown to 12,847 with a healthy 5.2% increase this month. The churn rate has decreased to 2.1%, our lowest in 6 months. Lead generation is strong with 342 active leads and a 15.7% conversion rate. The enterprise segment shows the highest growth potential with 15% faster acquisition. Customer satisfaction scores remain high at 4.6/5, with residential customers showing the most improvement. Focus areas include reducing duplicate records and improving email deliverability.`

const tasks = [
  {
    id: "1",
    title: "Clean up duplicate records",
    priority: "urgent" as const,
    status: "in-progress" as const,
    dueDate: "Today",
    assignee: "Emily Davis",
  },
  {
    id: "2",
    title: "Update customer segmentation",
    priority: "high" as const,
    status: "todo" as const,
    dueDate: "Tomorrow",
    assignee: "James Wilson",
  },
  {
    id: "3",
    title: "Review lead scoring criteria",
    priority: "normal" as const,
    status: "todo" as const,
    dueDate: "This week",
    assignee: "Maria Garcia",
  },
  {
    id: "4",
    title: "Send Q1 customer survey",
    priority: "normal" as const,
    status: "done" as const,
    dueDate: "Completed",
    assignee: "Anna Kim",
  },
]

const aiRecommendations = [
  {
    id: "1",
    title: "High Churn Risk Alert",
    description: "15 enterprise customers show reduced engagement. Initiate retention campaigns.",
    impact: "high" as const,
    category: "Retention",
  },
  {
    id: "2",
    title: "Upsell Opportunity",
    description: "87 SMB customers match enterprise upgrade criteria based on usage.",
    impact: "high" as const,
    category: "Growth",
  },
  {
    id: "3",
    title: "Lead Prioritization",
    description: "Focus on website leads this week - they show 40% higher intent signals.",
    impact: "medium" as const,
    category: "Sales",
  },
  {
    id: "4",
    title: "Data Quality",
    description: "Run deduplication process - estimated 3% duplicate rate affecting metrics.",
    impact: "medium" as const,
    category: "Operations",
  },
]

const tableData = [
  {
    id: "1",
    customer: "Telkom SA",
    type: "Enterprise",
    status: "Active",
    revenue: "R 2,400,000",
    since: "2019-03-15",
    health: "Excellent",
  },
  {
    id: "2",
    customer: "MTN Group",
    type: "Enterprise",
    status: "Active",
    revenue: "R 1,850,000",
    since: "2020-06-22",
    health: "Good",
  },
  {
    id: "3",
    customer: "Shoprite Holdings",
    type: "Enterprise",
    status: "Active",
    revenue: "R 980,000",
    since: "2021-01-10",
    health: "At Risk",
  },
  {
    id: "4",
    customer: "Pick n Pay",
    type: "SMB",
    status: "Active",
    revenue: "R 450,000",
    since: "2022-04-18",
    health: "Good",
  },
  {
    id: "5",
    customer: "Woolworths",
    type: "Enterprise",
    status: "Active",
    revenue: "R 1,200,000",
    since: "2020-11-05",
    health: "Excellent",
  },
]

const tableColumns = [
  { key: "customer", label: "Customer Name" },
  { key: "type", label: "Type" },
  { key: "status", label: "Status" },
  { key: "revenue", label: "Annual Revenue" },
  { key: "since", label: "Customer Since" },
  { key: "health", label: "Health Score" },
]

export function CrmModule() {
  return (
    <ModuleLayout
      title="CRM"
      flashcardKPIs={flashcardKPIs}
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
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Customer Growth & Churn</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={customerData}>
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
                <Line type="monotone" dataKey="churn" stroke="#ef4444" strokeWidth={2} name="Churn Rate" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Lead Generation & Conversion */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Lead Generation & Conversion</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={leadData}>
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

      {/* Customer Segments */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Customer Engagement Score</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={customerData}>
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
