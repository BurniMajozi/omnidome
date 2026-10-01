"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { NoDataYet, NotConnected, StatValue } from "@/components/ui/not-connected"
import { PageHeader } from "@/components/ui/page-header"
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Building2,
  Calendar,
  CalendarDays,
  ChevronDown,
  Gift,
  GraduationCap,
  LogOut,
  ShieldCheck,
  Sparkles,
  Users,
  UserCog,
  Target,
  TrendingUp,
  Bot,
  CheckCircle2,
  FileText,
} from "lucide-react"
import {
  listEmployees,
  listLeaveRequests,
  listTrainingCourses,
  getEmployeeTraining,
  listDisciplinary,
  listExits,
  getDepartmentCostAllocation,
  getStaffComplianceAudit,
  getOrchestratorWellnessInsights,
  executeOrchestratorAction,
  getPerformanceSummary,
  getWhoami,
  loadableFromError,
  type Employee,
  type LeaveRequest,
  type TrainingCourse,
  type TrainingEnrollment,
  type DisciplinaryAction,
  type ExitRecord,
  type PerformanceSummaryRow,
} from "@/lib/hr-api"
import {
  averageScore,
  collectOrThrow,
  exitsInLast12Months,
  formatHrError,
  hasHrAdminRole,
  mapLimit,
  turnoverPct,
  type FanOutResult,
} from "@/lib/talent-derive"
import type { Loadable } from "@/lib/service-state"
import { OnboardingKbView } from "./talent/onboarding-kb-view"
import { OrgChartView } from "./talent/org-chart-view"
import { PayrollPayslipsView } from "./talent/payroll-payslips-view"
import { PimDirectoryView } from "./talent/pim-directory-view"
import { LeaveJourneyView } from "./talent/leave-journey-view"
import { ReportsAnalyticsView } from "./talent/reports-analytics-view"
import { BenefitsPortalView } from "./talent/benefits-portal-view"
import { ServiceSchedulingView } from "./service/service-scheduling-view"
import { TalentTrainingView } from "./talent/talent-training-view"
import { TalentDisciplinaryView } from "./talent/talent-disciplinary-view"
import { TalentCultureView } from "./talent/talent-culture-view"
import { TalentExitView } from "./talent/talent-exit-view"
import { PerformanceObjectivesView } from "./talent/performance-objectives-view"

// ── Panel type & config ──────────────────────────────────────────────

type StaffPanelKey =
  | "directory"
  | "time"
  | "org_chart"
  | "onboarding"
  | "payroll"
  | "wellness_ai"
  | "performance"
  | "schedule"
  | "training"
  | "benefits"
  | "disciplinary"
  | "exit"
  | "culture"
  | "compliance_audit"
  | "reporting"

interface PanelMeta {
  key: StaffPanelKey
  title: string
  icon: React.ComponentType<{ className?: string }>
  tags: string[]
  /** Hidden from users without an HR-admin role (the backend returns 403 for them). */
  adminOnly?: boolean
}

const panelConfig: PanelMeta[] = [
  { key: "reporting", title: "Workforce Analysis", icon: BarChart3, tags: ["Staff Pipeline", "Headcount", "Attrition"] },
  { key: "culture", title: "Culture & Strategy", icon: Sparkles, tags: ["Strategy & OKRs", "5 Core Values", "Kudos Wall", "LLM Orchestrator"] },
  { key: "org_chart", title: "Hierarchical Org Structure", icon: Building2, tags: ["Zoom Controls", "Dynamic Sizing", "Direct Reports"] },
  { key: "performance", title: "Performance & Objectives", icon: Target, tags: ["KPI Tracker", "Competencies", "Attrition Risk"] },
  { key: "onboarding", title: "Knowledge & Onboarding", icon: BookOpen, tags: ["Checklists", "Markdown RAG Search"] },
  { key: "wellness_ai", title: "AI Talent Orchestrator", icon: Bot, tags: ["Burnout Risk", "Fatigue Detection", "Actions"] },
  { key: "time", title: "Leave Journey & Approvals", icon: CalendarDays, tags: ["BCEA 21-Day Annual", "Live Approvals"] },
  { key: "schedule", title: "Staff Shift Scheduling", icon: Calendar, tags: ["Service Operations Driven", "Interactive Roster", "Broker Costs"] },
  { key: "training", title: "Training & Development", icon: GraduationCap, tags: ["Courses", "Enrolments", "Progress"] },
  { key: "benefits", title: "Benefits & Care Corner", icon: Gift, tags: ["Provident Fund", "Medical Aid Options", "Employee Support"] },
  { key: "directory", title: "Personnel Directory (PIM)", icon: Users, tags: ["Employee 360", "Add Employee", "31-Module Matrix"] },
  { key: "payroll", title: "Payroll & Payslip Designer", icon: Gift, tags: ["SARS PAYE", "Payroll runs", "Payslips"], adminOnly: true },
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

interface StatCardProps {
  title: string
  value: React.ReactNode
  icon: React.ComponentType<{ className?: string }>
  description?: string
}

function StatCard({ title, value, icon: Icon, description }: StatCardProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">{title}</p>
            <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
            {description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
          </div>
          <Icon className="h-8 w-8 text-muted-foreground" />
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Loads data once the panel is active (and again on `reload`, which bypasses the
 * shared cache). Always runs the same hooks in the same order (no conditional
 * hooks). A failure keeps its HTTP meaning: 403 => "Not permitted", never an empty list.
 */
function usePanelLoad<T>(active: boolean, loader: (fresh: boolean) => Promise<T>): { value: Loadable<T>; reload: () => void } {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader
  const freshRef = useRef(false)

  useEffect(() => {
    if (!active) return
    let cancelled = false
    const fresh = freshRef.current
    freshRef.current = false
    loaderRef
      .current(fresh)
      .then((data) => {
        if (!cancelled) setValue({ state: "ready", data })
      })
      .catch((err) => {
        if (!cancelled) setValue(loadableFromError(err))
      })
    return () => {
      cancelled = true
    }
  }, [active, tick])

  const reload = useCallback(() => {
    freshRef.current = true
    setTick((t) => t + 1)
  }, [])
  return { value, reload }
}

/** Renders `children(data)` when ready, otherwise the shared honest state (loading / Not permitted / Service not running). */
function Gate<T>({
  value,
  service,
  onRetry,
  children,
}: {
  value: Loadable<T>
  service: string
  onRetry?: () => void
  children: (data: T) => React.ReactNode
}) {
  if (value.state === "ready") return <>{children(value.data)}</>
  return <NotConnected loadable={value} service={service} onRetry={onRetry} />
}

// ── Main component ───────────────────────────────────────────────────

export function TalentModule() {
  const [activePanel, setActivePanel] = useState<StaffPanelKey>("reporting")

  // Roles (from /api/whoami): HR-admin-only tabs and actions are hidden from everyone else.
  const [roles, setRoles] = useState<string[] | null>(null)
  const isHrAdmin = hasHrAdminRole(roles)
  useEffect(() => {
    let cancelled = false
    void getWhoami().then((w) => {
      if (!cancelled) setRoles(w?.roles ?? [])
    })
    return () => {
      cancelled = true
    }
  }, [])

  const visiblePanels = useMemo(() => panelConfig.filter((p) => !p.adminOnly || isHrAdmin), [isHrAdmin])
  useEffect(() => {
    if (roles !== null && !visiblePanels.some((p) => p.key === activePanel)) setActivePanel("reporting")
  }, [roles, visiblePanels, activePanel])
  const activePanelMeta = useMemo(
    () => visiblePanels.find((panel) => panel.key === activePanel) ?? visiblePanels[0],
    [activePanel, visiblePanels],
  )

  // ── Employees: loaded ONCE here and shared with every panel (no per-panel refetch) ──
  const [employees, setEmployees] = useState<Employee[]>([])
  const [empLoad, setEmpLoad] = useState<Loadable<null>>({ state: "loading" })
  const loadEmployees = useCallback(async (fresh = false) => {
    try {
      const data = await listEmployees(undefined, { fresh })
      setEmployees(data)
      setEmpLoad({ state: "ready", data: null })
    } catch (err) {
      setEmpLoad(loadableFromError(err))
    }
  }, [])
  useEffect(() => {
    void loadEmployees()
  }, [loadEmployees])

  // ── Exits: once, for the Turnover tile, the analysis panel and the Exit panel ──
  const exits = usePanelLoad<ExitRecord[]>(true, (fresh) => listExits(undefined, { fresh }))

  // ── KPI summary: ONE bulk request (never a per-employee fan-out from the header) ──
  const employeeIds = useMemo(() => employees.map((e) => e.id), [employees])
  const [perfSummary, setPerfSummary] = useState<Loadable<PerformanceSummaryRow[] | null>>({ state: "loading" })
  useEffect(() => {
    if (employeeIds.length === 0) {
      if (empLoad.state === "ready") setPerfSummary({ state: "ready", data: [] })
      return
    }
    let cancelled = false
    getPerformanceSummary(employeeIds, { bulkOnly: true })
      .then((rows) => {
        if (!cancelled) setPerfSummary({ state: "ready", data: rows })
      })
      .catch((err) => {
        if (!cancelled) setPerfSummary(loadableFromError(err))
      })
    return () => {
      cancelled = true
    }
  }, [employeeIds, empLoad.state])

  // ── Per-panel data ──
  const leave = usePanelLoad<LeaveRequest[]>(activePanel === "time", async (fresh) => {
    const emps = await listEmployees(undefined, { fresh: false })
    const results = await mapLimit(
      emps,
      4,
      async (e): Promise<FanOutResult<LeaveRequest[]>> => ({ ok: true, rows: await listLeaveRequests(e.id, { fresh }) }),
      (err): FanOutResult<LeaveRequest[]> => ({ ok: false, err }),
    )
    return collectOrThrow(results)
  })

  const training = usePanelLoad<{ courses: TrainingCourse[]; enrollments: TrainingEnrollment[]; enrollmentsNote: string | null }>(
    activePanel === "training",
    async (fresh) => {
      const courses = await listTrainingCourses(undefined, { fresh })
      const emps = await listEmployees(undefined, { fresh: false })
      try {
        const results = await mapLimit(
          emps,
          4,
          async (e): Promise<FanOutResult<TrainingEnrollment[]>> => ({ ok: true, rows: await getEmployeeTraining(e.id, { fresh }) }),
          (err): FanOutResult<TrainingEnrollment[]> => ({ ok: false, err }),
        )
        return { courses, enrollments: collectOrThrow(results), enrollmentsNote: null }
      } catch (err) {
        return { courses, enrollments: [], enrollmentsNote: formatHrError(err) }
      }
    },
  )

  const disciplinary = usePanelLoad<DisciplinaryAction[]>(activePanel === "disciplinary", (fresh) => listDisciplinary(undefined, { fresh }))
  const deptCost = usePanelLoad(activePanel === "payroll", () => getDepartmentCostAllocation())
  const compliance = usePanelLoad(activePanel === "compliance_audit", () => getStaffComplianceAudit())
  const wellness = usePanelLoad(activePanel === "wellness_ai", () => getOrchestratorWellnessInsights())

  const [executingAlertId, setExecutingAlertId] = useState<string | null>(null)
  const [wellnessActionMsg, setWellnessActionMsg] = useState<{ id: string; message: string } | null>(null)
  const [wellnessActionError, setWellnessActionError] = useState<string | null>(null)
  const handleExecuteWellnessAction = async (alertId: string, alertType: string) => {
    try {
      setExecutingAlertId(alertId)
      setWellnessActionError(null)
      const res = await executeOrchestratorAction(alertId, alertType)
      setWellnessActionMsg({ id: alertId, message: res.message || res.action })
    } catch (err: unknown) {
      setWellnessActionError(formatHrError(err))
    } finally {
      setExecutingAlertId(null)
    }
  }

  // ── Header KPI values: only from real rows ──
  const turnover = useMemo(() => {
    if (exits.value.state !== "ready" || empLoad.state !== "ready") return null
    return turnoverPct(exitsInLast12Months(exits.value.data, new Date()), employees.length)
  }, [exits.value, empLoad.state, employees.length])
  const avgKpi = useMemo(() => {
    if (perfSummary.state !== "ready" || perfSummary.data === null) return null
    return averageScore(perfSummary.data)
  }, [perfSummary])

  const empReady = empLoad.state === "ready"
  const empGate = (render: () => React.ReactNode) =>
    empReady ? render() : <NotConnected loadable={empLoad} service="Employee directory" onRetry={() => void loadEmployees(true)} />

  // ── Render panels ─────────────────────────────────────────────────
  const renderActivePanel = () => {
    switch (activePanel) {
      case "onboarding":
        return empGate(() => <OnboardingKbView employees={employees} />)

      case "directory":
        return empGate(() => (
          <PimDirectoryView employees={employees} loading={false} error={null} onRefresh={() => void loadEmployees(true)} />
        ))

      case "org_chart":
        return empGate(() => (
          <div className="space-y-6 min-w-0 w-full max-w-full overflow-hidden">
            <OrgChartView employees={employees} onRefresh={() => loadEmployees(true)} />
          </div>
        ))

      case "payroll":
        return (
          <PayrollPayslipsView
            deptCostAllocation={deptCost.value.state === "ready" ? deptCost.value.data : null}
            deptCostLoadable={deptCost.value}
            isHrAdmin={isHrAdmin}
          />
        )

      case "time":
        return empGate(() => (
          <Gate value={leave.value} service="Leave requests" onRetry={leave.reload}>
            {(rows) => (
              <LeaveJourneyView
                employees={employees}
                leaveRequests={rows}
                loading={false}
                error={null}
                onRefresh={() => {
                  void loadEmployees(true)
                  leave.reload()
                }}
              />
            )}
          </Gate>
        ))

      case "reporting":
        return empGate(() => (
          <ReportsAnalyticsView employees={employees} exits={exits.value} onRetryExits={exits.reload} />
        ))

      case "performance":
        return empGate(() => (
          <div className="space-y-6 min-w-0 w-full max-w-full">
            <PerformanceObjectivesView employees={employees} onRefresh={() => loadEmployees(true)} />
          </div>
        ))

      case "culture":
        return empGate(() => <TalentCultureView employees={employees} />)

      case "schedule":
        return (
          <div className="space-y-4">
            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 text-xs text-cyan-200">
                <Sparkles className="h-4 w-4 text-cyan-400 shrink-0" />
                <span>
                  <strong>Operational Synergy:</strong> Staff Shift Scheduling is coupled directly to the <strong>Service Panel</strong> where subscriber ticket volumes, MTTR/FTR skill tags, and call center demand drive human and broker rostering.
                </span>
              </div>
            </div>
            <ServiceSchedulingView />
          </div>
        )

      case "training":
        return empGate(() => (
          <Gate value={training.value} service="Training" onRetry={training.reload}>
            {(t) => (
              <TalentTrainingView
                employees={employees}
                courses={t.courses}
                enrollments={t.enrollments}
                enrollmentsNote={t.enrollmentsNote}
                onRefresh={training.reload}
              />
            )}
          </Gate>
        ))

      case "benefits":
        return empGate(() => <BenefitsPortalView employees={employees} />)

      case "disciplinary":
        return empGate(() => (
          <Gate value={disciplinary.value} service="Disciplinary records" onRetry={disciplinary.reload}>
            {(rows) => <TalentDisciplinaryView employees={employees} actions={rows} onRefresh={disciplinary.reload} />}
          </Gate>
        ))

      case "exit":
        return empGate(() => (
          <Gate value={exits.value} service="Exit records" onRetry={exits.reload}>
            {(rows) => <TalentExitView employees={employees} exits={rows} onRefresh={exits.reload} />}
          </Gate>
        ))

      case "compliance_audit":
        return (
          <Gate value={compliance.value} service="Labor compliance audit" onRetry={compliance.reload}>
            {(c) => (
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <StatCard title="Overall Readiness Score" value={`${c.overall_readiness_score}%`} icon={ShieldCheck} description="as reported by the compliance audit" />
                  <StatCard title="RICA Accredited Officers" value={c.rica_accredited_officers_count} icon={CheckCircle2} description={`${c.rica_verifications_completed} verifications completed`} />
                  <StatCard title="Foreign Worker DHA Permits" value={c.foreign_workers_with_permits} icon={FileText} description={`${c.expiring_permits_count} expiring soon`} />
                  <StatCard title="H&S Incidents (YTD)" value={c.health_and_safety_incidents} icon={AlertTriangle} description="recorded incidents" />
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-muted-foreground" /> Statutory & Regulatory Compliance Audit
                    </CardTitle>
                    <CardDescription>Cross-service figures for RICA, POPIA, Department of Home Affairs, BCEA and OHS Act.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                        <span className="font-semibold text-foreground">RICA Act</span>
                        <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                          <span>RICA officers: <strong>{c.rica_accredited_officers_count}</strong></span>
                          <span>Verifications completed: <strong>{c.rica_verifications_completed}</strong></span>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                        <span className="font-semibold text-foreground">DHA Foreign Worker Permits</span>
                        <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                          <span>Active permits: <strong>{c.foreign_workers_with_permits}</strong></span>
                          <span>Expiring soon: <strong>{c.expiring_permits_count}</strong></span>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                        <span className="font-semibold text-foreground">POPIA</span>
                        <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                          <span>Certified staff: <strong>{c.popia_certified_count} of {c.total_staff}</strong></span>
                          <span>Compliance: <strong>{c.popia_compliance_pct}%</strong></span>
                        </div>
                      </div>
                      <div className="rounded-lg border border-border bg-background/40 p-4 space-y-2">
                        <span className="font-semibold text-foreground">BCEA leave & OHS</span>
                        <div className="pt-2 text-xs text-muted-foreground flex justify-between">
                          <span>BCEA leave compliance: <strong>{c.bcea_leave_compliance_pct}%</strong></span>
                          <span>H&S incidents: <strong>{c.health_and_safety_incidents}</strong></span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </Gate>
        )

      case "wellness_ai":
        return (
          <Gate value={wellness.value} service="Workforce orchestrator" onRetry={wellness.reload}>
            {(alerts) => (
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <StatCard title="Active AI Insights" value={alerts.length} icon={Bot} description="workforce orchestrator" />
                  <StatCard title="High Risk Alerts" value={alerts.filter((a) => a.severity === "high").length} icon={AlertTriangle} description="requires intervention" />
                  <StatCard title="Medium Alerts" value={alerts.filter((a) => a.severity === "medium").length} icon={AlertTriangle} description="monitor" />
                  <StatCard title="Skill Gap Opportunities" value={alerts.filter((a) => a.alert_type?.includes("SKILL")).length} icon={Sparkles} description="upskilling recommended" />
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
                      {wellnessActionError && <p className="text-sm text-red-400" role="alert">{wellnessActionError}</p>}
                      {alerts.length === 0 ? (
                        <NoDataYet message="No wellness alerts flagged." />
                      ) : (
                        alerts.map((alert) => (
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
                              <span><strong>AI Recommendation:</strong> {alert.recommendation}</span>
                              <Button
                                size="sm"
                                variant="cta"
                                className="h-7 text-xs flex-shrink-0"
                                disabled={executingAlertId === alert.id || wellnessActionMsg?.id === alert.id || !isHrAdmin}
                                title={!isHrAdmin ? "HR admin only" : undefined}
                                onClick={() => handleExecuteWellnessAction(alert.id, alert.alert_type)}
                              >
                                {executingAlertId === alert.id ? "Executing…" : wellnessActionMsg?.id === alert.id ? "Executed" : "Execute Action"}
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
            )}
          </Gate>
        )

      default:
        return null
    }
  }

  // ── Main render ────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      <PageHeader
        icon={<UserCog className="h-5 w-5" />}
        title="Talent & HR"
        subtitle="Employee management, onboarding, performance, and workforce planning"
      />

      {/* KPI Cards: every figure is a real row count/score, or an honest state */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Employees"
          value={<StatValue loadable={empLoad}>{() => employees.length}</StatValue>}
          icon={UserCog}
          description="from the HR service"
        />
        <StatCard
          title="Open Positions"
          value={<span className="text-sm font-medium text-muted-foreground">Not connected</span>}
          icon={Target}
          description="no recruitment source is connected"
        />
        <StatCard
          title="Avg KPI Score"
          value={
            <StatValue loadable={perfSummary}>
              {(rows) =>
                rows === null ? (
                  <span className="text-sm font-medium text-muted-foreground">Not connected</span>
                ) : avgKpi ? (
                  `${avgKpi.avg}%`
                ) : (
                  "—"
                )
              }
            </StatValue>
          }
          icon={TrendingUp}
          description={avgKpi ? `${avgKpi.scored} scored KPI sheet${avgKpi.scored === 1 ? "" : "s"}` : "no scored KPI sheets yet"}
        />
        <StatCard
          title="Turnover Rate"
          value={
            <StatValue loadable={exits.value}>
              {() => (turnover === null ? "—" : `${turnover}%`)}
            </StatValue>
          }
          icon={Users}
          description="exits in the last 12 months / headcount"
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
                {visiblePanels.map((panel) => (
                  <DropdownMenuItem key={panel.key} onClick={() => setActivePanel(panel.key)} className="gap-2">
                    <panel.icon className="h-4 w-4 text-muted-foreground" />
                    {panel.title}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            <div className="mt-4 space-y-1">
              {visiblePanels.map((panel) => {
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

        <div className="min-w-0 w-full max-w-full overflow-hidden">{renderActivePanel()}</div>
      </div>
    </div>
  )
}
