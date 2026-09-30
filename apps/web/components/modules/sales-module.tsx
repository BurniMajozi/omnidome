"use client"

import { corpTargetText } from "@/lib/comm-helpers"
import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import type { JSX } from "react"
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
  PieChart,
  Pie,
  Cell,
} from "recharts"
import {
  DollarSign,
  TrendingUp,
  Target,
  Users,
  User,
  Mail,
  PhoneCall,
  PhoneOutgoing,
  MapPin,
  Store,
  Plus,
  ArrowRight,
  RefreshCw,
  Sparkles,
  Bot,
  Package,
  Building2,
  Phone,
  Coins,
} from "lucide-react"
import { useLoadable } from "@/lib/service-fetch"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { truncationNote } from "@/lib/sales-derive"
import { getCorporateSalesSnapshot, type CorporateSalesSnapshot } from "@/lib/hr-api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  salesApi,
  SALES_CHANNELS,
  PRODUCT_CATALOG,
  type SalesChannel,
  type SalesLead,
  type Deal,
  type PipelineOverviewStage,
  type ProductPackage,
} from "@/lib/sales-api"
import { SalesPipelineBoard } from "./sales-pipeline-board"
import { SalesLeadSources } from "./sales-lead-sources"
import { SalesLeadsTab, SALES_CHANGED_EVENT, announceSalesChange } from "./sales-leads-tab"
import { LeadActionsMenu, LeadPanel, type LeadPanelMode } from "./sales-lead-actions"
import { LeadWarmingRules } from "./sales-lead-warming"
import { LeadFunnelView } from "./sales/lead-funnel-view"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import { SalesCommissionsView } from "./talent/sales-commissions-view"
import {
  getSalesTalentOverview,
  listSalesRepsMetrics,
  listEmployees,
  type SalesOverviewResponse,
  type SalesRepMetric,
  type Employee,
} from "@/lib/hr-api"

const salesKpiIconMap: Record<string, JSX.Element> = {
  revenue: <DollarSign className="h-5 w-5 text-emerald-400" />,
  deals: <Target className="h-5 w-5 text-blue-400" />,
  pipeline: <TrendingUp className="h-5 w-5 text-amber-400" />,
  avgDeal: <Users className="h-5 w-5 text-purple-400" />,
}

// Real figures only: nothing here has a built-in default. Before the service answers the panels show
// a loading skeleton; afterwards real data, an empty state, or Not connected / Service not running / Error + Retry.
interface SalesStats {
  flashcardKPIs: {
    id: string; title: string; value: string; change: string; changeType: "positive" | "negative" | "neutral"
    iconKey: string; backTitle: string; backDetails: { label: string; value: string }[]; backInsight: string
  }[]
  activities: { id: string; user: string; action: string; target: string; time: string; type: "create" | "update" }[]
  aiRecommendations: { id: string; title: string; description: string; impact: "high" | "medium" | "low"; category: string }[]
  summary: string
  tableData: { id: string; [key: string]: string }[]
  tableColumns: { key: string; label: string }[]
  deals?: { loaded: number; total: number; truncated: boolean }
}

const NONE: never[] = []
const LEADS_PAGE = 200

export function SalesModule() {
  // Revenue / pipeline / KPI / summary / activity / recommendations all come from the real sales
  // backend (app/api/sales-stats). Issues and Tasks have no source connected to Sales.
  const stats = useLoadable<SalesStats>("/api/sales-stats")
  const live = stats.value.state === "ready" ? stats.value.data : null

  const flashcardKPIsWithIcons = useMemo(
    () => (live ? live.flashcardKPIs.map((kpi) => ({ ...kpi, icon: salesKpiIconMap[kpi.iconKey] ?? null })) : []),
    [live],
  )
  const salesState = (empty?: string) => {
    if (live) return undefined
    return <NotConnected loadable={stats.value} service="The sales service" onRetry={stats.reload} emptyTitle={empty} />
  }
  const panelStates = {
    kpis: salesState() ?? undefined,
    activity: salesState(),
    summary: salesState(),
    recommendations: salesState(),
    issues: <NoDataYet message="Not connected: no issue tracker is linked to Sales yet." />,
    tasks: <NoDataYet message="Not connected: no task list is linked to Sales yet." />,
  }

  // ── Lead Management & Channel Sales State ─────────────────────────
  const [leads, setLeads] = useState<SalesLead[]>([])
  const [loadingLeads, setLoadingLeads] = useState(false)
  const [leadsTotal, setLeadsTotal] = useState<number | null>(null)
  const [leadsError, setLeadsError] = useState<string | null>(null)
  const [corpSales, setCorpSales] = useState<CorporateSalesSnapshot | null>(null)
  const [corpSalesLoading, setCorpSalesLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    getCorporateSalesSnapshot()
      .then((snap) => { if (!cancelled) setCorpSales(snap) })
      .catch(() => { if (!cancelled) setCorpSales(null) })
      .finally(() => { if (!cancelled) setCorpSalesLoading(false) })
    return () => { cancelled = true }
  }, [])
  const fmtCorpZar = (v: number | null | undefined) =>
    v === null || v === undefined ? "Not connected" : `R ${Math.round(v).toLocaleString("en-ZA")}`
  const [activeTab, setActiveTab] = useState<"pipeline" | "channels" | "leads" | "ai-engine" | "commissions">("pipeline")
  const [pipelineRefreshCounter, setPipelineRefreshCounter] = useState(0)

  // ── Sales Commissions State ──────────────────────────────────────────
  const [salesOverview, setSalesOverview] = useState<SalesOverviewResponse | null>(null)
  const [salesReps, setSalesReps] = useState<SalesRepMetric[]>([])
  const [salesLoading, setSalesLoading] = useState(false)
  const [salesError, setSalesError] = useState<string | null>(null)
  const [salesEmployees, setSalesEmployees] = useState<Employee[]>([])

  const fetchSalesCommissions = useCallback(async () => {
    setSalesLoading(true)
    setSalesError(null)
    try {
      const [overview, reps, emps] = await Promise.all([
        getSalesTalentOverview().catch(() => null),
        listSalesRepsMetrics().catch(() => []),
        listEmployees().catch(() => []),
      ])
      setSalesOverview(overview)
      setSalesReps(reps)
      setSalesEmployees(emps)
    } catch (err: unknown) {
      setSalesError(err instanceof Error ? err.message : String(err))
    } finally {
      setSalesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === "commissions") {
      void fetchSalesCommissions()
    }
  }, [activeTab, fetchSalesCommissions])

  // Unified Deal & Lead Modal State (includes Contact Details & Product Selection)
  const [dealModalOpen, setDealModalOpen] = useState(false)
  const [dealFirstName, setDealFirstName] = useState("")
  const [dealLastName, setDealLastName] = useState("")
  const [dealCompany, setDealCompany] = useState("")
  const [dealEmail, setDealEmail] = useState("")
  const [dealPhone, setDealPhone] = useState("")
  const [dealAddress, setDealAddress] = useState("")
  const [dealProduct, setDealProduct] = useState(PRODUCT_CATALOG[0].name)
  const [dealValue, setDealValue] = useState<string>(String(PRODUCT_CATALOG[0].price_monthly * 12))
  const [dealSource, setDealSource] = useState<SalesChannel>("WALK_IN")
  const [dealStage, setDealStage] = useState("Qualified")
  const [dealNotes, setDealNotes] = useState("")
  const [dealInterest, setDealInterest] = useState<number>(4)
  const [savingDeal, setSavingDeal] = useState(false)

  // Real leads from the sales API. No placeholder leads: an empty list shows
  // the empty state (SPEC-lead-lifecycle.md).
  const loadLeads = useCallback(async () => {
    setLoadingLeads(true)
    try {
      const page = await salesApi.listLeadsPage({ limit: LEADS_PAGE })
      setLeads(page.data)
      // Total from X-Total-Count when the service sends it; a full page without it means "maybe more".
      setLeadsTotal(page.total ?? (page.data.length >= LEADS_PAGE ? null : page.data.length))
      setLeadsError(null)
    } catch (err) {
      // Keep the current list, but say the refresh failed.
      setLeadsError(err instanceof Error ? err.message : "Could not load leads")
    } finally {
      setLoadingLeads(false)
    }
  }, [])

  const updateLeadInList = useCallback((updated: SalesLead) => {
    setLeads((prev) => {
      const exists = prev.some((l) => l.id === updated.id)
      return exists ? prev.map((l) => (l.id === updated.id ? { ...l, ...updated } : l)) : [updated, ...prev]
    })
  }, [])

  // Lead table, Lead sources and the board announce changes; refresh the view
  // that is stale when the user switches to it (no polling, no double loads).
  const staleRef = useRef({ leads: false, board: false })
  useEffect(() => {
    const onChange = () => {
      staleRef.current = { leads: true, board: true }
    }
    window.addEventListener(SALES_CHANGED_EVENT, onChange)
    return () => window.removeEventListener(SALES_CHANGED_EVENT, onChange)
  }, [])

  // Lead action menu + record panel (SPEC-lead-actions.md); the bell opens
  // records through the "omnidome:open-lead" event.
  const [menuLeadId, setMenuLeadId] = useState<string | null>(null)
  const [leadPanel, setLeadPanel] = useState<{ id: string; mode: LeadPanelMode } | null>(null)
  useEffect(() => {
    const onOpen = (e: Event) => {
      const id = (e as CustomEvent<{ id?: string }>).detail?.id
      if (id) setLeadPanel({ id, mode: "record" })
    }
    window.addEventListener("omnidome:open-lead", onOpen)
    return () => window.removeEventListener("omnidome:open-lead", onOpen)
  }, [])

  const switchTab = (tab: "pipeline" | "channels" | "leads" | "ai-engine" | "commissions") => {
    if (tab === "leads" && staleRef.current.leads) {
      staleRef.current.leads = false
      void loadLeads()
    }
    if (tab === "pipeline" && staleRef.current.board) {
      staleRef.current.board = false
      setPipelineRefreshCounter((c) => c + 1)
    }
    setActiveTab(tab)
  }

  useEffect(() => {
    void loadLeads()
  }, [loadLeads])

  // Handle Unified Deal & Lead Submission (Captures Contact Details & Product)
  const handleCreateUnifiedDealAndLead = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!dealFirstName.trim() || !dealLastName.trim()) return
    setSavingDeal(true)

    try {
      const fullName = `${dealFirstName.trim()} ${dealLastName.trim()}`
      const dealTitle = dealCompany.trim()
        ? `${dealCompany.trim()} - ${dealProduct}`
        : `${fullName} - ${dealProduct}`

      const metaNotes = `Contact: ${fullName}${dealEmail.trim() ? ` | Email: ${dealEmail.trim()}` : ""}${
        dealPhone.trim() ? ` | Phone: ${dealPhone.trim()}` : ""
      }${dealCompany.trim() ? ` | Company: ${dealCompany.trim()}` : ""} | Product: ${dealProduct} | Channel: ${dealSource}${
        dealNotes.trim() ? `\n${dealNotes.trim()}` : ""
      }`

      // One lead + its deal on the board, linked, in one request
      // (it used to create an unrelated deal and lead).
      const created = await salesApi.createLead({
        first_name: dealFirstName.trim(),
        last_name: dealLastName.trim(),
        email: dealEmail.trim() || undefined,
        phone: dealPhone.trim() || undefined,
        address: dealAddress.trim() || undefined,
        source: dealSource,
        interest_level: dealInterest,
        notes: metaNotes,
        pipeline: { stage_name: dealStage, value_zar: Number(dealValue) || 0, deal_name: dealTitle },
      })
      updateLeadInList(created)
      announceSalesChange()
      setPipelineRefreshCounter((c) => c + 1)
      setDealModalOpen(false)

      // Reset form
      setDealFirstName("")
      setDealLastName("")
      setDealCompany("")
      setDealEmail("")
      setDealPhone("")
      setDealAddress("")
      setDealNotes("")
      alert(`${created.reference ?? "Lead"} "${dealTitle}" is on the Pipeline Board (${created.deal_stage ?? dealStage}).`)
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to record deal")
    } finally {
      setSavingDeal(false)
    }
  }


  return (
    <ModuleLayout
      title="Sales & Lead Management"
      icon={<Target className="h-5 w-5 text-blue-400" />}
      subtitle="Omnichannel sales capture (Walk-in, Website Portal, Inbound Email, Call Center, Field Sales), pipeline stages, and deal velocity"
      flashcardKPIs={flashcardKPIsWithIcons}
      activities={live?.activities ?? NONE}
      issues={NONE}
      summary={live?.summary ?? ""}
      tasks={NONE}
      aiRecommendations={live?.aiRecommendations ?? NONE}
      tableData={live?.tableData ?? NONE}
      tableColumns={live?.tableColumns ?? NONE}
      panelStates={panelStates}
      showTable={false} // Eliminates redundant bottom table, duplicate Export CSV, and broken + Add Record button!
      headerActions={
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setDealModalOpen(true)}
            className="h-8 gap-1.5 bg-primary text-primary-foreground text-xs shadow-sm font-semibold"
          >
            <Plus className="h-3.5 w-3.5" />
            + Create Deal / Lead
          </Button>
        </div>
      }
    >
      {/* ── Section Navigation Tabs ── */}
      <div className="flex items-center justify-between gap-4 border-b border-border pb-3">
        <Tabs value={activeTab} onValueChange={(v) => switchTab(v as typeof activeTab)} className="w-full">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <TabsList className="bg-muted/60 p-1">
              <TabsTrigger value="pipeline" className="text-xs font-semibold gap-1.5">
                <Target className="h-3.5 w-3.5 text-blue-400" />
                Pipeline Board
              </TabsTrigger>
              <TabsTrigger value="channels" className="text-xs font-semibold gap-1.5">
                <BarChart className="h-3.5 w-3.5 text-emerald-400" />
                Lead Funnel by Channel
              </TabsTrigger>
              <TabsTrigger value="leads" className="text-xs font-semibold gap-1.5">
                <Users className="h-3.5 w-3.5 text-purple-400" />
                Lead Stage Management ({leads.length})
              </TabsTrigger>
              <TabsTrigger
                value="ai-engine"
                className="text-xs font-semibold gap-1.5 bg-primary/10 text-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                <Sparkles className="h-3.5 w-3.5" />
                AI Lead Warming & Automations
              </TabsTrigger>
              <TabsTrigger
                value="commissions"
                className="text-xs font-semibold gap-1.5"
              >
                <Coins className="h-3.5 w-3.5 text-amber-400" />
                Sales & Commissions
              </TabsTrigger>
            </TabsList>

            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { void loadLeads(); stats.reload() }}
                className="h-8 text-xs text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="h-3 w-3 mr-1" />
                Refresh Data
              </Button>
            </div>
          </div>
        </Tabs>
      </div>

      {/* ── Corporate Sales KPI vs Budget Alignment Tile ── */}
      <div className="surface-card p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 mb-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 shrink-0">
              <Target className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-foreground">Sales Performance vs Corporate Budget Target</h4>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-[10px]">
                  {corpSalesLoading
                    ? "Loading..."
                    : corpSales?.achievementPct != null
                      ? `${corpSales.achievementPct.toFixed(1)}% of Budget`
                      : "Not connected"}
                </Badge>
                <Badge variant="outline" className="border-primary/40 text-primary text-[10px]">
                  Shared Corporate KPI
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Current Sales: <b className="text-foreground">{corpSalesLoading ? "Loading..." : fmtCorpZar(corpSales?.actual)}</b> • Target Budget: <b className="text-foreground">{corpSalesLoading ? "Loading..." : (corpTargetText(corpSales, fmtCorpZar) ?? "No target set")}</b> • Contributes to 60% of Exec / 20–40% of Staff Annual KPI Review
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="hidden sm:block text-right">
              <span className="text-[11px] text-muted-foreground">Variance to Budget</span>
              <p className={`text-xs font-bold ${corpSales?.varianceZar != null ? (corpSales.varianceZar >= 0 ? "text-emerald-400" : "text-amber-400") : "text-muted-foreground"}`}>
                {corpSalesLoading
                  ? "Loading..."
                  : corpSales?.varianceZar != null && corpSales.achievementPct != null
                    ? `${corpSales.varianceZar < 0 ? "-" : "+"}R ${Math.abs(Math.round(corpSales.varianceZar)).toLocaleString("en-ZA")} (${(corpSales.achievementPct - 100).toFixed(1)}%)`
                    : "Not connected"}
              </p>
            </div>
            <a
              href="#talent"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-card hover:bg-muted text-xs font-semibold text-foreground transition-all shadow-xs"
            >
              <span>Performance & Objectives</span>
              <ArrowRight className="h-3.5 w-3.5 text-primary" />
            </a>
          </div>
        </div>
      </div>

      {/* ── TAB 1: Visual Pipeline Board ── */}
      {activeTab === "pipeline" && (
        <div className="space-y-6">
          <div className="surface-card p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  <Target className="h-5 w-5 text-blue-400" />
                  Visual Deal Pipeline Board
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Adjustable deal stages · Drag & drop cards · Contact details & Product packages attached to every opportunity
                </p>
              </div>
            </div>
            <SalesPipelineBoard
              onOpenCreateModal={() => setDealModalOpen(true)}
              refreshTrigger={pipelineRefreshCounter}
            />
          </div>
        </div>
      )}

      {/* ── TAB 2: Lead Funnel by Channel & Attribution ── */}
      {activeTab === "channels" && (
        <ErrorBoundary fallbackTitle="Lead Funnel by Channel encountered an issue">
          <LeadFunnelView
            onNavigateToLeads={(channel, stage) => {
              setActiveTab("leads")
            }}
          />
        </ErrorBoundary>
      )}

      {/* ── TAB 3: Lead Stage Management (SPEC-lead-lifecycle.md) ── */}
      {activeTab === "leads" && leadsError && (
        <div role="alert" className="mb-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Could not refresh leads: {leadsError}
        </div>
      )}
      {activeTab === "leads" && (truncationNote(leads.length, leadsTotal) || (leadsTotal === null && leads.length >= LEADS_PAGE)) && (
        <p className="mb-2 text-xs text-amber-400">
          {truncationNote(leads.length, leadsTotal) ?? `Showing the latest ${leads.length} leads; there may be more.`}
        </p>
      )}
      {activeTab === "leads" && (
        <SalesLeadsTab
          leads={leads}
          loading={loadingLeads}
          onReload={() => void loadLeads()}
          onLeadUpdated={updateLeadInList}
          onOpenLead={(lead) => setLeadPanel({ id: lead.id, mode: "record" })}
          onRowContextMenu={(lead) => setMenuLeadId(lead.id)}
          renderActions={(lead) => (
            <LeadActionsMenu
              lead={lead}
              open={menuLeadId === lead.id}
              onOpenChange={(open) => setMenuLeadId(open ? lead.id : null)}
              onAction={(mode) => {
                setMenuLeadId(null)
                setLeadPanel({ id: lead.id, mode })
              }}
            />
          )}
        />
      )}
      {leadPanel && (
        <LeadPanel
          key={`${leadPanel.id}:${leadPanel.mode}`}
          leadId={leadPanel.id}
          initialMode={leadPanel.mode}
          onClose={() => setLeadPanel(null)}
          onUpdated={updateLeadInList}
        />
      )}

      {/* ── TAB 4: AI Lead Warming & Digital Channel Automation ── */}
      {activeTab === "ai-engine" && (
        <div className="space-y-6">
          {/* Architecture Explainer Card */}
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-5">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-primary/20 text-primary shrink-0 mt-0.5">
                <Bot className="h-6 w-6" />
              </div>
              <div className="space-y-2">
                <h3 className="text-base font-bold text-foreground">
                  Automating Lead Stage Movement & AI Warming via Digital Channels
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  In OmniDome, digital sales channels (Online Portal, Website, Inbound Email) are connected via an
                  <strong className="text-foreground"> Event-Driven Architecture</strong>. When customer events occur (e.g. 
                  an abandoned shopping basket, quotation request, or dormant signup), the event listener triggers the 
                  <strong className="text-foreground"> Agentic Flow Orchestrator</strong>. The orchestrator automatically advances 
                  the lead stage and dispatches DomeBot AI to draft and send hyper-personalized warm-up messages.
                </p>
                <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] font-mono">
                  <span className="px-2 py-0.5 rounded bg-background border border-border text-foreground">
                    1. Digital Event Emitted
                  </span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="px-2 py-0.5 rounded bg-primary/20 border border-primary/40 text-primary font-semibold">
                    2. Auto Stage Transition
                  </span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 font-semibold">
                    3. AI Lead Warming Outreach
                  </span>
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 font-semibold">
                    4. Deal Velocity Accelerated
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Event triggers & stage rules: real orchestrator workflows (SPEC-lead-automations.md) */}
          <LeadWarmingRules />

          {/* Real lead sources: FNO passed homes → geo segments (SPEC-geo-segments.md) */}
          <SalesLeadSources />
        </div>
      )}

      {/* ── TAB 5: Sales & Commission Management ── */}
      {activeTab === "commissions" && (
        <div className="space-y-6">
          <SalesCommissionsView
            salesOverview={salesOverview}
            salesReps={salesReps}
            salesLoading={salesLoading}
            salesError={salesError}
            employees={salesEmployees}
            onRefreshSales={fetchSalesCommissions}
          />
        </div>
      )}

      {/* ── Modal: Comprehensive Unified Deal & Lead Capture ── */}
      {dealModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div>
                <h3 className="text-base font-bold text-foreground">Record Deal & Customer Lead</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Captures Customer Contact Details, Product Package, Acquisition Channel & Initial Stage
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDealModalOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateUnifiedDealAndLead} className="space-y-3.5">
              {/* Contact Details Section */}
              <div className="rounded-lg border border-border/70 bg-muted/20 p-3 space-y-2.5">
                <div className="text-[11px] font-semibold text-foreground flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5 text-primary" /> Contact Person & Details *
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground">First Name *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Sipho"
                      value={dealFirstName}
                      onChange={(e) => setDealFirstName(e.target.value)}
                      className="mt-0.5 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground">Last Name *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Khumalo"
                      value={dealLastName}
                      onChange={(e) => setDealLastName(e.target.value)}
                      className="mt-0.5 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                      <Mail className="h-3 w-3" /> Email Address
                    </label>
                    <input
                      type="email"
                      placeholder="client@domain.co.za"
                      value={dealEmail}
                      onChange={(e) => setDealEmail(e.target.value)}
                      className="mt-0.5 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                      <Phone className="h-3 w-3" /> Phone Number
                    </label>
                    <input
                      type="tel"
                      placeholder="+27 82 123 4567"
                      value={dealPhone}
                      onChange={(e) => setDealPhone(e.target.value)}
                      className="mt-0.5 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                    <Building2 className="h-3 w-3" /> Company / Organization Name (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Apex Logistics SA"
                    value={dealCompany}
                    onChange={(e) => setDealCompany(e.target.value)}
                    className="mt-0.5 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Product Selection & Acquisition Channel */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1">
                    <Package className="h-3 w-3 text-cyan-400" /> Selected Product / Package *
                  </label>
                  <select
                    value={dealProduct}
                    onChange={(e) => {
                      const prod = PRODUCT_CATALOG.find((p) => p.name === e.target.value)
                      setDealProduct(e.target.value)
                      if (prod) {
                        setDealValue(String(prod.price_monthly * 12))
                      }
                    }}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {PRODUCT_CATALOG.map((p) => (
                      <option key={p.id} value={p.name}>
                        {p.name} (R{p.price_monthly.toLocaleString()}/mo)
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground flex items-center gap-1">
                    <Store className="h-3 w-3 text-amber-400" /> Acquisition Channel *
                  </label>
                  <select
                    value={dealSource}
                    onChange={(e) => setDealSource(e.target.value as SalesChannel)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-2.5 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {SALES_CHANNELS.map((ch) => (
                      <option key={ch.id} value={ch.id}>
                        {ch.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Value & Stage */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Estimated Value (ZAR / Annual) *</label>
                  <input
                    type="number"
                    required
                    min="0"
                    step="100"
                    value={dealValue}
                    onChange={(e) => setDealValue(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground">Initial Pipeline Stage *</label>
                  <select
                    value={dealStage}
                    onChange={(e) => setDealStage(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="Prospecting">Prospecting (10%)</option>
                    <option value="Qualified">Qualified (30%)</option>
                    <option value="Proposal">Proposal (60%)</option>
                    <option value="Negotiation">Negotiation (80%)</option>
                    <option value="Closed Won">Closed Won (100%)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Premises / Delivery Address</label>
                <input
                  type="text"
                  placeholder="e.g. 15 Sandton Drive, Rosebank, Johannesburg"
                  value={dealAddress}
                  onChange={(e) => setDealAddress(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Notes / Discussion Context</label>
                <textarea
                  rows={2}
                  placeholder="Customer walk-in requirements, bandwidth speed needed, contract term..."
                  value={dealNotes}
                  onChange={(e) => setDealNotes(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setDealModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={savingDeal || !dealFirstName.trim() || !dealLastName.trim()}
                  className="bg-primary text-primary-foreground font-semibold"
                >
                  {savingDeal ? "Saving..." : "Create Deal & Lead"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ModuleLayout>
  )
}
