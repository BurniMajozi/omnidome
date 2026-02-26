"use client"

import { useMemo, useState } from "react"
import { StatCard } from "@/components/dashboard/stat-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
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
import {
  BarChart3,
  BookOpen,
  Briefcase,
  Building2,
  CalendarDays,
  ChevronDown,
  Gift,
  IdCard,
  Laptop,
  ShieldCheck,
  Sparkles,
  Users,
  UserCog,
  Target,
  TrendingUp,
} from "lucide-react"
import { useModuleData } from "@/lib/module-data"

const defaultEmployeeGrowth = [
  { month: "Jan", employees: 215, hired: 8, separated: 2 },
  { month: "Feb", employees: 220, hired: 6, separated: 1 },
  { month: "Mar", employees: 225, hired: 7, separated: 2 },
  { month: "Apr", employees: 232, hired: 9, separated: 2 },
  { month: "May", employees: 240, hired: 10, separated: 2 },
  { month: "Jun", employees: 248, hired: 12, separated: 4 },
]

const defaultDepartmentStaff = [
  { department: "Sales", count: 48 },
  { department: "Service", count: 52 },
  { department: "Network", count: 38 },
  { department: "Marketing", count: 22 },
  { department: "HR", count: 18 },
  { department: "Admin", count: 70 },
]

const defaultTurnoverData = [
  { name: "Sales", value: 8, fill: "#ef4444" },
  { name: "Service", value: 5, fill: "#f97316" },
  { name: "Network", value: 3, fill: "#eab308" },
  { name: "Admin", value: 4, fill: "#4ade80" },
]

type StaffPanelKey =
  | "onboarding"
  | "directory"
  | "hiring"
  | "payroll"
  | "time"
  | "performance"
  | "culture"
  | "governance"

const panelConfig: {
  key: StaffPanelKey
  title: string
  icon: React.ComponentType<{ className?: string }>
  tags: string[]
}[] = [
  {
    key: "onboarding",
    title: "Onboarding & Knowledge",
    icon: BookOpen,
    tags: ["Employee Onboarding", "HR Knowledge Base"],
  },
  {
    key: "directory",
    title: "Directory & Org",
    icon: Building2,
    tags: ["Company Org Chart", "Pictures"],
  },
  {
    key: "hiring",
    title: "Hiring (ATS)",
    icon: Briefcase,
    tags: ["Applicant Tracker"],
  },
  {
    key: "payroll",
    title: "Payroll & Benefits",
    icon: Gift,
    tags: ["Payroll via Paystack", "Employee Benefit Management"],
  },
  {
    key: "time",
    title: "Time & Planning",
    icon: CalendarDays,
    tags: ["Leave Management", "Demand-Based Scheduling"],
  },
  {
    key: "performance",
    title: "Performance & Insights",
    icon: BarChart3,
    tags: ["KPI Management", "Surveys", "Attrition Prediction"],
  },
  {
    key: "culture",
    title: "Culture & Recognition",
    icon: Sparkles,
    tags: ["Kudos", "Birthdays & Milestones"],
  },
  {
    key: "governance",
    title: "Governance & Assets",
    icon: ShieldCheck,
    tags: ["Access Control", "Role-Based Access", "Asset Allocation", "Retirement", "Retrenchment"],
  },
]

function PanelTag({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
      {children}
    </span>
  )
}

export function TalentModule() {
  const [activePanel, setActivePanel] = useState<StaffPanelKey>("onboarding")
  const [knowledgeQuery, setKnowledgeQuery] = useState("")

  const { data } = useModuleData("talent", {
    employeeGrowth: defaultEmployeeGrowth,
    departmentStaff: defaultDepartmentStaff,
    turnoverData: defaultTurnoverData,
  })

  const { employeeGrowth, departmentStaff, turnoverData } = data

  const activePanelMeta = useMemo(
    () => panelConfig.find((panel) => panel.key === activePanel) ?? panelConfig[0],
    [activePanel],
  )

  const onboardingChecklist = [
    { task: "Create employee profile", owner: "HR", status: "Done" },
    { task: "Collect compliance docs", owner: "Employee", status: "In Progress" },
    { task: "Allocate laptop and access", owner: "IT", status: "To Do" },
    { task: "Add to org chart and directory", owner: "HR", status: "To Do" },
    { task: "Payroll + benefits enrollment", owner: "Finance", status: "To Do" },
  ]

  const knowledgeBaseArticles = useMemo(
    () =>
      [
        { title: "Leave policy", category: "Policy", updated: "2 days ago" },
        { title: "Performance review cadence", category: "Process", updated: "1 week ago" },
        { title: "Device and asset allocation", category: "IT", updated: "3 weeks ago" },
        { title: "Benefits enrollment guide", category: "Benefits", updated: "1 month ago" },
      ].filter((article) => article.title.toLowerCase().includes(knowledgeQuery.trim().toLowerCase())),
    [knowledgeQuery],
  )

  const applicantRows = [
    { name: "A. Ndlovu", role: "Support Agent", stage: "Interview", score: "82" },
    { name: "K. Patel", role: "Sales Exec", stage: "Offer", score: "91" },
    { name: "S. Maseko", role: "Network Tech", stage: "Screen", score: "76" },
  ]

  const leaveRequests = [
    { employee: "T. Mokoena", dates: "Mar 3–7", type: "Annual", status: "Pending" },
    { employee: "J. Naidoo", dates: "Feb 18", type: "Sick", status: "Approved" },
    { employee: "P. Dlamini", dates: "Apr 10–12", type: "Annual", status: "Pending" },
  ]

  const assetAllocations = [
    { employee: "K. Patel", asset: "Laptop", ref: "MBP-1142", status: "Assigned" },
    { employee: "S. Maseko", asset: "Company Car", ref: "GP-CA-7721", status: "Assigned" },
    { employee: "A. Ndlovu", asset: "Laptop", ref: "DELL-2209", status: "Pending" },
  ]

  const renderActivePanel = () => {
    switch (activePanel) {
      case "onboarding":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IdCard className="h-4 w-4 text-muted-foreground" /> Onboarding checklist
                </CardTitle>
                <CardDescription>Track the first 30 days with owners and statuses.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Task</th>
                        <th className="py-2 pr-4 font-medium">Owner</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {onboardingChecklist.map((row) => (
                        <tr key={row.task} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.task}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.owner}</td>
                          <td className="py-3 pr-4">
                            <Badge
                              variant="outline"
                              className={
                                row.status === "Done"
                                  ? "border-emerald-500/40 text-emerald-500"
                                  : row.status === "In Progress"
                                    ? "border-amber-500/40 text-amber-500"
                                    : "border-muted text-muted-foreground"
                              }
                            >
                              {row.status}
                            </Badge>
                          </td>
                          <td className="py-3">
                            <Button size="sm" variant="outline">
                              View
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-muted-foreground" /> HR knowledge base
                </CardTitle>
                <CardDescription>Search and publish policies, guides, and templates.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="w-full sm:max-w-sm">
                    <Input
                      value={knowledgeQuery}
                      onChange={(event) => setKnowledgeQuery(event.target.value)}
                      placeholder="Search articles…"
                    />
                  </div>
                  <Button variant="outline">New article</Button>
                </div>
                <div className="mt-4 space-y-3">
                  {knowledgeBaseArticles.map((article) => (
                    <div key={article.title} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                      <div>
                        <p className="font-medium text-foreground">{article.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {article.category} · Updated {article.updated}
                        </p>
                      </div>
                      <Button size="sm" variant="ghost">
                        Open
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "directory":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" /> Company org chart
                </CardTitle>
                <CardDescription>A living structure that updates with hires, moves, and exits.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-2">
                  {[
                    { leader: "CEO", team: "Executive", members: 6 },
                    { leader: "Head of Sales", team: "Sales", members: 48 },
                    { leader: "Head of Service", team: "Service", members: 52 },
                    { leader: "Head of Network", team: "Network", members: 38 },
                  ].map((node) => (
                    <div key={node.team} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="text-sm font-semibold text-foreground">{node.team}</p>
                      <p className="text-xs text-muted-foreground">{node.leader}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{node.members} people</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-muted-foreground" /> Employee directory
                </CardTitle>
                <CardDescription>Profiles, pictures, and current team/role assignments.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee</th>
                        <th className="py-2 pr-4 font-medium">Department</th>
                        <th className="py-2 pr-4 font-medium">Role</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { name: "Thandi Mokoena", dept: "HR", role: "HR Lead", status: "Active" },
                        { name: "Kiran Patel", dept: "Sales", role: "Sales Exec", status: "Active" },
                        { name: "Sibusiso Maseko", dept: "Network", role: "Technician", status: "Onboarding" },
                      ].map((row) => (
                        <tr key={row.name} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.name}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.dept}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.role}</td>
                          <td className="py-3 pr-4">
                            <Badge
                              variant="outline"
                              className={row.status === "Active" ? "border-emerald-500/40 text-emerald-500" : "border-amber-500/40 text-amber-500"}
                            >
                              {row.status}
                            </Badge>
                          </td>
                          <td className="py-3">
                            <Button size="sm" variant="outline">
                              Open
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "hiring":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Briefcase className="h-4 w-4 text-muted-foreground" /> Applicant tracker (ATS)
                </CardTitle>
                <CardDescription>Move candidates through stages with clear ownership.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-4">
                  {[
                    { label: "Screen", value: 6 },
                    { label: "Interview", value: 3 },
                    { label: "Offer", value: 2 },
                    { label: "Hired", value: 1 },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="text-xs text-muted-foreground">{metric.label}</p>
                      <p className="mt-1 text-2xl font-semibold text-foreground">{metric.value}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-5 overflow-x-auto">
                  <table className="w-full min-w-[680px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Candidate</th>
                        <th className="py-2 pr-4 font-medium">Role</th>
                        <th className="py-2 pr-4 font-medium">Stage</th>
                        <th className="py-2 pr-4 font-medium">Score</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {applicantRows.map((row) => (
                        <tr key={row.name} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.name}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.role}</td>
                          <td className="py-3 pr-4">
                            <Badge variant="outline" className="border-muted text-muted-foreground">
                              {row.stage}
                            </Badge>
                          </td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.score}</td>
                          <td className="py-3">
                            <Button size="sm" variant="outline">
                              Review
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "payroll":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Gift className="h-4 w-4 text-muted-foreground" /> Payroll (Paystack)
                </CardTitle>
                <CardDescription>Run salaries and wages with a Paystack-connected workflow.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-3">
                  {[
                    { label: "Next pay run", value: "Feb 28" },
                    { label: "Employees", value: "248" },
                    { label: "Estimated total", value: "R 3.9M" },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="text-xs text-muted-foreground">{metric.label}</p>
                      <p className="mt-1 text-lg font-semibold text-foreground">{metric.value}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm text-muted-foreground">Paystack sync keeps payment status consistent and auditable.</p>
                  <Button variant="outline">Sync Paystack</Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Gift className="h-4 w-4 text-muted-foreground" /> Employee benefit management
                </CardTitle>
                <CardDescription>Track enrollment and employer contributions.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Benefit</th>
                        <th className="py-2 pr-4 font-medium">Enrolled</th>
                        <th className="py-2 pr-4 font-medium">Employer share</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { benefit: "Medical aid", enrolled: "188", share: "70%" },
                        { benefit: "Pension/retirement", enrolled: "201", share: "5%" },
                        { benefit: "Life cover", enrolled: "140", share: "100%" },
                      ].map((row) => (
                        <tr key={row.benefit} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.benefit}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.enrolled}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.share}</td>
                          <td className="py-3">
                            <Button size="sm" variant="outline">
                              Manage
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "time":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-muted-foreground" /> Leave management
                </CardTitle>
                <CardDescription>Requests, approvals, and balances in one queue.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee</th>
                        <th className="py-2 pr-4 font-medium">Dates</th>
                        <th className="py-2 pr-4 font-medium">Type</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaveRequests.map((row) => (
                        <tr key={`${row.employee}-${row.dates}`} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.employee}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.dates}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.type}</td>
                          <td className="py-3 pr-4">
                            <Badge
                              variant="outline"
                              className={row.status === "Approved" ? "border-emerald-500/40 text-emerald-500" : "border-amber-500/40 text-amber-500"}
                            >
                              {row.status}
                            </Badge>
                          </td>
                          <td className="py-3">
                            {row.status === "Pending" ? (
                              <div className="flex flex-wrap gap-2">
                                <Button size="sm" variant="outline">
                                  Approve
                                </Button>
                                <Button size="sm" variant="ghost">
                                  Decline
                                </Button>
                              </div>
                            ) : (
                              <Button size="sm" variant="outline">
                                View
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-muted-foreground" /> Staff scheduling (based on demand)
                </CardTitle>
                <CardDescription>Plan coverage using expected demand and required staffing.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-3">
                  {[
                    { label: "Today demand", value: "High" },
                    { label: "Required coverage", value: "28 agents" },
                    { label: "Scheduled", value: "26 agents" },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="text-xs text-muted-foreground">{metric.label}</p>
                      <p className="mt-1 text-lg font-semibold text-foreground">{metric.value}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-lg border border-border bg-background/40 p-4 text-sm text-muted-foreground">
                  Create shift templates, then allocate staff based on predicted demand per channel (calls, tickets, walk-ins).
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "performance":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-muted-foreground" /> KPI management
                </CardTitle>
                <CardDescription>Targets, reviews, and team health metrics.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[680px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">KPI</th>
                        <th className="py-2 pr-4 font-medium">Owner</th>
                        <th className="py-2 pr-4 font-medium">Target</th>
                        <th className="py-2 pr-4 font-medium">Current</th>
                        <th className="py-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        { kpi: "Time-to-hire", owner: "HR", target: "≤ 21 days", current: "18 days", ok: true },
                        { kpi: "Engagement score", owner: "HR", target: "≥ 4.0", current: "4.2", ok: true },
                        { kpi: "Absence rate", owner: "Ops", target: "≤ 3%", current: "3.8%", ok: false },
                      ].map((row) => (
                        <tr key={row.kpi} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.kpi}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.owner}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.target}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.current}</td>
                          <td className="py-3">
                            <Badge
                              variant="outline"
                              className={row.ok ? "border-emerald-500/40 text-emerald-500" : "border-red-500/40 text-red-400"}
                            >
                              {row.ok ? "On track" : "At risk"}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Employee growth & turnover</CardTitle>
                  <CardDescription>Hiring vs separations over time.</CardDescription>
                </CardHeader>
                <CardContent>
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
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Attrition prediction</CardTitle>
                  <CardDescription>Early signals across departments.</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3">
                    {[
                      { dept: "Sales", risk: "High", note: "Quota pressure + overtime" },
                      { dept: "Service", risk: "Medium", note: "Coverage gaps on weekends" },
                      { dept: "Network", risk: "Low", note: "Stable shifts" },
                    ].map((row) => (
                      <div key={row.dept} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                        <div>
                          <p className="font-medium text-foreground">{row.dept}</p>
                          <p className="text-xs text-muted-foreground">{row.note}</p>
                        </div>
                        <Badge
                          variant="outline"
                          className={
                            row.risk === "High"
                              ? "border-red-500/40 text-red-400"
                              : row.risk === "Medium"
                                ? "border-amber-500/40 text-amber-500"
                                : "border-emerald-500/40 text-emerald-500"
                          }
                        >
                          {row.risk}
                        </Badge>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded-lg border border-border bg-background/40 p-4 text-sm text-muted-foreground">
                    Combine surveys, absence, performance, and scheduling load to flag retention risk.
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Surveys</CardTitle>
                <CardDescription>Pulse results and follow-ups.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-3">
                  {[
                    { label: "Last pulse", value: "4.2 / 5" },
                    { label: "Participation", value: "78%" },
                    { label: "Top theme", value: "Manager support" },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="text-xs text-muted-foreground">{metric.label}</p>
                      <p className="mt-1 text-lg font-semibold text-foreground">{metric.value}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm text-muted-foreground">Create a survey, publish to teams, and track action items.</p>
                  <Button variant="outline">New survey</Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "culture":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-muted-foreground" /> Kudos (recognition programme)
                </CardTitle>
                <CardDescription>Recognize wins and reinforce the culture you want.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[
                    { from: "Manager", to: "K. Patel", note: "Great customer follow-up on the MetroFibre deal." },
                    { from: "Team Lead", to: "S. Maseko", note: "Excellent incident response during the outage." },
                    { from: "Peer", to: "A. Ndlovu", note: "Thanks for covering the late shift." },
                  ].map((kudo) => (
                    <div key={`${kudo.to}-${kudo.note}`} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="text-sm text-foreground">
                        <span className="font-semibold">{kudo.to}</span> — {kudo.note}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">From {kudo.from}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex justify-end">
                  <Button variant="outline">Send kudos</Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Gift className="h-4 w-4 text-muted-foreground" /> Birthdays & milestones
                </CardTitle>
                <CardDescription>Celebrate consistently with a single calendar view.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    { name: "T. Mokoena", event: "Birthday", date: "Feb 15" },
                    { name: "K. Patel", event: "1 year at company", date: "Mar 2" },
                    { name: "S. Maseko", event: "Birthday", date: "Mar 10" },
                    { name: "A. Ndlovu", event: "Probation ends", date: "Mar 20" },
                  ].map((item) => (
                    <div key={`${item.name}-${item.event}`} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                      <div>
                        <p className="font-medium text-foreground">{item.name}</p>
                        <p className="text-xs text-muted-foreground">{item.event}</p>
                      </div>
                      <Badge variant="outline" className="border-muted text-muted-foreground">
                        {item.date}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      case "governance":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-muted-foreground" /> Access control & RBAC
                </CardTitle>
                <CardDescription>Control who can see and do what across HR workflows.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 sm:grid-cols-3">
                  {[
                    { role: "HR Admin", access: "Full HR + policies" },
                    { role: "Manager", access: "Team leave + reviews" },
                    { role: "Employee", access: "Profile + leave requests" },
                  ].map((row) => (
                    <div key={row.role} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="font-semibold text-foreground">{row.role}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{row.access}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex justify-end">
                  <Button variant="outline">Manage roles</Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Laptop className="h-4 w-4 text-muted-foreground" /> Asset allocation
                </CardTitle>
                <CardDescription>Track laptops, vehicles, and assigned equipment.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee</th>
                        <th className="py-2 pr-4 font-medium">Asset</th>
                        <th className="py-2 pr-4 font-medium">Reference</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assetAllocations.map((row) => (
                        <tr key={`${row.employee}-${row.ref}`} className="border-b border-border/60 text-sm">
                          <td className="py-3 pr-4 text-foreground">{row.employee}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.asset}</td>
                          <td className="py-3 pr-4 text-muted-foreground">{row.ref}</td>
                          <td className="py-3 pr-4">
                            <Badge
                              variant="outline"
                              className={row.status === "Assigned" ? "border-emerald-500/40 text-emerald-500" : "border-amber-500/40 text-amber-500"}
                            >
                              {row.status}
                            </Badge>
                          </td>
                          <td className="py-3">
                            <Button size="sm" variant="outline">
                              Open
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Retirement & retrenchment</CardTitle>
                <CardDescription>Lifecycle tracking with checklists and approvals.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    { flow: "Retirement", note: "Collect documents and finalize benefits" },
                    { flow: "Retrenchment", note: "Approvals, notices, and asset return" },
                  ].map((item) => (
                    <div key={item.flow} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="font-semibold text-foreground">{item.flow}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{item.note}</p>
                      <div className="mt-3">
                        <Button size="sm" variant="outline">
                          Open checklist
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      default:
        return null
    }
  }

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

      {/* Left panel navigation + active panel */}
      <div className="grid gap-6 lg:grid-cols-[320px_1fr] items-start">
        <Card>
          <CardHeader>
            <CardTitle>Staff Dome panels</CardTitle>
            <CardDescription>Select a panel to work inside it.</CardDescription>
          </CardHeader>
          <CardContent>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="w-full justify-between">
                  <span className="flex items-center gap-2">
                    <activePanelMeta.icon className="h-4 w-4 text-muted-foreground" />
                    {activePanelMeta.title}
                  </span>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-[280px]">
                {panelConfig.map((panel) => (
                  <DropdownMenuItem key={panel.key} onClick={() => setActivePanel(panel.key)}>
                    {panel.title}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="mt-4 space-y-2">
              {panelConfig.map((panel) => {
                const isActive = panel.key === activePanel
                const Icon = panel.icon
                return (
                  <Button
                    key={panel.key}
                    type="button"
                    variant={isActive ? "secondary" : "ghost"}
                    className="w-full justify-start gap-2"
                    onClick={() => setActivePanel(panel.key)}
                  >
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 text-left">{panel.title}</span>
                  </Button>
                )
              })}
            </div>

            <div className="mt-5 rounded-lg border border-border bg-background/40 p-4">
              <p className="text-xs font-medium text-muted-foreground mb-2">Included</p>
              <div className="flex flex-wrap gap-2">
                {activePanelMeta.tags.map((tag) => (
                  <PanelTag key={tag}>{tag}</PanelTag>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <div>
          {renderActivePanel()}

          {/* Keep staffing/turnover visuals available within Staff Dome */}
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Headcount by department</CardTitle>
                <CardDescription>Visibility into org distribution.</CardDescription>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Turnover by department</CardTitle>
                <CardDescription>Where churn concentrates.</CardDescription>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
