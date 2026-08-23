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
} from "lucide-react"
import {
  listEmployees,
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
} from "@/lib/hr-api"

type NewEmployeeModalProps = {
  isOpen: boolean
  onClose: () => void
}

// ── Panel type & config ──────────────────────────────────────────────

type StaffPanelKey =
  | "onboarding"
  | "directory"
  | "hiring"
  | "payroll"
  | "time"
  | "performance"
  | "culture"
  | "governance"
  | "schedule"
  | "training"
  | "benefits"
  | "disciplinary"
  | "exit"

interface PanelMeta {
  key: StaffPanelKey
  title: string
  icon: React.ComponentType<{ className?: string }>
  tags: string[]
}

const panelConfig: PanelMeta[] = [
  { key: "onboarding", title: "Onboarding & Knowledge", icon: BookOpen, tags: ["Employee Onboarding", "HR Knowledge Base"] },
  { key: "directory", title: "Directory & Org", icon: Building2, tags: ["Company Org Chart", "Pictures"] },
  { key: "hiring", title: "Hiring (ATS)", icon: Briefcase, tags: ["Applicant Tracker"] },
  { key: "payroll", title: "Payroll & Benefits", icon: Gift, tags: ["Payroll via Paystack", "Employee Benefit Management"] },
  { key: "time", title: "Time & Planning", icon: CalendarDays, tags: ["Leave Management", "Demand-Based Scheduling"] },
  { key: "performance", title: "Performance & Insights", icon: BarChart3, tags: ["KPI Management", "Surveys", "Attrition Prediction"] },
  { key: "culture", title: "Culture & Recognition", icon: Sparkles, tags: ["Kudos", "Birthdays & Milestones"] },
  { key: "governance", title: "Governance & Assets", icon: ShieldCheck, tags: ["Access Control", "Role-Based Access", "Asset Allocation", "Retirement", "Retrenchment"] },
  { key: "schedule", title: "Staff Schedule", icon: Calendar, tags: ["Shift Planning", "Demand Forecast"] },
  { key: "training", title: "Training", icon: GraduationCap, tags: ["Courses", "Progress Tracking", "Certifications"] },
  { key: "benefits", title: "Benefits Management", icon: Gift, tags: ["Leave Balance", "Shares", "Bonuses", "Medical"] },
  { key: "disciplinary", title: "Disciplinary Actions", icon: AlertTriangle, tags: ["Warnings", "Suspensions", "Dismissals"] },
  { key: "exit", title: "Staff Exit", icon: LogOut, tags: ["Resignation", "Termination", "Retirement", "Checklist"] },
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
  const [activePanel, setActivePanel] = useState<StaffPanelKey>("onboarding")
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
  useEffect(() => {
    if (activePanel !== "directory") return
    let cancelled = false
    async function fetchDir() {
      setDirLoading(true)
      setDirError(null)
      try {
        const data = await listEmployees()
        if (!cancelled) setEmployeesDir(data)
      } catch (err: unknown) {
        if (!cancelled) setDirError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setDirLoading(false)
      }
    }
    fetchDir()
    return () => { cancelled = true }
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
  useEffect(() => {
    if (activePanel !== "time") return
    let cancelled = false
    async function fetchLeave() {
      setLeaveLoading(true)
      setLeaveError(null)
      try {
        const emps = await listEmployees()
        if (cancelled) return
        const allLeaves: LeaveRequest[] = []
        for (const emp of emps.slice(0, 20)) {
          try {
            const leaves = await listLeaveRequests(emp.id)
            if (!cancelled) allLeaves.push(...leaves)
          } catch { /* skip individual failures */ }
        }
        if (!cancelled) setLeaveRequests(allLeaves)
      } catch (err: unknown) {
        if (!cancelled) setLeaveError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setLeaveLoading(false)
      }
    }
    fetchLeave()
    return () => { cancelled = true }
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

  // ── Data fetching: Governance / benefits ──────────────────────────
  useEffect(() => {
    if (activePanel !== "governance") return
    let cancelled = false
    async function fetchGov() {
      setGovLoading(true)
      setGovError(null)
      try {
        const data = await listBenefits()
        if (!cancelled) setGovernanceBenefits(data)
        try {
          const attr = await getAttritionRisk()
          if (!cancelled && attr && typeof attr === "object" && "departments" in attr) {
            setAttritionRisk((attr as { departments: { dept: string; risk: string; note: string }[] }).departments)
          } else if (!cancelled) {
            setAttritionRisk([])
          }
        } catch { if (!cancelled) setAttritionRisk([]) }
        if (!cancelled) setRoles([
          { role: "HR Admin", access: "Full HR + policies" },
          { role: "Manager", access: "Team leave + reviews" },
          { role: "Employee", access: "Profile + leave requests" },
        ])
      } catch (err: unknown) {
        if (!cancelled) setGovError(err instanceof Error ? err.message : String(err))
      } finally {
        if (!cancelled) setGovLoading(false)
      }
    }
    fetchGov()
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

  // ── Render panels ─────────────────────────────────────────────────
  const renderActivePanel = () => {
    switch (activePanel) {
      // ── ONBOARDING ────────────────────────────────────────────────
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
                      {onboardingLoading ? (
                        <LoadingRow cols={4} />
                      ) : onboardingError ? (
                        <ErrorRow message={onboardingError} cols={4} />
                      ) : onboardingTasks.length === 0 ? (
                        <tr><td colSpan={4} className="py-4 text-center text-sm text-muted-foreground">No onboarding tasks found.</td></tr>
                      ) : (
                        onboardingTasks.map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.task_name}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.owner_department}</td>
                            <td className="py-3 pr-4"><StatusBadge status={row.status} /></td>
                            <td className="py-3">
                              {row.status !== "Done" ? (
                                <Button size="sm" variant="outline" onClick={() => handleCompleteTask(row.id)}>Complete</Button>
                              ) : (
                                <Button size="sm" variant="ghost">View</Button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="outline" onClick={async () => {
                    try {
                      const emps = await listEmployees()
                      if (emps.length === 0) return
                      await createOnboardingTask({ employee_id: emps[0].id, task_name: "New task", owner_department: "HR" })
                      const tasks = await getOnboardingTasks(emps[0].id)
                      setOnboardingTasks(tasks)
                    } catch { /* ignore */ }
                  }}>Add task</Button>
                  <Button size="sm" variant="ghost" onClick={async () => {
                    try {
                      const emps = await listEmployees()
                      if (emps.length === 0) return
                      await bulkCreateOnboardingTasks(emps[0].id, [
                        { task_name: "Setup workstation", owner_department: "IT" },
                        { task_name: "Compliance training", owner_department: "HR" },
                      ])
                      const tasks = await getOnboardingTasks(emps[0].id)
                      setOnboardingTasks(tasks)
                    } catch { /* ignore */ }
                  }}>Bulk add</Button>
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
                    <Input value={knowledgeQuery} onChange={(event) => setKnowledgeQuery(event.target.value)} placeholder="Search articles…" />
                  </div>
                  <Button variant="outline">New article</Button>
                </div>
                <div className="mt-4 space-y-3">
                  {knowledgeBaseArticles.map((article) => (
                    <div key={article.title} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                      <div>
                        <p className="font-medium text-foreground">{article.title}</p>
                        <p className="text-xs text-muted-foreground">{article.category} · Updated {article.updated}</p>
                      </div>
                      <Button size="sm" variant="ghost">Open</Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── DIRECTORY ─────────────────────────────────────────────────
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
                  {departmentStaff.map((node) => (
                    <div key={node.department} className="rounded-lg border border-border bg-background/40 p-4">
                      <p className="card-title">{node.department}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{node.count} people</p>
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
                      {dirLoading ? (
                        <LoadingRow cols={5} />
                      ) : dirError ? (
                        <ErrorRow message={dirError} cols={5} />
                      ) : employeesDir.length === 0 ? (
                        <tr><td colSpan={5} className="py-4 text-center text-sm text-muted-foreground">No employees found.</td></tr>
                      ) : (
                        employeesDir.slice(0, 50).map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.full_name}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.department}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.job_title}</td>
                            <td className="py-3 pr-4"><StatusBadge status={row.status} /></td>
                            <td className="py-3"><Button size="sm" variant="outline">Open</Button></td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── HIRING ──────────────────────────────────────────────────────
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
                    { label: "Screen", value: candidates.filter(c => c.stage === "Screen").length },
                    { label: "Interview", value: candidates.filter(c => c.stage === "Interview").length },
                    { label: "Offer", value: candidates.filter(c => c.stage === "Offer").length },
                    { label: "Hired", value: candidates.filter(c => c.stage === "Hired").length },
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
                      {hiringLoading ? (
                        <LoadingRow cols={5} />
                      ) : hiringError ? (
                        <ErrorRow message={hiringError} cols={5} />
                      ) : candidates.length === 0 ? (
                        <tr><td colSpan={5} className="py-4 text-center text-sm text-muted-foreground">No candidates found.</td></tr>
                      ) : (
                        candidates.map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.name}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.role}</td>
                            <td className="py-3 pr-4"><Badge variant="outline" className="border-muted text-muted-foreground">{row.stage}</Badge></td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.score}</td>
                            <td className="py-3"><Button size="sm" variant="outline">Review</Button></td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── PAYROLL ──────────────────────────────────────────────────────────
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
                    { label: "Next pay run", value: (() => { const d = new Date(); const last = new Date(d.getFullYear(), d.getMonth() + 1, 0); return last.toLocaleDateString("en-ZA", { day: "numeric", month: "short" }) })() },
                    { label: "Employees", value: String(kpiTotal) },
                    { label: "Estimated total", value: `R ${(kpiTotal * 16000 / 1_000_000).toFixed(1)}M` },
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
                      {payrollLoading ? (
                        <LoadingRow cols={4} />
                      ) : payrollError ? (
                        <ErrorRow message={payrollError} cols={4} />
                      ) : payrollBenefits.length === 0 ? (
                        <tr><td colSpan={4} className="py-4 text-center text-sm text-muted-foreground">No benefit records found.</td></tr>
                      ) : (
                        // Group by benefit type
                        (() => {
                          const byType: Record<string, number> = {}
                          payrollBenefits.forEach(b => { byType[b.benefit_type] = (byType[b.benefit_type] || 0) + 1 })
                          return Object.entries(byType).map(([benefit, enrolled]) => (
                            <tr key={benefit} className="border-b border-border/60 text-sm">
                              <td className="py-3 pr-4 text-foreground">{benefit}</td>
                              <td className="py-3 pr-4 text-muted-foreground">{enrolled}</td>
                              <td className="py-3 pr-4 text-muted-foreground">Employer funded</td>
                              <td className="py-3"><Button size="sm" variant="outline">Manage</Button></td>
                            </tr>
                          ))
                        })()
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── TIME / LEAVE ──────────────────────────────────────────────
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
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Dates</th>
                        <th className="py-2 pr-4 font-medium">Type</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaveLoading ? (
                        <LoadingRow cols={5} />
                      ) : leaveError ? (
                        <ErrorRow message={leaveError} cols={5} />
                      ) : leaveRequests.length === 0 ? (
                        <tr><td colSpan={5} className="py-4 text-center text-sm text-muted-foreground">No leave requests found.</td></tr>
                      ) : (
                        leaveRequests.map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.start_date} – {row.end_date}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.leave_type}</td>
                            <td className="py-3 pr-4"><StatusBadge status={row.status} /></td>
                            <td className="py-3">
                              {row.status === "pending" || row.status === "Pending" ? (
                                <div className="flex flex-wrap gap-2">
                                  <Button size="sm" variant="outline" onClick={() => handleApproveLeave(row.id)}>Approve</Button>
                                  <Button size="sm" variant="ghost" onClick={() => handleDeclineLeave(row.id)}>Decline</Button>
                                </div>
                              ) : (
                                <Button size="sm" variant="outline">View</Button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
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
                    { label: "Today demand", value: (demandForecast?.[0]?.gap ?? 0) > 0 ? "High" : "Covered" },
                    { label: "Required coverage", value: demandForecast ? `${demandForecast[0]?.required_staff ?? "\u2014"} agents` : "28 agents" },
                    { label: "Scheduled", value: demandForecast ? `${demandForecast[0]?.scheduled_staff ?? "\u2014"} agents` : "26 agents" },
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

      // ── PERFORMANCE ───────────────────────────────────────────────
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
                            {perfLoading ? (
                              <LoadingRow cols={5} />
                            ) : perfError ? (
                              <ErrorRow message={perfError} cols={5} />
                            ) : kpis.length === 0 ? (
                              <tr><td colSpan={5} className="py-4 text-center text-sm text-muted-foreground">No KPI data available. Configure KPIs in analytics.</td></tr>
                            ) : (
                              kpis.map((row) => (
                                <tr key={row.kpi} className="border-b border-border/60 text-sm">
                                  <td className="py-3 pr-4 text-foreground">{row.kpi}</td>
                                  <td className="py-3 pr-4 text-muted-foreground">{row.owner}</td>
                                  <td className="py-3 pr-4 text-muted-foreground">{row.target}</td>
                                  <td className="py-3 pr-4 text-muted-foreground">{row.current}</td>
                                  <td className="py-3">
                                    <Badge variant="outline" className={row.ok ? "border-emerald-500/40 text-emerald-500" : "border-red-500/40 text-red-400"}>
                                      {row.ok ? "On track" : "At risk"}
                                    </Badge>
                                  </td>
                                </tr>
                              ))
                            )}
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
                              <Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} />
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
                          {attritionData.length === 0 ? (
                            <p className="col-span-full text-sm text-muted-foreground">No attrition risk data available. Run analytics to populate.</p>
                          ) : (
                            attritionData.map((row) => (
                              <div key={row.dept} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                                <div>
                                  <p className="font-medium text-foreground">{row.dept}</p>
                                  <p className="text-xs text-muted-foreground">{row.note}</p>
                                </div>
                                <Badge variant="outline" className={statusColor(row.risk)}>{row.risk}</Badge>
                              </div>
                            ))
                          )}
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
                          { label: "Last pulse", value: "—" },
                          { label: "Participation", value: "—" },
                          { label: "Top theme", value: "—" },
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

      // ── CULTURE ──────────────────────────────────────────────────────────
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
                  {cultureLoading ? (
                    <p className="text-sm text-muted-foreground">Loading kudos…</p>
                  ) : cultureError ? (
                    <p className="text-sm text-red-400">Error: {cultureError}</p>
                  ) : kudos.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No kudos yet. Be the first to send one!</p>
                  ) : (
                    kudos.map((kudo) => (
                      <div key={kudo.id} className="rounded-lg border border-border bg-background/40 p-4">
                        <p className="text-sm text-foreground">
                          <span className="font-semibold">{kudo.to}</span> — {kudo.note}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">From {kudo.from}</p>
                      </div>
                    ))
                  )}
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
                  {cultureLoading ? (
                    <p className="col-span-2 text-sm text-muted-foreground">Loading milestones…</p>
                  ) : cultureError ? (
                    <p className="col-span-2 text-sm text-red-400">Error: {cultureError}</p>
                  ) : milestones.length === 0 ? (
                    <p className="col-span-2 text-sm text-muted-foreground">No upcoming milestones.</p>
                  ) : (
                    milestones.map((item) => (
                      <div key={item.id} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                        <div>
                          <p className="font-medium text-foreground">{item.name}</p>
                          <p className="text-xs text-muted-foreground">{item.event}</p>
                        </div>
                        <Badge variant="outline" className="border-muted text-muted-foreground">{item.date}</Badge>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── GOVERNANCE ──────────────────────────────────────────────────────────
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
                  {govLoading ? (
                    <p className="col-span-3 text-sm text-muted-foreground">Loading roles…</p>
                  ) : govError ? (
                    <p className="col-span-3 text-sm text-red-400">Error: {govError}</p>
                  ) : (
                    roles.map((row) => (
                      <div key={row.role} className="rounded-lg border border-border bg-background/40 p-4">
                        <p className="font-semibold text-foreground">{row.role}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{row.access}</p>
                      </div>
                    ))
                  )}
                </div>
                <div className="mt-4 flex justify-end">
                  <Button variant="outline">Manage roles</Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Laptop className="h-4 w-4 text-muted-foreground" /> Asset / benefit allocation
                </CardTitle>
                <CardDescription>Track laptops, vehicles, and assigned equipment via benefits API.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Benefit Type</th>
                        <th className="py-2 pr-4 font-medium">Created</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {govLoading ? (
                        <LoadingRow cols={4} />
                      ) : govError ? (
                        <ErrorRow message={govError} cols={4} />
                      ) : governanceBenefits.length === 0 ? (
                        <tr><td colSpan={4} className="py-4 text-center text-sm text-muted-foreground">No benefit records found.</td></tr>
                      ) : (
                        governanceBenefits.slice(0, 50).map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.benefit_type}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.created_at?.slice(0, 10) ?? "—"}</td>
                            <td className="py-3"><Button size="sm" variant="outline">Open</Button></td>
                          </tr>
                        ))
                      )}
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
                        <Button size="sm" variant="outline">Open checklist</Button>
                      </div>
                    </div>
                  ))}
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
                  {attritionRisk.length === 0 ? (
                    <p className="col-span-full text-sm text-muted-foreground">No attrition risk data available. Run analytics to populate.</p>
                  ) : (
                    attritionRisk.map((row) => (
                      <div key={row.dept} className="flex items-center justify-between rounded-lg border border-border bg-background/40 p-3">
                        <div>
                          <p className="font-medium text-foreground">{row.dept}</p>
                          <p className="text-xs text-muted-foreground">{row.note}</p>
                        </div>
                        <Badge variant="outline" className={statusColor(row.risk)}>{row.risk}</Badge>
                      </div>
                    ))
                  )}
                </div>
                <div className="mt-4 rounded-lg border border-border bg-background/40 p-4 text-sm text-muted-foreground">
                  Combine surveys, absence, performance, and scheduling load to flag retention risk.
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── SCHEDULE ──────────────────────────────────────────────────
      case "schedule": {
        return (
          <div className="space-y-6">
            {/* Demand forecast summary */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground" /> Demand forecast
                </CardTitle>
                <CardDescription>Required vs scheduled staff for upcoming days.</CardDescription>
              </CardHeader>
              <CardContent>
                {schedLoading ? (
                  <p className="text-sm text-muted-foreground">Loading forecast…</p>
                ) : demandForecast && demandForecast.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-xs text-muted-foreground">
                          <th className="py-2 px-3 text-left">Date</th>
                          <th className="py-2 px-3 text-right">Required</th>
                          <th className="py-2 px-3 text-right">Scheduled</th>
                          <th className="py-2 px-3 text-right">Gap</th>
                        </tr>
                      </thead>
                      <tbody>
                        {demandForecast.slice(0, 7).map((row) => (
                          <tr key={row.date} className="border-b border-border/50">
                            <td className="py-2 px-3 text-foreground">{row.date}</td>
                            <td className="py-2 px-3 text-right text-foreground">{row.required_staff}</td>
                            <td className="py-2 px-3 text-right text-foreground">{row.scheduled_staff}</td>
                            <td className={`py-2 px-3 text-right ${row.gap > 0 ? "text-red-400" : "text-emerald-400"}`}>{row.gap > 0 ? `+${row.gap}` : row.gap}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-3">
                    {[
                      { label: "Next 7 days", value: "No data yet" },
                      { label: "Required staff/day", value: "—" },
                      { label: "Scheduled staff/day", value: "—" },
                    ].map((m) => (
                      <div key={m.label} className="rounded-lg border border-border bg-background/40 p-4">
                        <p className="text-xs text-muted-foreground">{m.label}</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{m.value}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Schedule list */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-muted-foreground" /> Staff schedules
                </CardTitle>
                <CardDescription>Shift assignments by date and department.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex justify-end">
                  <Button size="sm" variant="outline" onClick={handleCreateSchedule}>New schedule</Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Date</th>
                        <th className="py-2 pr-4 font-medium">Shift</th>
                        <th className="py-2 pr-4 font-medium">Department</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schedLoading ? (
                        <LoadingRow cols={6} />
                      ) : schedError ? (
                        <ErrorRow message={schedError} cols={6} />
                      ) : schedules.length === 0 ? (
                        <tr><td colSpan={6} className="py-4 text-center text-sm text-muted-foreground">No schedules found.</td></tr>
                      ) : (
                        schedules.slice(0, 50).map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.schedule_date}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.shift_start} – {row.shift_end}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.department}</td>
                            <td className="py-3 pr-4">
                              <Badge variant="outline" className={row.status === "CONFIRMED" ? "border-emerald-500/40 text-emerald-500" : "border-amber-500/40 text-amber-500"}>
                                {row.status === "CONFIRMED" ? "Confirmed" : row.status ?? "Scheduled"}
                              </Badge>
                            </td>
                            <td className="py-3">
                              <div className="flex flex-wrap gap-2">
                                {row.status !== "CONFIRMED" && (
                                  <Button size="sm" variant="outline" onClick={() => handleConfirmSchedule(row.id)}>Confirm</Button>
                                )}
                                <Button size="sm" variant="ghost" onClick={() => handleDeleteSchedule(row.id)}>Delete</Button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )
      }

      // ── TRAINING ──────────────────────────────────────────────────
      case "training":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <GraduationCap className="h-4 w-4 text-muted-foreground" /> Training courses
                </CardTitle>
                <CardDescription>Manage courses, categories, and mandatory requirements.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex justify-end">
                  <Button size="sm" variant="outline" onClick={handleCreateCourse}>New course</Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Title</th>
                        <th className="py-2 pr-4 font-medium">Category</th>
                        <th className="py-2 pr-4 font-medium">Duration (hrs)</th>
                        <th className="py-2 pr-4 font-medium">Mandatory</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trainingLoading ? (
                        <LoadingRow cols={5} />
                      ) : trainingError ? (
                        <ErrorRow message={trainingError} cols={5} />
                      ) : trainingCourses.length === 0 ? (
                        <tr><td colSpan={5} className="py-4 text-center text-sm text-muted-foreground">No training courses found.</td></tr>
                      ) : (
                        trainingCourses.map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.title}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.category}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.duration_hours ?? "—"}</td>
                            <td className="py-3 pr-4">
                              <Badge variant="outline" className={row.mandatory ? "border-red-500/40 text-red-400" : "border-muted text-muted-foreground"}>
                                {row.mandatory ? "Yes" : "No"}
                              </Badge>
                            </td>
                            <td className="py-3"><Button size="sm" variant="outline">Edit</Button></td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-muted-foreground" /> Employee training progress
                </CardTitle>
                <CardDescription>Enrollment and completion tracking.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex justify-end">
                  <Button size="sm" variant="outline" onClick={handleEnrollEmployee}>Enroll employee</Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Course ID</th>
                        <th className="py-2 pr-4 font-medium">Progress</th>
                        <th className="py-2 pr-4 font-medium">Score</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trainingLoading ? (
                        <LoadingRow cols={6} />
                      ) : trainingError ? (
                        <ErrorRow message={trainingError} cols={6} />
                      ) : trainingEnrollments.length === 0 ? (
                        <tr><td colSpan={6} className="py-4 text-center text-sm text-muted-foreground">No enrollments found.</td></tr>
                      ) : (
                        trainingEnrollments.slice(0, 50).map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.course_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.progress_pct}%</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.score ?? "—"}</td>
                            <td className="py-3 pr-4"><StatusBadge status={row.status} /></td>
                            <td className="py-3">
                              <Button size="sm" variant="outline" onClick={async () => {
                                try {
                                  await updateTrainingProgress(row.id, Math.min(row.progress_pct + 25, 100))
                                  setTrainingEnrollments((prev) => prev.map((e) => e.id === row.id ? { ...e, progress_pct: Math.min(e.progress_pct + 25, 100) } : e))
                                } catch { /* ignore */ }
                              }}>Update</Button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── BENEFITS ──────────────────────────────────────────────────
      case "benefits": {
        // Group benefits by type
        const benefitsByType: Record<string, Benefit[]> = {}
        benefitsList.forEach((b) => {
          if (!benefitsByType[b.benefit_type]) benefitsByType[b.benefit_type] = []
          benefitsByType[b.benefit_type].push(b)
        })

        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Gift className="h-4 w-4 text-muted-foreground" /> Benefits overview
                </CardTitle>
                <CardDescription>Enrollment by type: leave, shares, bonuses, medical, pension.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex justify-end">
                  <Button size="sm" variant="outline" onClick={handleCreateBenefit}>New enrollment</Button>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {benefitsLoading ? (
                    <p className="col-span-full text-sm text-muted-foreground">Loading benefits…</p>
                  ) : benefitsError ? (
                    <p className="col-span-full text-sm text-red-400">Error: {benefitsError}</p>
                  ) : Object.keys(benefitsByType).length === 0 ? (
                    <p className="col-span-full text-sm text-muted-foreground">No benefit enrollments found.</p>
                  ) : (
                    Object.entries(benefitsByType).map(([type, items]) => (
                      <div key={type} className="rounded-lg border border-border bg-background/40 p-4">
                        <p className="text-sm font-semibold text-foreground capitalize">{type}</p>
                        <p className="mt-1 text-2xl font-bold text-foreground">{items.length}</p>
                        <p className="mt-1 text-xs text-muted-foreground">enrolled</p>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Benefit enrollments</CardTitle>
                <CardDescription>Detailed list of all benefit records.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[600px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Type</th>
                        <th className="py-2 pr-4 font-medium">Created</th>
                        <th className="py-2 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {benefitsLoading ? (
                        <LoadingRow cols={4} />
                      ) : benefitsError ? (
                        <ErrorRow message={benefitsError} cols={4} />
                      ) : benefitsList.length === 0 ? (
                        <tr><td colSpan={4} className="py-4 text-center text-sm text-muted-foreground">No benefits found.</td></tr>
                      ) : (
                        benefitsList.slice(0, 50).map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4 text-muted-foreground capitalize">{row.benefit_type}</td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.created_at?.slice(0, 10) ?? "—"}</td>
                            <td className="py-3"><Button size="sm" variant="outline">View</Button></td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )
      }

      // ── DISCIPLINARY ──────────────────────────────────────────────
      case "disciplinary":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-muted-foreground" /> Disciplinary actions
                </CardTitle>
                <CardDescription>Warnings, suspensions, and dismissals tracking.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex justify-end">
                  <Button size="sm" variant="outline" onClick={handleCreateDisciplinary}>New action</Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Type</th>
                        <th className="py-2 pr-4 font-medium">Incident Date</th>
                        <th className="py-2 pr-4 font-medium">Description</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {disciplinaryLoading ? (
                        <LoadingRow cols={6} />
                      ) : disciplinaryError ? (
                        <ErrorRow message={disciplinaryError} cols={6} />
                      ) : disciplinaryActions.length === 0 ? (
                        <tr><td colSpan={6} className="py-4 text-center text-sm text-muted-foreground">No disciplinary actions found.</td></tr>
                      ) : (
                        disciplinaryActions.slice(0, 50).map((row) => (
                          <tr key={row.id} className="border-b border-border/60 text-sm">
                            <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                            <td className="py-3 pr-4">
                              <Badge variant="outline" className={
                                row.action_type === "DISMISSAL" ? "border-red-500/40 text-red-400" :
                                row.action_type === "SUSPENSION" ? "border-orange-500/40 text-orange-400" :
                                row.action_type === "FINAL_WARNING" ? "border-amber-500/40 text-amber-500" :
                                "border-muted text-muted-foreground"
                              }>{row.action_type}</Badge>
                            </td>
                            <td className="py-3 pr-4 text-muted-foreground">{row.incident_date}</td>
                            <td className="py-3 pr-4 text-muted-foreground max-w-[200px] truncate">{row.description}</td>
                            <td className="py-3 pr-4"><StatusBadge status={row.status} /></td>
                            <td className="py-3">
                              {row.status !== "Resolved" && (
                                <Button size="sm" variant="outline" onClick={() => handleResolveDisciplinary(row.id)}>Resolve</Button>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )

      // ── EXIT ──────────────────────────────────────────────────────
      case "exit":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <LogOut className="h-4 w-4 text-muted-foreground" /> Staff exit records
                </CardTitle>
                <CardDescription>Resignations, terminations, and retirement tracking.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex justify-end">
                  <Button size="sm" variant="outline" onClick={handleCreateExit}>New exit record</Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px]">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Employee ID</th>
                        <th className="py-2 pr-4 font-medium">Type</th>
                        <th className="py-2 pr-4 font-medium">Notice Date</th>
                        <th className="py-2 pr-4 font-medium">Last Working Day</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 font-medium">Checklist</th>
                      </tr>
                    </thead>
                    <tbody>
                      {exitLoading ? (
                        <LoadingRow cols={6} />
                      ) : exitError ? (
                        <ErrorRow message={exitError} cols={6} />
                      ) : exitRecords.length === 0 ? (
                        <tr><td colSpan={6} className="py-4 text-center text-sm text-muted-foreground">No exit records found.</td></tr>
                      ) : (
                        exitRecords.slice(0, 50).map((row) => {
                          const cl = exitChecklists[row.id]
                          return (
                            <tr key={row.id} className="border-b border-border/60 text-sm">
                              <td className="py-3 pr-4 text-foreground">{row.employee_id.slice(0, 8)}…</td>
                              <td className="py-3 pr-4">
                                <Badge variant="outline" className={
                                  row.exit_type === "Termination" ? "border-red-500/40 text-red-400" :
                                  row.exit_type === "Retirement" ? "border-blue-500/40 text-blue-400" :
                                  "border-muted text-muted-foreground"
                                }>{row.exit_type}</Badge>
                              </td>
                              <td className="py-3 pr-4 text-muted-foreground">{row.notice_date}</td>
                              <td className="py-3 pr-4 text-muted-foreground">{row.last_working_date}</td>
                              <td className="py-3 pr-4"><StatusBadge status={row.status} /></td>
                              <td className="py-3">
                                <div className="flex flex-wrap gap-1">
                                  <Button size="sm" variant={cl?.exit_interview_done ? "secondary" : "ghost"} onClick={() => handleUpdateExitChecklist(row.id, "exit_interview_done")}>
                                    {cl?.exit_interview_done ? "✓" : "○"} Interview
                                  </Button>
                                  <Button size="sm" variant={cl?.assets_returned ? "secondary" : "ghost"} onClick={() => handleUpdateExitChecklist(row.id, "assets_returned")}>
                                    {cl?.assets_returned ? "✓" : "○"} Assets
                                  </Button>
                                  <Button size="sm" variant={cl?.access_revoked ? "secondary" : "ghost"} onClick={() => handleUpdateExitChecklist(row.id, "access_revoked")}>
                                    {cl?.access_revoked ? "✓" : "○"} Access
                                  </Button>
                                </div>
                              </td>
                            </tr>
                          )
                        })
                      )}
                    </tbody>
                  </table>
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
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleExport}><Download className="h-3.5 w-3.5" />Export</Button>
            <Button variant="cta" size="sm" onClick={handleNewEmployee}><Plus className="h-3.5 w-3.5" />New Employee</Button>
          </>
        }
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
                      <YAxis type="category" dataKey="department" tick={{ fill: "#737373", fontSize: 12 }} width={80} />
                      <Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} />
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
                        dataKey="value"
                        nameKey="department"
                      />
                      <Tooltip contentStyle={{ backgroundColor: "#262626", border: "1px solid #404040", borderRadius: "8px", color: "#fff" }} />
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
