"use client"

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
  Globe,
  MapPin,
  Store,
  Plus,
  ArrowRight,
  RefreshCw,
  Sparkles,
  Bot,
  Zap,
  ShoppingCart,
  FileText,
  Package,
  Building2,
  Phone,
} from "lucide-react"
import { useModuleData } from "@/lib/module-data"
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

const defaultSalesData = [
  { month: "Jan", revenue: 450000, deals: 12 },
  { month: "Feb", revenue: 520000, deals: 15 },
  { month: "Mar", revenue: 480000, deals: 14 },
  { month: "Apr", revenue: 610000, deals: 18 },
  { month: "May", revenue: 580000, deals: 16 },
  { month: "Jun", revenue: 720000, deals: 21 },
]

const defaultPipelineData = [
  { name: "Prospecting", value: 45, fill: "#4ade80" },
  { name: "Negotiation", value: 35, fill: "#60a5fa" },
  { name: "Closed Won", value: 20, fill: "#a855f7" },
]

const defaultTopProducts = [
  { name: "Business Fiber", value: 42 },
  { name: "Home Broadband", value: 28 },
  { name: "VoIP Bundle", value: 18 },
  { name: "Cloud Services", value: 12 },
]

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

// Default Channel Breakdown Data
const defaultChannelSales = [
  { channel: "Marketing Campaigns", source: "MARKETING", deals: 36, revenue: 1950000, color: "#e03131", fill: "#e03131" },
  { channel: "Walk-in Customers", source: "WALK_IN", deals: 28, revenue: 1450000, color: "#38bdf8", fill: "#38bdf8" },
  { channel: "Portal & Website", source: "PORTAL_WEBSITE", deals: 42, revenue: 2180000, color: "#a78bfa", fill: "#a78bfa" },
  { channel: "Call Center Inbound", source: "CALL_CENTER_INBOUND", deals: 35, revenue: 1820000, color: "#34d399", fill: "#34d399" },
  { channel: "Field Sales Team", source: "FIELD_SALES", deals: 24, revenue: 1640000, color: "#f87171", fill: "#f87171" },
  { channel: "Inbound Email", source: "INBOUND_EMAIL", deals: 19, revenue: 980000, color: "#60a5fa", fill: "#60a5fa" },
  { channel: "Call Center Outbound", source: "CALL_CENTER_OUTBOUND", deals: 15, revenue: 720000, color: "#fbbf24", fill: "#fbbf24" },
]

const defaultFlashcardKPIs = [
  {
    id: "1",
    title: "Monthly Revenue",
    value: formatCurrency(2840000),
    change: "+18.5%",
    changeType: "positive" as const,
    iconKey: "revenue",
    backTitle: "Revenue Breakdown",
    backDetails: [
      { label: "New Business", value: formatCurrency(1420000) },
      { label: "Renewals", value: formatCurrency(980000) },
      { label: "Upsells", value: formatCurrency(440000) },
    ],
    backInsight: "New business revenue up 24% this quarter",
  },
  {
    id: "2",
    title: "Total Deals",
    value: "47",
    change: "+12.2%",
    changeType: "positive" as const,
    iconKey: "deals",
    backTitle: "Deal Analysis",
    backDetails: [
      { label: "Won", value: "32" },
      { label: "Lost", value: "8" },
      { label: "Pending", value: "7" },
    ],
    backInsight: "Win rate improved to 80% from 72%",
  },
  {
    id: "3",
    title: "Pipeline Value",
    value: formatCurrency(18000000),
    change: "+8.3%",
    changeType: "positive" as const,
    iconKey: "pipeline",
    backTitle: "Pipeline Stages",
    backDetails: [
      { label: "Prospecting", value: formatCurrency(8100000) },
      { label: "Negotiation", value: formatCurrency(6300000) },
      { label: "Closing", value: formatCurrency(3600000) },
    ],
    backInsight: "45% of pipeline in late stages",
  },
  {
    id: "4",
    title: "Avg Deal Size",
    value: formatCurrency(384000),
    change: "+5.1%",
    changeType: "positive" as const,
    iconKey: "avgDeal",
    backTitle: "Deal Size Distribution",
    backDetails: [
      { label: "Enterprise", value: formatCurrency(850000) },
      { label: "SMB", value: formatCurrency(280000) },
      { label: "Residential", value: formatCurrency(45000) },
    ],
    backInsight: "Enterprise deals growing fastest at 32%",
  },
]

const salesKpiIconMap: Record<string, JSX.Element> = {
  revenue: <DollarSign className="h-5 w-5 text-emerald-400" />,
  deals: <Target className="h-5 w-5 text-blue-400" />,
  pipeline: <TrendingUp className="h-5 w-5 text-amber-400" />,
  avgDeal: <Users className="h-5 w-5 text-purple-400" />,
}

const defaultActivities = [
  {
    id: "1",
    user: "John Smith",
    action: "closed deal with",
    target: "Telkom SA",
    time: "2 minutes ago",
    type: "create" as const,
  },
  {
    id: "2",
    user: "Sarah Jones",
    action: "updated proposal for",
    target: "MTN Group",
    time: "15 minutes ago",
    type: "update" as const,
  },
  {
    id: "3",
    user: "Mike Brown",
    action: "scheduled meeting with",
    target: "Vodacom",
    time: "1 hour ago",
    type: "create" as const,
  },
  {
    id: "4",
    user: "Lisa Chen",
    action: "sent contract to",
    target: "Dimension Data",
    time: "2 hours ago",
    type: "create" as const,
  },
  {
    id: "5",
    user: "David Wilson",
    action: "added notes to",
    target: "Cell C deal",
    time: "3 hours ago",
    type: "comment" as const,
  },
]

const defaultIssues = [
  {
    id: "1",
    title: "Quote approval delayed for MTN deal",
    severity: "high" as const,
    status: "open" as const,
    assignee: "Sarah Jones",
    time: "2 hours ago",
  },
  {
    id: "2",
    title: "Pricing discrepancy in Vodacom proposal",
    severity: "medium" as const,
    status: "in-progress" as const,
    assignee: "Mike Brown",
    time: "4 hours ago",
  },
  {
    id: "3",
    title: "Contract terms need legal review",
    severity: "high" as const,
    status: "open" as const,
    assignee: "John Smith",
    time: "Yesterday",
  },
  {
    id: "4",
    title: "Customer credit check pending",
    severity: "low" as const,
    status: "resolved" as const,
    assignee: "Lisa Chen",
    time: "2 days ago",
  },
]

const defaultSummary = `This month's sales performance shows strong growth with R2.84M in revenue, an 18.5% increase from last month. The team closed 47 deals with an average deal size of R384K. The pipeline is healthy at R18M with 45% of opportunities in late stages. Key wins include contracts with Telkom SA and Dimension Data. Focus areas for next month include improving conversion rates in the negotiation stage and expanding enterprise segment penetration.`

const defaultTasks = [
  {
    id: "1",
    title: "Follow up on MTN proposal",
    priority: "urgent" as const,
    status: "todo" as const,
    dueDate: "Today",
    assignee: "Sarah Jones",
  },
  {
    id: "2",
    title: "Prepare Q2 sales forecast",
    priority: "high" as const,
    status: "in-progress" as const,
    dueDate: "Tomorrow",
    assignee: "John Smith",
  },
  {
    id: "3",
    title: "Update CRM with new leads",
    priority: "normal" as const,
    status: "todo" as const,
    dueDate: "This week",
    assignee: "Mike Brown",
  },
  {
    id: "4",
    title: "Complete sales training module",
    priority: "low" as const,
    status: "done" as const,
    dueDate: "Completed",
    assignee: "Lisa Chen",
  },
]

const defaultAiRecommendations = [
  {
    id: "1",
    title: "Prioritize Vodacom Deal",
    description: "Based on engagement patterns, Vodacom is 85% likely to close this week. Schedule a final call.",
    impact: "high" as const,
    category: "Sales",
  },
  {
    id: "2",
    title: "Upsell Opportunity",
    description: "3 existing customers show interest in VoIP bundles based on usage patterns.",
    impact: "medium" as const,
    category: "Upsell",
  },
  {
    id: "3",
    title: "At-Risk Deal Alert",
    description: "Cell C deal has been stagnant for 2 weeks. Consider offering incentive.",
    impact: "high" as const,
    category: "Risk",
  },
  {
    id: "4",
    title: "Optimize Pricing",
    description: "Competitors reduced fiber pricing by 8%. Review pricing strategy.",
    impact: "medium" as const,
    category: "Strategy",
  },
]

const defaultTableData = [
  {
    id: "1",
    deal: "Telkom SA - Fiber Upgrade",
    value: "R 850,000",
    stage: "Closed Won",
    probability: "100%",
    closeDate: "2024-01-10",
    owner: "John Smith",
  },
  {
    id: "2",
    deal: "MTN Group - Enterprise Package",
    value: "R 1,200,000",
    stage: "Negotiation",
    probability: "75%",
    closeDate: "2024-01-20",
    owner: "Sarah Jones",
  },
  {
    id: "3",
    deal: "Vodacom - Data Center",
    value: "R 2,400,000",
    stage: "Proposal",
    probability: "60%",
    closeDate: "2024-02-01",
    owner: "Mike Brown",
  },
  {
    id: "4",
    deal: "Dimension Data - Cloud",
    value: "R 680,000",
    stage: "Closed Won",
    probability: "100%",
    closeDate: "2024-01-08",
    owner: "Lisa Chen",
  },
  {
    id: "5",
    deal: "Cell C - Network Services",
    value: "R 450,000",
    stage: "Discovery",
    probability: "30%",
    closeDate: "2024-02-15",
    owner: "David Wilson",
  },
]

const defaultTableColumns = [
  { key: "deal", label: "Deal Name" },
  { key: "value", label: "Value" },
  { key: "stage", label: "Stage" },
  { key: "probability", label: "Probability" },
  { key: "closeDate", label: "Close Date" },
  { key: "owner", label: "Owner" },
]

export function SalesModule() {
  const { data } = useModuleData("sales", {
    salesData: defaultSalesData,
    pipelineData: defaultPipelineData,
    topProducts: defaultTopProducts,
    flashcardKPIs: defaultFlashcardKPIs,
    activities: defaultActivities,
    issues: defaultIssues,
    summary: defaultSummary,
    tasks: defaultTasks,
    aiRecommendations: defaultAiRecommendations,
    tableData: defaultTableData,
    tableColumns: defaultTableColumns,
  })

  // Revenue/pipeline/KPI/deals-table widgets come from the real sales
  // backend, not the Supabase module_data blob above -- see
  // app/api/sales-stats. topProducts/activities/issues/tasks/
  // aiRecommendations have no real backend locally, so they stay on the
  // blob/defaults rather than being fabricated. Falls back to the blob on
  // any fetch failure, same resilience pattern as useModuleData itself.
  const [liveSales, setLiveSales] = useState<Partial<typeof data> | null>(null)
  useEffect(() => {
    let cancelled = false
    fetch("/api/sales-stats", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((payload) => {
        if (!cancelled && payload?.available) {
          const { available: _available, ...live } = payload
          setLiveSales(live)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const merged = { ...data, ...liveSales }
  const {
    salesData,
    pipelineData,
    topProducts,
    flashcardKPIs,
    activities,
    issues,
    summary,
    tasks,
    aiRecommendations,
    tableData,
    tableColumns,
  } = merged

  const flashcardKPIsWithIcons = flashcardKPIs.map((kpi) => ({
    ...kpi,
    icon: salesKpiIconMap[kpi.iconKey] ?? null,
  }))

  // ── Lead Management & Channel Sales State ─────────────────────────
  const [leads, setLeads] = useState<SalesLead[]>([])
  const [loadingLeads, setLoadingLeads] = useState(false)
  const [activeTab, setActiveTab] = useState<"pipeline" | "channels" | "leads" | "ai-engine">("pipeline")
  const [pipelineRefreshCounter, setPipelineRefreshCounter] = useState(0)

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
      const fetched = await salesApi.listLeads({ limit: 200 })
      setLeads(Array.isArray(fetched) ? fetched : [])
    } catch {
      // Keep the current list; the tab shows its own error on actions.
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

  const switchTab = (tab: "pipeline" | "channels" | "leads" | "ai-engine") => {
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


  // Aggregate sales by channel (combines deal metrics + channel metadata)
  const channelMetrics = useMemo(() => {
    const counts: Record<string, { deals: number; revenue: number }> = {}
    defaultChannelSales.forEach((c) => {
      counts[c.source] = { deals: c.deals, revenue: c.revenue }
    })

    // If leads exist, dynamically tally leads per channel
    leads.forEach((l) => {
      if (counts[l.source]) {
        counts[l.source].deals += 1
      }
    })

    return SALES_CHANNELS.map((ch) => {
      const metric = counts[ch.id] || { deals: 5, revenue: 250000 }
      return {
        name: ch.label,
        channel: ch.label,
        source: ch.id,
        deals: metric.deals,
        revenue: metric.revenue,
        color: ch.color,
        fill: ch.color,
        description: ch.description,
      }
    })
  }, [leads])

  const totalChannelRevenue = useMemo(
    () => channelMetrics.reduce((sum, c) => sum + c.revenue, 0),
    [channelMetrics]
  )

  return (
    <ModuleLayout
      title="Sales & Lead Management"
      icon={<Target className="h-5 w-5 text-blue-400" />}
      subtitle="Omnichannel sales capture (Walk-in, Website Portal, Inbound Email, Call Center, Field Sales), pipeline stages, and deal velocity"
      flashcardKPIs={flashcardKPIsWithIcons}
      activities={activities}
      issues={issues}
      summary={summary}
      tasks={tasks}
      aiRecommendations={aiRecommendations}
      tableData={tableData}
      tableColumns={tableColumns}
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
                Sales by Channel Chart
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
            </TabsList>

            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => loadLeads()}
                className="h-8 text-xs text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="h-3 w-3 mr-1" />
                Refresh Data
              </Button>
            </div>
          </div>
        </Tabs>
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

      {/* ── TAB 2: Sales by Channel Chart & Analytics ── */}
      {activeTab === "channels" && (
        <div className="space-y-6">
          {/* Quick Channel Pill Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {channelMetrics.map((ch) => (
              <div
                key={ch.source}
                className="rounded-xl border border-border bg-card p-3 shadow-sm hover:border-primary/40 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: ch.color }}
                  />
                  <span className="font-mono text-[11px] font-semibold text-foreground">
                    {ch.deals} deals
                  </span>
                </div>
                <div className="mt-2 text-xs font-semibold text-foreground truncate" title={ch.name}>
                  {ch.name}
                </div>
                <div className="mt-1 font-mono text-xs font-bold text-emerald-400">
                  {formatCurrency(ch.revenue)}
                </div>
              </div>
            ))}
          </div>

          {/* Main Charts: Bar Chart + Donut Split */}
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Sales Revenue by Channel Bar Chart */}
            <div className="surface-card p-5 lg:col-span-2">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="section-title">Sales Revenue by Channel</h3>
                  <p className="text-xs text-muted-foreground">
                    Direct attribution across Customer Walk-ins, Portal Applications, Email, Call Center & Field Reps
                  </p>
                </div>
                <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-xs">
                  Total: {formatCurrency(totalChannelRevenue)}
                </Badge>
              </div>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={channelMetrics} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "#9ca3af", fontSize: 11 }}
                      interval={0}
                      angle={-15}
                      textAnchor="end"
                    />
                    <YAxis
                      tick={{ fill: "#9ca3af", fontSize: 11 }}
                      tickFormatter={(v) => `R${v / 1000}K`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #3f3f46",
                        borderRadius: "8px",
                        color: "#fff",
                      }}
                      formatter={(value: number, name: string) => [
                        name === "revenue" ? formatCurrency(value) : value,
                        name === "revenue" ? "Revenue" : "Deals Closed",
                      ]}
                    />
                    <Legend />
                    <Bar dataKey="revenue" name="revenue" fill="#38bdf8" radius={[4, 4, 0, 0]}>
                      {channelMetrics.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Deal Volume Distribution Pie */}
            <div className="surface-card p-5">
              <h3 className="section-title mb-2">Deal Volume Share</h3>
              <p className="text-xs text-muted-foreground mb-4">Proportion of closed deals per channel</p>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={channelMetrics}
                      dataKey="deals"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={3}
                    >
                      {channelMetrics.map((entry, index) => (
                        <Cell key={`slice-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #3f3f46",
                        borderRadius: "8px",
                        color: "#fff",
                      }}
                      formatter={(val: number) => [`${val} Deals`, "Deals Count"]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-1.5 pt-2 border-t border-border/60">
                {channelMetrics.slice(0, 4).map((ch) => (
                  <div key={ch.source} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full" style={{ backgroundColor: ch.color }} />
                      <span className="text-muted-foreground truncate max-w-[120px]">{ch.name}</span>
                    </div>
                    <span className="font-semibold text-foreground">{ch.deals} deals</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 3: Lead Stage Management (SPEC-lead-lifecycle.md) ── */}
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

          {/* Active Digital Channel Automation Rules */}
          <div className="surface-card p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <Zap className="h-4 w-4 text-amber-400" />
                  Active Event Triggers & Stage Rules
                </h4>
                <p className="text-xs text-muted-foreground">
                  Automated stage movement criteria for digital customer interactions
                </p>
              </div>
              <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-xs">
                3 Active Event Listeners
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {/* Rule 1: Abandoned Cart */}
              <div className="rounded-xl border border-border bg-card p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <ShoppingCart className="h-4 w-4 text-cyan-400" />
                    Abandoned Basket ("Unbandered Basket")
                  </div>
                  <Badge className="bg-cyan-500/20 text-cyan-400 text-[10px]">Active</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Customer placed internet package in portal basket but left without paying (&gt;2 hrs).
                </p>
                <div className="rounded bg-muted/40 p-2 text-[11px] space-y-1">
                  <div className="text-muted-foreground">
                    Stage Movement: <span className="font-semibold text-foreground">New ➔ Contacted (Warming Active)</span>
                  </div>
                  <div className="text-emerald-400 font-medium">
                    AI Action: DomeBot generates 15% discount voucher <code className="text-xs">FIBERWARM15</code> + free installation waiver.
                  </div>
                </div>
              </div>

              {/* Rule 2: Quote Request */}
              <div className="rounded-xl border border-border bg-card p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <FileText className="h-4 w-4 text-purple-400" />
                    Instant Quotation Request
                  </div>
                  <Badge className="bg-purple-500/20 text-purple-400 text-[10px]">Active</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Customer requested pricing on website calculator or emailed inquiry.
                </p>
                <div className="rounded bg-muted/40 p-2 text-[11px] space-y-1">
                  <div className="text-muted-foreground">
                    Stage Movement: <span className="font-semibold text-foreground">New ➔ Proposal Sent</span>
                  </div>
                  <div className="text-purple-400 font-medium">
                    AI Action: DomeBot generates itemized quote spec PDF and schedules follow-up touchpoint.
                  </div>
                </div>
              </div>

              {/* Rule 3: Registered but Inactive */}
              <div className="rounded-xl border border-border bg-card p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <Globe className="h-4 w-4 text-amber-400" />
                    Online Registration Inactive
                  </div>
                  <Badge className="bg-amber-500/20 text-amber-400 text-[10px]">Active</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  User registered on self-service portal but took no action (&gt;24 hrs).
                </p>
                <div className="rounded bg-muted/40 p-2 text-[11px] space-y-1">
                  <div className="text-muted-foreground">
                    Stage Movement: <span className="font-semibold text-foreground">New ➔ Qualified</span>
                  </div>
                  <div className="text-amber-400 font-medium">
                    AI Action: Concierge bot sends friendly WhatsApp check-in offering address coverage check.
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Real lead sources: FNO passed homes → geo segments (SPEC-geo-segments.md) */}
          <SalesLeadSources />
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
