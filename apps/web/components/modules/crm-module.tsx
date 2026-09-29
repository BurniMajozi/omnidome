"use client"

import type { JSX } from "react"
import { useEffect, useState, useCallback, useMemo } from "react"
import {
  Users,
  UserCheck,
  UserPlus,
  TrendingUp,
  Building2,
  Kanban,
  Activity as ActivityIcon,
  Search,
  Filter,
  Plus,
  Phone,
  Mail,
  ShieldCheck,
  ShieldAlert,
  ChevronRight,
  ArrowRight,
  CheckCircle2,
  Clock,
  Home,
  FileText,
  AlertCircle,
  Loader2,
  RefreshCw,
  Sparkles,
  ExternalLink,
  Bot,
  Hash,
  X,
  MapPin,
  Calendar,
  Briefcase,
  DollarSign,
  Tag,
  Target,
} from "lucide-react"
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { PageHeader } from "@/components/ui/page-header"
import { LeadFunnelView } from "./sales/lead-funnel-view"
import { LifecycleDashboard } from "./lifecycle/lifecycle-dashboard"
import { ErrorBoundary } from "@/components/ui/error-boundary"
import {
  getActivities,
  getDashboardSummary,
  getInsights,
  getTasks,
  listCustomers,
  getCustomer360,
  getCustomerNotes,
  addCustomerNote,
  createCustomer,
  listLeads,
  createLead,
  updateLead,
  convertLead,
  listCompanies,
  createCompany,
  type Activity,
  type AiRecommendation,
  type CrmTask,
  type DashboardSummary,
  type Issue,
  type CustomerListItem,
  type Customer360Data,
  type CustomerNoteItem,
  type LeadItem,
  type CompanyItem,
} from "@/lib/crm-api"

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cn(...classes: (string | false | undefined | null)[]) {
  return classes.filter(Boolean).join(" ")
}

const formatCurrency = (value: number) => `R ${value.toLocaleString("en-ZA")}`

const crmKpiIconMap: Record<string, JSX.Element> = {
  customers: <Users className="h-5 w-5 text-emerald-400" />,
  leads: <UserPlus className="h-5 w-5 text-blue-400" />,
  conversion: <UserCheck className="h-5 w-5 text-amber-400" />,
  revenue: <TrendingUp className="h-5 w-5 text-purple-400" />,
}

const KANBAN_STAGES = [
  { id: "NEW", label: "New Leads", color: "border-blue-500/30 bg-blue-500/5 text-blue-400" },
  { id: "CONTACTED", label: "Contacted", color: "border-amber-500/30 bg-amber-500/5 text-amber-400" },
  { id: "QUALIFIED", label: "Qualified", color: "border-purple-500/30 bg-purple-500/5 text-purple-400" },
  { id: "PROPOSAL", label: "Coverage / Proposal", color: "border-cyan-500/30 bg-cyan-500/5 text-cyan-400" },
  { id: "CONVERTED", label: "Won / Customer", color: "border-emerald-500/30 bg-emerald-500/5 text-emerald-400" },
]

// ═════════════════════════════════════════════════════════════════════════════
// Customer 360 Slide-Over Sheet (Twenty CRM-style Record View)
// ═════════════════════════════════════════════════════════════════════════════

interface CustomerSheetProps {
  customer: CustomerListItem | null
  onClose: () => void
  onCall: (phone: string) => void
}

function CustomerSheet({ customer, onClose, onCall }: CustomerSheetProps) {
  const [data360, setData360] = useState<Customer360Data | null>(null)
  const [notes, setNotes] = useState<CustomerNoteItem[]>([])
  const [newNote, setNewNote] = useState("")
  const [loading, setLoading] = useState(false)
  const [submittingNote, setSubmittingNote] = useState(false)
  const [activeTab, setActiveTab] = useState<"overview" | "timeline" | "notes">("overview")

  const loadDetails = useCallback(async (id: string) => {
    setLoading(true)
    try {
      const [fullData, customerNotes] = await Promise.all([
        getCustomer360(id),
        getCustomerNotes(id),
      ])
      setData360(fullData)
      setNotes(customerNotes)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (customer?.id) {
      loadDetails(customer.id)
    }
  }, [customer, loadDetails])

  const handleAddNote = async () => {
    if (!customer?.id || !newNote.trim()) return
    setSubmittingNote(true)
    try {
      const created = await addCustomerNote(customer.id, newNote.trim())
      if (created) {
        setNotes((prev) => [created, ...prev])
        setNewNote("")
      }
    } catch (err) {
      console.error(err)
    } finally {
      setSubmittingNote(false)
    }
  }

  if (!customer) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm transition-opacity">
      <div className="relative flex h-full w-full max-w-xl flex-col border-l border-border bg-card shadow-2xl animate-in slide-in-from-right duration-300">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border p-6">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 font-semibold text-lg border border-emerald-500/20">
              {customer.first_name[0]}{customer.last_name[0]}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                {customer.first_name} {customer.last_name}
              </h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-muted-foreground font-mono">
                  {customer.account_number || "No Account #"}
                </span>
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[10px] uppercase font-bold",
                    customer.status === "active" ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/5" : "border-muted text-muted-foreground"
                  )}
                >
                  {customer.status}
                </Badge>
                {customer.rica_verified && (
                  <Badge variant="outline" className="border-blue-500/30 text-blue-400 text-[10px] bg-blue-500/5">
                    <ShieldCheck className="mr-1 h-3 w-3" /> RICA Verified
                  </Badge>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Quick Actions Bar */}
        <div className="flex items-center gap-2 border-b border-border/60 bg-muted/20 px-6 py-2.5">
          {customer.phone && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/10"
              onClick={() => onCall(customer.phone!)}
            >
              <Phone className="h-3.5 w-3.5" /> Call via Deepgram
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => window.open(`mailto:${customer.email}`)}
          >
            <Mail className="h-3.5 w-3.5" /> Send Email
          </Button>
          <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>MRR:</span>
            <span className="font-semibold text-foreground">{formatCurrency(customer.mrr)}</span>
          </div>
        </div>

        {/* Body Tabs */}
        <div className="flex items-center gap-4 border-b border-border px-6 pt-2">
          {(["overview", "timeline", "notes"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "pb-2.5 text-xs font-medium uppercase tracking-wider transition-colors border-b-2",
                activeTab === tab
                  ? "border-emerald-500 text-emerald-400"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {tab === "overview" && "Record Details"}
              {tab === "timeline" && "Omnidome Activity"}
              {tab === "notes" && `Notes (${notes.length})`}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <ScrollArea className="flex-1 p-6">
          {loading ? (
            <div className="flex h-48 items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
            </div>
          ) : activeTab === "overview" ? (
            <div className="space-y-6">
              {/* Contact Information */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Contact Information
                </h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-lg border border-border/50 bg-background/50 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">Email</p>
                    <p className="font-medium text-foreground truncate">{customer.email}</p>
                  </div>
                  <div className="rounded-lg border border-border/50 bg-background/50 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">Phone</p>
                    <p className="font-medium text-foreground">{customer.phone || "Not provided"}</p>
                  </div>
                  <div className="rounded-lg border border-border/50 bg-background/50 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">Province</p>
                    <p className="font-medium text-foreground capitalize">{customer.province || "Gauteng"}</p>
                  </div>
                  <div className="rounded-lg border border-border/50 bg-background/50 p-3">
                    <p className="text-[10px] text-muted-foreground uppercase">Customer Tier</p>
                    <p className="font-medium text-foreground">{customer.customer_type}</p>
                  </div>
                </div>
              </div>

              {/* Physical Address & Properties */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Physical Installation Address
                </h4>
                <div className="rounded-lg border border-border/50 bg-background/50 p-3.5">
                  <div className="flex items-start gap-2.5">
                    <MapPin className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {customer.address || "123 Main Road, Sandton, Johannesburg"}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        ISP Fibre ONT installed · Connected to Vumatel / Openserve network
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Omnidome Architecture Hooks */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Connected Omnidome Services
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/10 p-2.5">
                    <Phone className="h-4 w-4 text-cyan-400" />
                    <div>
                      <p className="font-medium text-foreground">Call Center</p>
                      <p className="text-[10px] text-muted-foreground">Deepgram logs synced</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/10 p-2.5">
                    <DollarSign className="h-4 w-4 text-purple-400" />
                    <div>
                      <p className="font-medium text-foreground">Sales Pipeline</p>
                      <p className="text-[10px] text-muted-foreground">Active quotes linked</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/10 p-2.5">
                    <Bot className="h-4 w-4 text-violet-400" />
                    <div>
                      <p className="font-medium text-foreground">Agent Orchestrator</p>
                      <p className="text-[10px] text-muted-foreground">Retention watcher active</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-muted/10 p-2.5">
                    <Home className="h-4 w-4 text-emerald-400" />
                    <div>
                      <p className="font-medium text-foreground">Property Handover</p>
                      <p className="text-[10px] text-muted-foreground">Equipment verified</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : activeTab === "timeline" ? (
            <div className="space-y-4">
              <div className="relative border-l border-border/60 pl-4 space-y-4 ml-2">
                <div className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-4 ring-card" />
                  <p className="text-xs font-semibold text-foreground">Account Created & RICA Verified</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Customer record provisioned in Omnidome database</p>
                </div>
                <div className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-cyan-400 ring-4 ring-card" />
                  <p className="text-xs font-semibold text-foreground">Fibre Service Active</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Package: 100 Mbps Uncapped Fibre (MRR: {formatCurrency(customer.mrr)})</p>
                </div>
                <div className="relative">
                  <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-violet-400 ring-4 ring-card" />
                  <p className="text-xs font-semibold text-foreground">Journey Engine Enrolled</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Monitoring retention signals and customer happiness</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Add Note Input */}
              <div className="space-y-2">
                <textarea
                  rows={3}
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  placeholder="Add an internal note or interaction log…"
                  className="w-full rounded-lg border border-border bg-background p-3 text-xs text-foreground placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
                <Button
                  size="sm"
                  onClick={handleAddNote}
                  disabled={submittingNote || !newNote.trim()}
                  className="w-full bg-emerald-600 hover:bg-emerald-500 text-white text-xs"
                >
                  {submittingNote ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Plus className="mr-1.5 h-3.5 w-3.5" />}
                  Save Note
                </Button>
              </div>

              {/* Notes List */}
              <div className="space-y-2.5 pt-2">
                {notes.length === 0 ? (
                  <p className="text-center py-8 text-xs text-muted-foreground">No notes recorded yet.</p>
                ) : (
                  notes.map((note) => (
                    <div key={note.id} className="rounded-lg border border-border/50 bg-background/40 p-3 space-y-1">
                      <p className="text-xs text-foreground leading-relaxed">{note.content}</p>
                      <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {new Date(note.created_at).toLocaleString("en-ZA")}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// Main CRM Module Export (Twenty CRM Architecture + Omnidome Microservices)
// ═════════════════════════════════════════════════════════════════════════════

export function CrmModule() {
  // ── Tab State ──────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<
    "overview" | "customers" | "pipeline" | "funnel" | "lifecycle" | "companies" | "activities"
  >("overview")

  // ── Data States ────────────────────────────────────────────────────────────
  const [summaryData, setSummaryData] = useState<DashboardSummary | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [tasks, setTasks] = useState<CrmTask[]>([])
  const [aiRecommendations, setAiRecommendations] = useState<AiRecommendation[]>([])
  const [issues, setIssues] = useState<Issue[]>([])
  const [customers, setCustomers] = useState<CustomerListItem[]>([])
  const [leads, setLeads] = useState<LeadItem[]>([])
  const [companies, setCompanies] = useState<CompanyItem[]>([])
  const [loading, setLoading] = useState(true)

  // ── Search & Filter States ─────────────────────────────────────────────────
  const [customerSearch, setCustomerSearch] = useState("")
  const [customerStatusFilter, setCustomerStatusFilter] = useState("all")
  const [leadSearch, setLeadSearch] = useState("")

  // ── Slide-Over & Modal States ──────────────────────────────────────────────
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerListItem | null>(null)
  const [isNewLeadOpen, setIsNewLeadOpen] = useState(false)
  const [isNewCustomerOpen, setIsNewCustomerOpen] = useState(false)
  const [isNewCompanyOpen, setIsNewCompanyOpen] = useState(false)

  // ── New Entity Form States ─────────────────────────────────────────────────
  const [newLeadForm, setNewLeadForm] = useState({ first_name: "", last_name: "", email: "", phone: "", source: "PORTAL_WEBSITE", interested_package: "100 Mbps Fibre" })
  const [newCustForm, setNewCustForm] = useState({ first_name: "", last_name: "", email: "", phone: "", address: "", province: "gauteng" })
  const [newCompForm, setNewCompForm] = useState({ name: "", registration_number: "", industry: "Technology", contact_person: "", email: "", phone: "" })
  const [savingEntity, setSavingEntity] = useState(false)

  // ── Initial Load ───────────────────────────────────────────────────────────
  const loadCrmData = useCallback(async () => {
    setLoading(true)
    try {
      const [summary, activityFeed, taskList, insights, custList, leadList, compList] = await Promise.all([
        getDashboardSummary(),
        getActivities(),
        getTasks(),
        getInsights(),
        listCustomers({ pageSize: 50 }),
        listLeads({ pageSize: 100 }),
        listCompanies({ pageSize: 50 }),
      ])
      setSummaryData(summary)
      setActivities(activityFeed)
      setTasks(taskList)
      setAiRecommendations(insights.aiRecommendations)
      setIssues(insights.issues)
      setCustomers(custList.items)
      setLeads(leadList.items)
      setCompanies(compList.items)
    } catch (err) {
      console.error("Failed to load CRM data", err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCrmData()
  }, [loadCrmData])

  // ── Filtered Customers ─────────────────────────────────────────────────────
  const filteredCustomers = useMemo(() => {
    return customers.filter((c) => {
      const matchesSearch =
        !customerSearch ||
        `${c.first_name} ${c.last_name}`.toLowerCase().includes(customerSearch.toLowerCase()) ||
        c.email.toLowerCase().includes(customerSearch.toLowerCase()) ||
        (c.account_number && c.account_number.toLowerCase().includes(customerSearch.toLowerCase()))
      const matchesStatus = customerStatusFilter === "all" || c.status.toLowerCase() === customerStatusFilter.toLowerCase()
      return matchesSearch && matchesStatus
    })
  }, [customers, customerSearch, customerStatusFilter])

  // ── Kanban Pipeline Grouping ───────────────────────────────────────────────
  const leadsByStage = useMemo(() => {
    const map: Record<string, LeadItem[]> = {
      NEW: [],
      CONTACTED: [],
      QUALIFIED: [],
      PROPOSAL: [],
      CONVERTED: [],
    }

    leads.forEach((l) => {
      const statusUpper = (l.status || "NEW").toUpperCase()
      if (map[statusUpper]) {
        map[statusUpper].push(l)
      } else {
        map.NEW.push(l)
      }
    })
    return map
  }, [leads])

  // ── Kanban Advance Stage ───────────────────────────────────────────────────
  const handleAdvanceStage = async (lead: LeadItem) => {
    const currentUpper = (lead.status || "NEW").toUpperCase()
    const stageOrder = ["NEW", "CONTACTED", "QUALIFIED", "PROPOSAL", "CONVERTED"]
    const currentIndex = stageOrder.indexOf(currentUpper)
    if (currentIndex >= 0 && currentIndex < stageOrder.length - 1) {
      const nextStage = stageOrder[currentIndex + 1]
      try {
        const updated = await updateLead(lead.id, { status: nextStage })
        if (updated) {
          setLeads((prev) => prev.map((item) => (item.id === lead.id ? updated : item)))
        }
      } catch (err) {
        console.error("Failed to advance lead", err)
      }
    }
  }

  // ── Convert Lead ───────────────────────────────────────────────────────────
  const handleConvertLead = async (leadId: string) => {
    try {
      const newCustomer = await convertLead(leadId)
      if (newCustomer) {
        setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, status: "CONVERTED" } : l)))
        setCustomers((prev) => [newCustomer, ...prev])
      }
    } catch (err) {
      console.error("Failed to convert lead", err)
    }
  }

  // ── Create Lead ────────────────────────────────────────────────────────────
  const handleCreateLead = async () => {
    if (!newLeadForm.first_name.trim() || !newLeadForm.last_name.trim()) return
    setSavingEntity(true)
    try {
      const created = await createLead(newLeadForm)
      if (created) {
        setLeads((prev) => [created, ...prev])
        setIsNewLeadOpen(false)
        setNewLeadForm({ first_name: "", last_name: "", email: "", phone: "", source: "PORTAL_WEBSITE", interested_package: "100 Mbps Fibre" })
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSavingEntity(false)
    }
  }

  // ── Create Customer ────────────────────────────────────────────────────────
  const handleCreateCustomer = async () => {
    if (!newCustForm.first_name.trim() || !newCustForm.last_name.trim() || !newCustForm.email.trim()) return
    setSavingEntity(true)
    try {
      const created = await createCustomer(newCustForm)
      if (created) {
        setCustomers((prev) => [created, ...prev])
        setIsNewCustomerOpen(false)
        setNewCustForm({ first_name: "", last_name: "", email: "", phone: "", address: "", province: "gauteng" })
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSavingEntity(false)
    }
  }

  // ── Create Company ─────────────────────────────────────────────────────────
  const handleCreateCompany = async () => {
    if (!newCompForm.name.trim()) return
    setSavingEntity(true)
    try {
      const created = await createCompany(newCompForm)
      if (created) {
        setCompanies((prev) => [created, ...prev])
        setIsNewCompanyOpen(false)
        setNewCompForm({ name: "", registration_number: "", industry: "Technology", contact_person: "", email: "", phone: "" })
      }
    } catch (e) {
      console.error(e)
    } finally {
      setSavingEntity(false)
    }
  }

  // ── Click to Call Handler ──────────────────────────────────────────────────
  const handleCallCustomer = (phone: string) => {
    // Navigates or cues Call Center module
    window.location.href = `/dashboard/call-center?dial=${encodeURIComponent(phone)}`
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Users className="h-5 w-5 text-emerald-400" />}
        title="CRM & Customer 360"
        subtitle="Twenty-inspired customer relationship engine integrated with Sales, Call Center, and Agent Orchestrator"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={() => setIsNewLeadOpen(true)}
            >
              <UserPlus className="h-3.5 w-3.5 text-blue-400" />
              New Lead
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={() => setIsNewCompanyOpen(true)}
            >
              <Building2 className="h-3.5 w-3.5 text-purple-400" />
              New B2B Company
            </Button>
            <Button
              variant="cta"
              size="sm"
              className="gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white"
              onClick={() => setIsNewCustomerOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              New Customer
            </Button>
          </div>
        }
      />

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full">
        <TabsList className="grid w-full grid-cols-7 bg-muted/30">
          <TabsTrigger value="overview" className="gap-1.5 text-xs data-[state=active]:text-emerald-400">
            <TrendingUp className="h-3.5 w-3.5" /> Overview
          </TabsTrigger>
          <TabsTrigger value="customers" className="gap-1.5 text-xs data-[state=active]:text-cyan-400">
            <Users className="h-3.5 w-3.5" /> People ({customers.length})
          </TabsTrigger>
          <TabsTrigger value="pipeline" className="gap-1.5 text-xs data-[state=active]:text-purple-400">
            <Kanban className="h-3.5 w-3.5" /> Pipeline ({leads.length})
          </TabsTrigger>
          <TabsTrigger value="funnel" className="gap-1.5 text-xs data-[state=active]:text-blue-400">
            <Target className="h-3.5 w-3.5" /> Lead Funnel
          </TabsTrigger>
          <TabsTrigger value="lifecycle" className="gap-1.5 text-xs data-[state=active]:text-emerald-400">
            <ActivityIcon className="h-3.5 w-3.5" /> Lifecycle
          </TabsTrigger>
          <TabsTrigger value="companies" className="gap-1.5 text-xs data-[state=active]:text-amber-400">
            <Building2 className="h-3.5 w-3.5" /> Companies ({companies.length})
          </TabsTrigger>
          <TabsTrigger value="activities" className="gap-1.5 text-xs data-[state=active]:text-pink-400">
            <Clock className="h-3.5 w-3.5" /> Activities
          </TabsTrigger>
        </TabsList>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 1: OVERVIEW & INTELLIGENCE                                    */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="overview" className="space-y-6 pt-4">
          {/* Flashcard KPIs */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {(summaryData?.flashcardKPIs ?? []).map((kpi) => (
              <Card key={kpi.id} className="border-border bg-card/60">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-xs font-medium text-muted-foreground">{kpi.title}</CardTitle>
                  {crmKpiIconMap[kpi.iconKey] ?? <Users className="h-4 w-4 text-muted-foreground" />}
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-foreground">{kpi.value}</div>
                  <p className="mt-1 text-[11px] text-muted-foreground line-clamp-1">{kpi.backInsight}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Growth & Churn Charts */}
          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2 border-border bg-card/60">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold text-foreground">Customer Growth & Churn Velocity</CardTitle>
                <CardDescription>6-month active subscriber base vs churn events</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={summaryData?.customerData ?? []}>
                      <defs>
                        <linearGradient id="customerGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                      <XAxis dataKey="month" stroke="#737373" fontSize={12} />
                      <YAxis stroke="#737373" fontSize={12} />
                      <Tooltip contentStyle={{ backgroundColor: "#171717", borderColor: "#404040", borderRadius: "8px" }} />
                      <Area type="monotone" dataKey="customers" stroke="#10b981" fillOpacity={1} fill="url(#customerGrad)" name="Active Customers" />
                      <Line type="monotone" dataKey="churn" stroke="#ef4444" strokeWidth={2} name="Churned" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Cross-Module AI Insights & Agent Orchestrator */}
            <Card className="border-border bg-card/60">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-emerald-400" />
                  <CardTitle className="text-sm font-semibold text-foreground">Agent Recommendations</CardTitle>
                </div>
                <CardDescription>Automated retention & sales actions</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {aiRecommendations.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-10 text-center">No high-risk churn signals detected.</p>
                ) : (
                  aiRecommendations.slice(0, 3).map((rec) => (
                    <div key={rec.id} className="rounded-lg border border-border/50 bg-background/40 p-3 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-foreground">{rec.title}</span>
                        <Badge variant="outline" className="border-amber-500/30 text-amber-400 text-[10px]">
                          {rec.impact} impact
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-relaxed">{rec.description}</p>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 2: PEOPLE & CUSTOMERS (TABLE VIEW)                            */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="customers" className="space-y-4 pt-4">
          {/* Search & Filter Toolbar */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by name, email, account #…"
                value={customerSearch}
                onChange={(e) => setCustomerSearch(e.target.value)}
                className="pl-9 h-9 text-xs"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={customerStatusFilter}
                onChange={(e) => setCustomerStatusFilter(e.target.value)}
                className="h-9 rounded-lg border border-border bg-card px-3 py-1 text-xs text-foreground focus:outline-none"
              >
                <option value="all">All Statuses</option>
                <option value="active">Active Only</option>
                <option value="suspended">Suspended</option>
                <option value="churned">Churned</option>
              </select>
              <Button variant="outline" size="sm" onClick={loadCrmData} className="h-9">
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Customers Table */}
          <Card className="border-border bg-card/60">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-border bg-muted/20 text-muted-foreground font-semibold">
                    <tr>
                      <th className="py-3 px-4">Customer Name</th>
                      <th className="py-3 px-4">Account Number</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Tier / Type</th>
                      <th className="py-3 px-4">Province</th>
                      <th className="py-3 px-4">MRR</th>
                      <th className="py-3 px-4">Health</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {filteredCustomers.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-12 text-center text-muted-foreground">
                          No customer records found matching filter.
                        </td>
                      </tr>
                    ) : (
                      filteredCustomers.map((cust) => (
                        <tr
                          key={cust.id}
                          className="hover:bg-muted/10 transition-colors cursor-pointer"
                          onClick={() => setSelectedCustomer(cust)}
                        >
                          <td className="py-3 px-4 font-medium text-foreground">
                            <div className="flex items-center gap-2">
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 font-semibold text-xs">
                                {cust.first_name[0]}{cust.last_name[0]}
                              </div>
                              <div>
                                <p className="font-semibold text-foreground">{cust.first_name} {cust.last_name}</p>
                                <p className="text-[10px] text-muted-foreground">{cust.email}</p>
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-4 font-mono text-muted-foreground">
                            {cust.account_number || "—"}
                          </td>
                          <td className="py-3 px-4">
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-[10px] capitalize font-medium",
                                cust.status === "active" ? "border-emerald-500/30 text-emerald-400" : "border-muted text-muted-foreground"
                              )}
                            >
                              {cust.status}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-muted-foreground">
                            {cust.customer_type}
                          </td>
                          <td className="py-3 px-4 text-muted-foreground capitalize">
                            {cust.province || "Gauteng"}
                          </td>
                          <td className="py-3 px-4 font-semibold text-foreground">
                            {formatCurrency(cust.mrr)}
                          </td>
                          <td className="py-3 px-4">
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-[10px]",
                                cust.health === "Excellent" || cust.health === "Good"
                                  ? "border-emerald-500/30 text-emerald-400"
                                  : "border-amber-500/30 text-amber-400"
                              )}
                            >
                              {cust.health}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-end gap-1.5">
                              {cust.phone && (
                                <Button
                                  size="icon-sm"
                                  variant="ghost"
                                  className="text-cyan-400 hover:bg-cyan-500/10"
                                  title="Call via Deepgram"
                                  onClick={() => handleCallCustomer(cust.phone!)}
                                >
                                  <Phone className="h-3.5 w-3.5" />
                                </Button>
                              )}
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                                onClick={() => setSelectedCustomer(cust)}
                              >
                                View 360 <ChevronRight className="h-3 w-3" />
                              </Button>
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
        </TabsContent>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 3: PIPELINE KANBAN (TWENTY CRM STYLE)                         */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="pipeline" className="space-y-4 pt-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Drag or advance leads through stages. Qualified leads can be converted into active subscriber accounts with one click.
            </p>
            <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={() => setIsNewLeadOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Add Lead
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
            {KANBAN_STAGES.map((col) => {
              const stageLeads = leadsByStage[col.id] || []
              return (
                <div key={col.id} className="flex flex-col rounded-xl border border-border/60 bg-muted/10 p-3 space-y-3 min-h-[500px]">
                  {/* Column Header */}
                  <div className="flex items-center justify-between border-b border-border/50 pb-2">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <span className={cn("h-2 w-2 rounded-full", col.color.split(" ")[2])} />
                      {col.label}
                    </span>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {stageLeads.length}
                    </Badge>
                  </div>

                  {/* Cards */}
                  <div className="space-y-2.5 flex-1 overflow-y-auto">
                    {stageLeads.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border/40 p-4 text-center text-[11px] text-muted-foreground">
                        No leads in stage
                      </div>
                    ) : (
                      stageLeads.map((lead) => (
                        <div
                          key={lead.id}
                          className="rounded-lg border border-border bg-card p-3 shadow-sm hover:border-emerald-500/40 transition-all space-y-2"
                        >
                          <div className="flex items-start justify-between gap-1">
                            <span className="font-semibold text-xs text-foreground line-clamp-1">
                              {lead.first_name} {lead.last_name}
                            </span>
                            <Badge variant="outline" className="text-[9px] border-border/50 text-muted-foreground uppercase">
                              {lead.source || "WEB"}
                            </Badge>
                          </div>

                          {lead.notes && (
                            <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                              {lead.notes}
                            </p>
                          )}

                          <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[10px] text-muted-foreground">
                            <span>{lead.interested_package || "Broadband"}</span>
                            {lead.coverage_area && (
                              <span className="flex items-center gap-0.5 text-cyan-400">
                                <MapPin className="h-2.5 w-2.5" /> {lead.coverage_area}
                              </span>
                            )}
                          </div>

                          {/* Action footer */}
                          <div className="flex items-center justify-between pt-1 gap-1">
                            {col.id !== "CONVERTED" ? (
                              <>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 px-1.5 text-[10px] text-emerald-400 hover:bg-emerald-500/10"
                                  onClick={() => handleConvertLead(lead.id)}
                                >
                                  Convert
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-6 px-2 text-[10px] gap-1 ml-auto text-muted-foreground hover:text-foreground"
                                  onClick={() => handleAdvanceStage(lead)}
                                >
                                  Advance <ArrowRight className="h-2.5 w-2.5" />
                                </Button>
                              </>
                            ) : (
                              <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                                <CheckCircle2 className="h-3 w-3" /> Active Customer
                              </span>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </TabsContent>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 4: B2B COMPANIES (ACCOUNTS DIRECTORY)                         */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="companies" className="space-y-4 pt-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Corporate entities that pay for multi-member internet services across employee homes or business branches.
            </p>
            <Button size="sm" variant="outline" className="gap-1.5 text-xs" onClick={() => setIsNewCompanyOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> Add B2B Company
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {companies.length === 0 ? (
              <div className="col-span-3 rounded-xl border border-dashed border-border/60 p-12 text-center">
                <Building2 className="mx-auto h-8 w-8 text-muted-foreground/40 mb-2" />
                <p className="text-sm font-medium text-foreground">No corporate accounts registered yet</p>
                <p className="text-xs text-muted-foreground mt-1">Add corporate clients paying for team internet packages.</p>
                <Button size="sm" variant="cta" className="mt-4 text-xs" onClick={() => setIsNewCompanyOpen(true)}>
                  Register First Company
                </Button>
              </div>
            ) : (
              companies.map((comp) => (
                <Card key={comp.id} className="border-border bg-card/60 hover:border-purple-500/40 transition-colors">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="text-sm font-semibold text-foreground">{comp.name}</CardTitle>
                        <CardDescription className="text-xs">{comp.industry || "Corporate Client"}</CardDescription>
                      </div>
                      <Badge variant="outline" className="border-purple-500/30 text-purple-400 text-[10px]">
                        {comp.members_count} Members
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2.5 text-xs text-muted-foreground">
                    <div className="flex items-center justify-between">
                      <span>Registration:</span>
                      <span className="font-mono text-foreground">{comp.registration_number || "—"}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Payment Terms:</span>
                      <span className="text-foreground">{comp.payment_terms || "Net 30"}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Contact Person:</span>
                      <span className="text-foreground">{comp.contact_person || "Operations Manager"}</span>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 5: ACTIVITIES & TASKS                                         */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="activities" className="space-y-6 pt-4">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Actionable Tasks */}
            <Card className="border-border bg-card/60">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold text-foreground">Pending Tasks & Action Items</CardTitle>
                <CardDescription>Follow-ups, customer outreach, and account verifications</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {tasks.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-10 text-center">No open tasks assigned.</p>
                ) : (
                  tasks.map((task) => (
                    <div key={task.id} className="flex items-center justify-between rounded-lg border border-border/50 bg-background/40 p-3">
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-foreground">{task.title}</p>
                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                          <span>Assignee: {task.assignee}</span>
                          {task.dueDate && <span>Due: {task.dueDate.slice(0, 10)}</span>}
                        </div>
                      </div>
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] capitalize",
                          task.priority === "urgent" || task.priority === "high"
                            ? "border-red-500/30 text-red-400"
                            : "border-muted text-muted-foreground"
                        )}
                      >
                        {task.priority}
                      </Badge>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Centralized Activity Feed */}
            <Card className="border-border bg-card/60">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold text-foreground">Omnidome Unified Activity Stream</CardTitle>
                <CardDescription>Live updates across CRM, call center, and subscriptions</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="relative border-l border-border/60 pl-4 space-y-4 ml-2">
                  {activities.map((act) => (
                    <div key={act.id} className="relative">
                      <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-4 ring-card" />
                      <p className="text-xs font-semibold text-foreground">
                        {act.user} <span className="font-normal text-muted-foreground">{act.action}</span>
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{act.target}</p>
                      <p className="text-[10px] text-muted-foreground/60 mt-1">{act.time}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 6: LEAD FUNNEL BY CHANNEL                                     */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="funnel" className="space-y-6 pt-4">
          <ErrorBoundary fallbackTitle="Lead Funnel View encountered an issue">
            <LeadFunnelView
              onNavigateToLeads={() => setActiveTab("pipeline")}
            />
          </ErrorBoundary>
        </TabsContent>

        {/* ───────────────────────────────────────────────────────────────── */}
        {/* TAB 7: CUSTOMER LIFECYCLE & RETENTION                             */}
        {/* ───────────────────────────────────────────────────────────────── */}
        <TabsContent value="lifecycle" className="space-y-6 pt-4">
          <ErrorBoundary fallbackTitle="Customer Lifecycle Dashboard encountered an issue">
            <LifecycleDashboard />
          </ErrorBoundary>
        </TabsContent>
      </Tabs>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Slide-over Customer 360 Sheet                                      */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <CustomerSheet
        customer={selectedCustomer}
        onClose={() => setSelectedCustomer(null)}
        onCall={handleCallCustomer}
      />

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Modal: New Lead                                                     */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {isNewLeadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-sm font-semibold text-foreground">Create New Lead</h3>
              <button onClick={() => setIsNewLeadOpen(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-muted-foreground">First Name</label>
                  <Input value={newLeadForm.first_name} onChange={(e) => setNewLeadForm({ ...newLeadForm, first_name: e.target.value })} />
                </div>
                <div>
                  <label className="mb-1 block text-muted-foreground">Last Name</label>
                  <Input value={newLeadForm.last_name} onChange={(e) => setNewLeadForm({ ...newLeadForm, last_name: e.target.value })} />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Email</label>
                <Input type="email" value={newLeadForm.email} onChange={(e) => setNewLeadForm({ ...newLeadForm, email: e.target.value })} />
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Phone</label>
                <Input value={newLeadForm.phone} onChange={(e) => setNewLeadForm({ ...newLeadForm, phone: e.target.value })} placeholder="+27 ..." />
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Interested Package</label>
                <select
                  value={newLeadForm.interested_package}
                  onChange={(e) => setNewLeadForm({ ...newLeadForm, interested_package: e.target.value })}
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-foreground"
                >
                  <option value="50 Mbps Fibre">50 Mbps Fibre (R 599/mo)</option>
                  <option value="100 Mbps Fibre">100 Mbps Fibre (R 799/mo)</option>
                  <option value="200 Mbps Fibre">200 Mbps Fibre (R 999/mo)</option>
                  <option value="500 Mbps Enterprise">500 Mbps Enterprise (R 2,499/mo)</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button size="sm" variant="outline" onClick={() => setIsNewLeadOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={handleCreateLead} disabled={savingEntity || !newLeadForm.first_name.trim()} className="bg-emerald-600 hover:bg-emerald-500 text-white">
                {savingEntity ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Lead"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Modal: New Customer                                                 */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {isNewCustomerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-sm font-semibold text-foreground">Add New Customer</h3>
              <button onClick={() => setIsNewCustomerOpen(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-muted-foreground">First Name</label>
                  <Input value={newCustForm.first_name} onChange={(e) => setNewCustForm({ ...newCustForm, first_name: e.target.value })} />
                </div>
                <div>
                  <label className="mb-1 block text-muted-foreground">Last Name</label>
                  <Input value={newCustForm.last_name} onChange={(e) => setNewCustForm({ ...newCustForm, last_name: e.target.value })} />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Email</label>
                <Input type="email" value={newCustForm.email} onChange={(e) => setNewCustForm({ ...newCustForm, email: e.target.value })} />
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Phone</label>
                <Input value={newCustForm.phone} onChange={(e) => setNewCustForm({ ...newCustForm, phone: e.target.value })} placeholder="+27 ..." />
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Installation Address</label>
                <Input value={newCustForm.address} onChange={(e) => setNewCustForm({ ...newCustForm, address: e.target.value })} placeholder="123 Street Name, Suburb" />
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Province</label>
                <select
                  value={newCustForm.province}
                  onChange={(e) => setNewCustForm({ ...newCustForm, province: e.target.value })}
                  className="w-full rounded-lg border border-border bg-card px-3 py-2 text-foreground capitalize"
                >
                  <option value="gauteng">Gauteng</option>
                  <option value="western_cape">Western Cape</option>
                  <option value="kwazulu_natal">KwaZulu-Natal</option>
                  <option value="eastern_cape">Eastern Cape</option>
                  <option value="free_state">Free State</option>
                  <option value="mpumalanga">Mpumalanga</option>
                  <option value="limpopo">Limpopo</option>
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button size="sm" variant="outline" onClick={() => setIsNewCustomerOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={handleCreateCustomer} disabled={savingEntity || !newCustForm.first_name.trim()} className="bg-emerald-600 hover:bg-emerald-500 text-white">
                {savingEntity ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create Customer"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Modal: New Company (B2B)                                            */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {isNewCompanyOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-sm font-semibold text-foreground">Register B2B Company</h3>
              <button onClick={() => setIsNewCompanyOpen(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="mb-1 block text-muted-foreground">Company Name</label>
                <Input value={newCompForm.name} onChange={(e) => setNewCompForm({ ...newCompForm, name: e.target.value })} placeholder="Acme Logistics (Pty) Ltd" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-muted-foreground">Registration #</label>
                  <Input value={newCompForm.registration_number} onChange={(e) => setNewCompForm({ ...newCompForm, registration_number: e.target.value })} placeholder="2024/123456/07" />
                </div>
                <div>
                  <label className="mb-1 block text-muted-foreground">Industry</label>
                  <Input value={newCompForm.industry} onChange={(e) => setNewCompForm({ ...newCompForm, industry: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-muted-foreground">Contact Person</label>
                  <Input value={newCompForm.contact_person} onChange={(e) => setNewCompForm({ ...newCompForm, contact_person: e.target.value })} />
                </div>
                <div>
                  <label className="mb-1 block text-muted-foreground">Phone</label>
                  <Input value={newCompForm.phone} onChange={(e) => setNewCompForm({ ...newCompForm, phone: e.target.value })} />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-muted-foreground">Billing Email</label>
                <Input type="email" value={newCompForm.email} onChange={(e) => setNewCompForm({ ...newCompForm, email: e.target.value })} placeholder="accounts@company.co.za" />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button size="sm" variant="outline" onClick={() => setIsNewCompanyOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={handleCreateCompany} disabled={savingEntity || !newCompForm.name.trim()} className="bg-purple-600 hover:bg-purple-500 text-white">
                {savingEntity ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Company"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
