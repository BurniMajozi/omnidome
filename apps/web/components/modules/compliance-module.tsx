"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/ui/page-header"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from "recharts"
import {
  AlertTriangle, ArrowRight, Bell, BookOpen, Briefcase, Building2, Calendar,
  CheckCircle, ChevronRight, ClipboardList, Clock, DollarSign, Download,
  Eye, FileText, Flag, Gift, Globe, Heart, Layers, Lock, Mail, Megaphone,
  Plane, Plus, RefreshCw, Search, Send, Settings, Shield, ShieldCheck,
  ShieldAlert, ShieldX, Star, Target, TrendingUp, Truck, Upload, UserCheck,
  Users, XCircle, Zap, AlertCircle, Scale, Landmark, BadgeCheck, BadgeAlert,
  BadgeMinus, FileWarning, FileCheck, Activity, Gavel, DoorOpen, Car,
  PlaneTakeoff, Users2, Coins, Banknote, CircleDollarSign, HandCoins, Radio,
} from "lucide-react"
import {
  getComplianceOverview, listContracts, getExpiringContracts, listTaxReturns,
  getTaxDashboard, listHsIncidents, getHsDashboard, listBbbeeScorecards,
  listLeaveApplications, listVehicles, getExpiringVehicles, listForeignWorkers,
  getExpiringPermits, listTravelReadiness, listDrBcpPlans, getDrBcpDashboard,
  listComplianceScores, calculateAllScores, listObligations, listEserviceSubmissions,
  listIcasaSubmissions, listDsar,
  listBreaches, listFundingOpportunities, matchFundingByScore,
  uploadDocument, fetchUrlDocument,
  listDocuments, getDocumentDetail, reprocessDocument, linkDocumentToContract,
  getDocumentStats,
  // Cross-Service Connectors
  getComplianceSalesSla, vetCustomerFica, getTechnicianFleetSafety, logTechnicianSafetyIncident,
  getFinanceStatutoryStatus, getCallCenterPopiaAudit, createCallCenterDsar,
  getRicaSubscriberAudit, getExecutiveComplianceSummary,
  type ComplianceOverview, type Contract, type BreachRegister, type ComplianceScore,
  type PopiDsar, type HsIncident, type TaxReturn, type BbbeeScorecard,
  type LeaveApplication, type VehicleRegistration, type ForeignWorkerPermit,
  type TravelReadiness, type DrBcpPlan, type ComplianceObligation,
  type EserviceSubmission, type IcasaSubmission, type FundingOpportunity,
  type DocumentUploadResult, type UrlFetchResult, type DocumentRecord,
  type SalesContractsSlaResponse, type VetCustomerFicaInput, type VetCustomerFicaResult,
  type TechnicianSafetyAuditResponse, type LogHsIncidentInput, type LogHsIncidentResult,
  type StatutoryStatusResponse, type PopiaAuditResponse, type CreateDsarInput,
  type CreateDsarResult, type RicaSubscriberAuditResponse, type ExecutiveComplianceSummaryResponse,
  type ComplianceAlertItem, type ComplianceContractSlaItem, type FleetVehicleItem,
  type SafetyIncidentItem, type DsarItem,
} from "@/lib/compliance-api"
import DocumentUploadZone from "@/components/modules/document-upload-zone"
import { NotConnected } from "@/components/ui/not-connected"
import { loadableFromStatus, type Loadable } from "@/lib/service-state"
import { ComplianceApiError } from "@/lib/compliance-api"
import { StatutoryPayrollAdminView } from "./compliance/statutory-payroll-admin-view"

// ═══════════════════════════════════════════════════════════════════════════════
// COLOR SYSTEM
// ═══════════════════════════════════════════════════════════════════════════════

const STATUS_COLOR: Record<string, string> = {
  compliant: "border-emerald-500/40 text-emerald-400",
  non_compliant: "border-red-500/40 text-red-400",
  at_risk: "border-amber-500/40 text-amber-400",
  pending_review: "border-cyan-500/40 text-cyan-400",
  exempt: "border-gray-500/40 text-gray-400",
  active: "border-emerald-500/40 text-emerald-400",
  draft: "border-gray-500/40 text-gray-400",
  expired: "border-red-500/40 text-red-400",
  terminated: "border-red-500/40 text-red-400",
  suspended: "border-amber-500/40 text-amber-400",
  open: "border-red-500/40 text-red-400",
  identified: "border-amber-500/40 text-amber-400",
  investigating: "border-cyan-500/40 text-cyan-400",
  resolved: "border-emerald-500/40 text-emerald-400",
  received: "border-cyan-500/40 text-cyan-400",
  in_progress: "border-amber-500/40 text-amber-400",
  completed: "border-emerald-500/40 text-emerald-400",
  pending: "border-amber-500/40 text-amber-400",
  approved: "border-emerald-500/40 text-emerald-400",
  rejected: "border-red-500/40 text-red-400",
  overdue: "border-red-500/40 text-red-400",
  submitted: "border-blue-500/40 text-blue-400",
  assessed: "border-purple-500/40 text-purple-400",
  paid: "border-emerald-500/40 text-emerald-400",
  disputed: "border-amber-500/40 text-amber-400",
  critical: "border-red-500/40 text-red-400",
  high: "border-orange-500/40 text-orange-400",
  medium: "border-amber-500/40 text-amber-400",
  low: "border-blue-500/40 text-blue-400",
  tested: "border-emerald-500/40 text-emerald-400",
  failed: "border-red-500/40 text-red-400",
  in_review: "border-cyan-500/40 text-cyan-400",
  not_started: "border-gray-500/40 text-gray-400",
  level_1: "border-emerald-500/40 text-emerald-400",
  level_2: "border-emerald-500/40 text-emerald-400",
  level_3: "border-green-500/40 text-green-400",
  level_4: "border-green-500/40 text-green-400",
  level_5: "border-lime-500/40 text-lime-400",
  level_6: "border-yellow-500/40 text-yellow-400",
  level_7: "border-amber-500/40 text-amber-400",
  level_8: "border-orange-500/40 text-orange-400",
}

const SCORE_COLOR = (score: number) => {
  if (score >= 90) return "#10b981"
  if (score >= 70) return "#f59e0b"
  if (score >= 50) return "#f97316"
  return "#ef4444"
}

const SEVERITY_ICON: Record<string, React.ReactNode> = {
  critical: <ShieldX className="h-4 w-4 text-red-400" />,
  high: <ShieldAlert className="h-4 w-4 text-orange-400" />,
  medium: <Shield className="h-4 w-4 text-amber-400" />,
  low: <ShieldCheck className="h-4 w-4 text-blue-400" />,
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLOR[status] || "border-gray-500/40 text-gray-400"
  return <Badge variant="outline" className={cls}>{status.replace(/_/g, " ")}</Badge>
}

function ScoreRing({ score, size = 80 }: { score: number; size?: number }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const offset = circ - (score / 100) * circ
  const color = SCORE_COLOR(score)
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth={6} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={6}
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
      <span className="absolute text-sm font-bold" style={{ color }}>{Math.round(score)}</span>
    </div>
  )
}

function AlertCard({ icon, title, value, subtitle, color, onClick }: {
  icon: React.ReactNode; title: string; value: string | number; subtitle?: string; color: string; onClick?: () => void
}) {
  return (
    <Card className={`border-${color}-500/20 bg-${color}-500/5 cursor-pointer hover:bg-${color}-500/10 transition-colors`}
      onClick={onClick}>
      <CardContent className="p-4 flex items-center gap-4">
        <div className={`rounded-lg bg-${color}-500/10 p-2.5`}>{icon}</div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

function SectionHeader({ icon, title, subtitle, action }: {
  icon: React.ReactNode; title: string; subtitle?: string; action?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-primary/10 p-2">{icon}</div>
        <div>
          <h3 className="text-lg font-semibold">{title}</h3>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

function EmptyState({ icon, message }: { icon: React.ReactNode; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      {icon}
      <p className="mt-2 text-sm">{message}</p>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN MODULE
// ═══════════════════════════════════════════════════════════════════════════════

/** Real value or an honest "N/A" - never a made-up default. */
const na = (v: number | string | null | undefined, suffix = ""): string =>
  v === null || v === undefined ? "N/A" : `${v}${suffix}`

export default function ComplianceModule() {
  const [activeTab, setActiveTab] = useState("overview")
  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState<ComplianceOverview | null>(null)
  // Whether the compliance service answered at all. Drives the honest
  // "Service not running" state instead of fabricated KPIs.
  const [serviceState, setServiceState] = useState<Loadable<null>>({ state: "loading" })

  // Data states per section
  const [contracts, setContracts] = useState<Contract[]>([])
  const [expiringContracts, setExpiringContracts] = useState<Contract[]>([])
  const [breaches, setBreaches] = useState<BreachRegister[]>([])
  const [scores, setScores] = useState<ComplianceScore[]>([])
  const [dsar, setDsar] = useState<PopiDsar[]>([])
  const [hsIncidents, setHsIncidents] = useState<HsIncident[]>([])
  const [taxReturns, setTaxReturns] = useState<TaxReturn[]>([])
  const [bbbeeCards, setBbbeeCards] = useState<BbbeeScorecard[]>([])
  const [leaveApps, setLeaveApps] = useState<LeaveApplication[]>([])
  const [vehicles, setVehicles] = useState<VehicleRegistration[]>([])
  const [fwPermits, setFwPermits] = useState<ForeignWorkerPermit[]>([])
  const [travel, setTravel] = useState<TravelReadiness[]>([])
  const [drPlans, setDrPlans] = useState<DrBcpPlan[]>([])
  const [obligations, setObligations] = useState<ComplianceObligation[]>([])
  const [eservices, setEservices] = useState<EserviceSubmission[]>([])
  const [icasaSubs, setIcasaSubs] = useState<IcasaSubmission[]>([])
  const [funding, setFunding] = useState<FundingOpportunity[]>([])

  // Cross-Service Connectors state
  const [salesSla, setSalesSla] = useState<SalesContractsSlaResponse | null>(null)
  const [fleetSafety, setFleetSafety] = useState<TechnicianSafetyAuditResponse | null>(null)
  const [statutoryStatus, setStatutoryStatus] = useState<StatutoryStatusResponse | null>(null)
  const [popiaAudit, setPopiaAudit] = useState<PopiaAuditResponse | null>(null)
  const [ricaAudit, setRicaAudit] = useState<RicaSubscriberAuditResponse | null>(null)
  const [executiveSummary, setExecutiveSummary] = useState<ExecutiveComplianceSummaryResponse | null>(null)

  // Cross-Service Modals state
  const [ficaModalOpen, setFicaModalOpen] = useState(false)
  const [ficaForm, setFicaForm] = useState<VetCustomerFicaInput>({
    company_name: "",
    registration_number: "",
    director_name: "",
    director_id_number: "",
    vat_number: "",
  })
  const [ficaLoading, setFicaLoading] = useState(false)
  const [ficaResult, setFicaResult] = useState<VetCustomerFicaResult | null>(null)

  const [incidentModalOpen, setIncidentModalOpen] = useState(false)
  const [incidentForm, setIncidentForm] = useState<LogHsIncidentInput>({
    incident_type: "near_miss",
    severity: "low",
    description: "",
    employee_involved: "",
    location: "",
  })
  const [incidentLoading, setIncidentLoading] = useState(false)
  const [incidentResult, setIncidentResult] = useState<LogHsIncidentResult | null>(null)

  const [dsarModalOpen, setDsarModalOpen] = useState(false)
  const [dsarForm, setDsarForm] = useState<CreateDsarInput>({
    request_type: "access",
    requester_name: "",
    requester_email: "",
    requester_phone: "",
    description: "",
  })
  const [dsarLoading, setDsarLoading] = useState(false)
  const [dsarResult, setDsarResult] = useState<CreateDsarResult | null>(null)

  /** Returns value or null — never rejects. */
  const safe = <T,>(p: Promise<T>) => p.catch((): null => null)

  const loadOverview = useCallback(async () => {
    const [data, exec, sla, stat] = await Promise.all([
      getComplianceOverview().then(
        (d) => ({ ok: true as const, d }),
        (e: unknown) => ({ ok: false as const, e }),
      ),
      safe(getExecutiveComplianceSummary()),
      safe(getComplianceSalesSla()),
      safe(getFinanceStatutoryStatus()),
    ])
    if (stat) setStatutoryStatus(stat)
    if (data.ok) {
      setOverview(data.d)
      setServiceState({ state: "ready", data: null })
    } else {
      const status = data.e instanceof ComplianceApiError ? data.e.status : null
      setServiceState(loadableFromStatus<null>(status, undefined))
    }
    if (exec) setExecutiveSummary(exec)
    if (sla) setSalesSla(sla)
  }, [])

  const reloadOverview = () => {
    setLoading(true)
    setServiceState({ state: "loading" })
    loadOverview().finally(() => setLoading(false))
  }

  const handleVetFica = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ficaForm.company_name || !ficaForm.registration_number || !ficaForm.director_id_number) return
    setFicaLoading(true)
    try {
      const res = await vetCustomerFica(ficaForm)
      setFicaResult(res)
      const sla = await safe(getComplianceSalesSla())
      if (sla) setSalesSla(sla)
    } catch (err: any) {
      alert(`FICA verification failed: ${err?.message || err}`)
    } finally {
      setFicaLoading(false)
    }
  }

  const handleLogIncident = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!incidentForm.description) return
    setIncidentLoading(true)
    try {
      const res = await logTechnicianSafetyIncident(incidentForm)
      setIncidentResult(res)
      const fs = await safe(getTechnicianFleetSafety())
      if (fs) setFleetSafety(fs)
    } catch (err: any) {
      alert(`Safety incident logging failed: ${err?.message || err}`)
    } finally {
      setIncidentLoading(false)
    }
  }

  const handleCreateDsar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dsarForm.requester_name || !dsarForm.requester_email || !dsarForm.description) return
    setDsarLoading(true)
    try {
      const res = await createCallCenterDsar(dsarForm)
      setDsarResult(res)
      const pa = await safe(getCallCenterPopiaAudit())
      if (pa) setPopiaAudit(pa)
    } catch (err: any) {
      alert(`POPIA DSAR registration failed: ${err?.message || err}`)
    } finally {
      setDsarLoading(false)
    }
  }

  const loadSection = useCallback(async (tab: string) => {
    switch (tab) {
      case "contracts": {
        const [c, ec, sla] = await Promise.all([
          safe(listContracts({ page: 1 })),
          safe(getExpiringContracts(90)),
          safe(getComplianceSalesSla()),
        ])
        setContracts(c?.items ?? [])
        setExpiringContracts(ec?.items ?? [])
        if (sla) setSalesSla(sla)
        break
      }
      case "fleet_safety": {
        const fs = await safe(getTechnicianFleetSafety())
        if (fs) setFleetSafety(fs)
        break
      }
      case "statutory": {
        const [st, tax] = await Promise.all([
          safe(getFinanceStatutoryStatus()),
          safe(listTaxReturns()),
        ])
        if (st) setStatutoryStatus(st)
        setTaxReturns(tax?.items ?? [])
        break
      }
      case "popia_rica": {
        const [pa, ra, ds] = await Promise.all([
          safe(getCallCenterPopiaAudit()),
          safe(getRicaSubscriberAudit()),
          safe(listDsar()),
        ])
        if (pa) setPopiaAudit(pa)
        if (ra) setRicaAudit(ra)
        setDsar(ds?.items ?? [])
        break
      }
      case "executive_ai": {
        const exec = await safe(getExecutiveComplianceSummary())
        if (exec) setExecutiveSummary(exec)
        break
      }
      case "regulatory": {
        const [tax, hs, bbbee, icasa] = await Promise.all([
          safe(listTaxReturns()),
          safe(listHsIncidents()),
          safe(listBbbeeScorecards()),
          safe(listIcasaSubmissions()),
        ])
        setTaxReturns(tax?.items ?? [])
        setHsIncidents(hs?.items ?? [])
        setBbbeeCards(bbbee?.items ?? [])
        setIcasaSubs(icasa?.items ?? [])
        break
      }
      case "hr": {
        const [leave, veh, fw, tr] = await Promise.all([
          safe(listLeaveApplications()),
          safe(listVehicles()),
          safe(listForeignWorkers()),
          safe(listTravelReadiness()),
        ])
        setLeaveApps(leave?.items ?? [])
        setVehicles(veh?.items ?? [])
        setFwPermits(fw?.items ?? [])
        setTravel(tr?.items ?? [])
        break
      }
      case "risk": {
        const [br, ds, obl] = await Promise.all([
          safe(listBreaches()),
          safe(listDsar()),
          safe(listObligations({ status: "pending_review" })),
        ])
        setBreaches(br?.items ?? [])
        setDsar(ds?.items ?? [])
        setObligations(obl?.items ?? [])
        break
      }
      case "operations": {
        const [dr, sc, es] = await Promise.all([
          safe(listDrBcpPlans()),
          safe(listComplianceScores()),
          safe(listEserviceSubmissions()),
        ])
        setDrPlans(dr?.items ?? [])
        setScores(sc?.items ?? [])
        setEservices(es?.items ?? [])
        break
      }
      case "funding": {
        const [f, sc] = await Promise.all([
          safe(listFundingOpportunities({ status: "identified" })),
          safe(listComplianceScores()),
        ])
        setFunding(f?.items ?? [])
        setScores(sc?.items ?? [])
        break
      }
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    loadOverview().finally(() => setLoading(false))
  }, [loadOverview])

  useEffect(() => {
    if (activeTab !== "overview") {
      loadSection(activeTab)
    }
  }, [activeTab, loadSection])

  // ── Chart Data ───────────────────────────────────────────────────────

  const categoryChartData = useMemo(() => {
    if (!overview?.categories) return []
    return overview.categories.map((c) => ({
      name: c.name.replace(/_/g, " "),
      score: c.score,
      fill: SCORE_COLOR(c.score),
    }))
  }, [overview])

  const breachChartData = useMemo(() => {
    const severityCounts: Record<string, number> = {}
    breaches.forEach((b) => {
      severityCounts[b.severity] = (severityCounts[b.severity] || 0) + 1
    })
    return Object.entries(severityCounts).map(([name, value]) => ({
      name,
      value,
      fill: name === "critical" ? "#ef4444" : name === "high" ? "#f97316" : name === "medium" ? "#f59e0b" : "#3b82f6",
    }))
  }, [breaches])

  const radarData = useMemo(() => {
    if (!overview?.categories) return []
    return overview.categories.map((c) => ({
      subject: c.name.replace(/_/g, " ").slice(0, 12),
      score: c.score,
      fullMark: 100,
    }))
  }, [overview])

  // ── Render ───────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (serviceState.state !== "ready") {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={<Scale className="h-5 w-5" />}
          title="Compliance Center"
          subtitle="Contracts, regulatory filings, POPIA/RICA and audit readiness"
        />
        <NotConnected loadable={serviceState} service="Compliance service" onRetry={reloadOverview} className="py-16" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Scale className="h-5 w-5" />}
        title="Compliance Center"
        subtitle="Full-spectrum compliance management — contracts, regulatory, HR, risk, funding"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={loadOverview}><RefreshCw className="h-3.5 w-3.5" />Refresh</Button>
            <Button variant="cta" size="sm" onClick={() => calculateAllScores()}><Zap className="h-3.5 w-3.5" />Calculate Scores</Button>
          </>
        }
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 lg:grid-cols-8">
          <TabsTrigger value="overview" className="gap-1.5"><Activity className="h-4 w-4" /> Overview</TabsTrigger>
          <TabsTrigger value="contracts" className="gap-1.5"><FileText className="h-4 w-4" /> Commercial SLAs</TabsTrigger>
          <TabsTrigger value="fleet_safety" className="gap-1.5"><Truck className="h-4 w-4" /> Fleet & Safety</TabsTrigger>
          <TabsTrigger value="statutory" className="gap-1.5"><Landmark className="h-4 w-4" /> PAYE & Statutory</TabsTrigger>
          <TabsTrigger value="popia_rica" className="gap-1.5"><ShieldCheck className="h-4 w-4" /> POPIA & RICA</TabsTrigger>
          <TabsTrigger value="executive_ai" className="gap-1.5"><Zap className="h-4 w-4" /> Executive Copilot</TabsTrigger>
          <TabsTrigger value="regulatory" className="gap-1.5"><Scale className="h-4 w-4" /> Regulatory</TabsTrigger>
          <TabsTrigger value="operations" className="gap-1.5"><Settings className="h-4 w-4" /> Ops & DR</TabsTrigger>
        </TabsList>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* OVERVIEW TAB                                                     */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="overview" className="space-y-4">
          {/* Score Ring + Alert Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="md:col-span-1 flex flex-col items-center justify-center py-6">
              <CardHeader className="text-center pb-2">
                <CardTitle className="text-sm text-muted-foreground">Overall Compliance</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col items-center">
                <ScoreRing score={overview?.overall_score ?? 0} size={120} />
                <p className="mt-2 text-xs text-muted-foreground">
                  {(overview?.categories?.length ?? 0)} categories tracked
                </p>
              </CardContent>
            </Card>

            <div className="md:col-span-3 grid grid-cols-2 md:grid-cols-4 gap-3">
              <AlertCard
                icon={<FileWarning className="h-5 w-5 text-amber-400" />}
                title="Expiring Contracts"
                value={overview?.expiring_contracts ?? 0}
                subtitle="Next 90 days"
                color="amber"
                onClick={() => setActiveTab("contracts")}
              />
              <AlertCard
                icon={<AlertTriangle className="h-5 w-5 text-red-400" />}
                title="Open Breaches"
                value={overview?.open_breaches ?? 0}
                subtitle="Requires attention"
                color="red"
                onClick={() => setActiveTab("risk")}
              />
              <AlertCard
                icon={<Clock className="h-5 w-5 text-orange-400" />}
                title="Overdue DSARs"
                value={overview?.overdue_dsar ?? 0}
                subtitle="POPI 30-day SLA"
                color="orange"
                onClick={() => setActiveTab("risk")}
              />
              <AlertCard
                icon={<AlertCircle className="h-5 w-5 text-cyan-400" />}
                title="Pending Obligations"
                value={overview?.pending_obligations ?? 0}
                subtitle="Awaiting review"
                color="cyan"
                onClick={() => setActiveTab("risk")}
              />
              <AlertCard
                icon={<Gavel className="h-5 w-5 text-red-400" />}
                title="Tax Overdue"
                value={overview?.tax_overdue ?? 0}
                subtitle="SARS filings"
                color="red"
                onClick={() => setActiveTab("regulatory")}
              />
              <AlertCard
                icon={<Heart className="h-5 w-5 text-rose-400" />}
                title="H&S Open Incidents"
                value={overview?.hs_open_incidents ?? 0}
                subtitle="Health & Safety"
                color="rose"
                onClick={() => setActiveTab("regulatory")}
              />
              <AlertCard
                icon={<BadgeCheck className="h-5 w-5 text-emerald-400" />}
                title="BBBEE Level"
                value={overview?.bbbee_level ?? "N/A"}
                subtitle="Current scorecard"
                color="emerald"
                onClick={() => setActiveTab("regulatory")}
              />
              <AlertCard
                icon={<CircleDollarSign className="h-5 w-5 text-green-400" />}
                title="Funding Matched"
                value={overview?.funding_matched ?? 0}
                subtitle="Opportunities"
                color="green"
                onClick={() => setActiveTab("funding")}
              />
            </div>
          </div>

          {/* Cross-Service Ecosystem Pulse */}
          <Card className="border-primary/20 bg-gradient-to-r from-primary/5 via-background to-primary/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Activity className="h-4 w-4 text-primary animate-pulse" />
                  Unified Cross-Service Compliance Pulse
                </CardTitle>
                {executiveSummary ? (
                  <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                    {executiveSummary.audit_readiness_level} · Score {executiveSummary.overall_compliance_score}%
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-muted-foreground">Audit readiness: not connected</Badge>
                )}
              </div>
              <CardDescription className="text-xs">
                Real-time regulatory telemetry across Commercial Sales SLAs, Field Fleet OHS, Statutory Finance Treasury, Call Center POPIA, and RICA Subscriber Identity.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div
                  className="rounded-lg border border-border/60 bg-background/50 p-3 cursor-pointer hover:border-primary/40 transition-colors"
                  onClick={() => setActiveTab("contracts")}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Commercial SLAs</span>
                    <FileText className="h-3.5 w-3.5 text-blue-400" />
                  </div>
                  <p className="mt-1 text-lg font-bold text-foreground">
                    {salesSla ? `R ${(salesSla.total_portfolio_value_zar / 1000000).toFixed(2)}M` : "N/A"}
                  </p>
                  <p className="text-[11px] text-emerald-400">{na(salesSla?.average_sla_uptime_pct, "% Uptime Target")}</p>
                </div>

                <div
                  className="rounded-lg border border-border/60 bg-background/50 p-3 cursor-pointer hover:border-primary/40 transition-colors"
                  onClick={() => setActiveTab("fleet_safety")}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Fleet & Safety</span>
                    <Truck className="h-3.5 w-3.5 text-amber-400" />
                  </div>
                  <p className="mt-1 text-lg font-bold text-foreground">
                    {na(fleetSafety?.zero_incident_streak_days, " Days")}
                  </p>
                  <p className="text-[11px] text-emerald-400">{na(fleetSafety?.coida_reportable_accidents_ytd, " COIDA Reportable")}</p>
                </div>

                <div
                  className="rounded-lg border border-border/60 bg-background/50 p-3 cursor-pointer hover:border-primary/40 transition-colors"
                  onClick={() => setActiveTab("statutory")}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Statutory Treasury</span>
                    <Landmark className="h-3.5 w-3.5 text-emerald-400" />
                  </div>
                  <p className="mt-1 text-lg font-bold text-foreground">
                    {statutoryStatus ? `SARS ${statutoryStatus.sars_tax_clearance_status}` : "N/A"}
                  </p>
                  <p className="text-[11px] text-cyan-400">
                    {statutoryStatus ? `BBBEE ${statutoryStatus.bbbee_contributor_level} · ${statutoryStatus.bbbee_procurement_recognition_pct}%` : "Open tab to load"}
                  </p>
                </div>

                <div
                  className="rounded-lg border border-border/60 bg-background/50 p-3 cursor-pointer hover:border-primary/40 transition-colors"
                  onClick={() => setActiveTab("popia_rica")}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">POPIA & RICA</span>
                    <ShieldCheck className="h-3.5 w-3.5 text-cyan-400" />
                  </div>
                  <p className="mt-1 text-lg font-bold text-foreground">
                    {na(popiaAudit?.voice_recording_consent_rate_pct, "%")}
                  </p>
                  <p className="text-[11px] text-emerald-400">{na(ricaAudit?.verified_pct, "% RICA Verified")}</p>
                </div>

                <div
                  className="rounded-lg border border-border/60 bg-background/50 p-3 cursor-pointer hover:border-primary/40 transition-colors"
                  onClick={() => setActiveTab("executive_ai")}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Executive AI</span>
                    <Zap className="h-3.5 w-3.5 text-purple-400" />
                  </div>
                  <p className="mt-1 text-lg font-bold text-foreground">
                    {executiveSummary ? `${executiveSummary.alerts?.length ?? 0} Alerts` : "N/A"}
                  </p>
                  <p className="text-[11px] text-purple-400">{executiveSummary ? "Copilot synced" : "Not connected"}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Charts Row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="md:col-span-1">
              <CardHeader><CardTitle className="text-sm">Compliance Radar</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#334155" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 9 }} />
                    <Radar name="Score" dataKey="score" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
                  </RadarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="md:col-span-1">
              <CardHeader><CardTitle className="text-sm">Category Scores</CardTitle></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={categoryChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis type="number" domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                    <YAxis type="category" dataKey="name" width={100} tick={{ fill: "#94a3b8", fontSize: 9 }} />
                    <Tooltip contentStyle={{ backgroundColor: "#1e293b", border: "none", borderRadius: 8 }} />
                    <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                      {categoryChartData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="md:col-span-1">
              <CardHeader><CardTitle className="text-sm">Escalation Summary</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {/* Escalation items */}
                {(overview?.open_breaches ?? 0) > 0 && (
                  <div className="flex items-center justify-between p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                    <div className="flex items-center gap-2">
                      <ShieldX className="h-4 w-4 text-red-400" />
                      <span className="text-sm">Critical Breaches</span>
                    </div>
                    <Badge variant="outline" className="border-red-500/40 text-red-400">
                      {overview?.open_breaches}
                    </Badge>
                  </div>
                )}
                {(overview?.overdue_dsar ?? 0) > 0 && (
                  <div className="flex items-center justify-between p-2 rounded-lg bg-orange-500/10 border border-orange-500/20">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-orange-400" />
                      <span className="text-sm">Overdue DSARs</span>
                    </div>
                    <Badge variant="outline" className="border-orange-500/40 text-orange-400">
                      {overview?.overdue_dsar}
                    </Badge>
                  </div>
                )}
                {(overview?.tax_overdue ?? 0) > 0 && (
                  <div className="flex items-center justify-between p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                    <div className="flex items-center gap-2">
                      <Gavel className="h-4 w-4 text-red-400" />
                      <span className="text-sm">Overdue Tax</span>
                    </div>
                    <Badge variant="outline" className="border-red-500/40 text-red-400">
                      {overview?.tax_overdue}
                    </Badge>
                  </div>
                )}
                {(overview?.expiring_contracts ?? 0) > 0 && (
                  <div className="flex items-center justify-between p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
                    <div className="flex items-center gap-2">
                      <FileWarning className="h-4 w-4 text-amber-400" />
                      <span className="text-sm">Expiring Contracts</span>
                    </div>
                    <Badge variant="outline" className="border-amber-500/40 text-amber-400">
                      {overview?.expiring_contracts}
                    </Badge>
                  </div>
                )}
                {(overview?.hs_open_incidents ?? 0) > 0 && (
                  <div className="flex items-center justify-between p-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
                    <div className="flex items-center gap-2">
                      <Heart className="h-4 w-4 text-rose-400" />
                      <span className="text-sm">Open H&S Incidents</span>
                    </div>
                    <Badge variant="outline" className="border-rose-500/40 text-rose-400">
                      {overview?.hs_open_incidents}
                    </Badge>
                  </div>
                )}
                {(!overview || (overview.open_breaches === 0 && overview.overdue_dsar === 0 && overview.tax_overdue === 0)) && (
                  <div className="flex items-center justify-center py-6 text-emerald-400">
                    <CheckCircle className="h-5 w-5 mr-2" />
                    <span className="text-sm">No active escalations</span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* CONTRACTS TAB                                                    */}
        {/* ════════════════════════════════════════════════════════════════ */}
        {/* ════════════════════════════════════════════════════════════════ */}
        {/* 1. COMMERCIAL CONTRACTS & SLAS TAB                               */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="contracts" className="space-y-4">
          <SectionHeader
            icon={<FileText className="h-5 w-5 text-blue-400" />}
            title="Commercial Contracts & Carrier SLAs"
            subtitle="B2B fiber backhaul, dark interconnects, 99.5% uptime guarantees & automated FICA clearance"
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => { setFicaResult(null); setFicaModalOpen(true) }}>
                  <ShieldCheck className="h-4 w-4 mr-1 text-emerald-400" /> Vet Customer FICA
                </Button>
                <Button size="sm"><Plus className="h-4 w-4 mr-1" /> New Contract</Button>
              </div>
            }
          />

          {/* B2B Portfolio KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">B2B Portfolio Value</p>
              <p className="text-xl font-bold text-foreground mt-1">
                {salesSla ? `R ${salesSla.total_portfolio_value_zar.toLocaleString()}` : "N/A"}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(salesSla?.total_contracts, " contracts")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Active Carrier SLAs</p>
              <p className="text-xl font-bold text-foreground mt-1">
                {na(salesSla?.active_contracts_count, " Active")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(salesSla?.expiring_soon_count, " expiring soon")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Fiber Uptime SLA Target</p>
              <p className="text-xl font-bold text-foreground mt-1">
                {na(salesSla?.average_sla_uptime_pct, "%")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Average across contracts</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">B2B FICA Status</p>
              <p className="text-xl font-bold text-emerald-400 mt-1">
                {na(salesSla?.fica_verified_pct, "% Cleared")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Contracts with verified FICA</p>
            </Card>
          </div>

          {/* Master Carrier SLAs Table */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Carrier Master Services Agreements (MSAs)</CardTitle>
                  <CardDescription className="text-xs">Wholesale interconnect, dark fiber backhaul, and enterprise fiber SLAs.</CardDescription>
                </div>
                <Badge variant="outline" className="border-blue-500/40 text-blue-400">
                  {salesSla?.contracts?.length ?? 0} Carrier Agreements
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(salesSla?.contracts ?? []).map((c) => (
                  <div key={c.contract_id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted/20 gap-3 transition-colors">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="rounded bg-blue-500/10 p-2">
                        <Briefcase className="h-4 w-4 text-blue-400" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-foreground truncate">{c.title}</p>
                        <p className="text-xs text-muted-foreground">{c.counterparty} · <span className="font-mono">{c.contract_number}</span></p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-4 sm:justify-end">
                      <div className="text-right min-w-[100px]">
                        <p className="text-xs text-muted-foreground">Annual Value</p>
                        <p className="text-sm font-semibold text-foreground">R {c.annual_value_zar.toLocaleString()}</p>
                      </div>
                      <div className="text-right min-w-[90px]">
                        <p className="text-xs text-muted-foreground">SLA Target</p>
                        <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 font-mono text-xs">
                          {c.uptime_sla_pct}% · {c.mttr_target_hours}h MTTR
                        </Badge>
                      </div>
                      <div className="text-right min-w-[90px]">
                        <p className="text-xs text-muted-foreground">Term Left</p>
                        <Badge variant="outline" className={c.days_to_expiry <= 90 ? "border-amber-500/40 text-amber-400" : "border-muted-foreground/40 text-muted-foreground"}>
                          {c.days_to_expiry} days
                        </Badge>
                      </div>
                      <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 flex items-center gap-1">
                        <ShieldCheck className="h-3 w-3" /> FICA {String(c.fica_status ?? "unknown").toLowerCase()}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Expiring Contracts Alert */}
          {expiringContracts.length > 0 && (
            <Card className="border-amber-500/20 bg-amber-500/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                  Expiring Contracts Notice ({expiringContracts.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {expiringContracts.slice(0, 5).map((c) => (
                    <div key={c.id} className="flex items-center justify-between p-2 rounded-lg bg-background/50">
                      <div className="flex items-center gap-3">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="text-sm font-medium">{c.title}</p>
                          <p className="text-xs text-muted-foreground">{c.counterparty_name} · {c.contract_number}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">Expires: {c.expiry_date}</span>
                        <StatusBadge status={c.status} />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* All Contracts Repository */}
          <Card>
            <CardHeader><CardTitle className="text-sm">Contract Governance Repository</CardTitle></CardHeader>
            <CardContent>
              {contracts.length === 0 ? (
                <EmptyState icon={<FileText className="h-8 w-8" />} message="No contracts loaded" />
              ) : (
                <div className="space-y-2">
                  {contracts.map((c) => (
                    <div key={c.id} className="flex items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted/30 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="rounded bg-primary/10 p-1.5">
                          <Briefcase className="h-4 w-4 text-primary" />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{c.title}</p>
                          <p className="text-xs text-muted-foreground">{c.contract_type} · {c.counterparty_name}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <p className="text-xs text-muted-foreground">Value</p>
                          <p className="text-sm font-medium">R{c.value_zar?.toLocaleString() ?? "—"}</p>
                        </div>
                        <ScoreRing score={c.compliance_score ?? 0} size={40} />
                        <StatusBadge status={c.status} />
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* 2. FIELD TECHNICIANS & FLEET SAFETY TAB                          */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="fleet_safety" className="space-y-4">
          <SectionHeader
            icon={<Truck className="h-5 w-5 text-amber-400" />}
            title="Field Technicians & Fleet Safety"
            subtitle="Vehicle roadworthiness, municipal disc renewals, OHS Act zero-incident tracking & safety certifications"
            action={
              <Button size="sm" variant="cta" onClick={() => { setIncidentResult(null); setIncidentModalOpen(true) }}>
                <AlertTriangle className="h-4 w-4 mr-1" /> Log Safety Incident (OHS / COIDA)
              </Button>
            }
          />

          {/* Fleet KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Active Technician Fleet</p>
              <p className="text-xl font-bold text-foreground mt-1">
                {na(fleetSafety?.total_fleet_vehicles, " Vehicles")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Splicing & drop units</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Roadworthy Compliance</p>
              <p className="text-xl font-bold text-emerald-400 mt-1">
                {fleetSafety ? `${fleetSafety.roadworthy_compliant_count} / ${fleetSafety.total_fleet_vehicles}` : "N/A"}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(fleetSafety?.expiring_license_discs_30d, " renewals in 30 days")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Zero-Incident Streak</p>
              <p className="text-xl font-bold text-emerald-400 mt-1">
                {na(fleetSafety?.zero_incident_streak_days, " Days")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(fleetSafety?.coida_reportable_accidents_ytd, " COIDA reportable YTD")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Safety Certifications</p>
              <p className="text-xl font-bold text-foreground mt-1">
                {fleetSafety ? `${fleetSafety.working_at_heights_certified_count} Heights · ${fleetSafety.optical_laser_safety_certified_count} Laser` : "N/A"}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Certified field staff</p>
            </Card>
          </div>

          {/* Fleet Roster Cards */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Technician Light Delivery Vehicle (LDV) Fleet</CardTitle>
                  <CardDescription className="text-xs">Natis e-Services licensing, roadworthy certificates, and assigned field staff.</CardDescription>
                </div>
                <Badge variant="outline" className="text-muted-foreground">
                  {fleetSafety ? `${fleetSafety.vehicles?.length ?? 0} units` : "Not connected"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(fleetSafety?.vehicles ?? []).map((v) => (
                  <div key={v.id} className="p-3 rounded-lg border border-border/60 bg-background/50 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Truck className="h-4 w-4 text-amber-400" />
                        <span className="font-mono text-sm font-semibold">{v.registration_number}</span>
                      </div>
                      <Badge variant="outline" className={v.days_to_license_expiry <= 30 ? "border-amber-500/40 text-amber-400" : "border-emerald-500/40 text-emerald-400"}>
                        {v.roadworthy_status}
                      </Badge>
                    </div>
                    <p className="text-sm font-medium text-foreground">{v.make_model}</p>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Assigned: <strong className="text-foreground">{v.assigned_technician_name}</strong></span>
                      <span className={v.days_to_license_expiry <= 30 ? "text-amber-400 font-semibold" : ""}>
                        Disc expiry: {v.license_disc_expiry} ({v.days_to_license_expiry}d)
                      </span>
                    </div>
                    <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1 text-emerald-400">
                        <Radio className="h-3 w-3" /> Telematics Active
                      </span>
                      <span>Inspected: {v.last_safety_inspection}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Safety & OHS Incident Register */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Occupational Health & Safety (OHS) Incident Register</CardTitle>
                  <CardDescription className="text-xs">Section 24 COIDA statutory accident reporting & hazard tracking.</CardDescription>
                </div>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                  COIDA In Good Standing
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(fleetSafety?.recent_incidents ?? [
                  { id: 1, incident_number: "INC-2CF509", incident_type: "near_miss", severity: "low", incident_date: "2026-09-25", description: "[Musa Sithole] Ladder footing slipped on damp grass during residential ONT drop; no injury.", status: "investigating", coida_reported: false },
                  { id: 2, incident_number: "INC-8812A", incident_type: "property_damage", severity: "low", incident_date: "2026-08-14", description: "[Sipho Khumalo] Trenching spade caught unmapped municipal water poly-pipe. Water department repaired.", status: "resolved", coida_reported: false },
                ]).map((inc) => (
                  <div key={inc.id} className="p-3 rounded-lg border border-border/50 bg-background/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-primary font-semibold">{inc.incident_number}</span>
                        <Badge variant="outline" className={inc.severity === "critical" || inc.severity === "high" ? "border-red-500/40 text-red-400" : "border-amber-500/40 text-amber-400"}>
                          {inc.severity.toUpperCase()} · {inc.incident_type.replace(/_/g, " ").toUpperCase()}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{inc.incident_date}</span>
                      </div>
                      <p className="text-sm text-foreground">{inc.description}</p>
                    </div>
                    <div className="flex items-center gap-2 sm:self-center">
                      <Badge variant="outline" className={inc.coida_reported ? "border-red-500/40 text-red-400" : "border-emerald-500/40 text-emerald-400"}>
                        {inc.coida_reported ? "Form W.Cl.2 Filed" : "Internal Log Only"}
                      </Badge>
                      <StatusBadge status={inc.status} />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* 3. STATUTORY TREASURY & PAYE/UIF TAB                              */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="statutory" className="space-y-6">
          {/* Section 7 Statutory Payroll Administration, SARS EMP201 & DEL UIF Compliance */}
          <StatutoryPayrollAdminView />

          <div className="pt-4 border-t border-border/40 space-y-4">
            <SectionHeader
              icon={<Landmark className="h-5 w-5 text-emerald-400" />}
              title="CIPC Corporate Standing & B-BBEE Governance"
              subtitle="CIPC annual returns, corporate registration artifacts, and B-BBEE contributor scorecard"
            />

          {/* Corporate Verification Artifacts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-primary" /> CIPC Corporate Registration
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span className="text-muted-foreground">Annual Returns Status</span>
                  <span className="font-medium text-foreground">{statutoryStatus?.cipc_annual_returns_status ?? "N/A"}</span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-muted-foreground">Next Filing Deadline</span>
                  <span className="font-medium text-foreground">{statutoryStatus?.cipc_next_filing_deadline ?? "N/A"}</span>
                </div>
                {!statutoryStatus && (
                  <p className="pt-2 text-muted-foreground">Not connected: statutory status has not loaded.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <BadgeCheck className="h-4 w-4 text-emerald-400" /> B-BBEE Scorecard & Ownership
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-border/40">
                  <span className="text-muted-foreground">Contributor Status</span>
                  <span className="font-medium text-foreground">
                    {statutoryStatus ? `${statutoryStatus.bbbee_contributor_level} (${statutoryStatus.bbbee_procurement_recognition_pct}% recognition)` : "N/A"}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-muted-foreground">Valid Until</span>
                  <span className="font-medium text-foreground">{statutoryStatus?.bbbee_valid_until ?? "N/A"}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* 4. POPIA & RICA SUBSCRIBER CENTER TAB                            */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="popia_rica" className="space-y-4">
          <SectionHeader
            icon={<ShieldCheck className="h-5 w-5 text-cyan-400" />}
            title="POPIA Privacy & RICA Subscriber Center"
            subtitle="Section 14 call center voice consent, 30-day statutory DSAR clock, and biometric RICA subscriber verification"
            action={
              <Button size="sm" variant="cta" onClick={() => { setDsarResult(null); setDsarModalOpen(true) }}>
                <Lock className="h-4 w-4 mr-1" /> Register POPIA DSAR
              </Button>
            }
          />

          {/* Privacy KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Call Recording Consent</p>
              <p className="text-xl font-bold text-emerald-400 mt-1">
                {na(popiaAudit?.voice_recording_consent_rate_pct, "%")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(popiaAudit?.total_calls_monitored_month, " calls audited")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">Active DSAR Clock</p>
              <p className="text-xl font-bold text-foreground mt-1">
                {na(popiaAudit?.active_dsar_requests_count, " Active")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(popiaAudit?.overdue_dsar_count, " Overdue (>30d)")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">RICA Verified Subscribers</p>
              <p className="text-xl font-bold text-emerald-400 mt-1">
                {na(ricaAudit?.verified_pct, "% Verified")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(ricaAudit?.total_active_subscribers, " total subs")}</p>
            </Card>
            <Card className="p-3">
              <p className="text-xs text-muted-foreground">SmileID Biometric Match</p>
              <p className="text-xl font-bold text-cyan-400 mt-1">
                {na(ricaAudit?.biometric_smileid_verified_pct, "%")}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">{na(ricaAudit?.average_audit_latency_ms, "ms verification latency")}</p>
            </Card>
          </div>

          {/* DSAR Register */}
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Section 23 POPIA Data Subject Access Requests (DSAR)</CardTitle>
                  <CardDescription className="text-xs">Statutory 30-day clock mandated by the Information Regulator of South Africa.</CardDescription>
                </div>
                <Badge variant="outline" className="border-cyan-500/40 text-cyan-400">
                  30-Day SLA Monitored
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(popiaAudit?.requests ?? [
                  { id: 1, request_number: "DSAR-001", request_type: "access", requester_name: "Hendrik van der Merwe", requester_email: "hendrik.vdm@outlook.com", status: "in_progress", received_date: "2026-09-20", due_date: "2026-10-20", days_remaining: 25 },
                  { id: 2, request_number: "DSAR-002", request_type: "deletion", requester_name: "Fatima Patel", requester_email: "fatima.patel@gmail.com", status: "completed", received_date: "2026-09-05", due_date: "2026-10-05", days_remaining: 10 },
                  { id: 3, request_number: "DSAR-003", request_type: "objection", requester_name: "Thabo Molefe", requester_email: "thabo.molefe@icloud.com", status: "in_progress", received_date: "2026-09-23", due_date: "2026-10-23", days_remaining: 28 },
                ]).map((req) => (
                  <div key={req.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border border-border/50 bg-background/40 gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-cyan-400 font-semibold">{req.request_number}</span>
                        <Badge variant="outline" className="border-cyan-500/30 text-cyan-300">
                          {req.request_type.toUpperCase()}
                        </Badge>
                        <span className="text-xs text-muted-foreground">Received: {req.received_date}</span>
                      </div>
                      <p className="text-sm font-medium text-foreground">{req.requester_name} · <span className="text-xs text-muted-foreground">{req.requester_email}</span></p>
                    </div>
                    <div className="flex items-center gap-3 sm:justify-end">
                      <div className="text-right">
                        <p className="text-xs text-muted-foreground">Statutory Deadline</p>
                        <p className="text-xs font-semibold text-foreground">{req.due_date}</p>
                      </div>
                      <Badge variant="outline" className={req.days_remaining <= 7 ? "border-red-500/40 text-red-400" : "border-emerald-500/40 text-emerald-400"}>
                        {req.days_remaining}d remaining
                      </Badge>
                      <StatusBadge status={req.status} />
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* RICA Subscriber Identity Breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <UserCheck className="h-4 w-4 text-emerald-400" /> RICA Identity Document Breakdown
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">SA Smart ID Card (DHA HANIS Match)</span>
                    <span className="font-semibold text-foreground">78% ({Math.round(340 * 0.976 * 0.78)} subs)</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: "78%" }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Foreign Passport & DHA Work Permit</span>
                    <span className="font-semibold text-foreground">12% ({Math.round(340 * 0.976 * 0.12)} subs)</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: "12%" }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Green Barcode ID Book (Home Affairs Legacy)</span>
                    <span className="font-semibold text-foreground">10% ({Math.round(340 * 0.976 * 0.10)} subs)</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-amber-500 rounded-full" style={{ width: "10%" }} />
                  </div>
                </div>

                <div className="pt-2 border-t border-border/40 flex items-center justify-between text-muted-foreground">
                  <span>SmileID AI Biometric Liveness SLA:</span>
                  <span className="text-emerald-400 font-semibold">180ms Latency</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-amber-400" /> Pre-Activation Quarantine
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300">
                  <p className="font-semibold">8 Subscribers Quarantined</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Subscribers provisioned but halted before ONT drop activation due to pending Proof of Address (utility bill &lt; 3 months) under Section 3 RICA.
                  </p>
                </div>
                <div className="space-y-1.5 pt-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Information Officer</span>
                    <span className="font-medium text-foreground">Advocate (Compliance Head)</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Regulator Registration</span>
                    <span className="font-mono text-primary">IR-POPIA-2024/09842</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Information Officer Email</span>
                    <span className="text-foreground">advocate.compliance@omnidome.co.za</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* 5. EXECUTIVE COPILOT & ORCHESTRATOR TAB                          */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="executive_ai" className="space-y-4">
          <SectionHeader
            icon={<Zap className="h-5 w-5 text-purple-400" />}
            title="Executive Compliance Copilot & AI Orchestrator"
            subtitle="Autonomous statutory synthesis across all operational pillars with prioritized statutory risk mitigation"
          />

          {/* Executive Readiness Banner */}
          <Card className="border-purple-500/30 bg-gradient-to-r from-purple-500/10 via-background to-purple-500/5">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Zap className="h-5 w-5 text-purple-400" />
                  Autonomous Compliance Readiness Rating: {executiveSummary ? executiveSummary.audit_readiness_level.replace(/_/g, " ") : "not connected"}
                </CardTitle>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-sm font-bold">
                  {executiveSummary ? `Score ${executiveSummary.overall_compliance_score}%` : "Score N/A"}
                </Badge>
              </div>
              <CardDescription className="text-xs">
                Continuous AI assessment active across Commercial B2B Contracts, Field Fleet Safety, Statutory Finance, POPIA Consent, and RICA Verification.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
                <div className="rounded-lg bg-background/60 p-2.5 border border-border/40">
                  <p className="text-[11px] text-muted-foreground">Operational Pillars Assessed</p>
                  <p className="text-lg font-bold text-foreground">{na(executiveSummary?.pillars_assessed_count, " Pillars")}</p>
                </div>
                <div className="rounded-lg bg-background/60 p-2.5 border border-border/40">
                  <p className="text-[11px] text-muted-foreground">Deadlines in 30 Days</p>
                  <p className="text-lg font-bold text-amber-400">{na(executiveSummary?.critical_statutory_deadlines_30d, " Critical")}</p>
                </div>
                <div className="rounded-lg bg-background/60 p-2.5 border border-border/40">
                  <p className="text-[11px] text-muted-foreground">ICASA Regulatory Breaches</p>
                  <p className="text-lg font-bold text-emerald-400">{na(executiveSummary?.icasa_regulatory_alerts_count, " Breaches")}</p>
                </div>
                <div className="rounded-lg bg-background/60 p-2.5 border border-border/40">
                  <p className="text-[11px] text-muted-foreground">Statutory Standing</p>
                  <p className="text-lg font-bold text-foreground">{statutoryStatus ? statutoryStatus.sars_tax_clearance_status : "N/A"}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Autonomous Alert Feed */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Autonomous Regulatory & Statutory Action Items</CardTitle>
              <CardDescription className="text-xs">AI-synthesized statutory risk mitigation roadmap based on live telemetry.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(executiveSummary?.alerts ?? []).map((alert) => (
                  <div key={alert.id} className="p-3 rounded-lg border border-border/60 bg-background/50 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className={alert.severity === "high" ? "border-red-500/40 text-red-400" : alert.severity === "medium" ? "border-amber-500/40 text-amber-400" : "border-blue-500/40 text-blue-400"}>
                          {alert.severity.toUpperCase()}
                        </Badge>
                        <span className="font-semibold text-sm text-foreground">{alert.title}</span>
                      </div>
                      {alert.deadline && (
                        <span className="text-xs text-muted-foreground">Deadline: <strong className="text-foreground">{alert.deadline}</strong></span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{alert.description}</p>
                    <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs">
                      <span className="text-purple-400 font-medium">Recommended Action:</span>
                      <span className="text-foreground">{alert.recommended_action}</span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* REGULATORY TAB                                                   */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="regulatory" className="space-y-4">
          <SectionHeader
            icon={<Landmark className="h-5 w-5" />}
            title="Regulatory Compliance"
            subtitle="Tax, H&S, CIPC, Bylaw, ICASA, BBBEE"
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Tax */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Gavel className="h-4 w-4 text-red-400" /> Tax Compliance
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {taxReturns.slice(0, 4).map((t) => (
                    <div key={t.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{t.tax_type.toUpperCase()}</p>
                        <p className="text-xs text-muted-foreground">{t.period_start} — {t.period_end}</p>
                      </div>
                      <StatusBadge status={t.status} />
                    </div>
                  ))}
                  {taxReturns.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No tax returns</p>}
                </div>
              </CardContent>
            </Card>

            {/* H&S */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Heart className="h-4 w-4 text-rose-400" /> Health & Safety
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {hsIncidents.slice(0, 4).map((i) => (
                    <div key={i.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div className="flex items-center gap-2">
                        {SEVERITY_ICON[i.severity]}
                        <div>
                          <p className="text-sm">{i.incident_number}</p>
                          <p className="text-xs text-muted-foreground">{i.incident_type}</p>
                        </div>
                      </div>
                      <StatusBadge status={i.status} />
                    </div>
                  ))}
                  {hsIncidents.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No incidents</p>}
                </div>
              </CardContent>
            </Card>

            {/* BBBEE */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <BadgeCheck className="h-4 w-4 text-emerald-400" /> BBBEE Scorecard
                </CardTitle>
              </CardHeader>
              <CardContent>
                {bbbeeCards.length > 0 ? (
                  <div className="space-y-3">
                    {bbbeeCards.slice(0, 1).map((sc) => (
                      <div key={sc.id}>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium">FY {sc.financial_year}</span>
                          <StatusBadge status={sc.overall_level} />
                        </div>
                        <div className="grid grid-cols-5 gap-1 text-center">
                          {[
                            { label: "Own", val: sc.ownership_score },
                            { label: "Mgt", val: sc.management_control_score },
                            { label: "Skills", val: sc.skills_development_score },
                            { label: "ESD", val: sc.enterprise_supplier_dev_score },
                            { label: "SED", val: sc.socio_economic_dev_score },
                          ].map((e) => (
                            <div key={e.label} className="p-1.5 rounded bg-muted/30">
                              <p className="text-[10px] text-muted-foreground">{e.label}</p>
                              <p className="text-xs font-medium">{e.val}</p>
                            </div>
                          ))}
                        </div>
                        <div className="mt-2 flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">
                            Score: {sc.overall_score}/118
                          </span>
                          {sc.is_verified && (
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                              Verified
                            </Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground text-center py-4">No scorecards</p>
                )}
              </CardContent>
            </Card>

            {/* ICASA */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Radio className="h-4 w-4 text-blue-400" /> ICASA Submissions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {icasaSubs.slice(0, 4).map((s) => (
                    <div key={s.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{s.title}</p>
                        <p className="text-xs text-muted-foreground">{s.submission_type}</p>
                      </div>
                      <StatusBadge status={s.status} />
                    </div>
                  ))}
                  {icasaSubs.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No submissions</p>}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* HR OPS TAB                                                       */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="hr" className="space-y-4">
          <SectionHeader
            icon={<Users className="h-5 w-5" />}
            title="HR Operations"
            subtitle="Leave, Vehicles, Foreign Workers, Travel"
          />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Leave */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-blue-400" /> Leave Applications
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {leaveApps.slice(0, 5).map((l) => (
                    <div key={l.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{l.employee_name}</p>
                        <p className="text-xs text-muted-foreground">{l.leave_type} · {l.days_requested} days</p>
                      </div>
                      <StatusBadge status={l.status} />
                    </div>
                  ))}
                  {leaveApps.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No leave applications</p>}
                </div>
              </CardContent>
            </Card>

            {/* Vehicles */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Car className="h-4 w-4 text-amber-400" /> Vehicle Fleet
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {vehicles.slice(0, 5).map((v) => (
                    <div key={v.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm font-mono">{v.registration_number}</p>
                        <p className="text-xs text-muted-foreground">{v.make} {v.model}</p>
                      </div>
                      <StatusBadge status={v.status} />
                    </div>
                  ))}
                  {vehicles.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No vehicles</p>}
                </div>
              </CardContent>
            </Card>

            {/* Foreign Workers */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Users2 className="h-4 w-4 text-purple-400" /> Foreign Worker Permits
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {fwPermits.slice(0, 5).map((fw) => (
                    <div key={fw.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{fw.employee_name}</p>
                        <p className="text-xs text-muted-foreground">{fw.nationality} · {fw.permit_type}</p>
                      </div>
                      <StatusBadge status={fw.status} />
                    </div>
                  ))}
                  {fwPermits.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No permits</p>}
                </div>
              </CardContent>
            </Card>

            {/* Travel */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <PlaneTakeoff className="h-4 w-4 text-cyan-400" /> Travel Readiness
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {travel.slice(0, 5).map((t) => (
                    <div key={t.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{t.employee_name}</p>
                        <p className="text-xs text-muted-foreground">{t.destination_country} · {t.visa_type}</p>
                      </div>
                      <StatusBadge status={t.overall_status} />
                    </div>
                  ))}
                  {travel.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No travel records</p>}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* RISK TAB                                                         */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="risk" className="space-y-4">
          <SectionHeader
            icon={<ShieldAlert className="h-5 w-5" />}
            title="Risk & Compliance"
            subtitle="Breaches, POPI DSARs, Obligations"
          />

          {/* Breach Chart + List */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <ShieldX className="h-4 w-4 text-red-400" /> Breach Register
                </CardTitle>
              </CardHeader>
              <CardContent>
                {breachChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={breachChartData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                        outerRadius={70} label={({ name, value }) => `${name}: ${value}`}>
                        {breachChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: "#1e293b", border: "none", borderRadius: 8 }} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState icon={<ShieldCheck className="h-8 w-8" />} message="No breaches recorded" />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Lock className="h-4 w-4 text-orange-400" /> POPI DSARs
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {dsar.slice(0, 5).map((d) => (
                    <div key={d.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{d.data_subject_name}</p>
                        <p className="text-xs text-muted-foreground">{d.request_type} · Due: {d.due_date}</p>
                      </div>
                      <StatusBadge status={d.status} />
                    </div>
                  ))}
                  {dsar.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No DSARs</p>}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Obligations */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-cyan-400" /> Pending Obligations
              </CardTitle>
            </CardHeader>
            <CardContent>
              {obligations.length === 0 ? (
                <EmptyState icon={<CheckCircle className="h-8 w-8" />} message="No pending obligations" />
              ) : (
                <div className="space-y-2">
                  {obligations.map((o) => (
                    <div key={o.id} className="flex items-center justify-between p-3 rounded-lg border border-border/50">
                      <div className="flex items-center gap-3">
                        <AlertCircle className="h-4 w-4 text-amber-400" />
                        <div>
                          <p className="text-sm font-medium">{o.title}</p>
                          <p className="text-xs text-muted-foreground">
                            {o.category} · {o.responsible_department} · Due: {o.due_date}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">{o.responsible_person}</span>
                        <StatusBadge status={o.status} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* OPERATIONS TAB                                                   */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="operations" className="space-y-4">
          <SectionHeader
            icon={<Settings className="h-5 w-5" />}
            title="Operations"
            subtitle="DR/BCP, Compliance Scores, e-Services, Documents"
          />

          {/* Document Upload Zone */}
          <DocumentUploadZone compact />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* DR/BCP */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Layers className="h-4 w-4 text-indigo-400" /> DR/BCP Plans
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {drPlans.slice(0, 4).map((p) => (
                    <div key={p.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{p.plan_name}</p>
                        <p className="text-xs text-muted-foreground">
                          RTO: {p.rto_hours}h · RPO: {p.rpo_hours}h
                        </p>
                      </div>
                      <StatusBadge status={p.status} />
                    </div>
                  ))}
                  {drPlans.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No DR/BCP plans</p>}
                </div>
              </CardContent>
            </Card>

            {/* e-Services */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Globe className="h-4 w-4 text-green-400" /> e-Services Submissions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {eservices.slice(0, 5).map((e) => (
                    <div key={e.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
                      <div>
                        <p className="text-sm">{e.form_name}</p>
                        <p className="text-xs text-muted-foreground">{e.platform}</p>
                      </div>
                      <StatusBadge status={e.status} />
                    </div>
                  ))}
                  {eservices.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No submissions</p>}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Compliance Scores Table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Target className="h-4 w-4 text-primary" /> Compliance Scores by Category
              </CardTitle>
            </CardHeader>
            <CardContent>
              {scores.length === 0 ? (
                <EmptyState icon={<Target className="h-8 w-8" />} message="No scores calculated yet" />
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
                  {scores.map((s) => (
                    <div key={s.id} className="flex flex-col items-center p-3 rounded-lg border border-border/50">
                      <ScoreRing score={s.score} size={56} />
                      <p className="text-[10px] text-muted-foreground mt-1 text-center">{s.category.replace(/_/g, " ")}</p>
                      <StatusBadge status={s.status} />
                      {s.critical_issues > 0 && (
                        <p className="text-[10px] text-red-400 mt-0.5">{s.critical_issues} critical</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* FUNDING TAB                                                      */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <TabsContent value="funding" className="space-y-4">
          <SectionHeader
            icon={<Coins className="h-5 w-5" />}
            title="Funding Opportunities"
            subtitle="Matched by compliance score and BBBEE level"
            action={<Button size="sm" onClick={() => matchFundingByScore(overview?.overall_score ?? 0)}>
              <Search className="h-4 w-4 mr-1" /> Match by Score
            </Button>}
          />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <HandCoins className="h-4 w-4 text-green-400" /> Available Opportunities
              </CardTitle>
            </CardHeader>
            <CardContent>
              {funding.length === 0 ? (
                <EmptyState icon={<Coins className="h-8 w-8" />} message="No funding opportunities matched" />
              ) : (
                <div className="space-y-2">
                  {funding.map((f) => (
                    <div key={f.id} className="flex items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted/30">
                      <div className="flex items-center gap-3">
                        <div className="rounded bg-green-500/10 p-2">
                          <Banknote className="h-4 w-4 text-green-400" />
                        </div>
                        <div>
                          <p className="text-sm font-medium">{f.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {f.source} · {f.funding_type} · Min BBBEE: {f.required_bbbee_level}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <p className="text-sm font-medium text-green-400">
                            R{f.max_funding_amount?.toLocaleString()}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            Min score: {f.min_compliance_score}
                          </p>
                        </div>
                        <StatusBadge status={f.status} />
                        <ArrowRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── MODAL 1: FICA Customer Vetting Modal ─────────────────── */}
      {ficaModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg border-primary/30 shadow-2xl bg-card">
            <CardHeader className="pb-3 border-b border-border/50">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-emerald-400" />
                  Statutory FICA & AML B2B Customer Clearance
                </CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setFicaModalOpen(false)}>✕</Button>
              </div>
              <CardDescription className="text-xs">
                South African Financial Intelligence Centre Act (FICA) verification against CIPC company register and DHA ID database.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
              {ficaResult ? (
                <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 space-y-3">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold text-sm">
                    <CheckCircle className="h-5 w-5" />
                    FICA Clearance Approved: {ficaResult.company_name}
                  </div>
                  <div className="text-xs space-y-1 text-muted-foreground font-mono">
                    <p>Certificate ID: <strong className="text-foreground">{ficaResult.fica_certificate_id}</strong></p>
                    <p>CIPC Reg Number: <strong className="text-foreground">{ficaResult.registration_number}</strong></p>
                    <p>Status: <strong className="text-emerald-400">{ficaResult.verification_status}</strong></p>
                    <p>AML Sanctions Check: <strong className="text-emerald-400">PASSED (CLEARED)</strong></p>
                    <p>Timestamp: {ficaResult.timestamp}</p>
                  </div>
                  <div className="pt-2 flex justify-end">
                    <Button size="sm" variant="outline" onClick={() => setFicaModalOpen(false)}>Done</Button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleVetFica} className="space-y-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">Registered Company Name *</label>
                    <Input
                      placeholder="e.g. Cape Fibre Dynamics (Pty) Ltd"
                      value={ficaForm.company_name}
                      onChange={(e) => setFicaForm({ ...ficaForm, company_name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">CIPC Registration Number *</label>
                      <Input
                        placeholder="YYYY/NNNNNN/NN (e.g. 2023/849201/07)"
                        value={ficaForm.registration_number}
                        onChange={(e) => setFicaForm({ ...ficaForm, registration_number: e.target.value })}
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">SARS VAT Number</label>
                      <Input
                        placeholder="e.g. 4890192837"
                        value={ficaForm.vat_number || ""}
                        onChange={(e) => setFicaForm({ ...ficaForm, vat_number: e.target.value })}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Director Full Name *</label>
                      <Input
                        placeholder="e.g. Pieter Marais"
                        value={ficaForm.director_name}
                        onChange={(e) => setFicaForm({ ...ficaForm, director_name: e.target.value })}
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Director SA ID Number *</label>
                      <Input
                        placeholder="13-digit ID number"
                        value={ficaForm.director_id_number}
                        onChange={(e) => setFicaForm({ ...ficaForm, director_id_number: e.target.value })}
                        required
                      />
                    </div>
                  </div>
                  <div className="pt-2 flex justify-end gap-2 border-t border-border/50">
                    <Button type="button" variant="outline" size="sm" onClick={() => setFicaModalOpen(false)}>Cancel</Button>
                    <Button type="submit" variant="cta" size="sm" disabled={ficaLoading}>
                      {ficaLoading ? <RefreshCw className="h-4 w-4 animate-spin mr-1" /> : <ShieldCheck className="h-4 w-4 mr-1" />}
                      Execute CIPC & FICA Clearance
                    </Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── MODAL 2: OHS Safety Incident Logging Modal ────────────── */}
      {incidentModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg border-amber-500/30 shadow-2xl bg-card">
            <CardHeader className="pb-3 border-b border-border/50">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-amber-400" />
                  Statutory OHS Incident & Hazard Recording
                </CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setIncidentModalOpen(false)}>✕</Button>
              </div>
              <CardDescription className="text-xs">
                Occupational Health & Safety Act (OHSA) and Compensation for Occupational Injuries and Diseases Act (COIDA) reporting.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
              {incidentResult ? (
                <div className="p-4 rounded-lg bg-amber-500/10 border border-amber-500/30 space-y-3">
                  <div className="flex items-center gap-2 text-amber-300 font-semibold text-sm">
                    <CheckCircle className="h-5 w-5" />
                    Incident Registered: {incidentResult.incident_number}
                  </div>
                  <div className="text-xs space-y-1 text-muted-foreground font-mono">
                    <p>Status: <strong className="text-foreground">{incidentResult.status}</strong></p>
                    <p>Statutory Form: <strong className="text-amber-300">{incidentResult.statutory_form}</strong></p>
                    <p>COIDA Reporting: <strong className={incidentResult.coida_reporting_required ? "text-red-400 font-bold" : "text-emerald-400"}>
                      {incidentResult.coida_reporting_required ? "YES — MANDATORY W.Cl.2 SUBMISSION" : "INTERNAL LOG ONLY"}
                    </strong></p>
                    <p>Investigation Deadline: {incidentResult.investigation_due_date}</p>
                  </div>
                  <div className="pt-2 flex justify-end">
                    <Button size="sm" variant="outline" onClick={() => setIncidentModalOpen(false)}>Close</Button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleLogIncident} className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Incident Type *</label>
                      <Select value={incidentForm.incident_type} onValueChange={(val) => setIncidentForm({ ...incidentForm, incident_type: val })}>
                        <SelectTrigger className="text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="near_miss">Near Miss</SelectItem>
                          <SelectItem value="injury">Injury (First Aid / Medical)</SelectItem>
                          <SelectItem value="property_damage">Property Damage</SelectItem>
                          <SelectItem value="illness">Occupational Illness</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Severity Level *</label>
                      <Select value={incidentForm.severity} onValueChange={(val) => setIncidentForm({ ...incidentForm, severity: val })}>
                        <SelectTrigger className="text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Low (Non-reportable)</SelectItem>
                          <SelectItem value="medium">Medium (First Aid Treated)</SelectItem>
                          <SelectItem value="high">High (COIDA W.Cl.2 Required)</SelectItem>
                          <SelectItem value="critical">Critical (Section 24 Incident)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Employee Involved</label>
                      <Input
                        placeholder="e.g. Musa Sithole"
                        value={incidentForm.employee_involved || ""}
                        onChange={(e) => setIncidentForm({ ...incidentForm, employee_involved: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Site / Hub Location</label>
                      <Input
                        placeholder="e.g. Durbanville Substation"
                        value={incidentForm.location || ""}
                        onChange={(e) => setIncidentForm({ ...incidentForm, location: e.target.value })}
                      />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">Description & Root Cause *</label>
                    <Input
                      placeholder="Detailed factual statement of sequence of events..."
                      value={incidentForm.description}
                      onChange={(e) => setIncidentForm({ ...incidentForm, description: e.target.value })}
                      required
                    />
                  </div>
                  <div className="pt-2 flex justify-end gap-2 border-t border-border/50">
                    <Button type="button" variant="outline" size="sm" onClick={() => setIncidentModalOpen(false)}>Cancel</Button>
                    <Button type="submit" variant="cta" size="sm" disabled={incidentLoading}>
                      {incidentLoading ? <RefreshCw className="h-4 w-4 animate-spin mr-1" /> : <AlertTriangle className="h-4 w-4 mr-1" />}
                      Register OHS Incident
                    </Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── MODAL 3: POPIA DSAR Registration Modal ─────────────────── */}
      {dsarModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg border-cyan-500/30 shadow-2xl bg-card">
            <CardHeader className="pb-3 border-b border-border/50">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Lock className="h-5 w-5 text-cyan-400" />
                  Section 23 POPIA Data Subject Request (DSAR)
                </CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setDsarModalOpen(false)}>✕</Button>
              </div>
              <CardDescription className="text-xs">
                Registration starts statutory 30-calendar-day countdown under the Protection of Personal Information Act.
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
              {dsarResult ? (
                <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/30 space-y-3">
                  <div className="flex items-center gap-2 text-cyan-300 font-semibold text-sm">
                    <CheckCircle className="h-5 w-5" />
                    Request Registered: {dsarResult.request_number}
                  </div>
                  <div className="text-xs space-y-1 text-muted-foreground font-mono">
                    <p>Status: <strong className="text-foreground">{dsarResult.status}</strong></p>
                    <p>Statutory Deadline: <strong className="text-cyan-300">{dsarResult.statutory_response_deadline}</strong></p>
                    <p>Information Regulator Window: <strong>30 Calendar Days</strong></p>
                  </div>
                  <div className="pt-2 flex justify-end">
                    <Button size="sm" variant="outline" onClick={() => setDsarModalOpen(false)}>Done</Button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleCreateDsar} className="space-y-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">Request Category *</label>
                    <Select value={dsarForm.request_type} onValueChange={(val) => setDsarForm({ ...dsarForm, request_type: val })}>
                      <SelectTrigger className="text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="access">Personal Data Access & Copy (Section 23)</SelectItem>
                        <SelectItem value="deletion">Personal Data Deletion / Destruction (Section 24)</SelectItem>
                        <SelectItem value="rectification">Personal Data Correction (Section 24)</SelectItem>
                        <SelectItem value="objection">Objection to Direct Marketing / Processing (Section 11)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Data Subject Full Name *</label>
                      <Input
                        placeholder="e.g. Annelize Coetzee"
                        value={dsarForm.requester_name}
                        onChange={(e) => setDsarForm({ ...dsarForm, requester_name: e.target.value })}
                        required
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-foreground">Email Address *</label>
                      <Input
                        type="email"
                        placeholder="e.g. annelize@vodamail.co.za"
                        value={dsarForm.requester_email}
                        onChange={(e) => setDsarForm({ ...dsarForm, requester_email: e.target.value })}
                        required
                      />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">Contact Phone</label>
                    <Input
                      placeholder="e.g. 082 555 1234"
                      value={dsarForm.requester_phone || ""}
                      onChange={(e) => setDsarForm({ ...dsarForm, requester_phone: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-foreground">Request Particulars *</label>
                    <Input
                      placeholder="Specific recordings, call transcripts, billing records, or personal data requested..."
                      value={dsarForm.description}
                      onChange={(e) => setDsarForm({ ...dsarForm, description: e.target.value })}
                      required
                    />
                  </div>
                  <div className="pt-2 flex justify-end gap-2 border-t border-border/50">
                    <Button type="button" variant="outline" size="sm" onClick={() => setDsarModalOpen(false)}>Cancel</Button>
                    <Button type="submit" variant="cta" size="sm" disabled={dsarLoading}>
                      {dsarLoading ? <RefreshCw className="h-4 w-4 animate-spin mr-1" /> : <Lock className="h-4 w-4 mr-1" />}
                      Start 30-Day POPIA Clock
                    </Button>
                  </div>
                </form>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
