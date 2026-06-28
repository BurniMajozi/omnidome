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
  type ComplianceOverview, type Contract, type BreachRegister, type ComplianceScore,
  type PopiDsar, type HsIncident, type TaxReturn, type BbbeeScorecard,
  type LeaveApplication, type VehicleRegistration, type ForeignWorkerPermit,
  type TravelReadiness, type DrBcpPlan, type ComplianceObligation,
  type EserviceSubmission, type IcasaSubmission, type FundingOpportunity,
  type DocumentUploadResult, type UrlFetchResult, type DocumentRecord,
} from "@/lib/compliance-api"
import DocumentUploadZone from "@/components/modules/document-upload-zone"

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

export default function ComplianceModule() {
  const [activeTab, setActiveTab] = useState("overview")
  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState<ComplianceOverview | null>(null)

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

  /** Returns value or null — never rejects. */
  const safe = <T,>(p: Promise<T>) => p.catch((): null => null)

  const loadOverview = useCallback(async () => {
    const data = await safe(getComplianceOverview())
    if (data) setOverview(data)
  }, [])

  const loadSection = useCallback(async (tab: string) => {
    switch (tab) {
      case "contracts": {
        const [c, ec] = await Promise.all([
          safe(listContracts({ page: 1 })),
          safe(getExpiringContracts(90)),
        ])
        setContracts(c?.items ?? [])
        setExpiringContracts(ec?.items ?? [])
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
        <TabsList className="grid w-full grid-cols-7">
          <TabsTrigger value="overview" className="gap-1.5"><Activity className="h-4 w-4" /> Overview</TabsTrigger>
          <TabsTrigger value="contracts" className="gap-1.5"><FileText className="h-4 w-4" /> Contracts</TabsTrigger>
          <TabsTrigger value="regulatory" className="gap-1.5"><Landmark className="h-4 w-4" /> Regulatory</TabsTrigger>
          <TabsTrigger value="hr" className="gap-1.5"><Users className="h-4 w-4" /> HR Ops</TabsTrigger>
          <TabsTrigger value="risk" className="gap-1.5"><ShieldAlert className="h-4 w-4" /> Risk</TabsTrigger>
          <TabsTrigger value="operations" className="gap-1.5"><Settings className="h-4 w-4" /> Operations</TabsTrigger>
          <TabsTrigger value="funding" className="gap-1.5"><Coins className="h-4 w-4" /> Funding</TabsTrigger>
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
        <TabsContent value="contracts" className="space-y-4">
          <SectionHeader
            icon={<FileText className="h-5 w-5" />}
            title="Contracts & SLAs"
            subtitle={`${contracts.length} contracts · ${expiringContracts.length} expiring within 90 days`}
            action={<Button size="sm"><Plus className="h-4 w-4 mr-1" /> New Contract</Button>}
          />

          {/* Expiring Contracts Alert */}
          {expiringContracts.length > 0 && (
            <Card className="border-amber-500/20 bg-amber-500/5">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                  Expiring Contracts ({expiringContracts.length})
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

          {/* Contract List */}
          <Card>
            <CardHeader><CardTitle className="text-sm">All Contracts</CardTitle></CardHeader>
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
    </div>
  )
}
