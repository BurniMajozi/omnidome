"use client"

import { ModuleLayout } from "./module-layout"
import {
  BarChart,
  Bar,
  LineChart,
  Line,
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
import { Headset, Clock, CheckCircle, AlertCircle } from "lucide-react"

const ticketTrend = [
  { day: "Mon", open: 28, resolved: 32 },
  { day: "Tue", open: 35, resolved: 28 },
  { day: "Wed", open: 42, resolved: 35 },
  { day: "Thu", open: 38, resolved: 40 },
  { day: "Fri", open: 28, resolved: 45 },
  { day: "Sat", open: 15, resolved: 18 },
  { day: "Sun", open: 12, resolved: 14 },
]

const ticketsByPriority = [
  { name: "Critical", value: 8, fill: "#ef4444" },
  { name: "High", value: 32, fill: "#f97316" },
  { name: "Medium", value: 52, fill: "#eab308" },
  { name: "Low", value: 36, fill: "#4ade80" },
]

const resolutionTime = [
  { priority: "Critical", time: 1.2 },
  { priority: "High", time: 2.8 },
  { priority: "Medium", time: 4.5 },
  { priority: "Low", time: 8.3 },
]

const flashcardKPIs = [
  {
    id: "1",
    title: "Open Tickets",
    value: "128",
    change: "-24%",
    changeType: "positive" as const,
    icon: <AlertCircle className="h-5 w-5 text-amber-400" />,
    backTitle: "Ticket Breakdown",
    backDetails: [
      { label: "Critical", value: "8" },
      { label: "High", value: "32" },
      { label: "Medium/Low", value: "88" },
    ],
    backInsight: "Critical tickets down 40% from last week",
  },
  {
    id: "2",
    title: "Avg Resolution Time",
    value: "4.2h",
    change: "-15%",
    changeType: "positive" as const,
    icon: <Clock className="h-5 w-5 text-blue-400" />,
    backTitle: "Resolution by Priority",
    backDetails: [
      { label: "Critical", value: "1.2h" },
      { label: "High", value: "2.8h" },
      { label: "Medium/Low", value: "6.4h" },
    ],
    backInsight: "SLA compliance at 98.5%",
  },
  {
    id: "3",
    title: "CSAT Score",
    value: "4.6/5",
    change: "+0.3",
    changeType: "positive" as const,
    icon: <CheckCircle className="h-5 w-5 text-emerald-400" />,
    backTitle: "Satisfaction Breakdown",
    backDetails: [
      { label: "5 Stars", value: "68%" },
      { label: "4 Stars", value: "24%" },
      { label: "1-3 Stars", value: "8%" },
    ],
    backInsight: "Highest score in 12 months",
  },
  {
    id: "4",
    title: "SLA Compliance",
    value: "98.5%",
    change: "+1.2%",
    changeType: "positive" as const,
    icon: <Headset className="h-5 w-5 text-purple-400" />,
    backTitle: "SLA by Category",
    backDetails: [
      { label: "Response Time", value: "99.2%" },
      { label: "Resolution Time", value: "97.8%" },
      { label: "First Contact", value: "98.5%" },
    ],
    backInsight: "Only 2 SLA breaches this month",
  },
]

const activities = [
  {
    id: "1",
    user: "Tech Support",
    action: "resolved ticket",
    target: "TKT-4521",
    time: "3 minutes ago",
    type: "update" as const,
  },
  {
    id: "2",
    user: "John Nkosi",
    action: "escalated ticket",
    target: "TKT-4518",
    time: "15 minutes ago",
    type: "assign" as const,
  },
  {
    id: "3",
    user: "Sarah Mbeki",
    action: "updated status of",
    target: "TKT-4515",
    time: "30 minutes ago",
    type: "update" as const,
  },
  {
    id: "4",
    user: "Field Team",
    action: "dispatched for",
    target: "TKT-4512",
    time: "1 hour ago",
    type: "create" as const,
  },
  {
    id: "5",
    user: "Customer",
    action: "rated service",
    target: "5 stars",
    time: "2 hours ago",
    type: "comment" as const,
  },
]

const issues = [
  {
    id: "1",
    title: "Network outage in Johannesburg North",
    severity: "critical" as const,
    status: "in-progress" as const,
    assignee: "Network Team",
    time: "30 min ago",
  },
  {
    id: "2",
    title: "Billing system slow response",
    severity: "high" as const,
    status: "open" as const,
    assignee: "IT Support",
    time: "1 hour ago",
  },
  {
    id: "3",
    title: "Customer portal login issues",
    severity: "medium" as const,
    status: "in-progress" as const,
    assignee: "Dev Team",
    time: "2 hours ago",
  },
  {
    id: "4",
    title: "Email notifications delayed",
    severity: "low" as const,
    status: "resolved" as const,
    assignee: "IT Support",
    time: "Yesterday",
  },
]

const summary = `Service desk performance is strong with 128 open tickets, down 24% from last week. Average resolution time improved to 4.2 hours, a 15% reduction. CSAT score reached 4.6/5, our highest in 12 months. SLA compliance is at 98.5% with only 2 breaches this month. The team resolved 212 tickets this week, with the network outage in Johannesburg North being the most significant ongoing issue. Focus areas include reducing critical ticket volume and maintaining the improved resolution times.`

const tasks = [
  {
    id: "1",
    title: "Resolve Johannesburg network outage",
    priority: "urgent" as const,
    status: "in-progress" as const,
    dueDate: "Today",
    assignee: "Network Team",
  },
  {
    id: "2",
    title: "Update knowledge base articles",
    priority: "high" as const,
    status: "todo" as const,
    dueDate: "Tomorrow",
    assignee: "Sarah Mbeki",
  },
  {
    id: "3",
    title: "Review escalation procedures",
    priority: "normal" as const,
    status: "todo" as const,
    dueDate: "This week",
    assignee: "John Nkosi",
  },
  {
    id: "4",
    title: "Complete Q1 service report",
    priority: "normal" as const,
    status: "done" as const,
    dueDate: "Completed",
    assignee: "Manager",
  },
]

const aiRecommendations = [
  {
    id: "1",
    title: "Pattern Detected",
    description: "20% of tickets relate to router firmware. Consider proactive firmware update campaign.",
    impact: "high" as const,
    category: "Prevention",
  },
  {
    id: "2",
    title: "Resource Optimization",
    description: "Tuesday/Wednesday have 40% more tickets. Adjust staffing accordingly.",
    impact: "medium" as const,
    category: "Staffing",
  },
  {
    id: "3",
    title: "Knowledge Gap",
    description: "VoIP setup queries increased 60%. Create video tutorial for self-service.",
    impact: "medium" as const,
    category: "Self-Service",
  },
  {
    id: "4",
    title: "Escalation Alert",
    description: "3 tickets approaching SLA breach in next 2 hours. Prioritize immediately.",
    impact: "high" as const,
    category: "SLA",
  },
]

const tableData = [
  {
    id: "1",
    ticket: "TKT-4521",
    customer: "Thabo Mokoena",
    issue: "No internet connection",
    priority: "High",
    status: "Resolved",
    created: "2024-01-12",
    agent: "Tech Support",
  },
  {
    id: "2",
    ticket: "TKT-4520",
    customer: "Sipho Ndlovu",
    issue: "Slow speeds",
    priority: "Medium",
    status: "In Progress",
    created: "2024-01-12",
    agent: "Sarah Mbeki",
  },
  {
    id: "3",
    ticket: "TKT-4519",
    customer: "Nomvula Dlamini",
    issue: "Billing query",
    priority: "Low",
    status: "Open",
    created: "2024-01-12",
    agent: "Unassigned",
  },
  {
    id: "4",
    ticket: "TKT-4518",
    customer: "Johan van der Merwe",
    issue: "VoIP not working",
    priority: "Critical",
    status: "Escalated",
    created: "2024-01-12",
    agent: "John Nkosi",
  },
  {
    id: "5",
    ticket: "TKT-4517",
    customer: "Lerato Molefe",
    issue: "Router replacement",
    priority: "Medium",
    status: "Pending",
    created: "2024-01-11",
    agent: "Field Team",
  },
]

const tableColumns = [
  { key: "ticket", label: "Ticket ID" },
  { key: "customer", label: "Customer" },
  { key: "issue", label: "Issue" },
  { key: "priority", label: "Priority" },
  { key: "status", label: "Status" },
  { key: "created", label: "Created" },
  { key: "agent", label: "Agent" },
]

export function ServiceModule() {
  return (
    <ModuleLayout
      title="Service"
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
        {/* Ticket Trend */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Daily Ticket Activity</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ticketTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                <XAxis dataKey="day" tick={{ fill: "#737373", fontSize: 12 }} />
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
                <Bar dataKey="open" fill="#ef4444" name="Open" />
                <Bar dataKey="resolved" fill="#4ade80" name="Resolved" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Tickets by Priority */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-lg font-semibold text-foreground">Tickets by Priority</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={ticketsByPriority}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}`}
                  outerRadius={80}
                  fill="#4ade80"
                  dataKey="value"
                >
                  {ticketsByPriority.map((entry, index) => (
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

      {/* Resolution Time by Priority */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-4 text-lg font-semibold text-foreground">Avg Resolution Time by Priority</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={resolutionTime}>
              <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
              <XAxis dataKey="priority" tick={{ fill: "#737373", fontSize: 12 }} />
              <YAxis
                label={{ value: "Hours", angle: -90, position: "insideLeft", fill: "#737373" }}
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
              <Line type="monotone" dataKey="time" stroke="#60a5fa" strokeWidth={2} name="Resolution Time (hrs)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </ModuleLayout>
  )
}
