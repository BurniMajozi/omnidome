"use client"

import { ModuleLayout } from "./module-layout"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  FunnelChart,
  Funnel,
  LabelList,
  Cell,
} from "recharts"
import { DollarSign, TrendingUp, Target, Users } from "lucide-react"

const salesData = [
  { month: "Jan", revenue: 450000, deals: 12 },
  { month: "Feb", revenue: 520000, deals: 15 },
  { month: "Mar", revenue: 480000, deals: 14 },
  { month: "Apr", revenue: 610000, deals: 18 },
  { month: "May", revenue: 580000, deals: 16 },
  { month: "Jun", revenue: 720000, deals: 21 },
]

const pipelineData = [
  { name: "Prospecting", value: 45, fill: "#4ade80" },
  { name: "Negotiation", value: 35, fill: "#60a5fa" },
  { name: "Closed Won", value: 20, fill: "#a855f7" },
]

const topProducts = [
  { name: "Business Fiber", value: 42 },
  { name: "Home Broadband", value: 28 },
  { name: "VoIP Bundle", value: 18 },
  { name: "Cloud Services", value: 12 },
]

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const flashcardKPIs = [
  {
    id: "1",
    title: "Monthly Revenue",
    value: formatCurrency(2840000),
    change: "+18.5%",
    changeType: "positive" as const,
    icon: <DollarSign className="h-5 w-5 text-emerald-400" />,
    backTitle: "Revenue Breakdown",
    backDetails: [
      { label: "New Business", value: formatCurrency(1420000) },
      { label: "Renewals", value: formatCurrency(980000) },
      { label: "Upsells", value: formatCurrency(440000) },
    ],
    backInsight: "New business revenue up 24% this quarter",
  },
  {
    id: "2",
    title: "Total Deals",
    value: "47",
    change: "+12.2%",
    changeType: "positive" as const,
    icon: <Target className="h-5 w-5 text-blue-400" />,
    backTitle: "Deal Analysis",
    backDetails: [
      { label: "Won", value: "32" },
      { label: "Lost", value: "8" },
      { label: "Pending", value: "7" },
    ],
    backInsight: "Win rate improved to 80% from 72%",
  },
  {
    id: "3",
    title: "Pipeline Value",
    value: formatCurrency(18000000),
    change: "+8.3%",
    changeType: "positive" as const,
    icon: <TrendingUp className="h-5 w-5 text-amber-400" />,
    backTitle: "Pipeline Stages",
    backDetails: [
      { label: "Prospecting", value: formatCurrency(8100000) },
      { label: "Negotiation", value: formatCurrency(6300000) },
      { label: "Closing", value: formatCurrency(3600000) },
    ],
    backInsight: "45% of pipeline in late stages",
  },
  {
    id: "4",
    title: "Avg Deal Size",
    value: formatCurrency(384000),
    change: "+5.1%",
    changeType: "positive" as const,
    icon: <Users className="h-5 w-5 text-purple-400" />,
    backTitle: "Deal Size Distribution",
    backDetails: [
      { label: "Enterprise", value: formatCurrency(850000) },
      { label: "SMB", value: formatCurrency(280000) },
      { label: "Residential", value: formatCurrency(45000) },
    ],
    backInsight: "Enterprise deals growing fastest at 32%",
  },
]

const activities = [
  {
    id: "1",
    user: "John Smith",
    action: "closed deal with",
    target: "Telkom SA",
    time: "2 minutes ago",
    type: "create" as const,
  },
  {
    id: "2",
    user: "Sarah Jones",
    action: "updated proposal for",
    target: "MTN Group",
    time: "15 minutes ago",
    type: "update" as const,
  },
  {
    id: "3",
    user: "Mike Brown",
    action: "scheduled meeting with",
    target: "Vodacom",
    time: "1 hour ago",
    type: "create" as const,
  },
  {
    id: "4",
    user: "Lisa Chen",
    action: "sent contract to",
    target: "Dimension Data",
    time: "2 hours ago",
    type: "create" as const,
  },
  {
    id: "5",
    user: "David Wilson",
    action: "added notes to",
    target: "Cell C deal",
    time: "3 hours ago",
    type: "comment" as const,
  },
]

const issues = [
  {
    id: "1",
    title: "Quote approval delayed for MTN deal",
    severity: "high" as const,
    status: "open" as const,
    assignee: "Sarah Jones",
    time: "2 hours ago",
  },
  {
    id: "2",
    title: "Pricing discrepancy in Vodacom proposal",
    severity: "medium" as const,
    status: "in-progress" as const,
    assignee: "Mike Brown",
    time: "4 hours ago",
  },
  {
    id: "3",
    title: "Contract terms need legal review",
    severity: "high" as const,
    status: "open" as const,
    assignee: "John Smith",
    time: "Yesterday",
  },
  {
    id: "4",
    title: "Customer credit check pending",
    severity: "low" as const,
    status: "resolved" as const,
    assignee: "Lisa Chen",
    time: "2 days ago",
  },
]

const summary = `This month's sales performance shows strong growth with R2.84M in revenue, an 18.5% increase from last month. The team closed 47 deals with an average deal size of R384K. The pipeline is healthy at R18M with 45% of opportunities in late stages. Key wins include contracts with Telkom SA and Dimension Data. Focus areas for next month include improving conversion rates in the negotiation stage and expanding enterprise segment penetration.`

const tasks = [
  {
    id: "1",
    title: "Follow up on MTN proposal",
    priority: "urgent" as const,
    status: "todo" as const,
    dueDate: "Today",
    assignee: "Sarah Jones",
  },
  {
    id: "2",
    title: "Prepare Q2 sales forecast",
    priority: "high" as const,
    status: "in-progress" as const,
    dueDate: "Tomorrow",
    assignee: "John Smith",
  },
  {
    id: "3",
    title: "Update CRM with new leads",
    priority: "normal" as const,
    status: "todo" as const,
    dueDate: "This week",
    assignee: "Mike Brown",
  },
  {
    id: "4",
    title: "Complete sales training module",
    priority: "low" as const,
    status: "done" as const,
    dueDate: "Completed",
    assignee: "Lisa Chen",
  },
]

const aiRecommendations = [
  {
    id: "1",
    title: "Prioritize Vodacom Deal",
    description: "Based on engagement patterns, Vodacom is 85% likely to close this week. Schedule a final call.",
    impact: "high" as const,
    category: "Sales",
  },
  {
    id: "2",
    title: "Upsell Opportunity",
    description: "3 existing customers show interest in VoIP bundles based on usage patterns.",
    impact: "medium" as const,
    category: "Upsell",
  },
  {
    id: "3",
    title: "At-Risk Deal Alert",
    description: "Cell C deal has been stagnant for 2 weeks. Consider offering incentive.",
    impact: "high" as const,
    category: "Risk",
  },
  {
    id: "4",
    title: "Optimize Pricing",
    description: "Competitors reduced fiber pricing by 8%. Review pricing strategy.",
    impact: "medium" as const,
    category: "Strategy",
  },
]

const tableData = [
  {
    id: "1",
    deal: "Telkom SA - Fiber Upgrade",
    value: "R 850,000",
    stage: "Closed Won",
    probability: "100%",
    closeDate: "2024-01-10",
    owner: "John Smith",
  },
  {
    id: "2",
    deal: "MTN Group - Enterprise Package",
    value: "R 1,200,000",
    stage: "Negotiation",
    probability: "75%",
    closeDate: "2024-01-20",
    owner: "Sarah Jones",
  },
  {
    id: "3",
    deal: "Vodacom - Data Center",
    value: "R 2,400,000",
    stage: "Proposal",
    probability: "60%",
    closeDate: "2024-02-01",
    owner: "Mike Brown",
  },
  {
    id: "4",
    deal: "Dimension Data - Cloud",
    value: "R 680,000",
    stage: "Closed Won",
    probability: "100%",
    closeDate: "2024-01-08",
    owner: "Lisa Chen",
  },
  {
    id: "5",
    deal: "Cell C - Network Services",
    value: "R 450,000",
    stage: "Discovery",
    probability: "30%",
    closeDate: "2024-02-15",
    owner: "David Wilson",
  },
]

const tableColumns = [
  { key: "deal", label: "Deal Name" },
  { key: "value", label: "Value" },
  { key: "stage", label: "Stage" },
  { key: "probability", label: "Probability" },
  { key: "closeDate", label: "Close Date" },
  { key: "owner", label: "Owner" },
]

export function SalesModule() {
  return (
    <ModuleLayout
      title="Sales"
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
        {/* Revenue & Deals Chart */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Revenue & Deals Trend</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={salesData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="month" tick={{ fill: "#737373", fontSize: 12 }} />
                <YAxis tick={{ fill: "#737373", fontSize: 12 }} tickFormatter={(v) => `R${v / 1000}K`} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#262626",
                    border: "1px solid #404040",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                  formatter={(value: number, name: string) => [
                    name === "revenue" ? formatCurrency(value) : value,
                    name === "revenue" ? "Revenue" : "Deals",
                  ]}
                />
                <Legend />
                <Bar dataKey="revenue" fill="#4ade80" name="Revenue" />
                <Bar dataKey="deals" fill="#60a5fa" name="Deals" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Sales Pipeline */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Sales Pipeline</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <FunnelChart>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#262626",
                    border: "1px solid #404040",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                />
                <Funnel dataKey="value" data={pipelineData} isAnimationActive>
                  <LabelList position="right" fill="#8884d8" stroke="none" dataKey="name" />
                </Funnel>
              </FunnelChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Top Products */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Top Selling Products</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={topProducts} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
              <XAxis type="number" tick={{ fill: "#737373", fontSize: 12 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: "#737373", fontSize: 12 }} width={120} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#262626",
                  border: "1px solid #404040",
                  borderRadius: "8px",
                  color: "#fff",
                }}
              />
              <Bar dataKey="value" fill="#a855f7" name="Sales %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </ModuleLayout>
  )
}
