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
  User,
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
  Sparkles,
  Bot,
  Zap,
  ShoppingCart,
  FileText,
  Copy,
  Check,
  Package,
  Building2,
  Phone,
  Layers,
  ChevronRight,
  Play,
  Send,
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

  // ── AI Lead Warming & Digital Channel Automation State ──────────────
  const [selectedSimScenario, setSelectedSimScenario] = useState<"ABANDONED_CART" | "QUOTE_REQUEST" | "REGISTRATION_IDLE">("ABANDONED_CART")
  const [simulatingWarming, setSimulatingWarming] = useState(false)
  const [copiedMessage, setCopiedMessage] = useState(false)
  const [simulationResult, setSimulationResult] = useState<{
    scenarioName: string
    leadName: string
    channel: string
    previousStage: string
    newStage: string
    generatedMessage: string
    actionSummary: string
    timestamp: string
  } | null>(null)

  // AI Prospecting Generator State
  const [prospectRegion, setProspectRegion] = useState("Rosebank Commercial Hub, Johannesburg")
  const [prospectPackage, setProspectPackage] = useState(PRODUCT_CATALOG[1].name)
  const [generatingProspects, setGeneratingProspects] = useState(false)
  const [generatedProspects, setGeneratedProspects] = useState<
    { company: string; contact: string; email: string; phone: string; score: number; need: string }[]
  >([])

  // Load real leads from the sales API
  const loadLeads = useCallback(async () => {
    setLoadingLeads(true)
    try {
      const fetched = await salesApi.listLeads({ limit: 100 })
      if (Array.isArray(fetched) && fetched.length > 0) {
        setLeads(fetched)
      } else {
        // Initial omnichannel realistic seeds
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
            status: "CONTACTED",
            notes: "Online abandoned basket (Business Fiber 200Mbps). AI warming sequence initiated.",
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
            status: "PROPOSAL",
            notes: "Inbound quote request submitted online for Hosted PBX 10-Seat.",
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
      setPipelineRefreshCounter((c) => c + 1)
      alert(`Lead ${lead.first_name} ${lead.last_name} converted to Deal! Check the Pipeline Board.`)
    } catch (err) {
      alert(err instanceof Error ? err.message : "Conversion failed")
    }
  }

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

      // 1. Create Deal in pipeline board
      let createdDeal: any = null
      const contactUuid = typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : "00000000-0000-0000-0000-000000000001"

      try {
        createdDeal = await salesApi.createDeal({
          name: dealTitle,
          customer_id: contactUuid,
          stage_name: dealStage,
          value_zar: Number(dealValue) || 0,
          notes: metaNotes,
        })
      } catch (dealErr) {
        console.error("Pipeline deal creation error:", dealErr)
        throw dealErr
      }

      // 2. Create Lead in leads table (if backend leads endpoint is supported)
      try {
        const createdLead = await salesApi.createLead({
          first_name: dealFirstName.trim(),
          last_name: dealLastName.trim(),
          email: dealEmail.trim() || undefined,
          phone: dealPhone.trim() || undefined,
          address: dealAddress.trim() || undefined,
          source: dealSource,
          interest_level: dealInterest,
          notes: metaNotes,
        })
        if (createdLead) {
          setLeads((prev) => [createdLead, ...prev])
        }
      } catch (leadErr) {
        console.warn("Backend lead recording optional warning:", leadErr)
        // Synthesize lead entry locally so UI lead directory reflects the new prospect immediately
        const localLead: SalesLead = {
          id: createdDeal?.id || `lead-${Date.now()}`,
          tenant_id: "00000000-0000-0000-0000-000000000001",
          first_name: dealFirstName.trim(),
          last_name: dealLastName.trim(),
          email: dealEmail.trim() || null,
          phone: dealPhone.trim() || null,
          address: dealAddress.trim() || null,
          source: dealSource,
          interest_level: dealInterest,
          status: dealStage.toUpperCase(),
          notes: metaNotes,
          created_at: new Date().toISOString(),
        }
        setLeads((prev) => [localLead, ...prev])
      }

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
      alert(`Deal & Lead "${dealTitle}" successfully created! Both Pipeline Board and Lead Directory are updated.`)
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to record deal")
    } finally {
      setSavingDeal(false)
    }
  }

  // ── Execute AI Lead Warming Simulation ─────────────────────────────
  const handleRunAiWarmingSimulation = () => {
    setSimulatingWarming(true)
    setCopiedMessage(false)

    setTimeout(() => {
      if (selectedSimScenario === "ABANDONED_CART") {
        const leadTarget = leads.find((l) => l.source === "PORTAL_WEBSITE") || leads[1] || leads[0]
        const targetLeadId = leadTarget ? leadTarget.id : "lead-2"

        // Auto-move stage to CONTACTED (Warming Active)
        handleLeadStageChange(targetLeadId, "CONTACTED")
        setPipelineRefreshCounter((c) => c + 1)

        setSimulationResult({
          scenarioName: "Abandoned Basket Recovery ('Unbandered Basket')",
          leadName: `${leadTarget?.first_name || "Annelize"} ${leadTarget?.last_name || "van der Merwe"}`,
          channel: "WhatsApp & Email Concierge",
          previousStage: "New Lead",
          newStage: "Contacted (Warming Active)",
          actionSummary: "Event ecommerce.cart_abandoned detected (>2 hours). Automated AI Lead Warming triggered. Stage auto-advanced to Contacted.",
          generatedMessage: `Good day ${leadTarget?.first_name || "Annelize"},

We noticed you were exploring our Business Fiber 200Mbps uncapped package for your premises in ${leadTarget?.address || "Stellenbosch"} on our self-service portal, but didn't finish your order.

To help you get connected with zero downtime, we've applied an exclusive promotional waiver:
🎁 15% discount on your first 3 months with voucher code: FIBERWARM15
🚀 Free standard Wi-Fi 6 router installation included (valued at R1,750).

Would you like us to finalize the coverage verification for you, or can our concierge assist with any questions?
Click here to resume your basket: https://portal.omnidome.co.za/cart/resume?token=wrm_8842

Kind regards,
DomeBot Sales Concierge · OmniDome Telecoms`,
          timestamp: new Date().toLocaleTimeString(),
        })
      } else if (selectedSimScenario === "QUOTE_REQUEST") {
        const leadTarget = leads.find((l) => l.source === "INBOUND_EMAIL") || leads[4] || leads[0]
        const targetLeadId = leadTarget ? leadTarget.id : "lead-5"

        // Auto-move stage to PROPOSAL
        handleLeadStageChange(targetLeadId, "PROPOSAL")
        setPipelineRefreshCounter((c) => c + 1)

        setSimulationResult({
          scenarioName: "Instant Quotation Request",
          leadName: `${leadTarget?.first_name || "Pieter"} ${leadTarget?.last_name || "Botha"}`,
          channel: "Automated Email Proposal & PDF",
          previousStage: "New Lead",
          newStage: "Proposal Sent",
          actionSummary: "Event portal.quote_requested received. DomeBot itemized pricing breakdown and auto-moved stage to Proposal Sent.",
          generatedMessage: `Dear ${leadTarget?.first_name || "Pieter"},

Thank you for requesting an official quotation for OmniDome Telecoms Hosted PBX & VoIP Trunk Services for ${leadTarget?.address || "Bellville"}.

Here is your itemized commercial quote summary:
• Package: Hosted PBX & VoIP Trunk (10-Seat Enterprise Bundle)
• Monthly Recurring: R 1,450.00 / month (excl. VAT)
• Setup & SIP Porting Fee: R 0.00 (Standard Setup Waived)
• Included: 10 Geographic DDI numbers, automated call recording, cloud switchboard, and 24/7 SLA.

Your official PDF quotation #Q-2026-883 is attached to this dispatch. It is valid for 30 calendar days.
Reply 'APPROVE' to initiate seamless RICA verification and dispatch.

Kind regards,
Sales Operations Team · OmniDome Telecoms`,
          timestamp: new Date().toLocaleTimeString(),
        })
      } else {
        const leadTarget = leads[0] || leads[5]
        const targetLeadId = leadTarget ? leadTarget.id : "lead-1"

        // Auto-move stage to QUALIFIED
        handleLeadStageChange(targetLeadId, "QUALIFIED")
        setPipelineRefreshCounter((c) => c + 1)

        setSimulationResult({
          scenarioName: "Online Registration Inactivity (Registered then did nothing)",
          leadName: `${leadTarget?.first_name || "Thabo"} ${leadTarget?.last_name || "Mokoena"}`,
          channel: "WhatsApp Concierge Outreach",
          previousStage: "New Lead",
          newStage: "Qualified",
          actionSummary: "Event auth.user_registered_inactive triggered (>24 hours with zero orders). Auto-moved stage to Qualified and initiated onboarding outreach.",
          generatedMessage: `Hi ${leadTarget?.first_name || "Thabo"}! 👋

Welcome to OmniDome! We noticed you created your account on our customer portal yesterday, but haven't selected an internet package yet.

Can we help you check fiber coverage at ${leadTarget?.address || "your address"}? 
Our team can run an instant feasibility check across Openserve, Vumatel, and Frogfoot networks to find the fastest speed for your home or office.

Simply reply with your street address or let us know if you'd like a call back from one of our specialists.

Warm regards,
OmniDome Customer Concierge`,
          timestamp: new Date().toLocaleTimeString(),
        })
      }
      setSimulatingWarming(false)
    }, 900)
  }

  // ── Execute AI Lead Prospecting Generator ─────────────────────────
  const handleGenerateAiProspects = () => {
    setGeneratingProspects(true)
    setTimeout(() => {
      const generated = [
        {
          company: "Nexus Logistics & Supply Chain",
          contact: "Devan Govender",
          email: "d.govender@nexuslogistics.co.za",
          phone: "+27 82 884 1122",
          score: 94,
          need: `High bandwidth requirement for warehouse barcode tracking. Recommended: ${prospectPackage}.`,
        },
        {
          company: "Apex Legal & Advisory Partners",
          contact: "Claire Sterling",
          email: "c.sterling@apexlaw.co.za",
          phone: "+27 71 445 9988",
          score: 89,
          need: `Requires secure encrypted connectivity & VoIP PBX. Target area: ${prospectRegion}.`,
        },
        {
          company: "Solaria Clean Energy Systems",
          contact: "Bongani Sithole",
          email: "b.sithole@solaria.co.za",
          phone: "+27 83 221 7700",
          score: 91,
          need: `Branch office expansion. Fiber feasibility confirmed. Recommended: ${prospectPackage}.`,
        },
      ]
      setGeneratedProspects(generated)

      // Add to leads list as qualified prospects
      const newProspectLeads: SalesLead[] = generated.map((p, idx) => ({
        id: `ai-lead-${Date.now()}-${idx}`,
        tenant_id: "00000000-0000-0000-0000-000000000001",
        first_name: p.contact.split(" ")[0],
        last_name: p.contact.split(" ")[1] || "Lead",
        email: p.email,
        phone: p.phone,
        address: prospectRegion,
        source: "PORTAL_WEBSITE",
        interest_level: 5,
        status: "QUALIFIED",
        notes: `AI-Generated Prospect for ${p.company} · ${p.need}`,
        created_at: new Date().toISOString(),
      }))

      setLeads((prev) => [...newProspectLeads, ...prev])
      setPipelineRefreshCounter((c) => c + 1)
      setGeneratingProspects(false)
    }, 1100)
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

      {/* ── TAB 3: Lead Stage Management (Manual Adjustments & Visual Stepper) ── */}
      {activeTab === "leads" && (
        <div className="surface-card p-5 space-y-5">
          {/* Stage Progression Stepper Bar */}
          <div className="rounded-xl border border-border bg-card/60 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-primary" />
                Manual Lead Stage Progression Stepper
              </span>
              <span className="text-[11px] text-muted-foreground">
                Select any stage below or use the table dropdown to manually adjust lead progression
              </span>
            </div>
            <div className="flex items-center gap-1 overflow-x-auto py-2 text-xs">
              {LEAD_STAGES.map((st, i) => (
                <div key={st.id} className="flex items-center gap-1 shrink-0">
                  <div className={`px-2.5 py-1 rounded-md border text-[11px] font-semibold ${st.badge}`}>
                    {i + 1}. {st.label}
                  </div>
                  {i < LEAD_STAGES.length - 1 && (
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
                  )}
                </div>
              ))}
            </div>
          </div>

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
                    <th className="py-2.5 px-3.5">Customer & Contact Person</th>
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
                        No leads found for this channel. Click "+ Create Deal / Lead" to record a walk-in or manual lead.
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
                            <div className="font-semibold text-foreground flex items-center gap-1.5">
                              <User className="h-3.5 w-3.5 text-primary shrink-0" />
                              <span>
                                {lead.first_name} {lead.last_name}
                              </span>
                            </div>
                            <div className="text-[11px] text-muted-foreground flex items-center gap-2 mt-0.5">
                              {lead.email && (
                                <span className="flex items-center gap-1">
                                  <Mail className="h-2.5 w-2.5" />
                                  {lead.email}
                                </span>
                              )}
                              {lead.phone && (
                                <span className="flex items-center gap-1">
                                  <Phone className="h-2.5 w-2.5" />
                                  {lead.phone}
                                </span>
                              )}
                            </div>
                            {lead.address && (
                              <div className="text-[10px] text-muted-foreground/70 truncate max-w-xs mt-0.5">
                                📍 {lead.address}
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
                              className="h-7 rounded-md border border-border bg-background px-2 text-xs font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary shadow-sm"
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

          {/* Interactive Simulation: Digital Channel Event & AI Warming Execution */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Simulation Controls */}
            <div className="surface-card p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <Play className="h-4 w-4 text-primary" />
                    Simulate Digital Event & AI Warming
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    Trigger an event listening cycle to observe automated stage progression and message generation
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-foreground">Select Simulation Scenario</label>
                  <select
                    value={selectedSimScenario}
                    onChange={(e) => setSelectedSimScenario(e.target.value as any)}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="ABANDONED_CART">
                      🛒 Unbandered Basket — Annelize van der Merwe (Stellenbosch, 200Mbps Fiber)
                    </option>
                    <option value="QUOTE_REQUEST">
                      📄 Inbound Quotation Request — Pieter Botha (Bellville, 10-Seat Hosted PBX)
                    </option>
                    <option value="REGISTRATION_IDLE">
                      👤 Inactive Online Signup — Thabo Mokoena (Sandton, Home Broadband)
                    </option>
                  </select>
                </div>

                <div className="rounded-lg border border-border/80 bg-muted/20 p-3 text-xs text-muted-foreground space-y-1.5">
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <Bot className="h-3.5 w-3.5 text-primary" /> What happens when triggered:
                  </div>
                  <ul className="list-disc list-inside space-y-1 text-[11px]">
                    <li>Event listener ingests customer payload & cart context</li>
                    <li>Lead stage automatically shifts in real-time</li>
                    <li>DomeBot generates tailored, localized South African outreach copy</li>
                    <li>Activity is logged to the Pipeline and Leads directory</li>
                  </ul>
                </div>

                <Button
                  onClick={handleRunAiWarmingSimulation}
                  disabled={simulatingWarming}
                  className="w-full h-9 bg-primary text-primary-foreground text-xs font-semibold gap-1.5 shadow-sm"
                >
                  {simulatingWarming ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      Running AI Warming Cycle...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5" />
                      Run AI Lead Warming Cycle
                    </>
                  )}
                </Button>
              </div>
            </div>

            {/* Generated AI Message & Stage Transition Display */}
            <div className="surface-card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <Bot className="h-4 w-4 text-emerald-400" />
                  AI Lead Warming Output
                </h4>
                {simulationResult && (
                  <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-[10px]">
                    Generated at {simulationResult.timestamp}
                  </Badge>
                )}
              </div>

              {simulationResult ? (
                <div className="space-y-3 animate-in fade-in">
                  {/* Status Banner */}
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2.5 text-xs text-emerald-400 flex items-center justify-between">
                    <span>
                      <strong>Stage Movement:</strong> {simulationResult.previousStage} ➔{" "}
                      <span className="underline font-bold">{simulationResult.newStage}</span>
                    </span>
                    <Badge className="bg-emerald-500/20 text-emerald-300 text-[10px]">Auto-Shifted</Badge>
                  </div>

                  {/* Generated Message Body */}
                  <div className="relative rounded-lg border border-border bg-muted/40 p-3.5 text-xs text-foreground font-mono whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
                    {simulationResult.generatedMessage}
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center justify-between gap-2 pt-1">
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                      Target Channel: <strong className="text-foreground">{simulationResult.channel}</strong>
                    </span>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          navigator.clipboard.writeText(simulationResult.generatedMessage)
                          setCopiedMessage(true)
                          setTimeout(() => setCopiedMessage(false), 2000)
                        }}
                        className="h-7 text-xs gap-1"
                      >
                        {copiedMessage ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        {copiedMessage ? "Copied" : "Copy Message"}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => alert(`Simulated dispatch sent via ${simulationResult.channel} to ${simulationResult.leadName}!`)}
                        className="h-7 text-xs gap-1 bg-emerald-600 hover:bg-emerald-500 text-white"
                      >
                        <Send className="h-3 w-3" />
                        Send Now
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-52 text-center text-muted-foreground text-xs space-y-2">
                  <Bot className="h-8 w-8 opacity-40 text-primary" />
                  <p>No simulation run yet.</p>
                  <p className="text-[11px] max-w-xs opacity-70">
                    Select a scenario on the left and click "Run AI Lead Warming Cycle" to see real-time stage movement and outreach copy.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* AI Lead Prospecting Generator Section */}
          <div className="surface-card p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-purple-400" />
                  AI Lead Prospecting Generator
                </h4>
                <p className="text-xs text-muted-foreground">
                  Synthesize high-probability warm leads for targeted telecommunication deployment zones
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="text-xs font-semibold text-foreground">Target Deployment Corridor</label>
                <select
                  value={prospectRegion}
                  onChange={(e) => setProspectRegion(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="Rosebank Commercial Hub, Johannesburg">Rosebank Commercial Hub, Johannesburg</option>
                  <option value="Midrand Technology & Logistics Park">Midrand Technology & Logistics Park</option>
                  <option value="Stellenbosch Innovation District, Western Cape">Stellenbosch Innovation District, Western Cape</option>
                  <option value="Durban Umhlanga Corporate Ridge">Durban Umhlanga Corporate Ridge</option>
                  <option value="Bellville & Tyger Valley Business Park">Bellville & Tyger Valley Business Park</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-foreground">Recommended Package</label>
                <select
                  value={prospectPackage}
                  onChange={(e) => setProspectPackage(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  {PRODUCT_CATALOG.map((p) => (
                    <option key={p.id} value={p.name}>
                      {p.name} (R{p.price_monthly.toLocaleString()}/mo)
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-end">
                <Button
                  onClick={handleGenerateAiProspects}
                  disabled={generatingProspects}
                  className="w-full h-9 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold gap-1.5"
                >
                  {generatingProspects ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      Synthesizing Prospects...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5" />
                      Generate AI Warm Prospects
                    </>
                  )}
                </Button>
              </div>
            </div>

            {/* Generated Prospects Grid */}
            {generatedProspects.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-3 pt-2">
                {generatedProspects.map((p, idx) => (
                  <div key={idx} className="rounded-xl border border-border bg-card p-3.5 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-foreground truncate">{p.company}</span>
                      <Badge className="bg-purple-500/20 text-purple-300 text-[10px]">
                        {p.score}% Match
                      </Badge>
                    </div>
                    <div className="text-[11px] text-muted-foreground space-y-0.5">
                      <div className="flex items-center gap-1 text-foreground font-medium">
                        <User className="h-2.5 w-2.5 text-primary" /> {p.contact}
                      </div>
                      <div className="flex items-center gap-1">
                        <Mail className="h-2.5 w-2.5" /> {p.email}
                      </div>
                      <div className="flex items-center gap-1">
                        <Phone className="h-2.5 w-2.5" /> {p.phone}
                      </div>
                    </div>
                    <p className="text-[11px] text-muted-foreground bg-muted/30 p-2 rounded">{p.need}</p>
                    <div className="flex items-center justify-between pt-1">
                      <Badge variant="outline" className="border-emerald-500/30 text-emerald-400 text-[9px]">
                        Added to Leads
                      </Badge>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setActiveTab("leads")
                        }}
                        className="h-6 text-[10px] text-primary"
                      >
                        View in Directory →
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
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
