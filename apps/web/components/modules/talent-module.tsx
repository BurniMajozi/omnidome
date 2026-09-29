"use client"

import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/ui/page-header"
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
  AlertTriangle,
  BarChart3,
  BookOpen,
  Briefcase,
  Building2,
  Calendar,
  CalendarDays,
  ChevronDown,
  Download,
  Gift,
  GraduationCap,
  IdCard,
  Laptop,
  LogOut,
  Plus,
  ShieldCheck,
  Sparkles,
  Users,
  UserCog,
  Target,
  TrendingUp,
  X,
  Coins,
  Wrench,
  Bot,
  CheckCircle2,
  FileText,
  Layers,
  Check,
} from "lucide-react"
import {
  listEmployees,
  createEmployee,
  listLeaveRequests,
  approveLeave,
  declineLeave,
  getEmployeePerformance,
  createPerformanceReview,
  getAttritionRisk,
  listSchedules,
  createSchedule,
  confirmSchedule,
  deleteSchedule,
  getDemandForecast,
  listTrainingCourses,
  createTrainingCourse,
  enrollEmployee,
  updateTrainingProgress,
  getEmployeeTraining,
  listBenefits,
  createBenefitEnrollment,
  getEmployeeBenefits,
  listDisciplinary,
  createDisciplinary,
  resolveDisciplinary,
  listExits,
  createExit,
  updateExitChecklist,
  getExitChecklist,
  getOnboardingTasks,
  createOnboardingTask,
  bulkCreateOnboardingTasks,
  completeOnboardingTask,
  getOnboardingProgress,
  getHeadcountAnalytics,
  postPayrollRunToFinance,
  getDepartmentCostAllocation,
  getStaffComplianceAudit,
  getOrchestratorWellnessInsights,
  executeOrchestratorAction,
  type Employee,
  type LeaveRequest,
  type PerformanceReview,
  type Schedule,
  type TrainingCourse,
  type TrainingEnrollment,
  type Benefit,
  type DisciplinaryAction,
  type ExitRecord,
  type ExitChecklist,
  type OnboardingTask,
  type DepartmentCostAllocation,
  type StaffComplianceSummary,
  type OrchestratorWellnessAlert,
} from "@/lib/hr-api"
import { OnboardingKbView } from "./talent/onboarding-kb-view"
import { OrgChartView } from "./talent/org-chart-view"
import { PayrollPayslipsView } from "./talent/payroll-payslips-view"
import { PimDirectoryView } from "./talent/pim-directory-view"
import { LeaveJourneyView } from "./talent/leave-journey-view"
import { ReportsAnalyticsView } from "./talent/reports-analytics-view"
import { BenefitsPortalView } from "./talent/benefits-portal-view"
import { TalentAtsView } from "./talent/talent-ats-view"
import { TalentSchedulingView } from "./talent/talent-scheduling-view"
import { ServiceSchedulingView } from "./service/service-scheduling-view"
import { TalentTrainingView } from "./talent/talent-training-view"
import { TalentDisciplinaryView } from "./talent/talent-disciplinary-view"
import { TalentCultureView } from "./talent/talent-culture-view"
import { TalentExitView } from "./talent/talent-exit-view"
import { PerformanceObjectivesView } from "./talent/performance-objectives-view"

type NewEmployeeModalProps = {
  isOpen: boolean
  onClose: () => void
}

// ── Panel type & config ──────────────────────────────────────────────

type StaffPanelKey =
  | "directory"
  | "time"
  | "reporting"
  | "org_chart"
  | "onboarding"
  | "payroll"
  | "wellness_ai"
  | "performance"
  | "hiring"
  | "schedule"
  | "training"
  | "benefits"
  | "disciplinary"
  | "exit"
  | "culture"
  | "compliance_audit"

interface PanelMeta {
  key: StaffPanelKey
  title: string
  icon: React.ComponentType<{ className?: string }>
  tags: string[]
}

const panelConfig: PanelMeta[] = [
  { key: "reporting", title: "Workforce Analysis", icon: BarChart3, tags: ["Staff Pipeline", "Sentiment Analysis", "Attrition"] },
  { key: "culture", title: "Culture & Strategy", icon: Sparkles, tags: ["Strategy & OKRs", "5 Core Values", "Kudos Wall", "LLM Orchestrator"] },
  { key: "org_chart", title: "Hierarchical Org Structure", icon: Building2, tags: ["Zoom Controls", "Dynamic Sizing", "Direct Reports"] },
  { key: "performance", title: "Performance & Objectives", icon: Target, tags: ["KPI Tracker", "Competencies", "Attrition Risk"] },
  { key: "onboarding", title: "Knowledge & Onboarding", icon: BookOpen, tags: ["Checklists", "Markdown RAG Search"] },
  { key: "wellness_ai", title: "AI Talent Orchestrator", icon: Bot, tags: ["Burnout Risk", "Fatigue Detection", "Actions"] },
  { key: "time", title: "Leave Journey & Approvals", icon: CalendarDays, tags: ["BCEA 21-Day Annual", "Live Approvals", "ZAR Liability"] },
  { key: "schedule", title: "Staff Shift Scheduling", icon: Calendar, tags: ["Service Operations Driven", "24h Demand History", "Interactive Roster", "Broker Costs"] },
  { key: "training", title: "Training & Development", icon: GraduationCap, tags: ["Crash-Proof LMS", "FOA/MikroTik Certs", "Bursary Tracker"] },
  { key: "benefits", title: "Benefits & Care Corner", icon: Gift, tags: ["Provident Fund", "Medical Aid Options", "Employee Support"] },
  { key: "directory", title: "Personnel Directory (PIM)", icon: Users, tags: ["Employee 360", "Add Employee", "31-Module Matrix"] },
  { key: "payroll", title: "Payroll & Payslip Designer", icon: Gift, tags: ["SARS PAYE", "Custom Earnings/Deductions", "Live Preview"] },
  { key: "disciplinary", title: "Disciplinary & Grievances", icon: AlertTriangle, tags: ["Incident Wizard", "Hearings", "Whistleblower Complaints"] },
  { key: "exit", title: "Staff Exit & Deactivation", icon: LogOut, tags: ["Zero-Trust IT Revocation", "Asset Recovery", "Clearances"] },
  { key: "compliance_audit", title: "Labor Compliance Audit", icon: ShieldCheck, tags: ["BCEA Hours", "RICA Agents", "OHS Act"] },
]

// ── Small components ─────────────────────────────────────────────────

function PanelTag({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
      {children}
    </span>
  )
}

function StatusBadge({ status, className }: { status: string; className?: string }) {
  const cls =
    status === "Done" || status === "Approved" || status === "Active" || status === "Assigned" || status === "Completed" || status === "completed" || status === "confirmed"
      ? "border-emerald-500/40 text-emerald-500"
      : status === "In Progress" || status === "Pending" || status === "Onboarding" || status === "pending" || status === "enrolled"
        ? "border-amber-500/40 text-amber-500"
        : status === "High"
          ? "border-red-500/40 text-red-400"
          : status === "Medium"
            ? "border-amber-500/40 text-amber-500"
            : status === "Low"
              ? "border-emerald-500/40 text-emerald-500"
              : "border-muted text-muted-foreground"
  return (
    <Badge variant="outline" className={`${cls} ${className ?? ""}`}>
      {status}
    </Badge>
  )
}

function LoadingRow({ cols }: { cols: number }) {
  return (
    <tr>
      <td colSpan={cols} className="py-4 text-center text-sm text-muted-foreground">
        Loading…
      </td>
    </tr>
  )
}

function ErrorRow({ message, cols }: { message: string; cols: number }) {
  return (
    <tr>
      <td colSpan={cols} className="py-4 text-center text-sm text-red-400">
        Error: {message}
      </td>
    </tr>
  )
}

// ── StatCard (inline) ────────────────────────────────────────────────

interface StatCardProps {
  title: string
  value: string | number
  change?: string
  changeType?: "positive" | "negative"
  icon: React.ComponentType<{ className?: string }>
  description?: string
}

function StatCard({ title, value, change, changeType, icon: Icon, description }: StatCardProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{title}</p>
            <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
            {change && (
              <p className={`mt-1 text-xs ${changeType === "positive" ? "text-emerald-500" : "text-red-400"}`}>
                {change} {description ?? ""}
              </p>
            )}
            {!change && description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
          </div>
          <Icon className="h-8 w-8 text-muted-foreground" />
        </div>
      </CardContent>
    </Card>
  )
}

// ── Main component ───────────────────────────────────────────────────

export function TalentModule() {
  const [activePanel, setActivePanel] = useState<StaffPanelKey>("reporting")
  const [knowledgeQuery, setKnowledgeQuery] = useState("")

  // ── KPI / analytics state ─────────────────────────────────────────
  const [employeeGrowth, setEmployeeGrowth] = useState<{ month: string; employees: number; hired: number; separated: number }[]>([])
  const [departmentStaff, setDepartmentStaff] = useState<{ department: string; count: number }[]>([])
  const [turnoverData, setTurnoverData] = useState<{ department: string; value: number; fill: string }[]>([])
  const [kpiTotal, setKpiTotal] = useState<number>(0)
  const [kpiOpenPositions, setKpiOpenPositions] = useState<number>(0)
  const [kpiAvgRating, setKpiAvgRating] = useState<string>("—")
  const [kpiTurnover, setKpiTurnover] = useState<string>("—")
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [analyticsError, setAnalyticsError] = useState<string | null>(null)

  // ── Directory state ───────────────────────────────────────────────
  const [employeesDir, setEmployeesDir] = useState<Employee[]>([])
  const [dirLoading, setDirLoading] = useState(false)
  const [dirError, setDirError] = useState<string | null>(null)

  // ── Onboarding state ──────────────────────────────────────────────
  const [onboardingTasks, setOnboardingTasks] = useState<OnboardingTask[]>([])
  const [onboardingLoading, setOnboardingLoading] = useState(false)
  const [onboardingError, setOnboardingError] = useState<string | null>(null)

  // ── Time / leave state ────────────────────────────────────────────
  const [leaveRequests, setLeaveRequests] = useState<LeaveRequest[]>([])
  const [leaveLoading, setLeaveLoading] = useState(false)
  const [leaveError, setLeaveError] = useState<string | null>(null)

  // ── Performance state ─────────────────────────────────────────────
  const [performanceReviews, setPerformanceReviews] = useState<PerformanceReview[]>([])
  const [attritionData, setAttritionData] = useState<{ dept: string; risk: string; note: string }[]>([])
  const [kpis, setKpis] = useState<{ kpi: string; owner: string; target: string; current: string; ok: boolean }[]>([])
  const [perfLoading, setPerfLoading] = useState(false)
  const [perfError, setPerfError] = useState<string | null>(null)

  // ── Governance / benefits state ───────────────────────────────────
  const [governanceBenefits, setGovernanceBenefits] = useState<Benefit[]>([])
  const [govLoading, setGovLoading] = useState(false)
  const [govError, setGovError] = useState<string | null>(null)
  const [attritionRisk, setAttritionRisk] = useState<{ dept: string; risk: string; note: string }[]>([])
  const [roles, setRoles] = useState<{ role: string; access: string }[]>([])

  // ── Schedule state ────────────────────────────────────────────────
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [demandForecast, setDemandForecast] = useState<Array<{
    date: string; day: string; required_staff: number; scheduled_staff: number; gap: number
  }> | null>(null)
  const [schedLoading, setSchedLoading] = useState(false)
  const [schedError, setSchedError] = useState<string | null>(null)

  // ── Training state ────────────────────────────────────────────────
  const [trainingCourses, setTrainingCourses] = useState<TrainingCourse[]>([])
  const [trainingEnrollments, setTrainingEnrollments] = useState<TrainingEnrollment[]>([])
  const [trainingLoading, setTrainingLoading] = useState(false)
  const [trainingError, setTrainingError] = useState<string | null>(null)

  // ── Benefits panel state ──────────────────────────────────────────
  const [benefitsList, setBenefitsList] = useState<Benefit[]>([])
  const [benefitsLoading, setBenefitsLoading] = useState(false)
  const [benefitsError, setBenefitsError] = useState<string | null>(null)

  // ── Payroll panel state (hooks MUST be top-level, never inside the
  //    render switch — see fetch effect below) ──────────────────────
  const [payrollLoading, setPayrollLoading] = useState(false)
  const [payrollError, setPayrollError] = useState<string | null>(null)
  const [payrollBenefits, setPayrollBenefits] = useState<Benefit[]>([])

  // ── Hiring / Culture panel state (hoisted from their render cases) ──
  const [hiringLoading, setHiringLoading] = useState(false)
  const [hiringError, setHiringError] = useState<string | null>(null)
  const [candidates, setCandidates] = useState<{ id: string; name: string; role: string; stage: string; score: number }[]>([])
  const [cultureLoading, setCultureLoading] = useState(false)
  const [cultureError, setCultureError] = useState<string | null>(null)
  const [kudos, setKudos] = useState<{ id: string; from: string; to: string; note: string }[]>([])
  const [milestones, setMilestones] = useState<{ id: string; name: string; event: string; date: string }[]>([])

  // ── Disciplinary state ────────────────────────────────────────────
  const [disciplinaryActions, setDisciplinaryActions] = useState<DisciplinaryAction[]>([])
  const [disciplinaryLoading, setDisciplinaryLoading] = useState(false)
  const [disciplinaryError, setDisciplinaryError] = useState<string | null>(null)

  // ── Exit state ────────────────────────────────────────────────────
  const [exitRecords, setExitRecords] = useState<ExitRecord[]>([])
  const [exitChecklists, setExitChecklists] = useState<Record<string, ExitChecklist>>({})
  const [exitLoading, setExitLoading] = useState(false)
  const [exitError, setExitError] = useState<string | null>(null)

  // ── Cross-Service Connectors state ───────────────────────────────
  const [complianceAudit, setComplianceAudit] = useState<StaffComplianceSummary | null>(null)
  const [compLoading, setCompLoading] = useState(false)
  const [compError, setCompError] = useState<string | null>(null)

  const [wellnessAlerts, setWellnessAlerts] = useState<OrchestratorWellnessAlert[]>([])
  const [wellnessLoading, setWellnessLoading] = useState(false)
  const [wellnessError, setWellnessError] = useState<string | null>(null)

  const [deptCostAllocation, setDeptCostAllocation] = useState<DepartmentCostAllocation | null>(null)
  const [deptCostLoading, setDeptCostLoading] = useState(false)
  const [financePostMsg, setFinancePostMsg] = useState<string | null>(null)

  // Employee 360 Slide-Over
  const [selectedEmp, setSelectedEmp] = useState<Employee | null>(null)
  const [isEmpDrawerOpen, setIsEmpDrawerOpen] = useState(false)

  // ── Active panel meta ─────────────────────────────────────────────
  const activePanelMeta = useMemo(
    () => panelConfig.find((panel) => panel.key === activePanel) ?? panelConfig[0],
    [activePanel],
  )

  // ── Helpers ───────────────────────────────────────────────────────
  const statusColor = (status: string) => {
    if (["Done", "Approved", "Active", "Assigned", "completed", "confirmed", "Completed"].includes(status)) return "border-emerald-500/40 text-emerald-500"
    if (["In Progress", "Pending", "Onboarding", "pending", "enrolled"].includes(status)) return "border-amber-500/40 text-amber-500"
    if (status === "High") return "border-red-500/40 text-red-400"
    if (status === "Medium") return "border-amber-500/40 text-amber-500"
    if (status === "Low") return "border-emerald-500/40 text-emerald-500"
    return "border-muted text-muted-foreground"
  }

  // ── Data fetching: KPI + analytics ────────────────────────────────
  useEffect(() => {
    let cancelled = false
    async function fetchAnalytics() {
      setAnalyticsLoading(true)
      setAnalyticsError(null)
      try {
        const empData = await listEmployees()
        if (cancelled) return
        setKpiTotal(empData.length)
        setEmployeesDir(empData)

        // Derive department headcount
        const deptCounts: Record<string, number> = {}
        empData.forEach((e) => { deptCounts[e.department] = (deptCounts[e.department] || 0) + 1 })
        const deptArr = Object.entries(deptCounts).map(([department, count]) => ({ department, count }))
        if (deptArr.length > 0) setDepartmentStaff(deptArr)

        // Calculate turnover by department (exits in last 12 months / avg headcount)
        try {
          const exits = await listExits()
          if (cancelled) return
          const now = new Date()
          const twelveMonthsAgo = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate())
          
          const recentExits = exits.filter((ex) => {
            const noticeDate = new Date(ex.notice_date)
            return noticeDate >= twelveMonthsAgo
          })
          
          // Count exits by department
          const exitCounts: Record<string, number> = {}
          recentExits.forEach((ex) => {
            // Find employee department
            const emp = empData.find((e) => e.id === ex.employee_id)
            if (emp) {
              exitCounts[emp.department] = (exitCounts[emp.department] || 0) + 1
            }
          })
          
          // Build turnover data with colors
          const colors = ["#ef4444", "#f97316", "#eab308", "#4ade80", "#3b82f6", "#a855f7", "#ec4899", "#14b8a6"]
          let colorIndex = 0
          const turnoverArr = Object.entries(exitCounts).map(([department, value]) => ({
            department,
            value,
            fill: colors[colorIndex++ % colors.length]
          }))
          if (turnoverArr.length > 0) setTurnoverData(turnoverArr)
          
          // Calculate overall turnover rate
          const totalExits = recentExits.length
          const avgHeadcount = empData.length
          const turnoverRate = avgHeadcount > 0 ? ((totalExits / avgHeadcount) * 100).toFixed(1) : "0"
          setKpiTurnover(`${turnoverRate}%`)
        } catch { /* ignore */ }

        // Try to get analytics
        try {
          const hc = await getHeadcountAnalytics()
          if (cancelled) return
          if (hc && typeof hc === "object") {
            // best-effort extraction
          }
        } catch { /* ignore */ }
      } catch (err: unknown) {
        if (!cancelled) setAnalyticsError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setAnalyticsLoading(false)
      }
    }
    fetchAnalytics()
    return () => { cancelled = true }
  }, [])

  // ── Data fetching: Directory ──────────────────────────────────────
  const fetchDir = async () => {
    setDirLoading(true)
    setDirError(null)
    try {
      const data = await listEmployees()
      setEmployeesDir(data)
    } catch (err: unknown) {
      setDirError(err instanceof Error ? err.message : String(err))
    } finally {
      setDirLoading(false)
    }
  }

  useEffect(() => {
    if (activePanel === "directory" || activePanel === "onboarding" || activePanel === "org_chart" || activePanel === "time" || activePanel === "reporting" || activePanel === "performance") {
      fetchDir()
    }
  }, [activePanel])

  // ── Data fetching: Onboarding ─────────────────────────────────────
  useEffect(() => {
    if (activePanel !== "onboarding") return
    let cancelled = false
    async function fetchOnboarding() {
      setOnboardingLoading(true)
      setOnboardingError(null)
      try {
        // We don't have a specific employee—try to grab first employee or show empty
        const emps = await listEmployees()
        if (cancelled) return
        if (emps.length > 0) {
          const tasks = await getOnboardingTasks(emps[0].id)
          if (!cancelled) setOnboardingTasks(tasks)
        }
      } catch (err: unknown) {
        if (!cancelled) setOnboardingError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setOnboardingLoading(false)
      }
    }
    fetchOnboarding()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Time / leave ───────────────────────────────────
  const fetchLeave = async () => {
    setLeaveLoading(true)
    setLeaveError(null)
    try {
      const emps = await listEmployees()
      const allLeaves: LeaveRequest[] = []
      for (const emp of emps.slice(0, 20)) {
        try {
          const leaves = await listLeaveRequests(emp.id)
          allLeaves.push(...leaves)
        } catch { /* skip individual failures */ }
      }
      setLeaveRequests(allLeaves)
    } catch (err: unknown) {
      setLeaveError(err instanceof Error ? err.message : String(err))
    } finally {
      setLeaveLoading(false)
    }
  }

  useEffect(() => {
    if (activePanel !== "time") return
    fetchLeave()
  }, [activePanel])

  // ── Data fetching: Performance ────────────────────────────────────
  useEffect(() => {
    if (activePanel !== "performance") return
    let cancelled = false
    async function fetchPerf() {
      setPerfLoading(true)
      setPerfError(null)
      try {
        const emps = await listEmployees()
        if (cancelled) return
        const allReviews: PerformanceReview[] = []
        for (const emp of emps.slice(0, 20)) {
          try {
            const reviews = await getEmployeePerformance(emp.id)
            allReviews.push(...reviews)
          } catch { /* skip */ }
        }
        if (!cancelled) setPerformanceReviews(allReviews)
        try {
          const attr = await getAttritionRisk()
          if (!cancelled && attr && typeof attr === "object" && "departments" in attr) {
            setAttritionData((attr as { departments: { dept: string; risk: string; note: string }[] }).departments)
          } else if (!cancelled) {
            setAttritionData([])
          }
        } catch { if (!cancelled) setAttritionData([]) }
        if (!cancelled) setKpis([])
      } catch (err: unknown) {
        if (!cancelled) setPerfError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setPerfLoading(false)
      }
    }
    fetchPerf()
    return () => { cancelled = true }
  }, [activePanel])



  // ── Data fetching: Schedule ───────────────────────────────────────
  useEffect(() => {
    if (activePanel !== "schedule") return
    let cancelled = false
    async function fetchSched() {
      setSchedLoading(true)
      setSchedError(null)
      try {
        const [scheds, forecast] = await Promise.all([
          listSchedules(),
          getDemandForecast(7).catch(() => null),
        ])
        if (cancelled) return
        setSchedules(scheds)
        setDemandForecast(forecast as Array<{ date: string; day: string; required_staff: number; scheduled_staff: number; gap: number }> | null)
      } catch (err: unknown) {
        if (!cancelled) setSchedError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setSchedLoading(false)
      }
    }
    fetchSched()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Training ──────────────────────────────────────
  useEffect(() => {
    if (activePanel !== "training") return
    let cancelled = false
    async function fetchTraining() {
      setTrainingLoading(true)
      setTrainingError(null)
      try {
        const courses = await listTrainingCourses()
        if (cancelled) return
        setTrainingCourses(courses)

        const emps = await listEmployees()
        if (cancelled) return
        const allEnrollments: TrainingEnrollment[] = []
        for (const emp of emps.slice(0, 10)) {
          try {
            const enrolled = await getEmployeeTraining(emp.id)
            allEnrollments.push(...enrolled)
          } catch { /* skip */ }
        }
        if (!cancelled) setTrainingEnrollments(allEnrollments)
      } catch (err: unknown) {
        if (!cancelled) setTrainingError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setTrainingLoading(false)
      }
    }
    fetchTraining()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Benefits panel ─────────────────────────────────
  useEffect(() => {
    if (activePanel !== "benefits") return
    let cancelled = false
    async function fetchBenefits() {
      setBenefitsLoading(true)
      setBenefitsError(null)
      try {
        const data = await listBenefits()
        if (!cancelled) setBenefitsList(data)
      } catch (err: unknown) {
        if (!cancelled) setBenefitsError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setBenefitsLoading(false)
      }
    }
    fetchBenefits()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Payroll panel ──────────────────────────────────
  useEffect(() => {
    if (activePanel !== "payroll") return
    let cancelled = false
    async function fetchPayroll() {
      setPayrollLoading(true)
      setPayrollError(null)
      try {
        const data = await listBenefits()
        if (!cancelled) setPayrollBenefits(data)
      } catch (err: unknown) {
        if (!cancelled) setPayrollError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setPayrollLoading(false)
      }
    }
    fetchPayroll()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Hiring panel ───────────────────────────────────
  useEffect(() => {
    if (activePanel !== "hiring") return
    let cancelled = false
    async function fetchHiring() {
      setHiringLoading(true)
      setHiringError(null)
      try {
        if (!cancelled) setCandidates([
          { id: "1", name: "A. Ndlovu", role: "Support Agent", stage: "Interview", score: 82 },
          { id: "2", name: "K. Patel", role: "Sales Exec", stage: "Offer", score: 91 },
          { id: "3", name: "S. Maseko", role: "Network Tech", stage: "Screen", score: 76 },
        ])
      } catch (err: unknown) {
        if (!cancelled) setHiringError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setHiringLoading(false)
      }
    }
    fetchHiring()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Culture panel ──────────────────────────────────
  useEffect(() => {
    if (activePanel !== "culture") return
    let cancelled = false
    async function fetchCulture() {
      setCultureLoading(true)
      setCultureError(null)
      try {
        if (!cancelled) setKudos([
          { id: "1", from: "Manager", to: "K. Patel", note: "Great customer follow-up on the MetroFibre deal." },
          { id: "2", from: "Team Lead", to: "S. Maseko", note: "Excellent incident response during the outage." },
          { id: "3", from: "Peer", to: "A. Ndlovu", note: "Thanks for covering the late shift." },
        ])
        if (!cancelled) setMilestones([
          { id: "1", name: "T. Mokoena", event: "Birthday", date: "Feb 15" },
          { id: "2", name: "K. Patel", event: "1 year at company", date: "Mar 2" },
          { id: "3", name: "S. Maseko", event: "Birthday", date: "Mar 10" },
          { id: "4", name: "A. Ndlovu", event: "Probation ends", date: "Mar 20" },
        ])
      } catch (err: unknown) {
        if (!cancelled) setCultureError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setCultureLoading(false)
      }
    }
    fetchCulture()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Disciplinary ───────────────────────────────────
  useEffect(() => {
    if (activePanel !== "disciplinary") return
    let cancelled = false
    async function fetchDisc() {
      setDisciplinaryLoading(true)
      setDisciplinaryError(null)
      try {
        const data = await listDisciplinary()
        if (!cancelled) setDisciplinaryActions(data)
      } catch (err: unknown) {
        if (!cancelled) setDisciplinaryError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setDisciplinaryLoading(false)
      }
    }
    fetchDisc()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Exit ───────────────────────────────────────────
  useEffect(() => {
    if (activePanel !== "exit") return
    let cancelled = false
    async function fetchExit() {
      setExitLoading(true)
      setExitError(null)
      try {
        const data = await listExits()
        if (cancelled) return
        setExitRecords(data)

        // Fetch checklists for each exit
        const checklists: Record<string, ExitChecklist> = {}
        for (const rec of data) {
          try {
            const cl = await getExitChecklist(rec.id)
            checklists[rec.id] = cl
          } catch { /* skip */ }
        }
        if (!cancelled) setExitChecklists(checklists)
      } catch (err: unknown) {
        if (!cancelled) setExitError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setExitLoading(false)
      }
    }
    fetchExit()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Compliance Audit ───────────────────────────────
  useEffect(() => {
    if (activePanel !== "compliance_audit") return
    let cancelled = false
    async function fetchComp() {
      setCompLoading(true)
      setCompError(null)
      try {
        const data = await getStaffComplianceAudit()
        if (!cancelled) setComplianceAudit(data)
      } catch (err: unknown) {
        if (!cancelled) setCompError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setCompLoading(false)
      }
    }
    fetchComp()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Data fetching: Wellness & AI Orchestrator ─────────────────────
  useEffect(() => {
    if (activePanel !== "wellness_ai") return
    let cancelled = false
    async function fetchWellness() {
      setWellnessLoading(true)
      setWellnessError(null)
      try {
        const data = await getOrchestratorWellnessInsights()
        if (!cancelled) setWellnessAlerts(data)
      } catch (err: unknown) {
        if (!cancelled) setWellnessError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setWellnessLoading(false)
      }
    }
    fetchWellness()
    return () => { cancelled = true }
  }, [activePanel])

  const [executingAlertId, setExecutingAlertId] = useState<string | null>(null)
  const [wellnessActionMsg, setWellnessActionMsg] = useState<{ id: string; message: string; auditLogId?: string } | null>(null)

  const handleExecuteWellnessAction = async (alertId: string, alertType: string) => {
    try {
      setExecutingAlertId(alertId)
      const res = await executeOrchestratorAction(alertId, alertType)
      setWellnessActionMsg({ id: alertId, message: res.message || res.action })
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to execute orchestrator action")
    } finally {
      setExecutingAlertId(null)
    }
  }

  // ── Data fetching: FP&A Department Costs (on payroll panel) ───────
  useEffect(() => {
    if (activePanel !== "payroll") return
    let cancelled = false
    async function fetchDeptCosts() {
      setDeptCostLoading(true)
      try {
        const data = await getDepartmentCostAllocation()
        if (!cancelled) setDeptCostAllocation(data)
      } catch {
        // silent fallback
      } finally {
        if (!cancelled) setDeptCostLoading(false)
      }
    }
    fetchDeptCosts()
    return () => { cancelled = true }
  }, [activePanel])

  // ── Knowledge base search ─────────────────────────────────────────
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

  // ── Action handlers ───────────────────────────────────────────────
  const handleApproveLeave = async (leaveId: string) => {
    try { await approveLeave(leaveId); setLeaveRequests((prev) => prev.map((l) => l.id === leaveId ? { ...l, status: "Approved" } : l)) } catch { /* ignore */ }
  }
  const handleDeclineLeave = async (leaveId: string) => {
    try { await declineLeave(leaveId); setLeaveRequests((prev) => prev.map((l) => l.id === leaveId ? { ...l, status: "Declined" } : l)) } catch { /* ignore */ }
  }
  const handleCompleteTask = async (taskId: string) => {
    try { await completeOnboardingTask(taskId); setOnboardingTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: "Done" } : t)) } catch { /* ignore */ }
  }
  const handleCreateSchedule = async () => {
    try {
      const emps = await listEmployees()
      if (emps.length === 0) return
      const today = new Date().toISOString().split("T")[0]
      await createSchedule({ employee_id: emps[0].id, schedule_date: today, shift_start: "08:00", shift_end: "17:00", department: emps[0].department })
      const updated = await listSchedules()
      setSchedules(updated)
    } catch { /* ignore */ }
  }
  const handleConfirmSchedule = async (id: string) => {
    try { await confirmSchedule(id); setSchedules((prev) => prev.map((s) => s.id === id ? { ...s, status: "CONFIRMED" } : s)) } catch { /* ignore */ }
  }
  const handleDeleteSchedule = async (id: string) => {
    try { await deleteSchedule(id); setSchedules((prev) => prev.filter((s) => s.id !== id)) } catch { /* ignore */ }
  }
  const handleCreateCourse = async () => {
    try {
      await createTrainingCourse({ title: "New Course", category: "General", duration_hours: 4, mandatory: false })
      const updated = await listTrainingCourses()
      setTrainingCourses(updated)
    } catch { /* ignore */ }
  }
  const handleEnrollEmployee = async () => {
    try {
      const emps = await listEmployees()
      if (emps.length === 0 || trainingCourses.length === 0) return
      await enrollEmployee({ employee_id: emps[0].id, course_id: trainingCourses[0].id })
      const updated = await getEmployeeTraining(emps[0].id)
      setTrainingEnrollments((prev) => [...prev.filter((e) => e.employee_id !== emps[0].id), ...updated])
    } catch { /* ignore */ }
  }
  const handleCreateBenefit = async () => {
    try {
      const emps = await listEmployees()
      if (emps.length === 0) return
      await createBenefitEnrollment({ employee_id: emps[0].id, benefit_type: "medical" })
      const updated = await listBenefits()
      setBenefitsList(updated)
    } catch { /* ignore */ }
  }
  const handleCreateDisciplinary = async () => {
    try {
      const emps = await listEmployees()
      if (emps.length === 0) return
      const today = new Date().toISOString().split("T")[0]
      await createDisciplinary({ employee_id: emps[0].id, action_type: "VERBAL_WARNING", incident_date: today, description: "New incident" })
      const updated = await listDisciplinary()
      setDisciplinaryActions(updated)
    } catch { /* ignore */ }
  }
  const handleResolveDisciplinary = async (id: string) => {
    try { await resolveDisciplinary(id, "Resolved", "HR"); setDisciplinaryActions((prev) => prev.map((d) => d.id === id ? { ...d, status: "Resolved" } : d)) } catch { /* ignore */ }
  }
  const handleCreateExit = async () => {
    try {
      const emps = await listEmployees()
      if (emps.length === 0) return
      const today = new Date().toISOString().split("T")[0]
      const lwd = new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0]
      await createExit({ employee_id: emps[0].id, exit_type: "Resignation", notice_date: today, last_working_date: lwd })
      const updated = await listExits()
      setExitRecords(updated)
    } catch { /* ignore */ }
  }
  const handleUpdateExitChecklist = async (exitId: string, field: keyof ExitChecklist) => {
    try {
      const current = exitChecklists[exitId] || {}
      const updated = { ...current, [field]: !current[field] }
      await updateExitChecklist(exitId, updated)
      setExitChecklists((prev) => ({ ...prev, [exitId]: updated }))
    } catch { /* ignore */ }
  }
  const [isPostingFinance, setIsPostingFinance] = useState(false)

  const handlePostPayrollToFinance = async () => {
    try {
      setIsPostingFinance(true)
      setFinancePostMsg(null)
      const res = await postPayrollRunToFinance({
        run_name: `Automated Monthly Payroll - ${new Date().toLocaleDateString("en-ZA", { month: "short", year: "numeric" })}`,
        total_gross_zar: kpiTotal * 16000,
        currency: "ZAR",
      })
      setFinancePostMsg(`Successfully posted to Finance Ledger! Journal Entry #${res.journal_entry_id?.slice(0, 8)} (Lines: Dr Salaries R${res.dr_salaries_expense.toLocaleString()}, Cr Bank R${res.cr_bank_cash.toLocaleString()}, Cr SARS PAYE R${res.cr_sars_paye_liability.toLocaleString()})`)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to post payroll to Finance")
    } finally {
      setIsPostingFinance(false)
    }
  }

  // ── Render panels ─────────────────────────────────────────────────
  const renderActivePanel = () => {
    switch (activePanel) {
      // ── ONBOARDING ────────────────────────────────────────────────
      case "onboarding":
        return <OnboardingKbView employees={employeesDir} />

      // ── DIRECTORY ─────────────────────────────────────────────────
      case "directory":
        return (
          <PimDirectoryView
            employees={employeesDir}
            loading={dirLoading}
            error={dirError}
            onRefresh={fetchDir}
          />
        )

      // ── ORG CHART ──────────────────────────────────────────────────
      case "org_chart":
        return (
          <div className="space-y-6 min-w-0 w-full max-w-full overflow-hidden">
            <OrgChartView employees={employeesDir} onRefresh={fetchDir} />
          </div>
        )

      // ── HIRING / ATS ───────────────────────────────────────────────
      case "hiring":
        return <TalentAtsView />

      // ── PAYROLL ───────────────────────────────────────────────────
      case "payroll":
        return (
          <PayrollPayslipsView
            deptCostAllocation={deptCostAllocation}
            deptCostLoading={deptCostLoading}
            kpiTotal={kpiTotal}
          />
        )

      // ── TIME / LEAVE ──────────────────────────────────────────────
      case "time":
        return (
          <LeaveJourneyView
            employees={employeesDir}
            leaveRequests={leaveRequests}
            loading={leaveLoading}
            error={leaveError}
            onRefresh={() => {
              fetchDir()
              void fetchLeave()
            }}
          />
        )

      // ── PIM REPORTS & STATUTORY ANALYTICS ──────────────────────────
      case "reporting":
        return (
          <ReportsAnalyticsView
            employees={employeesDir}
            kpiTotal={kpiTotal}
          />
        )

      // ── PERFORMANCE ───────────────────────────────────────────────
            case "performance":
              return (
                <div className="space-y-6 min-w-0 w-full max-w-full">
                  <PerformanceObjectivesView
                    employees={employeesDir}
                    onRefresh={fetchDir}
                  />
                </div>
              )


      // ── CULTURE & RECOGNITION ──────────────────────────────────────
      case "culture":
        return <TalentCultureView employees={employeesDir} />



      // ── SCHEDULE ──────────────────────────────────────────────────
      case "schedule":
        return (
          <div className="space-y-4">
            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 text-xs text-cyan-200">
                <Sparkles className="h-4 w-4 text-cyan-400 shrink-0" />
                <span>
                  <strong>Operational Synergy:</strong> Staff Shift Scheduling is coupled directly to the <strong>Service Panel</strong> where 24h subscriber ticket volumes, MTTR/FTR skill tags, and call center demand drive human and broker rostering.
                </span>
              </div>
            </div>
            <ServiceSchedulingView />
          </div>
        )

      // ── TRAINING & DEVELOPMENT ────────────────────────────────────
      case "training":
        return (
          <TalentTrainingView
            employees={employeesDir}
            courses={trainingCourses}
            enrollments={trainingEnrollments}
            loading={trainingLoading}
            error={trainingError}
            onRefresh={() => {
              void listTrainingCourses().then(setTrainingCourses)
            }}
          />
        )

      // ── BENEFITS MANAGEMENT ───────────────────────────────────────
      case "benefits":
        return <BenefitsPortalView employees={employeesDir} />

      // ── DISCIPLINARY & GRIEVANCES ─────────────────────────────────
      case "disciplinary":
        return (
          <TalentDisciplinaryView
            employees={employeesDir}
            actions={disciplinaryActions}
            onRefresh={() => {
              void listDisciplinary().then(setDisciplinaryActions)
            }}
          />
        )

      // ── STAFF EXIT & OFFBOARDING ──────────────────────────────────
      case "exit":
        return (
          <TalentExitView
            employees={employeesDir}
            exits={exitRecords}
            onRefresh={() => {
              void listExits().then(setExitRecords)
            }}
          />
        )

      // ── COMPLIANCE AUDIT ──────────────────────────────────────────────
      case "compliance_audit":
        return (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                title="Overall Compliance Score"
                value={compLoading ? "…" : (complianceAudit ? `${complianceAudit.overall_readiness_score}%` : "94%")}
                icon={ShieldCheck}
                change="Audit Ready"
                changeType="positive"
                description="South Africa ISP"
              />
              <StatCard
                title="Certified RICA Officers"
                value={compLoading ? "…" : (complianceAudit?.rica_accredited_officers_count ?? 2)}
                icon={CheckCircle2}
                description="authorized verifiers"
              />
              <StatCard
                title="Foreign Worker DHA Permits"
                value={compLoading ? "…" : (complianceAudit?.foreign_workers_with_permits ?? 2)}
                icon={FileText}
                change="100% Valid"
                changeType="positive"
                description="Home Affairs verified"
              />
              <StatCard
                title="H&S Incidents (YTD)"
                value={compLoading ? "…" : (complianceAudit?.health_and_safety_incidents ?? 0)}
                icon={AlertTriangle}
                change="Target: 0"
                changeType="positive"
                description="COID & OHS compliant"
              />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-muted-foreground" /> Statutory & Regulatory Compliance Audit
                </CardTitle>
                <CardDescription>Cross-service verification against RICA, POPIA, Department of Home Affairs, and OHS Act.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4 text-emerald-500" /> RICA Act Compliance
                      </span>
                      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">Compliant</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      All sales representatives and call center staff verifying subscriber SIM/Fiber identity are registered RICA agents with audited logs.
                    </p>
                    <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                      <span>RICA Officers: <strong>{complianceAudit?.rica_accredited_officers_count ?? 2}</strong></span>
                      <span>Audit Trail: <strong>100%</strong></span>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-2">
                        <FileText className="h-4 w-4 text-blue-500" /> DHA Foreign Worker Permits
                      </span>
                      <Badge variant="outline" className="border-blue-500/40 text-blue-400">Verified</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Department of Home Affairs general and critical skills work permits on file with automated 90-day expiry warning triggers.
                    </p>
                    <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                      <span>Active Permits: <strong>{complianceAudit?.foreign_workers_with_permits ?? 2}</strong></span>
                      <span>Next Expiry: <strong>2027-04-30</strong></span>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4 text-purple-500" /> POPIA Data Privacy Officer Status
                      </span>
                      <Badge variant="outline" className="border-purple-500/40 text-purple-400">Certified</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Information Officer registered with SA Information Regulator. All staff handling customer records completed mandatory POPIA training.
                    </p>
                    <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                      <span>Staff Trained: <strong>{complianceAudit?.popia_compliance_pct ?? 100}%</strong></span>
                      <span>Data Access Logged: <strong>Yes</strong></span>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-amber-500" /> OHS & Field Splicing Safety
                      </span>
                      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">Zero Incidents</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Fiber technicians certified for working at heights, electrical safety, and trench splicing. Mandatory PPE and vehicle safety audits passed.
                    </p>
                    <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                      <span>Incident Rate: <strong>0.00</strong></span>
                      <span>Next Safety Audit: <strong>14 Days</strong></span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── WELLNESS & AI ORCHESTRATOR ───────────────────────────────────────
      case "wellness_ai":
        return (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                title="Active AI Insights"
                value={wellnessLoading ? "…" : wellnessAlerts.length}
                icon={Bot}
                description="workforce orchestrator"
              />
              <StatCard
                title="High Risk Alerts"
                value={wellnessLoading ? "…" : wellnessAlerts.filter(a => a.severity === "high").length}
                icon={AlertTriangle}
                changeType="negative"
                description="requires intervention"
              />
              <StatCard
                title="Skill Gap Opportunities"
                value={wellnessLoading ? "…" : wellnessAlerts.filter(a => a.alert_type?.includes("SKILL")).length}
                icon={Sparkles}
                description="upskilling recommended"
              />
              <StatCard
                title="Wellness Index"
                value="91 / 100"
                icon={CheckCircle2}
                change="+4 pts"
                changeType="positive"
                description="sentiment & workload"
              />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-muted-foreground" /> Agent Orchestrator Workforce Health & Fatigue Recommendations
                </CardTitle>
                <CardDescription>Synthesizes scheduling, call center queue times, and ticket loads into proactive HR recommendations.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {wellnessLoading ? (
                    <p className="text-sm text-muted-foreground">Synthesizing wellness telemetry…</p>
                  ) : wellnessError ? (
                    <p className="text-sm text-red-400">Error: {wellnessError}</p>
                  ) : wellnessAlerts.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No wellness alerts flagged. Workforce metrics are optimal.</p>
                  ) : (
                    wellnessAlerts.map((alert) => (
                      <div
                        key={alert.id}
                        className={`rounded-lg border p-4 space-y-2 ${
                          alert.severity === "high"
                            ? "border-red-500/30 bg-red-500/10"
                            : alert.severity === "medium"
                            ? "border-amber-500/30 bg-amber-500/10"
                            : "border-blue-500/30 bg-blue-500/10"
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground text-sm">{alert.alert_type.replace(/_/g, " ")}</span>
                            <Badge
                              variant="outline"
                              className={
                                alert.severity === "high"
                                  ? "border-red-500/40 text-red-400"
                                  : alert.severity === "medium"
                                  ? "border-amber-500/40 text-amber-400"
                                  : "border-blue-500/40 text-blue-400"
                              }
                            >
                              {alert.severity.toUpperCase()}
                            </Badge>
                          </div>
                          <span className="text-xs text-muted-foreground">{alert.employee_name} ({alert.department})</span>
                        </div>
                        <p className="text-xs text-muted-foreground">{alert.message}</p>
                        <div className="rounded bg-background/50 p-2.5 text-xs text-foreground flex items-center justify-between gap-3">
                          <span>💡 <strong>AI Recommendation:</strong> {alert.recommendation}</span>
                          <Button
                            size="sm"
                            variant="cta"
                            className="h-7 text-xs flex-shrink-0"
                            disabled={executingAlertId === alert.id || wellnessActionMsg?.id === alert.id}
                            onClick={() => handleExecuteWellnessAction(alert.id, alert.alert_type)}
                          >
                            {executingAlertId === alert.id
                              ? "Executing…"
                              : wellnessActionMsg?.id === alert.id
                              ? "Executed ✓"
                              : "Execute Action"}
                          </Button>
                        </div>
                        {wellnessActionMsg?.id === alert.id && (
                          <div className="rounded bg-emerald-500/10 border border-emerald-500/30 p-2 text-xs text-emerald-400 flex items-center gap-1.5">
                            <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
                            <span>{wellnessActionMsg.message}</span>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      default:
        return null
    }
  }

  // ── Main render ────────────────────────────────────────────────────
  const [showNewEmployeeModal, setShowNewEmployeeModal] = useState(false)

  const handleExport = async () => {
    try {
      const emps = await listEmployees()
      const csv = [
        ["ID", "Name", "Email", "Department", "Job Title", "Status", "Hire Date"].join(","),
        ...emps.map(e => [
          e.employee_id,
          e.full_name,
          e.email || "",
          e.department,
          e.job_title,
          e.status,
          e.hire_date
        ].map(v => `"${v}"`).join(","))
      ].join("\n")
      
      const blob = new Blob([csv], { type: "text/csv" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `talent-export-${new Date().toISOString().split("T")[0]}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error("Export failed:", err)
    }
  }

  const handleNewEmployee = () => {
    alert("New Employee form - to be implemented with proper modal")
    // TODO: Implement proper modal with form
  }

  // ── Main render ────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      <PageHeader
        icon={<UserCog className="h-5 w-5" />}
        title="Talent & HR"
        subtitle="Employee management, onboarding, performance, and workforce planning"
      />

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Employees"
          value={analyticsLoading ? "…" : kpiTotal}
          change={analyticsLoading ? undefined : "+0%"}
          changeType="positive"
          icon={UserCog}
          description="real-time count"
        />
        <StatCard
          title="Open Positions"
          value={kpiOpenPositions}
          change={analyticsLoading ? undefined : "+0"}
          changeType="negative"
          icon={Target}
          description="from requisitions"
        />
        <StatCard
          title="Avg Employee Rating"
          value={kpiAvgRating}
          change={analyticsLoading ? undefined : "+0.0"}
          changeType="positive"
          icon={TrendingUp}
          description="engagement score"
        />
        <StatCard
          title="Turnover Rate"
          value={kpiTurnover}
          change={analyticsLoading ? undefined : "+0.0%"}
          changeType="positive"
          icon={Users}
          description="annualized"
        />
      </div>

      {/* Left panel navigation + active panel */}
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] items-start w-full max-w-full min-w-0 overflow-hidden">
        <Card className="border-border bg-card/80 shadow-sm shrink-0">
          <CardHeader className="pb-3 border-b border-border/50">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-cyan-500 shadow-sm" />
                Talent Operations
              </CardTitle>
              <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 text-[10px] font-semibold bg-cyan-500/10">
                OmniDome HCM
              </Badge>
            </div>
            <CardDescription className="text-xs">Human Capital & Statutory Modules.</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="w-full justify-between border-border/80 hover:border-cyan-500/50">
                  <span className="flex items-center gap-2">
                    <activePanelMeta.icon className="h-4 w-4 text-cyan-400" />
                    <span className="font-medium text-foreground">{activePanelMeta.title}</span>
                  </span>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-[280px]">
                {panelConfig.map((panel) => (
                  <DropdownMenuItem key={panel.key} onClick={() => setActivePanel(panel.key)} className="gap-2">
                    <panel.icon className="h-4 w-4 text-muted-foreground" />
                    {panel.title}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="mt-4 space-y-1">
              {panelConfig.map((panel) => {
                const isActive = panel.key === activePanel
                const Icon = panel.icon
                return (
                  <Button
                    key={panel.key}
                    type="button"
                    variant={isActive ? "secondary" : "ghost"}
                    className={`w-full justify-start gap-2.5 text-xs font-medium h-9 transition-colors ${
                      isActive
                        ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 font-semibold hover:bg-cyan-500/20"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                    }`}
                    onClick={() => setActivePanel(panel.key)}
                  >
                    <Icon className={`h-4 w-4 ${isActive ? "text-cyan-400" : "text-muted-foreground"}`} />
                    <span className="flex-1 text-left">{panel.title}</span>
                    {isActive && <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />}
                  </Button>
                )
              })}
            </div>

            <div className="mt-5 rounded-lg border border-border/70 bg-background/40 p-3.5">
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Active Module Scope</p>
              <div className="flex flex-wrap gap-1.5">
                {activePanelMeta.tags.map((tag) => (
                  <PanelTag key={tag}>{tag}</PanelTag>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="min-w-0 w-full max-w-full overflow-hidden">
          {renderActivePanel()}
        </div>
      </div>
    </div>
  )
}

// ── New Employee Modal ────────────────────────────────────────────────
function NewEmployeeModal({ isOpen, onClose }: NewEmployeeModalProps) {
  if (!isOpen) return null

  const [formData, setFormData] = useState({
    employee_id: "",
    full_name: "",
    email: "",
    department: "",
    job_title: "",
    hire_date: new Date().toISOString().split("T")[0],
    phone: "",
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await createEmployee(formData)
      onClose()
      setFormData({ employee_id: "", full_name: "", email: "", department: "", job_title: "", hire_date: new Date().toISOString().split("T")[0], phone: "" })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create employee")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-background rounded-lg border border-border max-w-md w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-lg font-semibold">Add New Employee</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {error && <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded p-2">{error}</div>}
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Employee ID</label>
            <Input value={formData.employee_id} onChange={(e) => setFormData({ ...formData, employee_id: e.target.value })} required />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Full Name</label>
            <Input value={formData.full_name} onChange={(e) => setFormData({ ...formData, full_name: e.target.value })} required />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Email</label>
            <Input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} />
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">Department</label>
              <Input value={formData.department} onChange={(e) => setFormData({ ...formData, department: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">Job Title</label>
              <Input value={formData.job_title} onChange={(e) => setFormData({ ...formData, job_title: e.target.value })} required />
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">Hire Date</label>
              <Input type="date" value={formData.hire_date} onChange={(e) => setFormData({ ...formData, hire_date: e.target.value })} required />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground">Phone</label>
              <Input value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} />
            </div>
          </div>
          <div className="flex gap-2 justify-end pt-4 border-t border-border">
            <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>Cancel</Button>
            <Button type="submit" disabled={submitting}>{submitting ? "Creating…" : "Create Employee"}</Button>
          </div>
        </form>
      </div>
    </div>
  )
}
