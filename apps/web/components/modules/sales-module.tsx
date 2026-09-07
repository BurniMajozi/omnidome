"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
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
  Mail,
  PhoneCall,
  PhoneOutgoing,
  Globe,
  MapPin,
  Store,
  Plus,
  ArrowRight,
  Filter,
  CheckCircle2,
  RefreshCw,
} from "lucide-react"
import { useModuleData } from "@/lib/module-data"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  salesApi,
  SALES_CHANNELS,
  type SalesChannel,
  type SalesLead,
  type Deal,
  type PipelineOverviewStage,
} from "@/lib/sales-api"
import { SalesPipelineBoard } from "./sales-pipeline-board"

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
  { channel: "Walk-in Customers", source: "WALK_IN", deals: 28, revenue: 1450000, color: "#38bdf8", fill: "#38bdf8" },
  { channel: "Portal & Website", source: "PORTAL_WEBSITE", deals: 42, revenue: 2180000, color: "#a78bfa", fill: "#a78bfa" },
  { channel: "Call Center Inbound", source: "CALL_CENTER_INBOUND", deals: 35, revenue: 1820000, color: "#34d399", fill: "#34d399" },
  { channel: "Field Sales Team", source: "FIELD_SALES", deals: 24, revenue: 1640000, color: "#f87171", fill: "#f87171" },
  { channel: "Inbound Email", source: "INBOUND_EMAIL", deals: 19, revenue: 980000, color: "#60a5fa", fill: "#60a5fa" },
  { channel: "Call Center Outbound", source: "CALL_CENTER_OUTBOUND", deals: 15, revenue: 720000, color: "#fbbf24", fill: "#fbbf24" },
]

const LEAD_STAGES = [
  { id: "NEW", label: "New Lead", badge: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  { id: "CONTACTED", label: "Contacted", badge: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30" },
  { id: "QUALIFIED", label: "Qualified", badge: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  { id: "PROPOSAL", label: "Proposal Sent", badge: "bg-purple-500/20 text-purple-400 border-purple-500/30" },
  { id: "NEGOTIATION", label: "Negotiation", badge: "bg-orange-500/20 text-orange-400 border-orange-500/30" },
  { id: "CONVERTED", label: "Converted to Deal", badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  { id: "LOST", label: "Lost / Disqualified", badge: "bg-red-500/20 text-red-400 border-red-500/30" },
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
  } = data

  const flashcardKPIsWithIcons = flashcardKPIs.map((kpi) => ({
    ...kpi,
    icon: salesKpiIconMap[kpi.iconKey] ?? null,
  }))

  // ── Lead Management & Channel Sales State ─────────────────────────
  const [leads, setLeads] = useState<SalesLead[]>([])
  const [loadingLeads, setLoadingLeads] = useState(false)
  const [selectedChannel, setSelectedChannel] = useState<string>("ALL")
  const [leadModalOpen, setLeadModalOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<"pipeline" | "channels" | "leads">("pipeline")

  // Form state for creating a new lead
  const [leadFirstName, setLeadFirstName] = useState("")
  const [leadLastName, setLeadLastName] = useState("")
  const [leadEmail, setLeadEmail] = useState("")
  const [leadPhone, setLeadPhone] = useState("")
  const [leadAddress, setLeadAddress] = useState("")
  const [leadSource, setLeadSource] = useState<SalesChannel>("WALK_IN")
  const [leadNotes, setLeadNotes] = useState("")
  const [leadInterest, setLeadInterest] = useState<number>(3)
  const [savingLead, setSavingLead] = useState(false)

  // Load real leads from the sales API
  const loadLeads = useCallback(async () => {
    setLoadingLeads(true)
    try {
      const fetched = await salesApi.listLeads({ limit: 100 })
      if (Array.isArray(fetched) && fetched.length > 0) {
        setLeads(fetched)
      } else {
        // Mock seed leads covering each requested channel if empty
        setLeads([
          {
            id: "lead-1",
            tenant_id: "00000000-0000-0000-0000-000000000001",
            first_name: "Thabo",
            last_name: "Mokoena",
            email: "thabo.m@acme.co.za",
            phone: "+27 82 123 4567",
            address: "Sandton City, Johannesburg",
            source: "WALK_IN",
            interest_level: 5,
            status: "QUALIFIED",
            notes: "Walked into Rosebank branch inquiring on 500Mbps Business Fiber.",
            created_at: new Date(Date.now() - 3600000 * 4).toISOString(),
          },
          {
            id: "lead-2",
            tenant_id: "00000000-0000-0000-0000-000000000001",
            first_name: "Annelize",
            last_name: "van der Merwe",
            email: "annelize@capevines.co.za",
            phone: "+27 71 987 6543",
            address: "Stellenbosch Central, Western Cape",
            source: "PORTAL_WEBSITE",
            interest_level: 4,
            status: "PROPOSAL",
            notes: "Online application submitted via customer self-service portal.",
            created_at: new Date(Date.now() - 3600000 * 8).toISOString(),
          },
          {
            id: "lead-3",
            tenant_id: "00000000-0000-0000-0000-000000000001",
            first_name: "Sipho",
            last_name: "Dlamini",
            email: "sipho@durbanfreight.co.za",
            phone: "+27 83 555 8899",
            address: "Umhlanga Ridge, Durban",
            source: "CALL_CENTER_INBOUND",
            interest_level: 4,
            status: "NEGOTIATION",
            notes: "Called inbound support hotline asking for quote on multi-site SD-WAN.",
            created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
          },
          {
            id: "lead-4",
            tenant_id: "00000000-0000-0000-0000-000000000001",
            first_name: "Kavitha",
            last_name: "Naidoo",
            email: "kavitha@solarsolutions.co.za",
            phone: "+27 84 333 2211",
            address: "Midrand Corporate Park, Gauteng",
            source: "FIELD_SALES",
            interest_level: 5,
            status: "CONTACTED",
            notes: "On-site visit by field sales rep John Smith. Quote requested.",
            created_at: new Date(Date.now() - 3600000 * 30).toISOString(),
          },
          {
            id: "lead-5",
            tenant_id: "00000000-0000-0000-0000-000000000001",
            first_name: "Pieter",
            last_name: "Botha",
            email: "pbotha@apexlogistics.co.za",
            phone: "+27 82 777 4411",
            address: "Bellville, Cape Town",
            source: "INBOUND_EMAIL",
            interest_level: 3,
            status: "NEW",
            notes: "Inbound RFP email received at sales@omnidome.com.",
            created_at: new Date(Date.now() - 3600000 * 48).toISOString(),
          },
          {
            id: "lead-6",
            tenant_id: "00000000-0000-0000-0000-000000000001",
            first_name: "Zanele",
            last_name: "Khumalo",
            email: "zanele@cresthotel.co.za",
            phone: "+27 81 222 9900",
            address: "Centurion, Pretoria",
            source: "CALL_CENTER_OUTBOUND",
            interest_level: 4,
            status: "QUALIFIED",
            notes: "Contacted during Q3 enterprise telesales campaign.",
            created_at: new Date(Date.now() - 3600000 * 72).toISOString(),
          },
        ])
      }
    } catch {
      // Keep existing leads state
    } finally {
      setLoadingLeads(false)
    }
  }, [])

  useEffect(() => {
    loadLeads()
  }, [loadLeads])

  // Handle manual lead status adjustment
  const handleLeadStageChange = async (leadId: string, newStatus: string) => {
    setLeads((prev) =>
      prev.map((l) => (l.id === leadId ? { ...l, status: newStatus } : l))
    )
    try {
      await salesApi.updateLead(leadId, { status: newStatus })
    } catch (err) {
      console.error("Failed to update lead status:", err)
      loadLeads()
    }
  }

  // Handle lead conversion to pipeline deal
  const handleConvertLead = async (lead: SalesLead) => {
    const value = prompt(`Enter deal value in ZAR for ${lead.first_name} ${lead.last_name}:`, "75000")
    if (!value || isNaN(Number(value))) return
    try {
      await salesApi.convertLead(lead.id, {
        name: `${lead.first_name} ${lead.last_name} - ${lead.source}`,
        value_zar: Number(value),
      })
      setLeads((prev) =>
        prev.map((l) => (l.id === lead.id ? { ...l, status: "CONVERTED" } : l))
      )
      alert(`Lead ${lead.first_name} ${lead.last_name} converted to Deal! Check the Pipeline Board.`)
    } catch (err) {
      alert(err instanceof Error ? err.message : "Conversion failed")
    }
  }

  // Handle manual lead submission
  const handleCreateLead = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!leadFirstName.trim() || !leadLastName.trim()) return
    setSavingLead(true)
    try {
      const created = await salesApi.createLead({
        first_name: leadFirstName.trim(),
        last_name: leadLastName.trim(),
        email: leadEmail.trim() || undefined,
        phone: leadPhone.trim() || undefined,
        address: leadAddress.trim() || undefined,
        source: leadSource,
        interest_level: leadInterest,
        notes: leadNotes.trim() || undefined,
      })
      setLeads((prev) => [created, ...prev])
      setLeadModalOpen(false)
      setLeadFirstName("")
      setLeadLastName("")
      setLeadEmail("")
      setLeadPhone("")
      setLeadAddress("")
      setLeadNotes("")
      setLeadInterest(3)
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create lead")
    } finally {
      setSavingLead(false)
    }
  }

  // Filter leads by channel
  const filteredLeads = useMemo(() => {
    if (selectedChannel === "ALL") return leads
    return leads.filter((l) => l.source === selectedChannel)
  }, [leads, selectedChannel])

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
      headerActions={
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            onClick={() => setLeadModalOpen(true)}
            className="h-8 gap-1.5 bg-primary text-primary-foreground text-xs shadow-sm"
          >
            <Plus className="h-3.5 w-3.5" />
            New Customer Lead
          </Button>
        </div>
      }
    >
      {/* ── Section Navigation Tabs: Pipeline vs. Channel Analytics vs. Lead Directory ── */}
      <div className="flex items-center justify-between gap-4 border-b border-border pb-3">
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full">
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
                  Adjustable deal stages · Drag & drop cards · Manual deal entry for customer walk-ins & proposals
                </p>
              </div>
            </div>
            <SalesPipelineBoard />
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

      {/* ── TAB 3: Lead Stage Management (Manual Adjustments & Tracking) ── */}
      {activeTab === "leads" && (
        <div className="surface-card p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-bold text-foreground">Customer Leads & Acquisition Channels</h3>
              <p className="text-xs text-muted-foreground">
                Filter by capture source, manually adjust lead stages, or convert prospective leads into pipeline deals
              </p>
            </div>

            {/* Filter by Channel */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-medium flex items-center gap-1">
                <Filter className="h-3 w-3" /> Channel:
              </span>
              <select
                value={selectedChannel}
                onChange={(e) => setSelectedChannel(e.target.value)}
                className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="ALL">All Acquisition Channels</option>
                {SALES_CHANNELS.map((ch) => (
                  <option key={ch.id} value={ch.id}>
                    {ch.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Leads Table with Adjustable Stages */}
          <div className="rounded-xl border border-border overflow-hidden bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-muted/40 font-medium text-muted-foreground">
                  <tr>
                    <th className="py-2.5 px-3.5">Customer / Contact</th>
                    <th className="py-2.5 px-3.5">Acquisition Channel</th>
                    <th className="py-2.5 px-3.5">Interest Level</th>
                    <th className="py-2.5 px-3.5">Adjust Lead Stage</th>
                    <th className="py-2.5 px-3.5">Notes & Context</th>
                    <th className="py-2.5 px-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filteredLeads.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-muted-foreground">
                        No leads found for this channel. Click "+ New Customer Lead" to record a walk-in or manual lead.
                      </td>
                    </tr>
                  ) : (
                    filteredLeads.map((lead) => {
                      const channelInfo = SALES_CHANNELS.find((c) => c.id === lead.source) || {
                        label: lead.source,
                        color: "#9ca3af",
                      }
                      return (
                        <tr key={lead.id} className="hover:bg-muted/30 transition-colors">
                          <td className="py-3 px-3.5">
                            <div className="font-semibold text-foreground">
                              {lead.first_name} {lead.last_name}
                            </div>
                            <div className="text-[11px] text-muted-foreground flex items-center gap-2 mt-0.5">
                              {lead.email && <span>{lead.email}</span>}
                              {lead.phone && <span>· {lead.phone}</span>}
                            </div>
                            {lead.address && (
                              <div className="text-[10px] text-muted-foreground/70 truncate max-w-xs mt-0.5">
                                {lead.address}
                              </div>
                            )}
                          </td>

                          <td className="py-3 px-3.5">
                            <span
                              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium border"
                              style={{
                                borderColor: `${channelInfo.color}40`,
                                backgroundColor: `${channelInfo.color}15`,
                                color: channelInfo.color,
                              }}
                            >
                              <div
                                className="h-1.5 w-1.5 rounded-full"
                                style={{ backgroundColor: channelInfo.color }}
                              />
                              {channelInfo.label}
                            </span>
                          </td>

                          <td className="py-3 px-3.5">
                            <span className="font-mono text-amber-400 font-semibold text-xs">
                              {"★".repeat(lead.interest_level || 3)}
                            </span>
                          </td>

                          {/* Adjustable Lead Stage Dropdown */}
                          <td className="py-3 px-3.5">
                            <select
                              value={lead.status}
                              onChange={(e) => handleLeadStageChange(lead.id, e.target.value)}
                              className="h-7 rounded-md border border-border bg-background px-2 text-xs font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                            >
                              {LEAD_STAGES.map((st) => (
                                <option key={st.id} value={st.id}>
                                  {st.label}
                                </option>
                              ))}
                            </select>
                          </td>

                          <td className="py-3 px-3.5 max-w-xs truncate text-muted-foreground">
                            {lead.notes || "—"}
                          </td>

                          <td className="py-3 px-3.5 text-right">
                            {lead.status !== "CONVERTED" ? (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs gap-1 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10"
                                onClick={() => handleConvertLead(lead)}
                              >
                                <CheckCircle2 className="h-3 w-3" />
                                Convert to Deal
                              </Button>
                            ) : (
                              <Badge className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px]">
                                Converted Deal
                              </Badge>
                            )}
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Manual Lead Capture (Walk-in, Phone, Inbound) ── */}
      {leadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-bold text-foreground">Record Customer Lead</h3>
              <button
                type="button"
                onClick={() => setLeadModalOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateLead} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">First Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Sipho"
                    value={leadFirstName}
                    onChange={(e) => setLeadFirstName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground">Last Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Khumalo"
                    value={leadLastName}
                    onChange={(e) => setLeadLastName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Email Address</label>
                  <input
                    type="email"
                    placeholder="client@domain.com"
                    value={leadEmail}
                    onChange={(e) => setLeadEmail(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground">Phone Number</label>
                  <input
                    type="tel"
                    placeholder="+27 82 123 4567"
                    value={leadPhone}
                    onChange={(e) => setLeadPhone(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Acquisition Channel *</label>
                  <select
                    value={leadSource}
                    onChange={(e) => setLeadSource(e.target.value as SalesChannel)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {SALES_CHANNELS.map((ch) => (
                      <option key={ch.id} value={ch.id}>
                        {ch.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-foreground">Interest Level (1-5)</label>
                  <select
                    value={leadInterest}
                    onChange={(e) => setLeadInterest(Number(e.target.value))}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value={1}>★☆☆☆☆ - Low</option>
                    <option value={2}>★★☆☆☆ - Exploring</option>
                    <option value={3}>★★★☆☆ - Moderate</option>
                    <option value={4}>★★★★☆ - High</option>
                    <option value={5}>★★★★★ - Urgent / Ready</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Premises / Address</label>
                <input
                  type="text"
                  placeholder="Street address, building or suburb"
                  value={leadAddress}
                  onChange={(e) => setLeadAddress(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Discussion Notes / Plan Request</label>
                <textarea
                  rows={3}
                  placeholder="Customer work-in notes, packages discussed, bandwidth needs..."
                  value={leadNotes}
                  onChange={(e) => setLeadNotes(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setLeadModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={savingLead || !leadFirstName.trim()}
                  className="bg-primary text-primary-foreground"
                >
                  {savingLead ? "Saving..." : "Save Lead"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ModuleLayout>
  )
}
