"use client"

import React, { useState } from "react"
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
  LineChart,
  Line,
  AreaChart,
  Area,
} from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Users,
  ShieldCheck,
  Calendar,
  AlertTriangle,
  GraduationCap,
  Sparkles,
  Download,
  Target,
  FileText,
  Heart,
  Smile,
  Frown,
  Meh,
  Building2,
} from "lucide-react"
import type { Employee } from "@/lib/hr-api"

interface ReportsAnalyticsViewProps {
  employees: Employee[]
  kpiTotal: number
}

// Staff Pipeline Data (12-month Hires vs Exits)
const STAFF_PIPELINE_DATA = [
  { month: "Oct 25", hires: 2, exits: 0, net: 2 },
  { month: "Nov 25", hires: 3, exits: 1, net: 2 },
  { month: "Dec 25", hires: 1, exits: 0, net: 1 },
  { month: "Jan 26", hires: 4, exits: 1, net: 3 },
  { month: "Feb 26", hires: 3, exits: 1, net: 2 },
  { month: "Mar 26", hires: 2, exits: 0, net: 2 },
  { month: "Apr 26", hires: 3, exits: 1, net: 2 },
  { month: "May 26", hires: 2, exits: 0, net: 2 },
  { month: "Jun 26", hires: 4, exits: 1, net: 3 },
  { month: "Jul 26", hires: 3, exits: 0, net: 3 },
  { month: "Aug 26", hires: 2, exits: 1, net: 1 },
  { month: "Sep 26", hires: 3, exits: 0, net: 3 },
]

// Open Positions & Requisitions
const OPEN_POSITIONS = [
  { title: "Senior NOC Engineer (BGP/MPLS)", department: "Network Operations", openDays: 14, applicants: 18, status: "Interviewing" },
  { title: "Optical Fiber Splicing Specialist", department: "Field Operations", openDays: 8, applicants: 24, status: "Shortlisted" },
  { title: "Enterprise FTTH Sales Executive", department: "Sales", openDays: 21, applicants: 12, status: "Offer Stage" },
  { title: "Tier-2 ISP Technical Support Agent", department: "Customer Support", openDays: 5, applicants: 31, status: "Screening" },
]

// Leave Trends Data (Monthly utilization)
const LEAVE_TRENDS_DATA = [
  { month: "Apr", annual: 18, sick: 6, family: 2 },
  { month: "May", annual: 14, sick: 8, family: 1 },
  { month: "Jun", annual: 22, sick: 12, family: 3 },
  { month: "Jul", annual: 26, sick: 14, family: 4 },
  { month: "Aug", annual: 19, sick: 9, family: 2 },
  { month: "Sep", annual: 24, sick: 7, family: 3 },
]

// Disciplinary Category Distribution
const DISCIPLINARY_DATA = [
  { category: "Shift Punctuality", count: 4, fill: "#38bdf8" },
  { category: "SLA / Ticket Breach", count: 2, fill: "#818cf8" },
  { category: "Safety / OHS Protocol", count: 1, fill: "#fbbf24" },
  { category: "Policy & Conduct", count: 1, fill: "#f87171" },
]

// Sentiment Breakdown
const SENTIMENT_DATA = [
  { name: "Positive (Promoters)", value: 78, color: "#10b981" },
  { name: "Neutral (Passives)", value: 16, color: "#60a5fa" },
  { name: "Negative (Detractors)", value: 6, color: "#f87171" },
]

// Attrition Projections by Department
const ATTRITION_PROJECTIONS = [
  { department: "Network Operations", risk: "Low", projectedChurn: "3.2%", drivers: "Competitive compensation, clear cert progression" },
  { department: "Field Operations", risk: "Low", projectedChurn: "4.5%", drivers: "Modern toolkits, van stock reliability" },
  { department: "Customer Support", risk: "Medium", projectedChurn: "9.1%", drivers: "High call volume spikes, night shift fatigue" },
  { department: "Sales & Commercial", risk: "Low", projectedChurn: "2.8%", drivers: "Strong commission payout pipeline" },
]

export function ReportsAnalyticsView({ employees, kpiTotal }: ReportsAnalyticsViewProps) {
  const [activeReportTab, setActiveReportTab] = useState<"pipeline" | "leave" | "skills" | "sentiment" | "attrition">("pipeline")

  // Department distribution from live employees
  const departmentStaff = React.useMemo(() => {
    const counts: Record<string, number> = {}
    employees.forEach((e) => {
      counts[e.department] = (counts[e.department] || 0) + 1
    })
    return Object.entries(counts).map(([department, count]) => ({
      department: department.length > 15 ? `${department.slice(0, 13)}…` : department,
      count,
    }))
  }, [employees])

  const handleExportCSV = () => {
    const csvContent = [
      ["Metric", "Value", "Notes"].join(","),
      ["Total Active Personnel", kpiTotal, "Full-time & Contract"],
      ["Net Headcount Growth YTD", "+23", "Staff Pipeline"],
      ["Leave Liability Provision ZAR", "R 432,650", "Statutory BCEA Balance Sheet"],
      ["Active Open Requisitions", OPEN_POSITIONS.length, "Across NOC & Field"],
      ["Employee Net Promoter Score (eNPS)", "+46", "Top Quartile"],
    ].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `omnidome-workforce-analytics-${new Date().toISOString().split("T")[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            <h1 className="text-xl font-bold tracking-tight text-foreground">Workforce Intelligence & Analytics</h1>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Holistic HR intelligence: hiring pipeline, leave utilization, skills & bursaries, sentiment, and predictive attrition.
          </p>
        </div>

        <Button size="sm" variant="outline" onClick={handleExportCSV} className="gap-1.5 text-xs">
          <Download className="h-3.5 w-3.5" />
          Export Executive CSV
        </Button>
      </div>

      {/* KPI Cards Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Staff Pipeline Growth</p>
                <p className="mt-1 text-2xl font-bold text-foreground">+18.2%</p>
                <p className="mt-0.5 text-xs text-emerald-400">+23 Net hires (12m)</p>
              </div>
              <TrendingUp className="h-8 w-8 text-emerald-400/50" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Open Requisitions</p>
                <p className="mt-1 text-2xl font-bold text-foreground">4 Roles</p>
                <p className="mt-0.5 text-xs text-muted-foreground">85 active applicants</p>
              </div>
              <Target className="h-8 w-8 text-primary/50" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Employee eNPS Score</p>
                <p className="mt-1 text-2xl font-bold text-emerald-400">+46</p>
                <p className="mt-0.5 text-xs text-muted-foreground">78% Positive sentiment</p>
              </div>
              <Smile className="h-8 w-8 text-cyan-400/50" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Leave Liability Provision</p>
                <p className="mt-1 text-2xl font-bold text-foreground">R 432,650</p>
                <p className="mt-0.5 text-xs text-muted-foreground">BCEA balance sheet</p>
              </div>
              <Calendar className="h-8 w-8 text-violet-400/50" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Analytics Sub-Tab Navigation */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border pb-2 text-xs">
        {[
          { id: "pipeline", label: "Staff Pipeline & Hires vs Exits" },
          { id: "leave", label: "Leave Days Trends & Accruals" },
          { id: "skills", label: "Training, Certifications & Bursaries" },
          { id: "sentiment", label: "Surveys & Sentiment Analysis" },
          { id: "attrition", label: "Predictive Attrition Risk" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveReportTab(tab.id as typeof activeReportTab)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              activeReportTab === tab.id
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Staff Pipeline & Open Positions ───────────────────── */}
      {activeReportTab === "pipeline" && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Pipeline Chart */}
            <Card className="border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-emerald-400" />
                  Staff Pipeline (New Hires vs Exits)
                </CardTitle>
                <CardDescription className="text-xs">
                  Monthly recruitment intake compared to departures over the last 12 months.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={STAFF_PIPELINE_DATA}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="month" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} />
                      <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444", borderRadius: "8px" }} />
                      <Legend />
                      <Bar dataKey="hires" name="New Hires" fill="#10b981" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="exits" name="Departures / Exits" fill="#f87171" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Department Headcount Distribution */}
            <Card className="border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-primary" />
                  Headcount Distribution by Department
                </CardTitle>
                <CardDescription className="text-xs">
                  Active staff breakdown across ISP operational units.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={departmentStaff} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis type="number" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis type="category" dataKey="department" tick={{ fill: "#888", fontSize: 11 }} width={90} />
                      <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444", borderRadius: "8px" }} />
                      <Bar dataKey="count" name="Staff Count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Open Requisitions Table */}
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Target className="h-4 w-4 text-cyan-400" /> Open Positions & Requisition Pipeline
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Current active job vacancies authorized by executive management.
                  </CardDescription>
                </div>
                <Badge variant="outline" className="border-primary/40 text-primary">
                  {OPEN_POSITIONS.length} Active Positions
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Requisition Title</th>
                      <th className="py-2.5 px-4 font-medium">Department</th>
                      <th className="py-2.5 px-4 font-medium">Days Open</th>
                      <th className="py-2.5 px-4 font-medium">Applicants</th>
                      <th className="py-2.5 px-4 font-medium">Current Stage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {OPEN_POSITIONS.map((pos) => (
                      <tr key={pos.title} className="hover:bg-muted/30">
                        <td className="py-3 px-4 font-semibold text-foreground">{pos.title}</td>
                        <td className="py-3 px-4 text-muted-foreground">{pos.department}</td>
                        <td className="py-3 px-4 text-muted-foreground font-mono">{pos.openDays} days</td>
                        <td className="py-3 px-4 text-foreground font-semibold">{pos.applicants} candidates</td>
                        <td className="py-3 px-4">
                          <Badge variant="outline" className="border-primary/40 text-primary">
                            {pos.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 2: Leave Days Trends ─────────────────────────────────── */}
      {activeReportTab === "leave" && (
        <div className="space-y-6">
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Calendar className="h-4 w-4 text-violet-400" />
                Monthly Leave Days Utilization & Seasonality
              </CardTitle>
              <CardDescription className="text-xs">
                Tracking statutory Annual, Sick, and Family Responsibility leave usage.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={LEAVE_TRENDS_DATA}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="month" tick={{ fill: "#888", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#888", fontSize: 11 }} />
                    <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444", borderRadius: "8px" }} />
                    <Legend />
                    <Area type="monotone" dataKey="annual" name="Annual Leave Days" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.2} />
                    <Area type="monotone" dataKey="sick" name="Sick Leave Days" stroke="#fbbf24" fill="#fbbf24" fillOpacity={0.2} />
                    <Area type="monotone" dataKey="family" name="Family Responsibility" stroke="#a78bfa" fill="#a78bfa" fillOpacity={0.2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-3 text-xs">
            <div className="rounded-lg border border-border bg-card/60 p-4 space-y-1">
              <span className="text-muted-foreground">Accrued Leave Days Liability</span>
              <p className="text-xl font-bold text-foreground">328 Total Days</p>
              <p className="text-[11px] text-muted-foreground">Average: 15.6 days / staff</p>
            </div>
            <div className="rounded-lg border border-border bg-card/60 p-4 space-y-1">
              <span className="text-muted-foreground">Balance Sheet Reserve</span>
              <p className="text-xl font-bold text-emerald-400">R 432,650 ZAR</p>
              <p className="text-[11px] text-muted-foreground">Fully funded balance</p>
            </div>
            <div className="rounded-lg border border-border bg-card/60 p-4 space-y-1">
              <span className="text-muted-foreground">BCEA Maximum Encashment</span>
              <p className="text-xl font-bold text-amber-400">Only upon termination</p>
              <p className="text-[11px] text-muted-foreground">Section 20(11) compliant</p>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 3: Skills, Training & Bursaries ──────────────────────── */}
      {activeReportTab === "skills" && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Training Certifications */}
            <Card className="border-border">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-base flex items-center gap-2">
                  <GraduationCap className="h-4 w-4 text-emerald-400" />
                  ISP Certifications & SETA Skills Plan
                </CardTitle>
                <CardDescription className="text-xs">
                  Mandatory and technical accreditations for field & NOC personnel.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 space-y-3 text-xs">
                <div className="flex items-center justify-between border-b border-border/50 pb-2">
                  <div>
                    <p className="font-semibold text-foreground">Fiber Optics CFOT / Splicing</p>
                    <p className="text-muted-foreground text-[11px]">Fiber Optics Association (FOA)</p>
                  </div>
                  <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                    14 Techs Certified
                  </Badge>
                </div>
                <div className="flex items-center justify-between border-b border-border/50 pb-2">
                  <div>
                    <p className="font-semibold text-foreground">MikroTik MTCNA / MTCRE</p>
                    <p className="text-muted-foreground text-[11px]">Core routing & queues</p>
                  </div>
                  <Badge variant="outline" className="border-cyan-500/40 text-cyan-400">
                    8 Engineers Certified
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-foreground">OHS Act Working at Heights</p>
                    <p className="text-muted-foreground text-[11px]">Mandatory safety credential</p>
                  </div>
                  <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                    100% Field Compliant
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* Bursary Scheme */}
            <Card className="border-border">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-base flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  Corporate Bursary & Talent Pipeline
                </CardTitle>
                <CardDescription className="text-xs">
                  Company-sponsored higher education & advanced networking qualifications.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 space-y-3 text-xs">
                <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground">Active Bursary Candidates</span>
                    <Badge variant="outline" className="border-primary/40 text-primary">4 Staff Members</Badge>
                  </div>
                  <p className="text-muted-foreground text-[11px]">
                    BSc Computer Science / BTech Telecommunications (UNISA & Wits University).
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 text-muted-foreground pt-1">
                  <div>Annual Bursary Fund: <span className="text-foreground font-semibold">R 280,000 ZAR</span></div>
                  <div>Course Pass Rate: <span className="text-emerald-400 font-semibold">94.5%</span></div>
                  <div>Service Bonding Period: <span className="text-foreground font-semibold">2 Years post-grad</span></div>
                  <div>SETA Levy Refundable: <span className="text-foreground font-semibold">Yes (WSP/ATR)</span></div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ── TAB 4: Surveys & Sentiment Analysis ──────────────────────── */}
      {activeReportTab === "sentiment" && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Sentiment Pie */}
            <Card className="border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Smile className="h-4 w-4 text-emerald-400" />
                  Employee Sentiment & eNPS Breakdown
                </CardTitle>
                <CardDescription className="text-xs">
                  Results from the Q3 Employee Pulse Survey (88% participation rate).
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={SENTIMENT_DATA}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={90}
                        paddingAngle={4}
                        dataKey="value"
                      >
                        {SENTIMENT_DATA.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444", borderRadius: "8px" }} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Qualitative Sentiment Themes */}
            <Card className="border-border">
              <CardHeader className="pb-3 border-b border-border/60">
                <CardTitle className="text-base flex items-center gap-2">
                  <FileText className="h-4 w-4 text-cyan-400" />
                  Key Survey Insights & Sentiment Signals
                </CardTitle>
                <CardDescription className="text-xs">
                  NLP analysis of anonymous employee survey feedback comments.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 space-y-3 text-xs">
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-400">High Satisfaction: Tooling & Equipment</span>
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">89% Positive</Badge>
                  </div>
                  <p className="text-muted-foreground text-[11px]">
                    Field technicians strongly praise the new Fujikura 90S+ splicers and rugged OTDR units.
                  </p>
                </div>

                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-amber-400">Improvement Area: Night Shift Rotation</span>
                    <Badge variant="outline" className="border-amber-500/40 text-amber-400">Requires Attention</Badge>
                  </div>
                  <p className="text-muted-foreground text-[11px]">
                    NOC staff requested more equitable weekend rotation and enhanced night differential allowances.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* ── TAB 5: Attrition Projections ─────────────────────────────── */}
      {activeReportTab === "attrition" && (
        <div className="space-y-6">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                    Departmental Attrition Projections & Risk Heatmap
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Predictive turnover modeling based on compensation benchmarking, overtime hours, and tenure.
                  </CardDescription>
                </div>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                  Overall Company Risk: Low (4.1%)
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Department</th>
                      <th className="py-2.5 px-4 font-medium">Risk Tier</th>
                      <th className="py-2.5 px-4 font-medium">Projected Annual Churn</th>
                      <th className="py-2.5 px-4 font-medium">Key Drivers & Mitigations</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {ATTRITION_PROJECTIONS.map((row) => (
                      <tr key={row.department} className="hover:bg-muted/30">
                        <td className="py-3 px-4 font-semibold text-foreground">{row.department}</td>
                        <td className="py-3 px-4">
                          <Badge
                            variant="outline"
                            className={
                              row.risk === "Low"
                                ? "border-emerald-500/40 text-emerald-400"
                                : "border-amber-500/40 text-amber-400"
                            }
                          >
                            {row.risk} Risk
                          </Badge>
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-foreground">{row.projectedChurn}</td>
                        <td className="py-3 px-4 text-muted-foreground">{row.drivers}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
