"use client"

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Target,
  TrendingUp,
  DollarSign,
  PieChart as PieChartIcon,
  Sparkles,
  Sliders,
  Users,
  Building2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Layers,
  Bot,
  HelpCircle,
  Save,
  Send,
  Plus,
  Trash2,
  Edit2,
  RefreshCw,
  Search,
  ChevronRight,
  ShieldCheck,
  Award,
  BarChart3,
  Percent,
  Check,
  SlidersHorizontal,
  Flame,
  Database,
  ArrowUpRight,
  ArrowDownRight,
  Gauge,
  Zap,
  ArrowUp,
  ArrowDown,
  Copy,
  Undo2,
  ChevronDown,
} from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts"
import {
  getCompanyKPIConfig,
  updateCompanyKPIConfig,
  cascadeSharedKPIs,
  getEmployeeKPISheet,
  updateEmployeeKPISheet,
  approveEmployeeKPISheet,
  rejectEmployeeKPISheet,
  reopenEmployeeKPISheet,
  type ValueKey,
  generateAISmartCriteria,
  getKpisLiveActuals,
  getPerformanceSummary,
  getWhoami,
  loadableFromError,
  listEmployees,
  type PerformanceSummaryRow,
  type Employee,
  type CompanyKPIConfig,
  type EmployeeKPISheet,
  type IndividualKPIItem,
  type SmartLevelCriterion,
  type LiveActualsResponse,
  type LiveActualsMetric,
} from "@/lib/hr-api"
import { fmtZar } from "@/lib/format"
import {
  clampLevel,
  companyIndexTile,
  estimateComposite,
  formatHrError,
  hasHrAdminRole,
  hrErrorStatus,
  levelScorePct,
  pickHeadline,
  pointsFromComposite,
} from "@/lib/talent-derive"
import { NotConnected } from "@/components/ui/not-connected"
import type { Loadable } from "@/lib/service-state"

interface PerformanceObjectivesViewProps {
  employees?: Employee[]
  onRefresh?: () => Promise<void>
}

// ── Default fallback company config ──────────────────────────────────
const INITIAL_COMPANY_CONFIG: CompanyKPIConfig = {
  id: "default-config",
  fiscal_year: "FY 2026/2027",
  // No figures are assumed: budgets/actuals stay at 0 (shown as "Not connected") until the HR service returns them.
  sales_budget_zar: 0,
  sales_actual_zar: 0,
  sales_achievement_pct: 0,
  cost_budget_zar: 0,
  cost_actual_zar: 0,
  cost_efficiency_pct: 0,
  profit_budget_zar: 0,
  profit_actual_zar: 0,
  profit_achievement_pct: 0,
  company_shared_score_pct: null,
  corporate_attainment_index: null,
  company_missing: true,
  values_weight_pct: 10.0,
  values_description: "Ubuntu & Customer Empathy, Operational Excellence & Speed, Staff Wellness (BCEA), POPIA & Ethical Governance",
  level_weights: {
    EXECUTIVE: 60.0,
    DIRECTOR: 40.0,
    MANAGER: 30.0,
    STAFF: 20.0,
  },
  sales_source_mode: "LIVE_TABLE",
  cost_source_mode: "LIVE_TABLE",
  profit_source_mode: "LIVE_TABLE",
}

// Stable empty default so a defaulted prop never changes identity between renders
const EMPTY_EMPLOYEES: Employee[] = []

type SmartCriteria = NonNullable<IndividualKPIItem["smart_criteria"]>
type LevelKey = keyof SmartCriteria
const LEVEL_KEYS: LevelKey[] = ["level_1", "level_2", "level_3", "level_4", "level_5"]
const KPI_CATEGORIES: string[] = ["Cost Optimization", "Revenue Growth", "Operational Excellence", "Customer Success"]

const fmtZAR = (val: number) => fmtZar(Number(val))

const makeKpiId = () => `kpi-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`

const blankLevel = (): SmartLevelCriterion => ({ timeline: "", measurable: "", requirement: "" })

const makeBlankCriteria = (): SmartCriteria => ({
  level_1: blankLevel(),
  level_2: blankLevel(),
  level_3: blankLevel(),
  level_4: blankLevel(),
  level_5: blankLevel(),
})

const normalizeCriteria = (c?: Partial<SmartCriteria> | null): SmartCriteria => {
  const out = makeBlankCriteria()
  for (const key of LEVEL_KEYS) {
    const src = c?.[key]
    if (src) out[key] = { ...src, timeline: src.timeline ?? "", measurable: src.measurable ?? "", requirement: src.requirement ?? "" }
  }
  return out
}

const makeBlankKpi = (): IndividualKPIItem => ({
  id: makeKpiId(),
  title: "",
  category: "Operational Excellence",
  weight_pct: 0,
  timeline: "",
  measurable: "",
  requirement: "",
  current_level: 3,
  score: 100,
  source_mode: "MANUAL",
  smart_criteria: makeBlankCriteria(),
})

const normalizeSheet = (sheet: EmployeeKPISheet): EmployeeKPISheet => ({
  ...sheet,
  kpis: (sheet.kpis || []).map((k) => ({
    ...k,
    id: k.id || makeKpiId(),
    title: k.title ?? "",
    category: k.category ?? "Operational Excellence",
    weight_pct: Number(k.weight_pct) || 0,
    timeline: k.timeline ?? "",
    measurable: k.measurable ?? "",
    requirement: k.requirement ?? "",
    smart_criteria: normalizeCriteria(k.smart_criteria),
  })),
})

const VALUE_DEFS: { key: ValueKey; label: string }[] = [
  { key: "ubuntu_empathy", label: "Ubuntu & Empathy" },
  { key: "operational_speed", label: "Operational Speed" },
  { key: "staff_wellness_bcea", label: "Staff Wellness / BCEA" },
  { key: "popia_ethical_governance", label: "POPIA & Ethical Governance" },
]

/** Score % for a KPI at its achieved level (level 3 = 100% of target; level is always clamped to 1-5). */
const kpiLevelScore = (k: IndividualKPIItem) => levelScorePct(k.current_level ?? 3)

/** Server text for inline messages (403 => "Not permitted: ...", 422 => "Rejected by the server: ..."). */
function describeApiError(err: unknown): string {
  return formatHrError(err)
}

// ── Preset ISP KPIs for 1-click drafting ─────────────────────────────
const PRESET_KPIS = [
  {
    title: "Reduce Operating & Cloud Infrastructure Costs",
    category: "Cost Optimization",
    suggestedWeight: 15,
    sourceMode: "LIVE_TABLE" as const,
    sourceMetricId: "payroll_statutory",
    measurable: "Maintain monthly AWS and datacenter expenses below R85k (12% reduction vs baseline)",
    timeline: "Monthly reviews, target achieved by end of Q3",
    requirement: "Monthly AWS billing invoice and audited CFO expense ledger",
  },
  {
    title: "Enterprise Fiber SLA & MTTR Acceleration",
    category: "Operational Excellence",
    suggestedWeight: 20,
    sourceMode: "LIVE_TABLE" as const,
    sourceMetricId: "network_mttr",
    measurable: "Reduce fiber core Mean Time to Repair (MTTR) to < 3.5 hours with 99.9% uptime",
    timeline: "Continuous telemetry monitoring / Quarterly sign-off",
    requirement: "Automated Zabbix outage logs and NOC Manager incident sign-offs",
  },
  {
    title: "High-Velocity Fiber B2B & FTTH Sales Expansion",
    category: "Revenue Growth",
    suggestedWeight: 25,
    sourceMode: "LIVE_TABLE" as const,
    sourceMetricId: "sales_leads_won",
    measurable: "Attain 100% of monthly sales quota (R250k new contracted MRR)",
    timeline: "Monthly quota cycle with quarterly compounding targets",
    requirement: "Signed 24/36 month customer SLAs and activated billing verification",
  },
  {
    title: "Zero-Avoidable-Churn & Retention Shield",
    category: "Customer Success",
    suggestedWeight: 15,
    sourceMode: "LIVE_TABLE" as const,
    sourceMetricId: "subscribers_churn",
    measurable: "Sustain subscriber churn below 1.8% per month across serviced FNO clusters",
    timeline: "Monthly cohort retention audit",
    requirement: "Billing churn report and call-center outreach logs",
  },
]

// ── Circular Speedometer Radial Dial Component ────────────────────────
interface CircularKPIGaugeProps {
  valuePct: number
  budgetFormatted: string
  actualFormatted: string
  title: string
  sublabel: string
  sourceMode?: string
  sourceLabel?: string
  colorTheme?: "emerald" | "blue" | "purple" | "amber"
  trendPct?: number
  isCostEfficiency?: boolean
  unavailable?: boolean
  /** Centre text when there is no figure (default "Not connected"). */
  unavailableLabel?: string
  /** Overrides the "Actual ..." caption (e.g. "Paid payroll YTD"). */
  actualLabel?: string
}

function CircularKPIGauge({
  valuePct,
  budgetFormatted,
  actualFormatted,
  title,
  sublabel,
  sourceMode = "LIVE_TABLE",
  sourceLabel,
  colorTheme = "emerald",
  trendPct,
  isCostEfficiency = false,
  unavailable = false,
  unavailableLabel = "Not connected",
  actualLabel,
}: CircularKPIGaugeProps) {
  // 240-degree arc gauge
  // Radius = 52, center = (65, 65)
  // Full circumference = 2 * PI * 52 = 326.72
  // Arc length = 326.72 * (240 / 360) = 217.81
  const radius = 52
  const strokeWidth = 8
  const fullCircumference = 2 * Math.PI * radius
  const arcLength = fullCircumference * (240 / 360)
  
  // Cap percentage representation for arc fill between 0% and 130%
  const clampedPct = unavailable ? 0 : Math.max(0, Math.min(130, valuePct))
  const progressRatio = clampedPct / 100
  const progressOffset = arcLength * (1 - Math.min(1.0, progressRatio * (100 / 130)))

  // Color schemes
  const colorMap = {
    emerald: {
      stroke: "#10b981",
      glow: "rgba(16, 185, 129, 0.25)",
      bg: "border-emerald-500/30 bg-emerald-500/5",
      badge: "border-emerald-500/40 text-emerald-400 bg-emerald-500/10",
      text: "text-emerald-400",
    },
    blue: {
      stroke: "#3b82f6",
      glow: "rgba(59, 130, 246, 0.25)",
      bg: "border-blue-500/30 bg-blue-500/5",
      badge: "border-blue-500/40 text-blue-400 bg-blue-500/10",
      text: "text-blue-400",
    },
    purple: {
      stroke: "#a855f7",
      glow: "rgba(168, 85, 247, 0.25)",
      bg: "border-purple-500/30 bg-purple-500/5",
      badge: "border-purple-500/40 text-purple-400 bg-purple-500/10",
      text: "text-purple-400",
    },
    amber: {
      stroke: "#f59e0b",
      glow: "rgba(245, 158, 11, 0.25)",
      bg: "border-amber-500/30 bg-amber-500/5",
      badge: "border-amber-500/40 text-amber-400 bg-amber-500/10",
      text: "text-amber-400",
    },
  }

  const theme = colorMap[colorTheme] || colorMap.emerald
  const isTargetAchieved = !unavailable && valuePct >= 100.0

  return (
    <Card className={`border transition-all duration-300 hover:shadow-md relative overflow-hidden ${theme.bg}`}>
      {/* Top Header */}
      <CardHeader className="p-3.5 pb-1 flex flex-row items-center justify-between space-y-0">
        <span className="text-xs font-semibold text-foreground tracking-tight flex items-center gap-1.5">
          <Gauge className={`h-3.5 w-3.5 ${theme.text}`} />
          {title}
        </span>
        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${theme.badge}`}>
          {sourceMode === "LIVE_TABLE" ? (
            <span className="flex items-center gap-1">
              <Zap className="h-2.5 w-2.5 animate-pulse text-amber-400" />
              Live Table
            </span>
          ) : sourceMode === "PERCENTAGE" ? (
            <span className="flex items-center gap-1">
              <Percent className="h-2.5 w-2.5" />
              Direct %
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <SlidersHorizontal className="h-2.5 w-2.5" />
              Manual
            </span>
          )}
        </Badge>
      </CardHeader>

      <CardContent className="p-3.5 pt-0">
        {/* Radial SVG Dial */}
        <div className="flex flex-col items-center justify-center my-1 relative">
          <div className="relative w-36 h-28 flex items-center justify-center">
            <svg
              className="w-36 h-36 transform -rotate-210"
              viewBox="0 0 130 130"
              style={{ filter: `drop-shadow(0 0 8px ${theme.glow})` }}
            >
              {/* Background Arc Track */}
              <circle
                cx="65"
                cy="65"
                r={radius}
                fill="none"
                stroke="currentColor"
                strokeWidth={strokeWidth}
                strokeDasharray={`${arcLength} ${fullCircumference}`}
                strokeLinecap="round"
                className="text-muted/30"
              />
              {/* 100% Target Notch Marker (around 77% of 130% max sweep) */}
              <circle
                cx="65"
                cy="65"
                r={radius}
                fill="none"
                stroke="#ffffff"
                strokeWidth={strokeWidth + 2}
                strokeDasharray={`2 ${fullCircumference}`}
                strokeDashoffset={-(arcLength * (100 / 130))}
                className="opacity-70"
              />
              {/* Foreground Colored Value Arc */}
              <circle
                cx="65"
                cy="65"
                r={radius}
                fill="none"
                stroke={theme.stroke}
                strokeWidth={strokeWidth}
                strokeDasharray={`${arcLength} ${fullCircumference}`}
                strokeDashoffset={progressOffset}
                strokeLinecap="round"
                className="transition-all duration-700 ease-out"
              />
            </svg>

            {/* Center Gauge Reading */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pt-5">
              {unavailable ? (
                <span className="text-sm font-bold tracking-tight text-muted-foreground text-center px-2">{unavailableLabel}</span>
              ) : (
                <div className="flex items-baseline gap-0.5">
                  <span className="text-2xl font-black tracking-tight text-foreground font-mono">
                    {valuePct.toFixed(1)}
                  </span>
                  <span className={`text-xs font-bold ${theme.text}`}>%</span>
                </div>
              )}
              <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                {sublabel}
              </span>
            </div>
          </div>

          {/* Directional Trend Pill */}
          <div className="mt-[-8px] flex items-center gap-1.5">
            {trendPct !== undefined && (
            <div
              className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                trendPct >= 0
                  ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                  : "border-rose-500/40 text-rose-400 bg-rose-500/10"
              }`}
            >
              {trendPct >= 0 ? (
                <ArrowUpRight className="h-3 w-3 shrink-0" />
              ) : (
                <ArrowDownRight className="h-3 w-3 shrink-0" />
              )}
              <span>{trendPct >= 0 ? `+${trendPct}%` : `${trendPct}%`}</span>
              <span className="text-muted-foreground font-normal ml-0.5">vs prior</span>
            </div>
            )}

            {isTargetAchieved && (
              <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[9px] px-1 py-0">
                100% On-Track
              </Badge>
            )}
          </div>
        </div>

        {/* Financial Numbers: Actual vs Budget */}
        <div className="mt-2.5 pt-2 border-t border-border/40 grid grid-cols-2 gap-2 text-xs">
          <div>
            <span className="text-[10px] text-muted-foreground block">
              {actualLabel ?? (isCostEfficiency ? "Actual Spend:" : "Actual Achieved:")}
            </span>
            <span className="font-bold text-foreground font-mono truncate block text-[11px]">
              {unavailable ? unavailableLabel : actualFormatted}
            </span>
          </div>
          <div className="text-right">
            <span className="text-[10px] text-muted-foreground block">
              {isCostEfficiency ? "Approved Ceiling:" : "Target Budget:"}
            </span>
            <span className="font-medium text-muted-foreground font-mono truncate block text-[11px]">
              {budgetFormatted}
            </span>
          </div>
        </div>

        {/* Source Table Subtext */}
        {sourceLabel && (
          <p className="mt-1 text-[9px] text-muted-foreground truncate" title={sourceLabel}>
            Source: <span className="font-mono text-foreground/80">{sourceLabel}</span>
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Main Component ───────────────────────────────────────────────────
export function PerformanceObjectivesView({ employees = EMPTY_EMPLOYEES, onRefresh }: PerformanceObjectivesViewProps) {
  // Navigation tabs: "individual" | "company" | "analytics"
  const [activeTab, setActiveTab] = useState<"individual" | "company" | "analytics">("individual")

  // Fallback internal employees list if parent passes empty
  const [internalEmployees, setInternalEmployees] = useState<Employee[]>(employees)
  const [loadingInternalEmps, setLoadingInternalEmps] = useState(false)

  // Roles from /api/whoami: HR-admin-only actions (cascade, company config, approvals) are disabled otherwise
  const [roles, setRoles] = useState<string[] | null>(null)
  const isHrAdmin = hasHrAdminRole(roles)
  const ADMIN_ONLY_TIP = "HR admin only"

  // Company config load outcome (so a 403/outage is shown honestly instead of as zeros)
  const [configLoad, setConfigLoad] = useState<Loadable<null>>({ state: "loading" })

  // Bulk performance summary (one request for all employees)
  const [perfSummary, setPerfSummary] = useState<Loadable<PerformanceSummaryRow[]>>({ state: "loading" })

  // Sheet could not be shown (403 / outage) rather than "blank draft"
  const [sheetDenied, setSheetDenied] = useState<Loadable<null> | null>(null)

  // Company Configuration State
  const [companyConfig, setCompanyConfig] = useState<CompanyKPIConfig>(INITIAL_COMPANY_CONFIG)
  const [loadingConfig, setLoadingConfig] = useState(false)
  const [savingConfig, setSavingConfig] = useState(false)
  const [cascading, setCascading] = useState(false)
  const [cascadeMessage, setCascadeMessage] = useState<string | null>(null)

  // Latest company config available to async callbacks without re-triggering effects
  const companyConfigRef = useRef<CompanyKPIConfig>(companyConfig)
  companyConfigRef.current = companyConfig

  // Ground Truth Live Actuals State
  const [liveActuals, setLiveActuals] = useState<LiveActualsResponse | null>(null)
  const [syncingActuals, setSyncingActuals] = useState(false)
  const [syncMessage, setSyncMessage] = useState<string | null>(null)
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null)

  // Selected Employee for Individual Journey
  const [selectedEmpId, setSelectedEmpId] = useState<string>("")
  const selectedEmpIdRef = useRef<string>("")
  selectedEmpIdRef.current = selectedEmpId
  const [employeeSearch, setEmployeeSearch] = useState("")
  const [empSheet, setEmpSheet] = useState<EmployeeKPISheet | null>(null)
  const [loadingSheet, setLoadingSheet] = useState(false)
  const [savingSheet, setSavingSheet] = useState(false)
  const [sheetSaveMessage, setSheetSaveMessage] = useState<string | null>(null)
  const [sheetError, setSheetError] = useState<string | null>(null)
  const [sheetLoadWarning, setSheetLoadWarning] = useState<string | null>(null)
  const [sheetDirty, setSheetDirty] = useState(false)
  const editVersionRef = useRef(0)

  // Approval workflow state
  const [workflowBusy, setWorkflowBusy] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [rejectReasonText, setRejectReasonText] = useState("")

  // Selected KPI (expanded editor) + AI copilot state
  const [selectedKpiId, setSelectedKpiId] = useState<string | null>(null)
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiFeedback, setAiFeedback] = useState<string | null>(null)
  const [aiUndo, setAiUndo] = useState<{
    kpiId: string
    previous: Pick<IndividualKPIItem, "measurable" | "timeline" | "requirement" | "smart_criteria">
  } | null>(null)

  // Active roster
  const activeStaffList = useMemo(() => {
    return internalEmployees.length > 0 ? internalEmployees : employees
  }, [internalEmployees, employees])
  const staffRef = useRef<Employee[]>(activeStaffList)
  staffRef.current = activeStaffList

  // Ensure employees are fetched if passed prop was empty
  useEffect(() => {
    let cancelled = false
    async function fetchStaff() {
      if (employees && employees.length > 0) {
        setInternalEmployees(employees)
        return
      }
      setLoadingInternalEmps(true)
      try {
        const staff = await listEmployees()
        if (!cancelled && staff && staff.length > 0) {
          setInternalEmployees(staff)
        }
      } catch (err) {
        console.warn("Could not fetch employee directory for KPI sheet:", err)
      } finally {
        if (!cancelled) setLoadingInternalEmps(false)
      }
    }
    void fetchStaff()
    return () => { cancelled = true }
  }, [employees])

  // Who am I (cached once per page visit)
  useEffect(() => {
    let cancelled = false
    void getWhoami().then((w) => {
      if (!cancelled) setRoles(w?.roles ?? [])
    })
    return () => { cancelled = true }
  }, [])

  // Sync Live Actuals Ground Truth from tables. Reads config through a ref so its identity is stable.
  // `manual` (the Sync button) bypasses the 60s cache; the initial load shares the cached request.
  const handleSyncLiveActuals = useCallback(async (manual = false) => {
    setSyncingActuals(true)
    setSyncMessage(null)
    try {
      const res = await getKpisLiveActuals({ fresh: manual })
      setLiveActuals(res)
      setLastSyncedAt(new Date().toLocaleTimeString())

      const isLive = (m?: LiveActualsMetric) => !!m && m.source !== "unavailable"
      const salesLive = isLive(res.sources?.sales)
      const costLive = isLive(res.sources?.cost)
      const profitLive = isLive(res.sources?.profit)

      // Prefer the backend-computed attainment index: refetch the config it recomputed
      let fresh: CompanyKPIConfig | null = null
      try {
        fresh = await getCompanyKPIConfig({ fresh: manual })
      } catch {
        fresh = null
      }

      if (fresh) setConfigLoad({ state: "ready", data: null })
      const cur = companyConfigRef.current
      const salesVal = salesLive ? Number(res.sources.sales.current_value) || 0 : cur.sales_actual_zar
      const costVal = costLive ? Number(res.sources.cost.current_value) || 0 : cur.cost_actual_zar
      const profitVal = profitLive ? Number(res.sources.profit.current_value) || 0 : cur.profit_actual_zar

      // Per-gauge ratios are plain actual/budget arithmetic on real figures (fallback only; the server's win).
      // The company INDEX is never computed here: it comes from the server or is "Set company targets".
      const salesAch = Number(cur.sales_budget_zar) > 0 ? (salesVal / Number(cur.sales_budget_zar)) * 100 : 0
      const costEff = Number(costVal) > 0 && Number(cur.cost_budget_zar) > 0 ? (Number(cur.cost_budget_zar) / costVal) * 100 : 0
      const profitAch = Number(cur.profit_budget_zar) > 0 ? (profitVal / Number(cur.profit_budget_zar)) * 100 : 0
      const round2 = (n: number) => Math.round(n * 100) / 100

      setCompanyConfig((prev) => ({
        ...prev,
        ...(fresh
          ? {
              company_missing: fresh.company_missing,
              corporate_attainment_index: fresh.corporate_attainment_index ?? null,
              company_shared_score_pct: fresh.company_shared_score_pct ?? null,
            }
          : {}),
        sales_actual_zar: salesVal,
        sales_achievement_pct: fresh?.sales_achievement_pct ?? round2(salesAch),
        cost_actual_zar: costVal,
        cost_efficiency_pct: fresh?.cost_efficiency_pct ?? round2(costEff),
        profit_actual_zar: profitVal,
        profit_achievement_pct: fresh?.profit_achievement_pct ?? round2(profitAch),
      }))

      const missing = [
        !salesLive ? "Sales" : null,
        !costLive ? "Cost" : null,
        !profitLive ? "Profit" : null,
      ].filter(Boolean) as string[]
      setSyncMessage(
        missing.length === 0
          ? `Live actuals synced: Sales ${fmtZAR(salesVal)} • Cost ${fmtZAR(costVal)} • Profit ${fmtZAR(profitVal)}`
          : `Live actuals synced. Not connected: ${missing.join(", ")}.`
      )
    } catch (err) {
      console.warn("Syncing live actuals failed:", err)
      setSyncMessage("Live actuals could not be reached. Sources shown as not connected.")
    } finally {
      setSyncingActuals(false)
    }
  }, [])

  // Initial load (once): Company Config, then a live-actuals sync
  useEffect(() => {
    let cancelled = false
    async function loadData() {
      setLoadingConfig(true)
      try {
        const cfg = await getCompanyKPIConfig()
        if (!cancelled && cfg) {
          setCompanyConfig(cfg)
          companyConfigRef.current = cfg
          setConfigLoad({ state: "ready", data: null })
        }
      } catch (err) {
        console.warn("Company KPI config not available:", err)
        if (!cancelled) setConfigLoad(loadableFromError(err))
      } finally {
        if (!cancelled) setLoadingConfig(false)
      }
      if (!cancelled) await handleSyncLiveActuals(false)
    }
    void loadData()
    return () => { cancelled = true }
  }, [handleSyncLiveActuals])

  // Set default selected employee when employees list loads
  useEffect(() => {
    const list = activeStaffList
    if (list && list.length > 0 && !selectedEmpId) {
      const exec = list.find((e) =>
        e.job_title?.toLowerCase().includes("ceo") ||
        e.job_title?.toLowerCase().includes("director")
      ) || list[0]
      setSelectedEmpId(exec.id)
    }
  }, [activeStaffList, selectedEmpId])

  // One bulk request for every employee's score (falls back to per-employee sheets, 4 at a time)
  const staffIdsKey = activeStaffList.map((e) => e.id).join(",")
  useEffect(() => {
    if (!staffIdsKey) return
    let cancelled = false
    void getPerformanceSummary(staffIdsKey.split(","))
      .then((rows) => {
        if (!cancelled) setPerfSummary(rows ? { state: "ready", data: rows } : { state: "unreachable", status: null })
      })
      .catch((err) => {
        if (!cancelled) setPerfSummary(loadableFromError(err))
      })
    return () => { cancelled = true }
  }, [staffIdsKey])
  const scoreByEmployee = useMemo(() => {
    const m = new Map<string, PerformanceSummaryRow>()
    if (perfSummary.state === "ready") for (const r of perfSummary.data) m.set(r.employee_id, r)
    return m
  }, [perfSummary])

  // Load selected employee's KPI sheet. Depends on the selected employee ONLY so that
  // config / roster refreshes never wipe unsaved edits.
  useEffect(() => {
    if (!selectedEmpId) return
    let cancelled = false
    // Clear the previous employee's sheet immediately
    setEmpSheet(null)
    setSheetDirty(false)
    setSelectedKpiId(null)
    setAiUndo(null)
    setAiFeedback(null)
    setSheetError(null)
    setSheetLoadWarning(null)
    setSheetSaveMessage(null)
    setSheetDenied(null)
    editVersionRef.current += 1
    async function loadSheet() {
      setLoadingSheet(true)
      try {
        const sheet = await getEmployeeKPISheet(selectedEmpId)
        if (!cancelled && sheet) {
          // A template is not persisted: no invented KPIs and no score until Save Draft creates it.
          const base = sheet.is_template ? { ...sheet, kpis: [], overall_score: null, composite: null } : sheet
          setEmpSheet(normalizeSheet(base))
        }
      } catch (err) {
        console.warn("Could not load KPI sheet:", err)
        const st = hrErrorStatus(err)
        if (!cancelled && (st === 401 || st === 403)) {
          setSheetDenied(loadableFromError(err))
        } else if (!cancelled) {
          const cfg = companyConfigRef.current
          const currentEmp = staffRef.current.find((e) => e.id === selectedEmpId)
          const jobLower = (currentEmp?.job_title || "").toLowerCase()
          let posLevel: "EXECUTIVE" | "DIRECTOR" | "MANAGER" | "STAFF" = "STAFF"
          if (jobLower.includes("ceo") || jobLower.includes("chief") || jobLower.includes("executive")) posLevel = "EXECUTIVE"
          else if (jobLower.includes("director") || jobLower.includes("vp")) posLevel = "DIRECTOR"
          else if (jobLower.includes("manager") || jobLower.includes("lead")) posLevel = "MANAGER"

          const sharedWeight = cfg.level_weights[posLevel] || 20
          const valuesWeight = cfg.values_weight_pct || 10
          const indivTarget = Math.max(0, 100 - (sharedWeight + valuesWeight))

          setSheetLoadWarning("Could not load the saved KPI sheet from the HR service. Showing a blank draft; saving will create it.")
          setEmpSheet({
            id: `sheet-${selectedEmpId}`,
            employee_id: selectedEmpId,
            employee_name: currentEmp?.full_name || "Employee",
            job_title: currentEmp?.job_title || "Specialist",
            department: currentEmp?.department || "Operations",
            fiscal_year: cfg.fiscal_year,
            position_level: posLevel,
            company_shared_weight_pct: sharedWeight,
            values_weight_pct: valuesWeight,
            individual_target_weight_pct: indivTarget,
            total_weight_pct: sharedWeight + valuesWeight,
            status: "DRAFT",
            kpis: [],
            overall_score: null,
            is_template: true,
          })
        }
      } finally {
        if (!cancelled) setLoadingSheet(false)
      }
    }
    void loadSheet()
    return () => { cancelled = true }
  }, [selectedEmpId])

  // Warn on tab close / reload with unsaved edits
  useEffect(() => {
    if (!sheetDirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [sheetDirty])

  // Employee switching with unsaved-edit guard
  const requestSelectEmployee = (id: string) => {
    if (id === selectedEmpId) return
    if (sheetDirty && !window.confirm("You have unsaved KPI edits for this employee. Switch and discard them?")) return
    setSelectedEmpId(id)
  }

  // Filtered employee list
  const filteredEmployees = useMemo(() => {
    if (!employeeSearch.trim()) return activeStaffList
    const q = employeeSearch.toLowerCase()
    return activeStaffList.filter(
      (e) =>
        e.full_name?.toLowerCase().includes(q) ||
        e.job_title?.toLowerCase().includes(q) ||
        e.department?.toLowerCase().includes(q)
    )
  }, [activeStaffList, employeeSearch])

  // Current selected employee object
  const currentEmployee = useMemo(() => {
    return activeStaffList.find((e) => e.id === selectedEmpId)
  }, [activeStaffList, selectedEmpId])

  // Weight calculations for employee sheet
  const individualWeightsSum = useMemo(() => {
    if (!empSheet?.kpis) return 0
    return Math.round(empSheet.kpis.reduce((acc, k) => acc + (Number(k.weight_pct) || 0), 0) * 10) / 10
  }, [empSheet?.kpis])

  const calculatedTotalWeight = useMemo(() => {
    if (!empSheet) return 0
    const shared = Number(empSheet.company_shared_weight_pct) || 0
    const vals = Number(empSheet.values_weight_pct) || 0
    return Math.round((shared + vals + individualWeightsSum) * 10) / 10
  }, [empSheet, individualWeightsSum])

  const isWeightBalanced = Math.abs(calculatedTotalWeight - 100.0) < 0.1

  // Individual weight budget: what is left after shared + values pillars
  const individualBudget = empSheet
    ? Math.max(0, 100 - (Number(empSheet.company_shared_weight_pct) || 0) - (Number(empSheet.values_weight_pct) || 0))
    : 0
  const remainingIndividualBudget = Math.round((individualBudget - individualWeightsSum) * 10) / 10

  const untitledKpiCount = empSheet ? empSheet.kpis.filter((k) => !k.title?.trim()).length : 0
  const canSubmit = isWeightBalanced && untitledKpiCount === 0 && (empSheet?.kpis.length ?? 0) > 0

  // Live actuals availability per source (drives "Not connected" states)
  const isSourceUnavailable = (key: "sales" | "cost" | "profit", mode?: string) =>
    (mode || "LIVE_TABLE") === "LIVE_TABLE" && liveActuals?.sources?.[key]?.source === "unavailable"
  const salesUnavailable = Number(companyConfig.sales_budget_zar) <= 0 || isSourceUnavailable("sales", companyConfig.sales_source_mode)
  const costUnavailable = Number(companyConfig.cost_budget_zar) <= 0 || isSourceUnavailable("cost", companyConfig.cost_source_mode)
  const profitUnavailable = Number(companyConfig.profit_budget_zar) <= 0 || isSourceUnavailable("profit", companyConfig.profit_source_mode)

  // Company attainment index: only the server's value. Null / company_missing / a 0 budget => "Set company targets".
  const indexTile = companyIndexTile(companyConfig)
  const companyIndex: number | null = indexTile.kind === "value" && !(salesUnavailable || costUnavailable || profitUnavailable) ? indexTile.value : null

  // Save Company Config
  const handleSaveCompanyConfig = async () => {
    if (!isHrAdmin) {
      setCascadeMessage(`${ADMIN_ONLY_TIP}: your role cannot change company targets.`)
      return
    }
    setSavingConfig(true)
    setCascadeMessage(null)
    try {
      const updated = await updateCompanyKPIConfig(companyConfig)
      setCompanyConfig(updated)
      setCascadeMessage("Company Budget & Shared KPI weights saved successfully!")
    } catch (err) {
      setCascadeMessage(`Could not save company configuration: ${describeApiError(err)}`)
    } finally {
      setSavingConfig(false)
    }
  }

  // Cascade to All Employees
  const handleCascadeToAll = async () => {
    if (!isHrAdmin) {
      setCascadeMessage(`${ADMIN_ONLY_TIP}: your role cannot cascade company KPIs.`)
      return
    }
    setCascading(true)
    setCascadeMessage(null)
    try {
      const res = await cascadeSharedKPIs(companyConfig.fiscal_year)
      setCascadeMessage(`Successfully cascaded Shared KPIs to ${res.employees_cascaded ?? 0} employees across all departments!`)
      if (onRefresh) await onRefresh()
    } catch (err) {
      setCascadeMessage(`Cascade failed: ${describeApiError(err)}`)
    } finally {
      setCascading(false)
    }
  }

  // ── Sheet mutation helpers (every edit marks the sheet dirty) ──────
  const mutateSheet = useCallback((fn: (s: EmployeeKPISheet) => EmployeeKPISheet) => {
    editVersionRef.current += 1
    // APPROVED sheets are locked; edits are ignored until an admin reopens the sheet
    setEmpSheet((prev) => (prev && prev.status !== "APPROVED" ? fn(prev) : prev))
    setSheetDirty(true)
    setSheetSaveMessage(null)
    setSheetError(null)
  }, [])

  const updateKpi = (id: string, patch: Partial<IndividualKPIItem>) =>
    mutateSheet((s) => ({ ...s, kpis: s.kpis.map((k) => (k.id === id ? { ...k, ...patch } : k)) }))

  const updateLevelField = (id: string, key: LevelKey, field: keyof SmartLevelCriterion, value: string) =>
    mutateSheet((s) => ({
      ...s,
      kpis: s.kpis.map((k) => {
        if (k.id !== id) return k
        const base = k.smart_criteria ?? makeBlankCriteria()
        return { ...k, smart_criteria: { ...base, [key]: { ...base[key], [field]: value } } }
      }),
    }))

  const handleAddKpi = (seed?: Partial<IndividualKPIItem>) => {
    if (!empSheet) return
    const blank = makeBlankKpi()
    const kpi: IndividualKPIItem = {
      ...blank,
      weight_pct: Math.max(0, remainingIndividualBudget),
      ...seed,
      id: blank.id,
    }
    mutateSheet((s) => ({ ...s, kpis: [...s.kpis, kpi] }))
    setSelectedKpiId(kpi.id)
  }

  const handleAddPreset = (preset: (typeof PRESET_KPIS)[number]) => {
    handleAddKpi({
      title: preset.title,
      category: preset.category,
      weight_pct: preset.suggestedWeight,
      measurable: preset.measurable,
      timeline: preset.timeline,
      requirement: preset.requirement,
      source_mode: preset.sourceMode,
      source_metric_id: preset.sourceMetricId,
      smart_criteria: {
        level_1: { timeline: "Month 1-3", measurable: "Over budget spend or <80% fulfillment", requirement: "Non-conformance report" },
        level_2: { timeline: "Mid-Year", measurable: "Within 2% of budget or 80-94% fulfillment", requirement: "Remediation plan" },
        level_3: { timeline: preset.timeline, measurable: preset.measurable, requirement: preset.requirement },
        level_4: { timeline: "Q3-Q4", measurable: "5-10% cost reduction / 115% quota achievement", requirement: "Manager sign-off" },
        level_5: { timeline: "Annual Fiscal", measurable: ">15% structural saving or breakthrough innovation", requirement: "Executive award" },
      },
    })
  }

  const handleDeleteKpi = (id: string) => {
    if (!empSheet) return
    const kpi = empSheet.kpis.find((k) => k.id === id)
    if (!kpi) return
    if (!window.confirm(`Delete KPI "${kpi.title || "Untitled KPI"}"? This cannot be undone once saved.`)) return
    mutateSheet((s) => ({ ...s, kpis: s.kpis.filter((k) => k.id !== id) }))
    if (selectedKpiId === id) setSelectedKpiId(null)
    if (aiUndo?.kpiId === id) setAiUndo(null)
  }

  const handleDuplicateKpi = (id: string) => {
    if (!empSheet) return
    const idx = empSheet.kpis.findIndex((k) => k.id === id)
    if (idx < 0) return
    const src = empSheet.kpis[idx]
    const copy: IndividualKPIItem = {
      ...src,
      id: makeKpiId(),
      title: src.title ? `${src.title} (copy)` : "",
      smart_criteria: normalizeCriteria(src.smart_criteria),
    }
    mutateSheet((s) => {
      const list = [...s.kpis]
      list.splice(idx + 1, 0, copy)
      return { ...s, kpis: list }
    })
    setSelectedKpiId(copy.id)
  }

  const handleMoveKpi = (id: string, dir: -1 | 1) => {
    mutateSheet((s) => {
      const idx = s.kpis.findIndex((k) => k.id === id)
      const target = idx + dir
      if (idx < 0 || target < 0 || target >= s.kpis.length) return s
      const list = [...s.kpis]
      ;[list[idx], list[target]] = [list[target], list[idx]]
      return { ...s, kpis: list }
    })
  }

  // Auto-Balance Individual Weights to ensure exactly 100%
  const handleAutoBalanceIndividual = () => {
    if (!empSheet || !empSheet.kpis || empSheet.kpis.length === 0) return
    const shared = Number(empSheet.company_shared_weight_pct) || 0
    const vals = Number(empSheet.values_weight_pct) || 10
    const targetIndiv = Math.max(0, 100 - (shared + vals))
    const n = empSheet.kpis.length
    const currentTotal = empSheet.kpis.reduce((acc, k) => acc + (Number(k.weight_pct) || 0), 0)

    mutateSheet((s) => {
      let updated: IndividualKPIItem[]
      if (currentTotal <= 0) {
        const evenWeight = Math.round((targetIndiv / n) * 10) / 10
        updated = s.kpis.map((k, idx) => ({
          ...k,
          weight_pct: idx === n - 1 ? Math.round((targetIndiv - evenWeight * (n - 1)) * 10) / 10 : evenWeight,
        }))
      } else {
        const factor = targetIndiv / currentTotal
        let allocated = 0
        updated = s.kpis.map((k, idx) => {
          if (idx === n - 1) {
            const w = Math.round((targetIndiv - allocated) * 10) / 10
            return { ...k, weight_pct: Math.max(0, w) }
          }
          const w = Math.round(Number(k.weight_pct) * factor * 10) / 10
          allocated += w
          return { ...k, weight_pct: w }
        })
      }
      return { ...s, kpis: updated, individual_target_weight_pct: targetIndiv, total_weight_pct: 100 }
    })
  }

  // Update position level for selected employee (shared/values weights follow the level cascade)
  const handleEmployeeLevelChange = (newLevel: "EXECUTIVE" | "DIRECTOR" | "MANAGER" | "STAFF") => {
    if (!empSheet || empSheet.position_level === newLevel) return
    const newShared = companyConfig.level_weights[newLevel] || 20
    mutateSheet((s) => {
      const vals = s.values_weight_pct || 10
      return {
        ...s,
        position_level: newLevel,
        company_shared_weight_pct: newShared,
        individual_target_weight_pct: Math.max(0, 100 - (newShared + vals)),
      }
    })
  }

  // Save Employee KPI Sheet
  const handleSaveEmpSheet = async (status: string = "DRAFT") => {
    if (!empSheet || !selectedEmpId) return
    if (status !== "DRAFT" && !canSubmit) {
      setSheetError(
        untitledKpiCount > 0
          ? "Every KPI needs a title before the sheet can be submitted."
          : "Weights must total exactly 100% (and at least one KPI is required) before submitting."
      )
      return
    }
    const empIdAtSave = selectedEmpId
    const versionAtSave = editVersionRef.current
    setSavingSheet(true)
    setSheetSaveMessage(null)
    setSheetError(null)
    try {
      const payload: Partial<EmployeeKPISheet> = {
        fiscal_year: empSheet.fiscal_year,
        position_level: empSheet.position_level,
        company_shared_weight_pct: empSheet.company_shared_weight_pct,
        values_weight_pct: empSheet.values_weight_pct,
        individual_target_weight_pct: individualWeightsSum,
        total_weight_pct: calculatedTotalWeight,
        status: status,
        kpis: empSheet.kpis,
        values_ratings: empSheet.values_ratings || {},
      }
      const res = await updateEmployeeKPISheet(empIdAtSave, payload)
      if (selectedEmpIdRef.current !== empIdAtSave) return
      setEmpSheet((prev) =>
        prev
          ? {
              ...prev,
              status: res?.status || status,
              total_weight_pct: res?.total_weight_pct ?? calculatedTotalWeight,
              overall_score: res?.overall_score ?? prev.overall_score,
              is_template: false,
            }
          : prev
      )
      // Only clear dirty if nothing was edited while the request was in flight
      if (editVersionRef.current === versionAtSave) {
        setSheetDirty(false)
        // Pull the server's composite / score_basis so the headline is the server's number
        void getEmployeeKPISheet(empIdAtSave, { fresh: true })
          .then((fresh) => {
            if (selectedEmpIdRef.current !== empIdAtSave || editVersionRef.current !== versionAtSave) return
            setEmpSheet((prev) =>
              prev
                ? {
                    ...prev,
                    composite: fresh.composite ?? null,
                    overall_score: fresh.overall_score ?? prev.overall_score,
                    score_basis: fresh.score_basis ?? prev.score_basis,
                    permissions: fresh.permissions ?? prev.permissions,
                    is_template: false,
                  }
                : prev,
            )
          })
          .catch(() => undefined)
      }
      setSheetSaveMessage(
        `KPI Sheet for ${empSheet.employee_name || "Employee"} saved as ${res?.status || status}. Total Weight: ${calculatedTotalWeight}%`
      )
    } catch (err) {
      if (selectedEmpIdRef.current === empIdAtSave) {
        setSheetError(`Save failed: ${describeApiError(err)}`)
      }
    } finally {
      setSavingSheet(false)
    }
  }

  // Approval workflow actions (server enforces roles; UI only shows them when permitted)
  const runWorkflow = async (action: "approve" | "reject" | "reopen") => {
    if (!empSheet || !selectedEmpId) return
    const empIdAtStart = selectedEmpId
    setWorkflowBusy(true)
    setSheetError(null)
    setSheetSaveMessage(null)
    try {
      if (action === "approve") await approveEmployeeKPISheet(empIdAtStart, empSheet.fiscal_year)
      else if (action === "reject") await rejectEmployeeKPISheet(empIdAtStart, rejectReasonText.trim(), empSheet.fiscal_year)
      else await reopenEmployeeKPISheet(empIdAtStart, empSheet.fiscal_year)
      const fresh = await getEmployeeKPISheet(empIdAtStart)
      if (selectedEmpIdRef.current !== empIdAtStart) return
      setEmpSheet(normalizeSheet(fresh))
      setSheetDirty(false)
      setRejectOpen(false)
      setRejectReasonText("")
      setSheetSaveMessage(
        action === "approve" ? "KPI sheet approved and locked." : action === "reject" ? "Changes requested; sheet returned to draft." : "KPI sheet reopened for editing."
      )
    } catch (err) {
      if (selectedEmpIdRef.current === empIdAtStart) setSheetError(`Action failed: ${describeApiError(err)}`)
    } finally {
      setWorkflowBusy(false)
    }
  }

  // Trigger AI SMART Criteria Generation for the currently selected KPI (undoable)
  const handleGenerateAISmart = async () => {
    const kpi = empSheet?.kpis.find((k) => k.id === selectedKpiId)
    if (!kpi) {
      setAiFeedback("Select a KPI first.")
      return
    }
    if (!kpi.title?.trim()) {
      setAiFeedback("Give the KPI a title first so the AI knows what to draft.")
      return
    }
    const empIdAtStart = selectedEmpId
    const kpiId = kpi.id
    const previous = {
      measurable: kpi.measurable,
      timeline: kpi.timeline,
      requirement: kpi.requirement,
      smart_criteria: kpi.smart_criteria,
    }
    setAiGenerating(true)
    setAiFeedback(null)
    try {
      const res = await generateAISmartCriteria({
        title: kpi.title,
        category: kpi.category || "Cost Optimization",
        job_title: currentEmployee?.job_title,
        department: currentEmployee?.department,
      })
      if (selectedEmpIdRef.current !== empIdAtStart) return
      const criteria = normalizeCriteria(res.smart_criteria)
      mutateSheet((s) => ({
        ...s,
        kpis: s.kpis.map((k) =>
          k.id === kpiId
            ? {
                ...k,
                measurable: res.suggested_measurable || k.measurable,
                timeline: res.suggested_timeline || k.timeline,
                requirement: res.suggested_requirement || k.requirement,
                smart_criteria: criteria,
              }
            : k
        ),
      }))
      setAiUndo({ kpiId, previous })
      setAiFeedback(`AI filled SMART Levels 1-5 for "${kpi.title}". Review and edit them below, or undo.`)
    } catch (err) {
      setAiFeedback(`AI SMART generation failed: ${describeApiError(err)}. Nothing was changed.`)
    } finally {
      setAiGenerating(false)
    }
  }

  const handleUndoAI = () => {
    if (!aiUndo) return
    const { kpiId, previous } = aiUndo
    mutateSheet((s) => ({
      ...s,
      kpis: s.kpis.map((k) => (k.id === kpiId ? { ...k, ...previous } : k)),
    }))
    setAiUndo(null)
    setAiFeedback("AI changes undone.")
  }

  // Approvals: HR admins (whoami roles) or whoever the server says may approve this sheet. The server still enforces.
  const canApprove = isHrAdmin || empSheet?.permissions?.can_approve === true
  const canReopen = isHrAdmin || empSheet?.permissions?.can_reopen === true

  // Composite headline: the server's `composite.total` whenever the sheet has no unsaved edits;
  // the client formula is only a labelled ESTIMATE (while editing). A template sheet has no score.
  const compositeBreakdown = useMemo(() => {
    const none = {
      total: null as number | null,
      basis: "none" as "server" | "estimate" | "none",
      sharedPts: null as number | null,
      valuesPts: null as number | null,
      indivPts: 0,
      companyMissing: companyIndex === null,
      valuesRated: false,
      valuesScore: null as number | null,
    }
    if (!empSheet) return none
    const weights = {
      shared: Number(empSheet.company_shared_weight_pct) || 0,
      values: Number(empSheet.values_weight_pct) || 0,
      individual: individualWeightsSum,
    }
    const ratings = empSheet.values_ratings || {}
    const rated = VALUE_DEFS.every((v) => typeof ratings[v.key] === "number")
    const est = estimateComposite({
      companyIndex,
      valuesRatings: rated ? VALUE_DEFS.map((v) => ratings[v.key] as number) : null,
      kpis: empSheet.kpis,
      weights,
    })
    const head = pickHeadline({
      composite: empSheet.composite,
      sheetDirty,
      localEstimate: empSheet.kpis.length === 0 && empSheet.is_template ? null : est.total,
      isTemplate: empSheet.is_template,
    })
    if (head.basis === "server" && empSheet.composite) {
      const srv = pointsFromComposite(empSheet.composite, weights)
      if (srv) {
        return {
          total: head.value,
          basis: head.basis,
          sharedPts: srv.sharedPts,
          valuesPts: srv.valuesPts,
          indivPts: srv.indivPts,
          companyMissing: srv.companyMissing,
          valuesRated: srv.valuesRated,
          valuesScore: srv.valuesScore,
        }
      }
    }
    return {
      total: head.value,
      basis: head.basis,
      sharedPts: est.sharedPts,
      valuesPts: est.valuesPts,
      indivPts: est.indivPts,
      companyMissing: est.companyMissing,
      valuesRated: est.valuesRated,
      valuesScore: est.valuesScore,
    }
  }, [empSheet, companyIndex, sheetDirty, individualWeightsSum])

  // Analytics Chart Data: Budget vs Actuals
  const financialBudgetChartData = useMemo(() => {
    return [
      {
        metric: "Sales Revenue",
        Budget: companyConfig.sales_budget_zar / 1000,
        Actual: companyConfig.sales_actual_zar / 1000,
        unit: "k ZAR",
        achievement: companyConfig.sales_achievement_pct,
      },
      {
        metric: "Operating Cost",
        Budget: companyConfig.cost_budget_zar / 1000,
        Actual: companyConfig.cost_actual_zar / 1000,
        unit: "k ZAR",
        achievement: companyConfig.cost_efficiency_pct,
      },
      {
        metric: "Net Profit",
        Budget: companyConfig.profit_budget_zar / 1000,
        Actual: companyConfig.profit_actual_zar / 1000,
        unit: "k ZAR",
        achievement: companyConfig.profit_achievement_pct,
      },
    ]
  }, [companyConfig])

  return (
    <div className="space-y-6">
      {/* ── Top Header & Tab Controls ── */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between border-b border-border/60 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="p-2 rounded-xl bg-primary/10 text-primary">
              <Target className="h-6 w-6" />
            </span>
            <div>
              <h2 className="text-xl font-bold tracking-tight text-foreground flex items-center gap-2">
                Performance & Objective Management
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10">
                  {companyConfig.fiscal_year}
                </Badge>
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Whole-Company Shared Budget KPIs • Level-Based Cascading Weights • 5-Level SMART Criteria • Live Table Actuals
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Live Actuals Ground Truth Sync Button */}
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleSyncLiveActuals(true)}
            disabled={syncingActuals}
            className="text-xs h-8 border-primary/40 text-primary hover:bg-primary/10 flex items-center gap-1.5 shadow-sm"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncingActuals ? "animate-spin" : ""}`} />
            {syncingActuals ? "Pulling Ground Truth..." : "Sync Live Actuals from Tables"}
          </Button>

          {/* Tab Navigation */}
          <div className="flex rounded-lg border border-border bg-card p-1">
            <button
              onClick={() => setActiveTab("individual")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                activeTab === "individual"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Users className="h-3.5 w-3.5" />
              Individual Drafting Journey
            </button>
            <button
              onClick={() => setActiveTab("company")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                activeTab === "company"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Building2 className="h-3.5 w-3.5" />
              Company Shared Setup
            </button>
            <button
              onClick={() => setActiveTab("analytics")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
                activeTab === "analytics"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              Budget vs Actuals Scorecard
            </button>
          </div>
        </div>
      </div>

      {/* Sync Notification Banner */}
      {syncMessage && (
        <div className="p-2.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 text-xs text-emerald-400 flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            {syncMessage}
          </span>
          {lastSyncedAt && <span className="text-[10px] text-muted-foreground">Synced at {lastSyncedAt}</span>}
        </div>
      )}

      {configLoad.state !== "ready" && configLoad.state !== "loading" && (
        <NotConnected loadable={configLoad} service="Company KPI targets" onRetry={() => void handleSyncLiveActuals(true)} />
      )}

      {/* ── 4 Benchmark Speedometer Radial Dials (Visual Anchor) ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Dial 1: Sales vs Budget */}
        <CircularKPIGauge
          title="Sales vs Budget"
          sublabel="of Quota Target"
          valuePct={companyConfig.sales_achievement_pct ?? 0}
          unavailable={salesUnavailable}
          actualFormatted={fmtZAR(companyConfig.sales_actual_zar)}
          budgetFormatted={fmtZAR(companyConfig.sales_budget_zar)}
          colorTheme="emerald"
          sourceMode={companyConfig.sales_source_mode || "LIVE_TABLE"}
          sourceLabel="sales_leads (Won Deals) & commissions"
        />

        {/* Dial 2: Cost Ceiling vs Actual */}
        <CircularKPIGauge
          title="Operating Cost Ceiling"
          sublabel="Cost Efficiency"
          valuePct={companyConfig.cost_efficiency_pct ?? 0}
          unavailable={costUnavailable}
          actualFormatted={fmtZAR(companyConfig.cost_actual_zar)}
          budgetFormatted={fmtZAR(companyConfig.cost_budget_zar)}
          colorTheme="blue"
          sourceMode={companyConfig.cost_source_mode || "LIVE_TABLE"}
          sourceLabel="hr.payslips (paid payroll YTD)"
          actualLabel="Paid payroll YTD:"
          isCostEfficiency={true}
        />

        {/* Dial 3: Net Profit Target */}
        <CircularKPIGauge
          title="Net Profit Target"
          sublabel="EBITDA Margin"
          valuePct={companyConfig.profit_achievement_pct ?? 0}
          unavailable={profitUnavailable}
          actualFormatted={fmtZAR(companyConfig.profit_actual_zar)}
          budgetFormatted={fmtZAR(companyConfig.profit_budget_zar)}
          colorTheme="purple"
          sourceMode={companyConfig.profit_source_mode || "LIVE_TABLE"}
          sourceLabel="finance_general_ledger (Net Margin)"
        />

        {/* Dial 4: Shared Company Attainment Index */}
        <CircularKPIGauge
          title="Shared Company Index"
          sublabel="Cascaded Score"
          valuePct={companyIndex ?? 0}
          unavailable={companyIndex === null}
          unavailableLabel="Set company targets"
          actualFormatted={`Values: ${companyConfig.values_weight_pct}% Fixed`}
          budgetFormatted="Target: 100%"
          colorTheme="amber"
          sourceMode="LIVE_TABLE"
          sourceLabel="Ubuntu Empathy • Speed • Rest • POPIA"
        />
      </div>

      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {/* TAB 1: INDIVIDUAL EMPLOYEE KPI JOURNEY                                    */}
      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {activeTab === "individual" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Employee Selector & Directory */}
          <div className="lg:col-span-4 space-y-4">
            <Card className="border-border bg-card">
              <CardHeader className="p-4 pb-3">
                <CardTitle className="text-sm font-semibold flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-primary" />
                    Select Employee / Staff
                  </span>
                  <Badge variant="outline" className="text-[10px]">
                    {activeStaffList.length} Loaded
                  </Badge>
                  {perfSummary.state === "denied" && (
                    <Badge variant="outline" className="text-[10px] border-amber-500/40 text-amber-400">
                      Scores: Not permitted
                    </Badge>
                  )}
                </CardTitle>
                <div className="relative mt-2">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search staff, role, dept..."
                    value={employeeSearch}
                    onChange={(e) => setEmployeeSearch(e.target.value)}
                    className="pl-8 text-xs h-8 bg-background"
                  />
                </div>
              </CardHeader>
              <CardContent className="p-2 pt-0 max-h-[480px] overflow-y-auto space-y-1">
                {loadingInternalEmps ? (
                  <div className="p-6 text-center text-xs text-muted-foreground flex items-center justify-center gap-2">
                    <RefreshCw className="h-3.5 w-3.5 animate-spin text-primary" /> Loading staff directory...
                  </div>
                ) : filteredEmployees.length === 0 ? (
                  <div className="p-4 text-center text-xs text-muted-foreground">
                    No employees found matching filter.
                  </div>
                ) : (
                  filteredEmployees.map((emp) => {
                    const isSelected = emp.id === selectedEmpId
                    const jobLower = (emp.job_title || "").toLowerCase()
                    const isExec = jobLower.includes("ceo") || jobLower.includes("chief") || jobLower.includes("director")
                    return (
                      <button
                        key={emp.id}
                        onClick={() => requestSelectEmployee(emp.id)}
                        className={`w-full text-left p-2.5 rounded-lg border transition-all flex items-center justify-between ${
                          isSelected
                            ? "border-primary bg-primary/10 text-foreground font-medium shadow-sm"
                            : "border-transparent hover:border-border hover:bg-muted/50 text-muted-foreground"
                        }`}
                      >
                        <div className="min-w-0 pr-2">
                          <div className="flex items-center gap-1.5">
                            <p className="text-xs font-semibold truncate text-foreground">
                              {emp.full_name}
                            </p>
                            {isExec && (
                              <span className="h-1.5 w-1.5 rounded-full bg-amber-400" title="Leadership / Exec" />
                            )}
                          </div>
                          <p className="text-[11px] text-muted-foreground truncate">
                            {emp.job_title}
                          </p>
                          <p className="text-[10px] text-muted-foreground/80 truncate">
                            {emp.department}
                          </p>
                          {scoreByEmployee.get(emp.id)?.overall_score != null && (
                            <p className="text-[10px] text-primary font-mono">
                              Score {Number(scoreByEmployee.get(emp.id)?.overall_score).toFixed(1)}%
                              {scoreByEmployee.get(emp.id)?.status ? ` · ${scoreByEmployee.get(emp.id)?.status}` : ""}
                            </p>
                          )}
                        </div>
                        <ChevronRight className={`h-4 w-4 shrink-0 transition-transform ${isSelected ? "text-primary translate-x-0.5" : "text-muted-foreground/40"}`} />
                      </button>
                    )
                  })
                )}
              </CardContent>
            </Card>

            {/* Quick Presets for KPI drafting */}
            <Card className="border-border bg-card">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-xs font-semibold flex items-center gap-2 text-foreground">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  ISP KPI Templates (1-Click Load)
                </CardTitle>
                <CardDescription className="text-[11px]">
                  Add verified telecom objectives to this sheet:
                </CardDescription>
              </CardHeader>
              <CardContent className="p-3 pt-0 space-y-2">
                {PRESET_KPIS.map((preset, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleAddPreset(preset)}
                    disabled={!empSheet}
                    className="w-full text-left p-2.5 rounded-md border border-border/60 hover:border-primary/50 hover:bg-primary/5 transition-all text-[11px]"
                  >
                    <p className="font-medium text-foreground truncate">{preset.title}</p>
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground mt-1">
                      <span>{preset.category}</span>
                      <span className="text-primary font-semibold">+{preset.suggestedWeight}% Wt</span>
                    </div>
                  </button>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Employee KPI Sheet & SMART Drafting Studio */}
          <div className="lg:col-span-8 space-y-6">
            {loadingSheet ? (
              <div className="p-12 text-center text-sm text-muted-foreground rounded-xl border border-border bg-card">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-primary" />
                Loading employee KPI sheet...
              </div>
            ) : empSheet ? (
              <>
                {sheetLoadWarning && (
                  <div className="p-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 text-xs text-amber-400 flex items-center gap-1.5">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    {sheetLoadWarning}
                  </div>
                )}
                {/* Approval workflow banner (outside the lockable fieldset so actions stay usable) */}
                {(empSheet.status === "SUBMITTED" || empSheet.status === "APPROVED" || !!empSheet.reject_reason) && (
                  <div className="p-3 rounded-lg border border-border bg-card text-xs space-y-2" data-testid="kpi-approval-banner">
                    {empSheet.status === "DRAFT" && empSheet.reject_reason && (
                      <div className="p-2 rounded border border-red-500/40 bg-red-500/10 text-red-400">
                        <b>Changes requested:</b> {empSheet.reject_reason}
                      </div>
                    )}
                    {empSheet.status === "SUBMITTED" && (
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-muted-foreground flex items-center gap-1.5">
                            <Clock className="h-3.5 w-3.5 text-amber-400" />
                            Submitted and awaiting approval.
                            {!canApprove && " HR admin only: only a manager or HR user (other than the sheet owner) can approve."}
                          </span>
                          {(
                            <div className="flex items-center gap-2">
                              <Button
                                size="sm"
                                onClick={() => void runWorkflow("approve")}
                                disabled={workflowBusy || !canApprove}
                                title={!canApprove ? ADMIN_ONLY_TIP : undefined}
                                className="text-xs h-8 bg-emerald-600 text-white font-semibold hover:bg-emerald-600/90"
                              >
                                <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                                Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setRejectOpen((o) => !o)}
                                disabled={workflowBusy || !canApprove}
                                title={!canApprove ? ADMIN_ONLY_TIP : undefined}
                                className="text-xs h-8"
                              >
                                Request changes
                              </Button>
                            </div>
                          )}
                        </div>
                        {rejectOpen && canApprove && (
                          <div className="space-y-2">
                            <Textarea
                              value={rejectReasonText}
                              onChange={(e) => setRejectReasonText(e.target.value)}
                              placeholder="Explain what needs to change (required)"
                              className="text-xs min-h-[70px]"
                            />
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void runWorkflow("reject")}
                              disabled={workflowBusy || !rejectReasonText.trim()}
                              className="text-xs h-8 border-red-500/50 text-red-400"
                            >
                              Send back to draft
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                    {empSheet.status === "APPROVED" && (
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-emerald-400 flex items-center gap-1.5">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Approved and locked
                          {empSheet.approved_at ? ` on ${new Date(empSheet.approved_at).toLocaleDateString("en-ZA")}` : ""}. Editing is disabled.
                        </span>
                        {(
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void runWorkflow("reopen")}
                            disabled={workflowBusy || !canReopen}
                            title={!canReopen ? ADMIN_ONLY_TIP : undefined}
                            className="text-xs h-8"
                          >
                            Reopen
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                )}
                <fieldset disabled={empSheet.status === "APPROVED"} className="contents border-0 p-0 m-0 min-w-0">
                {/* Employee Profile Header & 100% Weight Verification Banner */}
                <Card className="border-border bg-card shadow-sm">
                  <CardContent className="p-5">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-lg font-bold text-foreground">
                            {empSheet.employee_name || currentEmployee?.full_name || "Employee"}
                          </h3>
                          <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10">
                            {empSheet.status}
                          </Badge>
                          {empSheet.is_template && (
                            <Badge variant="outline" className="border-amber-500/40 text-amber-400 bg-amber-500/10 text-[10px]">
                              Not saved yet
                            </Badge>
                          )}
                          {sheetDirty && (
                            <Badge variant="outline" className="border-amber-500/40 text-amber-400 bg-amber-500/10 text-[10px]">
                              Unsaved changes
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {empSheet.job_title} • {empSheet.department}
                        </p>
                      </div>

                      {/* Position Level Selector (Adjusts Level) */}
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-muted-foreground">Position Level:</span>
                        <div className="flex rounded-md border border-border bg-background p-0.5 text-xs">
                          {(["EXECUTIVE", "DIRECTOR", "MANAGER", "STAFF"] as const).map((lvl) => (
                            <button
                              key={lvl}
                              onClick={() => handleEmployeeLevelChange(lvl)}
                              className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all ${
                                empSheet.position_level === lvl
                                  ? "bg-primary text-primary-foreground shadow-sm"
                                  : "text-muted-foreground hover:text-foreground"
                              }`}
                            >
                              {`${lvl === "EXECUTIVE" ? "Exec" : lvl === "DIRECTOR" ? "Dir" : lvl === "MANAGER" ? "Mgr" : "Staff"} (${companyConfig.level_weights[lvl]}%)`}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Weight Breakdown & 100% Verification Bar */}
                    <div className="mt-5 p-4 rounded-xl border border-border bg-background/50 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-foreground">Total Sheet Weight:</span>
                          <span className={`font-mono text-sm font-bold ${isWeightBalanced ? "text-emerald-400" : "text-amber-400"}`}>
                            {calculatedTotalWeight}% / 100%
                          </span>
                          {isWeightBalanced ? (
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px] flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" /> Balanced 100%
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="border-amber-500/40 text-amber-400 bg-amber-500/10 text-[10px] flex items-center gap-1">
                              <AlertCircle className="h-3 w-3" />
                              {calculatedTotalWeight < 100 ? `${(100 - calculatedTotalWeight).toFixed(1)}% Remaining` : `${(calculatedTotalWeight - 100).toFixed(1)}% Over`}
                            </Badge>
                          )}
                        </div>

                        {!isWeightBalanced && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleAutoBalanceIndividual}
                            className="text-xs h-7 text-primary border-primary/40 hover:bg-primary/10 mt-2 sm:mt-0"
                          >
                            <SlidersHorizontal className="h-3 w-3 mr-1" />
                            Auto-Balance to 100%
                          </Button>
                        )}
                      </div>

                      {/* Stacked Progress Bar */}
                      <div className="h-3 w-full rounded-full bg-muted overflow-hidden flex">
                        {/* Company Shared Portion */}
                        <div
                          style={{ width: `${Math.min(100, empSheet.company_shared_weight_pct)}%` }}
                          className="bg-emerald-500 h-full transition-all"
                          title={`Shared Company KPIs: ${empSheet.company_shared_weight_pct}%`}
                        />
                        {/* Values Portion */}
                        <div
                          style={{ width: `${Math.min(100, empSheet.values_weight_pct)}%` }}
                          className="bg-purple-500 h-full transition-all"
                          title={`Company Strategic Values: ${empSheet.values_weight_pct}%`}
                        />
                        {/* Individual KPIs Portion */}
                        <div
                          style={{ width: `${Math.min(100, individualWeightsSum)}%` }}
                          className={`h-full transition-all ${isWeightBalanced ? "bg-primary" : calculatedTotalWeight > 100 ? "bg-red-500" : "bg-blue-400"}`}
                          title={`Individual KPIs: ${individualWeightsSum}%`}
                        />
                      </div>

                      {/* Legend */}
                      <div className="flex flex-wrap items-center gap-4 text-[11px] text-muted-foreground pt-1">
                        <span className="flex items-center gap-1.5">
                          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                          Shared Company (Sales, Cost, Profit): <b className="text-foreground">{empSheet.company_shared_weight_pct}%</b>
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="h-2.5 w-2.5 rounded-full bg-purple-500" />
                          Values & Culture: <b className="text-foreground">{empSheet.values_weight_pct}%</b>
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="h-2.5 w-2.5 rounded-full bg-primary" />
                          Individual KPIs: <b className="text-foreground">{individualWeightsSum}%</b>
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Section 1: Non-Negotiable Shared KPIs (Automatically Applied) */}
                <Card className="border-border bg-card">
                  <CardHeader className="p-4 pb-2">
                    <CardTitle className="text-sm font-semibold flex items-center justify-between">
                      <span className="flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4 text-emerald-400" />
                        Pillar 1 & 2: Non-Negotiable Shared Company KPIs
                      </span>
                      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                        Weight: {Number(empSheet.company_shared_weight_pct) + Number(empSheet.values_weight_pct)}%
                      </Badge>
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Standard corporate performance benchmarks calculated against the company budget.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="p-4 pt-2 space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {/* Shared Financials */}
                      <div className="p-3 rounded-lg border border-border/80 bg-background/60 space-y-1.5">
                        <div className="flex items-center justify-between text-xs font-semibold">
                          <span className="text-foreground">Corporate Sales, Cost & Profit Target</span>
                          <span className="text-emerald-400 font-bold">{empSheet.company_shared_weight_pct}% Weight</span>
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          Budget: {salesUnavailable ? "Not connected" : fmtZAR(companyConfig.sales_budget_zar)} Sales • {costUnavailable ? "Not connected" : fmtZAR(companyConfig.cost_budget_zar)} Cost Ceiling
                        </p>
                        <div className="flex items-center justify-between text-[11px] pt-1">
                          <span className="text-muted-foreground">Attainment Index:</span>
                          <span className="font-semibold text-foreground">{companyIndex === null ? "Not connected" : `${companyIndex}%`}</span>
                        </div>
                      </div>

                      {/* Shared Strategic Values */}
                      <div className="p-3 rounded-lg border border-border/80 bg-background/60 space-y-1.5">
                        <div className="flex items-center justify-between text-xs font-semibold">
                          <span className="text-foreground">Company Strategic Values & Code</span>
                          <span className="text-purple-400 font-bold">{empSheet.values_weight_pct}% Weight</span>
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          Ubuntu Empathy • Operational Speed • BCEA Rest • POPIA Governance
                        </p>
                        <div className="flex items-center justify-between text-[11px] pt-1">
                          <span className="text-muted-foreground">Compliance Rating:</span>
                          <span className="font-semibold text-muted-foreground">Assessed at review</span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Section 2: Individual KPIs (inline-editable drafting & SMART rubric studio) */}
                <Card className="border-border bg-card">
                  <CardHeader className="p-4 pb-2">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <CardTitle className="text-sm font-semibold flex items-center gap-2">
                          <Sliders className="h-4 w-4 text-primary" />
                          Pillar 3: Individual Role-Specific KPIs ({empSheet.kpis?.length || 0})
                        </CardTitle>
                        <CardDescription className="text-xs">
                          Click a KPI to edit its title, category, weight and the 5-level SMART rubric. Individual weight budget:{" "}
                          <b className="text-foreground">{individualBudget}%</b> • Allocated:{" "}
                          <b className="text-foreground">{individualWeightsSum}%</b> •{" "}
                          <b className={remainingIndividualBudget === 0 ? "text-emerald-400" : remainingIndividualBudget < 0 ? "text-red-400" : "text-amber-400"}>
                            {remainingIndividualBudget < 0
                              ? `${Math.abs(remainingIndividualBudget)}% over budget`
                              : `${remainingIndividualBudget}% remaining`}
                          </b>
                        </CardDescription>
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleAddKpi()}
                          className="text-xs h-8 bg-primary text-primary-foreground font-semibold"
                        >
                          <Plus className="h-3.5 w-3.5 mr-1" />
                          Add Individual KPI
                        </Button>
                      </div>
                    </div>
                  </CardHeader>

                  <CardContent className="p-4 pt-2 space-y-4">
                    {empSheet.kpis && empSheet.kpis.length > 0 ? (
                      <div className="space-y-4">
                        {empSheet.kpis.map((kpi, idx) => {
                          const isSelected = selectedKpiId === kpi.id
                          const criteria = kpi.smart_criteria ?? makeBlankCriteria()
                          const achieved = clampLevel(kpi.current_level ?? 3)
                          const isCustomCategory = !KPI_CATEGORIES.includes(kpi.category)
                          const contribution = Math.round(((kpiLevelScore(kpi) * (Number(kpi.weight_pct) || 0)) / 100) * 10) / 10
                          return (
                            <div
                              key={kpi.id}
                              className={`p-4 rounded-xl border bg-background/50 transition-all space-y-3 ${
                                isSelected ? "border-primary/60 ring-1 ring-primary/30" : "border-border/80 hover:border-border"
                              }`}
                            >
                              {/* Row 1: index, title, reorder / duplicate / delete */}
                              <div className="flex items-center gap-2">
                                <span className="h-6 w-6 shrink-0 rounded-full bg-primary/10 text-primary text-[11px] font-bold flex items-center justify-center">
                                  {idx + 1}
                                </span>
                                <Input
                                  placeholder="KPI title / objective name"
                                  value={kpi.title}
                                  onFocus={() => setSelectedKpiId(kpi.id)}
                                  onChange={(e) => updateKpi(kpi.id, { title: e.target.value })}
                                  className={`text-sm font-semibold h-8 bg-background ${!kpi.title.trim() ? "border-amber-500/60" : ""}`}
                                />
                                <div className="flex items-center gap-0.5 shrink-0">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    title="Move up"
                                    disabled={idx === 0}
                                    onClick={() => handleMoveKpi(kpi.id, -1)}
                                    className="h-7 w-7 p-0"
                                  >
                                    <ArrowUp className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    title="Move down"
                                    disabled={idx === empSheet.kpis.length - 1}
                                    onClick={() => handleMoveKpi(kpi.id, 1)}
                                    className="h-7 w-7 p-0"
                                  >
                                    <ArrowDown className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    title="Duplicate KPI"
                                    onClick={() => handleDuplicateKpi(kpi.id)}
                                    className="h-7 w-7 p-0"
                                  >
                                    <Copy className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    title="Delete KPI"
                                    onClick={() => handleDeleteKpi(kpi.id)}
                                    className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    title={isSelected ? "Collapse rubric" : "Edit rubric"}
                                    onClick={() => setSelectedKpiId(isSelected ? null : kpi.id)}
                                    className="h-7 w-7 p-0"
                                  >
                                    <ChevronDown className={`h-4 w-4 transition-transform ${isSelected ? "rotate-180 text-primary" : ""}`} />
                                  </Button>
                                </div>
                              </div>

                              {/* Row 2: category, weight, achieved level, contribution */}
                              <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
                                <div className="sm:col-span-4 space-y-1">
                                  <label className="text-[11px] font-medium text-muted-foreground">Category:</label>
                                  <select
                                    value={isCustomCategory ? "__custom__" : kpi.category}
                                    onChange={(e) =>
                                      updateKpi(kpi.id, { category: e.target.value === "__custom__" ? "Custom" : e.target.value })
                                    }
                                    className="w-full text-xs h-8 bg-background border border-border rounded-md px-2 text-foreground"
                                  >
                                    {KPI_CATEGORIES.map((c) => (
                                      <option key={c} value={c}>{c}</option>
                                    ))}
                                    <option value="__custom__">Custom</option>
                                  </select>
                                  {isCustomCategory && (
                                    <Input
                                      placeholder="Custom category name"
                                      value={kpi.category}
                                      onChange={(e) => updateKpi(kpi.id, { category: e.target.value })}
                                      className="text-xs h-7 bg-background mt-1"
                                    />
                                  )}
                                </div>
                                <div className="sm:col-span-2 space-y-1">
                                  <label className="text-[11px] font-medium text-muted-foreground">Weight (%):</label>
                                  <Input
                                    type="number"
                                    min="0"
                                    max="100"
                                    step="0.5"
                                    value={Number.isFinite(Number(kpi.weight_pct)) ? kpi.weight_pct : 0}
                                    onChange={(e) =>
                                      updateKpi(kpi.id, { weight_pct: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })
                                    }
                                    className="text-xs h-8 bg-background font-mono"
                                  />
                                </div>
                                <div className="sm:col-span-6 space-y-1">
                                  <div className="flex items-center justify-between">
                                    <label className="text-[11px] font-medium text-muted-foreground">Achieved level (manager assessment):</label>
                                    <span className="text-[10px] text-muted-foreground">
                                      Score: <b className="text-foreground">{Math.round(kpiLevelScore(kpi))}%</b> • Contributes{" "}
                                      <b className="text-primary">{contribution} pts</b>
                                    </span>
                                  </div>
                                  <div className="flex rounded-md border border-border bg-background p-0.5">
                                    {[1, 2, 3, 4, 5].map((lvl) => (
                                      <button
                                        key={lvl}
                                        type="button"
                                        onClick={() => updateKpi(kpi.id, { current_level: clampLevel(lvl), score: Math.round((clampLevel(lvl) / 3) * 100) })}
                                        className={`flex-1 py-1 rounded text-[11px] font-semibold transition-all ${
                                          achieved === lvl
                                            ? "bg-primary text-primary-foreground shadow-sm"
                                            : "text-muted-foreground hover:text-foreground"
                                        }`}
                                      >
                                        L{lvl}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              {/* Collapsed summary */}
                              {!isSelected && (
                                <p className="text-[11px] text-muted-foreground">
                                  <b className="text-foreground">Target metric:</b> {kpi.measurable || "Not set"} •{" "}
                                  <b className="text-foreground">Level {achieved}:</b> {criteria[`level_${achieved}` as LevelKey]?.measurable || "Not set"}
                                </p>
                              )}

                              {/* Expanded editor: metric summary + 5-level SMART rubric */}
                              {isSelected && (
                                <div className="pt-3 border-t border-border/50 space-y-4">
                                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
                                    <div className="sm:col-span-6 space-y-1">
                                      <label className="text-[11px] font-medium text-muted-foreground">Measurable Metric (target threshold):</label>
                                      <Input
                                        placeholder="e.g. Monthly cloud expenditure < R85k (12% reduction)"
                                        value={kpi.measurable}
                                        onChange={(e) => updateKpi(kpi.id, { measurable: e.target.value })}
                                        className="text-xs h-8 bg-background"
                                      />
                                    </div>
                                    <div className="sm:col-span-3 space-y-1">
                                      <label className="text-[11px] font-medium text-muted-foreground">Timeline / Cadence:</label>
                                      <Input
                                        placeholder="e.g. Monthly / End of Q3"
                                        value={kpi.timeline}
                                        onChange={(e) => updateKpi(kpi.id, { timeline: e.target.value })}
                                        className="text-xs h-8 bg-background"
                                      />
                                    </div>
                                    <div className="sm:col-span-3 space-y-1">
                                      <label className="text-[11px] font-medium text-muted-foreground">Audit Requirement:</label>
                                      <Input
                                        placeholder="e.g. Invoice & CFO sign-off"
                                        value={kpi.requirement}
                                        onChange={(e) => updateKpi(kpi.id, { requirement: e.target.value })}
                                        className="text-xs h-8 bg-background"
                                      />
                                    </div>
                                    <div className="sm:col-span-6 space-y-1">
                                      <label className="text-[11px] font-medium text-muted-foreground">Source of Actuals:</label>
                                      <select
                                        value={kpi.source_mode || "MANUAL"}
                                        onChange={(e) => updateKpi(kpi.id, { source_mode: e.target.value as IndividualKPIItem["source_mode"] })}
                                        className="w-full text-xs h-8 bg-background border border-border rounded-md px-2 text-foreground"
                                      >
                                        <option value="LIVE_TABLE">Live Database Table (Ground Truth)</option>
                                        <option value="PERCENTAGE">Direct Percentage (% Achieved)</option>
                                        <option value="MANUAL">Manual Override (Adjusted Value)</option>
                                      </select>
                                    </div>
                                    <div className="sm:col-span-6 space-y-1">
                                      <label className="text-[11px] font-medium text-muted-foreground">Linked Metric Table / Option:</label>
                                      <select
                                        value={kpi.source_metric_id || ""}
                                        onChange={(e) => updateKpi(kpi.id, { source_metric_id: e.target.value || undefined })}
                                        disabled={(kpi.source_mode || "MANUAL") !== "LIVE_TABLE"}
                                        className="w-full text-xs h-8 bg-background border border-border rounded-md px-2 text-foreground font-mono text-[11px] disabled:opacity-50"
                                      >
                                        <option value="">None</option>
                                        <option value="sales_leads_won">sales_leads (Won Deals Pipeline ZAR)</option>
                                        <option value="payroll_statutory">hr.payslips & Statutory Levies (ZAR)</option>
                                        <option value="net_ebitda">finance_general_ledger (Net Operating EBITDA)</option>
                                        <option value="support_fcr">support.tickets (First Contact Resolution %)</option>
                                        <option value="subscribers_churn">lifecycle.subscribers (Monthly Churn %)</option>
                                        <option value="network_mttr">network.telemetry (Fiber Core MTTR Hours)</option>
                                      </select>
                                    </div>
                                  </div>

                                  <div className="space-y-2">
                                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                      <span className="text-[11px] font-semibold text-foreground flex items-center gap-1.5">
                                        <Award className="h-3.5 w-3.5 text-primary" />
                                        5-Level SMART Achievement Rubric (timeline • measurable metric • verification):
                                      </span>
                                      <div className="flex items-center gap-2">
                                        {aiUndo?.kpiId === kpi.id && (
                                          <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={handleUndoAI}
                                            className="text-xs h-7"
                                          >
                                            <Undo2 className="h-3 w-3 mr-1" />
                                            Undo AI fill
                                          </Button>
                                        )}
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          onClick={() => void handleGenerateAISmart()}
                                          disabled={aiGenerating || !kpi.title.trim()}
                                          className="text-xs h-7 text-primary border-primary/40 hover:bg-primary/10"
                                        >
                                          <Bot className="h-3 w-3 mr-1" />
                                          {aiGenerating ? "Generating..." : "Generate SMART Levels with AI"}
                                        </Button>
                                      </div>
                                    </div>

                                    {aiFeedback && (
                                      <div className="p-2 rounded-lg border border-primary/40 bg-primary/10 text-xs text-foreground flex items-center gap-2">
                                        <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                                        <span>{aiFeedback}</span>
                                      </div>
                                    )}

                                    <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
                                      {LEVEL_KEYS.map((key, i) => {
                                        const lvl = i + 1
                                        const crit = criteria[key]
                                        return (
                                          <div
                                            key={key}
                                            className={`p-2.5 rounded-lg border space-y-1.5 text-xs ${
                                              achieved === lvl ? "border-primary bg-primary/5" : "border-border bg-background"
                                            }`}
                                          >
                                            <div className="flex items-center justify-between text-[10px] font-bold text-foreground">
                                              <span>Level {lvl}</span>
                                              {lvl === 3 ? (
                                                <span className="text-emerald-400 font-semibold">100% Target</span>
                                              ) : lvl > 3 ? (
                                                <span className="text-primary">Exceeds</span>
                                              ) : (
                                                <span className="text-amber-400">Below</span>
                                              )}
                                            </div>
                                            <Input
                                              placeholder="Timeline"
                                              value={crit.timeline}
                                              onChange={(e) => updateLevelField(kpi.id, key, "timeline", e.target.value)}
                                              className="text-[11px] h-7 px-1.5"
                                            />
                                            <Textarea
                                              placeholder="Measurable metric / threshold"
                                              value={crit.measurable}
                                              onChange={(e) => updateLevelField(kpi.id, key, "measurable", e.target.value)}
                                              rows={3}
                                              className="text-[11px] px-1.5 py-1 min-h-0 resize-y"
                                            />
                                            <Textarea
                                              placeholder="Verification / audit requirement"
                                              value={crit.requirement}
                                              onChange={(e) => updateLevelField(kpi.id, key, "requirement", e.target.value)}
                                              rows={2}
                                              className="text-[11px] px-1.5 py-1 min-h-0 resize-y"
                                            />
                                          </div>
                                        )
                                      })}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    ) : (
                      <div className="p-8 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl space-y-2">
                        <Target className="h-6 w-6 text-muted-foreground/40 mx-auto" />
                        <p>No individual KPIs added to this sheet yet.</p>
                        <p className="text-[11px] text-muted-foreground/80">Click &quot;Add Individual KPI&quot; or choose an ISP template from the left column to begin drafting.</p>
                      </div>
                    )}

                    {/* Values assessment (manager rates 1-5) */}
                    <div className="p-3 rounded-lg border border-border/80 bg-background/60 text-[11px] space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground">Values assessment (1-5, rated by manager)</span>
                        <span className="text-muted-foreground">
                          {compositeBreakdown.valuesRated && compositeBreakdown.valuesScore !== null
                            ? `Values score ${compositeBreakdown.valuesScore.toFixed(0)}%`
                            : "Values not yet rated"}
                        </span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {VALUE_DEFS.map((v) => (
                          <div key={v.key} className="flex items-center justify-between gap-2">
                            <span className="text-muted-foreground">{v.label}</span>
                            <div className="flex gap-0.5">
                              {[1, 2, 3, 4, 5].map((n) => (
                                <button
                                  key={n}
                                  type="button"
                                  onClick={() =>
                                    mutateSheet((s) => ({ ...s, values_ratings: { ...(s.values_ratings || {}), [v.key]: n } }))
                                  }
                                  className={`h-6 w-6 rounded text-[11px] font-semibold border ${
                                    empSheet.values_ratings?.[v.key] === n
                                      ? "bg-primary text-primary-foreground border-primary"
                                      : "border-border text-muted-foreground hover:text-foreground"
                                  }`}
                                >
                                  {n}
                                </button>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Composite score */}
                    <div className="p-3 rounded-lg border border-border/80 bg-background/60 text-[11px] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground">
                          Composite score
                          {compositeBreakdown.basis === "estimate" ? " (estimate: unsaved edits)" : compositeBreakdown.basis === "server" ? " (server)" : ""}
                          {compositeBreakdown.basis === "server" && empSheet.score_basis ? ` · ${empSheet.score_basis}` : ""}
                        </span>
                        <span className="font-mono text-sm font-bold text-primary">
                          {compositeBreakdown.total === null ? (empSheet.is_template ? "Not saved yet" : "—") : `${compositeBreakdown.total}%`}
                        </span>
                      </div>
                      {compositeBreakdown.total !== null && (
                        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-muted-foreground">
                          <span>
                            Shared company: <b className="text-foreground">{compositeBreakdown.companyMissing || compositeBreakdown.sharedPts === null ? "Set company targets" : `${compositeBreakdown.sharedPts.toFixed(1)} pts`}</b>
                          </span>
                          <span>Values: <b className="text-foreground">{compositeBreakdown.valuesRated && compositeBreakdown.valuesPts !== null ? `${compositeBreakdown.valuesPts.toFixed(1)} pts` : "Values not yet rated"}</b></span>
                          <span>Individual KPIs: <b className="text-foreground">{compositeBreakdown.indivPts.toFixed(1)} pts</b></span>
                        </div>
                      )}
                      <p className="text-[10px] text-muted-foreground/80">
                        Level 3 = 100% of target.
                        {empSheet.is_template ? " Nothing is saved for this employee yet: Save Draft to create the sheet." : ""}
                        {compositeBreakdown.basis === "estimate" ? " Save the sheet to see the server's score." : ""}
                        {compositeBreakdown.total !== null && !compositeBreakdown.valuesRated ? " Values count as 0 pts until all four values are rated." : ""}
                        {compositeBreakdown.total !== null && compositeBreakdown.companyMissing ? " Shared company score counts as 0 until company targets are set." : ""}
                      </p>
                    </div>

                    {/* Sheet Actions & Save */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-border">
                      <div className="text-xs space-y-1">
                        {sheetError && (
                          <span className="text-red-400 font-medium flex items-start gap-1.5" role="alert">
                            <AlertCircle className="h-4 w-4 shrink-0 mt-px" />
                            {sheetError}
                          </span>
                        )}
                        {sheetSaveMessage && !sheetError && (
                          <span className="text-emerald-400 font-medium flex items-center gap-1.5">
                            <CheckCircle2 className="h-4 w-4" />
                            {sheetSaveMessage}
                          </span>
                        )}
                        {sheetDirty && (
                          <span className="text-amber-400 font-medium flex items-center gap-1.5">
                            <AlertCircle className="h-3.5 w-3.5" />
                            Unsaved changes
                          </span>
                        )}
                        {!isWeightBalanced && (
                          <span className="text-muted-foreground block">
                            Submit is disabled until weights total 100% (currently {calculatedTotalWeight}%). Drafts can always be saved.
                          </span>
                        )}
                        {isWeightBalanced && untitledKpiCount > 0 && (
                          <span className="text-muted-foreground block">
                            Submit is disabled until every KPI has a title ({untitledKpiCount} untitled).
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void handleSaveEmpSheet("DRAFT")}
                          disabled={savingSheet}
                          className={`text-xs h-8 ${sheetDirty ? "border-amber-500/60" : ""}`}
                        >
                          <Save className="h-3.5 w-3.5 mr-1" />
                          {savingSheet ? "Saving..." : "Save Draft"}
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => void handleSaveEmpSheet("SUBMITTED")}
                          disabled={savingSheet || !canSubmit}
                          className="text-xs h-8 bg-primary text-primary-foreground font-semibold"
                        >
                          <Send className="h-3.5 w-3.5 mr-1" />
                          Submit for approval
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                </fieldset>
              </>
            ) : sheetDenied ? (
              <NotConnected loadable={sheetDenied} service="this employee's KPI sheet" />
            ) : null}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {/* TAB 2: COMPANY SHARED KPI & LEVEL WEIGHT SETUP                            */}
      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {activeTab === "company" && (
        <div className="space-y-6">
          <Card className="border-border bg-card">
            <CardHeader className="p-5 pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <CardTitle className="text-base font-bold flex items-center gap-2">
                  <Building2 className="h-5 w-5 text-primary" />
                  Whole-Company Shared KPI Setup & Actuals Source Linking
                </CardTitle>
                <CardDescription className="text-xs">
                  Configure corporate shared budgets (Sales, Cost, Profit), choose ground-truth table sources, and cascade weights down organizational tiers.
                </CardDescription>
              </div>

              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleSyncLiveActuals(true)}
                disabled={syncingActuals}
                className="text-xs h-8 border-primary/40 text-primary hover:bg-primary/10 flex items-center gap-1.5 shrink-0"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${syncingActuals ? "animate-spin" : ""}`} />
                {syncingActuals ? "Syncing..." : "Sync Live Table Actuals"}
              </Button>
            </CardHeader>

            <CardContent className="p-5 pt-0 space-y-6">
              {/* Financial Budget Targets & Actuals with Source Selector */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <DollarSign className="h-4 w-4 text-emerald-400" />
                  1. Company Performance Targets vs Budget & Source Mode (FY 2026/2027)
                </h4>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* Sales */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-foreground">Sales Revenue KPI</label>
                      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                        {companyConfig.sales_achievement_pct ?? 0}% Target
                      </Badge>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Source of Actuals:</label>
                      <select
                        value={companyConfig.sales_source_mode || "LIVE_TABLE"}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, sales_source_mode: e.target.value as any })}
                        className="w-full text-xs h-7 bg-card border border-border rounded px-2 text-foreground"
                      >
                        <option value="LIVE_TABLE">⚡ Live: sales_leads (Won Deals Table)</option>
                        <option value="PERCENTAGE">📊 Direct Percentage Mode</option>
                        <option value="MANUAL">✏️ Manual Freehand Override</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Sales Budget Target (ZAR):</label>
                      <Input
                        type="number"
                        value={companyConfig.sales_budget_zar}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, sales_budget_zar: Number(e.target.value) })}
                        className="text-xs h-8 font-mono"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Current Actual Revenue (ZAR):</label>
                      <Input
                        type="number"
                        value={companyConfig.sales_actual_zar}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, sales_actual_zar: Number(e.target.value) })}
                        className="text-xs h-8 font-mono"
                      />
                    </div>
                  </div>

                  {/* Operating Cost */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-foreground">Operating Cost Ceiling</label>
                      <Badge variant="outline" className="border-blue-500/40 text-blue-400 text-[10px]">
                        {companyConfig.cost_efficiency_pct ?? 0}% Efficient
                      </Badge>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Source of Actuals:</label>
                      <select
                        value={companyConfig.cost_source_mode || "LIVE_TABLE"}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, cost_source_mode: e.target.value as any })}
                        className="w-full text-xs h-7 bg-card border border-border rounded px-2 text-foreground"
                      >
                        <option value="LIVE_TABLE">⚡ Live: hr.payslips & Statutory Ledger</option>
                        <option value="PERCENTAGE">📊 Direct Efficiency %</option>
                        <option value="MANUAL">✏️ Manual Freehand Override</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Cost Ceiling Budget (ZAR):</label>
                      <Input
                        type="number"
                        value={companyConfig.cost_budget_zar}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, cost_budget_zar: Number(e.target.value) })}
                        className="text-xs h-8 font-mono"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Current Actual Expenditure (ZAR):</label>
                      <Input
                        type="number"
                        value={companyConfig.cost_actual_zar}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, cost_actual_zar: Number(e.target.value) })}
                        className="text-xs h-8 font-mono"
                      />
                    </div>
                  </div>

                  {/* Profit Target */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-3">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-foreground">Net EBITDA / Profit</label>
                      <Badge variant="outline" className="border-purple-500/40 text-purple-400 text-[10px]">
                        {companyConfig.profit_achievement_pct ?? 0}% Target
                      </Badge>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Source of Actuals:</label>
                      <select
                        value={companyConfig.profit_source_mode || "LIVE_TABLE"}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, profit_source_mode: e.target.value as any })}
                        className="w-full text-xs h-7 bg-card border border-border rounded px-2 text-foreground"
                      >
                        <option value="LIVE_TABLE">⚡ Live: Net Margin (Sales - Cost)</option>
                        <option value="PERCENTAGE">📊 Direct Margin %</option>
                        <option value="MANUAL">✏️ Manual Freehand Override</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Profit Budget Target (ZAR):</label>
                      <Input
                        type="number"
                        value={companyConfig.profit_budget_zar}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, profit_budget_zar: Number(e.target.value) })}
                        className="text-xs h-8 font-mono"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-[11px] text-muted-foreground">Current Actual Profit (ZAR):</label>
                      <Input
                        type="number"
                        value={companyConfig.profit_actual_zar}
                        onChange={(e) => setCompanyConfig({ ...companyConfig, profit_actual_zar: Number(e.target.value) })}
                        className="text-xs h-8 font-mono"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Position Level Weights Matrix (Adjustable) */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Sliders className="h-4 w-4 text-primary" />
                    2. Cascading Shared Weight Matrix by Job Level
                  </h4>
                  <span className="text-[11px] text-muted-foreground">
                    Values weight fixed at <b className="text-foreground">10%</b> across all staff.
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Executive */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-foreground">Executive (CEO/C-Level)</span>
                      <Badge variant="outline" className="text-[10px] text-primary">Level 4</Badge>
                    </div>
                    <label className="text-[11px] text-muted-foreground">Company Shared Weight (%):</label>
                    <Input
                      type="number"
                      min="10"
                      max="90"
                      value={companyConfig.level_weights.EXECUTIVE}
                      onChange={(e) => setCompanyConfig((prev) => ({
                        ...prev,
                        level_weights: { ...prev.level_weights, EXECUTIVE: Number(e.target.value) }
                      }))}
                      className="text-xs h-8 font-mono"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Remainder Individual KPIs: <b className="text-foreground">{100 - companyConfig.level_weights.EXECUTIVE - 10}%</b>
                    </p>
                  </div>

                  {/* Director */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-foreground">Director / VP</span>
                      <Badge variant="outline" className="text-[10px] text-primary">Level 3</Badge>
                    </div>
                    <label className="text-[11px] text-muted-foreground">Company Shared Weight (%):</label>
                    <Input
                      type="number"
                      min="10"
                      max="90"
                      value={companyConfig.level_weights.DIRECTOR}
                      onChange={(e) => setCompanyConfig((prev) => ({
                        ...prev,
                        level_weights: { ...prev.level_weights, DIRECTOR: Number(e.target.value) }
                      }))}
                      className="text-xs h-8 font-mono"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Remainder Individual KPIs: <b className="text-foreground">{100 - companyConfig.level_weights.DIRECTOR - 10}%</b>
                    </p>
                  </div>

                  {/* Manager */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-foreground">Manager / Lead</span>
                      <Badge variant="outline" className="text-[10px] text-primary">Level 2</Badge>
                    </div>
                    <label className="text-[11px] text-muted-foreground">Company Shared Weight (%):</label>
                    <Input
                      type="number"
                      min="10"
                      max="90"
                      value={companyConfig.level_weights.MANAGER}
                      onChange={(e) => setCompanyConfig((prev) => ({
                        ...prev,
                        level_weights: { ...prev.level_weights, MANAGER: Number(e.target.value) }
                      }))}
                      className="text-xs h-8 font-mono"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Remainder Individual KPIs: <b className="text-foreground">{100 - companyConfig.level_weights.MANAGER - 10}%</b>
                    </p>
                  </div>

                  {/* Staff */}
                  <div className="p-4 rounded-xl border border-border bg-background space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-foreground">Operational Staff</span>
                      <Badge variant="outline" className="text-[10px] text-primary">Level 1</Badge>
                    </div>
                    <label className="text-[11px] text-muted-foreground">Company Shared Weight (%):</label>
                    <Input
                      type="number"
                      min="10"
                      max="90"
                      value={companyConfig.level_weights.STAFF}
                      onChange={(e) => setCompanyConfig((prev) => ({
                        ...prev,
                        level_weights: { ...prev.level_weights, STAFF: Number(e.target.value) }
                      }))}
                      className="text-xs h-8 font-mono"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Remainder Individual KPIs: <b className="text-foreground">{100 - companyConfig.level_weights.STAFF - 10}%</b>
                    </p>
                  </div>
                </div>
              </div>

              {/* Strategic Values */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <Award className="h-4 w-4 text-purple-400" />
                  3. Company Core Strategic Values (Standard 10%)
                </h4>
                <Textarea
                  value={companyConfig.values_description}
                  onChange={(e) => setCompanyConfig({ ...companyConfig, values_description: e.target.value })}
                  rows={2}
                  className="text-xs bg-background"
                />
              </div>

              {/* Actions & Cascade */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-4 border-t border-border">
                {cascadeMessage && (
                  <span className="text-xs text-emerald-400 font-medium flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4" />
                    {cascadeMessage}
                  </span>
                )}

                <div className="flex items-center gap-2 ml-auto">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleSaveCompanyConfig}
                    disabled={savingConfig || !isHrAdmin}
                    title={!isHrAdmin ? ADMIN_ONLY_TIP : undefined}
                    className="text-xs h-8"
                  >
                    <Save className="h-3.5 w-3.5 mr-1" />
                    Save Settings
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleCascadeToAll}
                    disabled={cascading || !isHrAdmin}
                    title={!isHrAdmin ? ADMIN_ONLY_TIP : undefined}
                    className="text-xs h-8 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 mr-1 ${cascading ? "animate-spin" : ""}`} />
                    Cascade Shared KPIs to All {activeStaffList.length} Staff
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {/* TAB 3: BUDGET VS ACTUALS SCORECARD & ANALYTICS                            */}
      {/* ═══════════════════════════════════════════════════════════════════════════ */}
      {activeTab === "analytics" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Visual Bar Chart: Budget vs Actuals */}
            <Card className="border-border bg-card">
              <CardHeader className="p-4">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  Budget vs Actual Financial Performance (ZAR &apos;000)
                </CardTitle>
                <CardDescription className="text-xs">
                  Sales, Cost, and Profit variance driving the Company Shared KPI index.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <div className="h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={financialBudgetChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="metric" tick={{ fill: "#888", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#888", fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1e1e1e", borderColor: "#333", borderRadius: 8, fontSize: 11 }}
                        formatter={(val: number) => [fmtZar(val * 1000), ""]}
                      />
                      <Legend />
                      <Bar dataKey="Budget" fill="#3b82f6" name="Target Budget" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Actual" fill="#10b981" name="Current Actual" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Department Alignment Matrix */}
            <Card className="border-border bg-card">
              <CardHeader className="p-4">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Layers className="h-4 w-4 text-purple-400" />
                  Departmental Shared KPI Weight Cascade
                </CardTitle>
                <CardDescription className="text-xs">
                  How the corporate budget benchmarks cascade across positions.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <div className="space-y-3">
                  {[
                    { level: "Executive / C-Suite", weight: companyConfig.level_weights.EXECUTIVE, desc: "Executive positions" },
                    { level: "Directors & VPs", weight: companyConfig.level_weights.DIRECTOR, desc: "Director positions" },
                    { level: "Managers & Team Leads", weight: companyConfig.level_weights.MANAGER, desc: "Manager positions" },
                    { level: "Operational Staff", weight: companyConfig.level_weights.STAFF, desc: "Staff positions" },
                  ].map((r) => ({
                    ...r,
                    target: `${r.weight}% Corporate + ${companyConfig.values_weight_pct}% Values + ${Math.max(0, Math.round((100 - r.weight - companyConfig.values_weight_pct) * 10) / 10)}% Individual`,
                  })).map((row, i) => (
                    <div key={i} className="p-3 rounded-lg border border-border bg-background flex items-center justify-between text-xs">
                      <div>
                        <p className="font-semibold text-foreground">{row.level}</p>
                        <p className="text-[10px] text-muted-foreground">{row.desc}</p>
                        <p className="text-[10px] text-primary font-medium mt-0.5">{row.target}</p>
                      </div>
                      <Badge variant="outline" className="border-primary/40 text-primary text-xs font-bold">
                        {row.weight}% Shared
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
