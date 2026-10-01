"use client"

import React, { useState, useMemo } from "react"
import {
  Users,
  Search,
  Plus,
  Filter,
  Grid,
  List,
  Mail,
  Phone,
  Building2,
  Calendar,
  UserCheck,
  UserX,
  Clock,
  MoreVertical,
  Download,
  Eye,
  Shield,
  Briefcase,
  IdCard,
  CheckCircle2,
  X,
  ExternalLink,
  ChevronRight,
  Sparkles,
  Award,
  AlertTriangle,
  GraduationCap,
  TrendingUp,
  CreditCard,
  HeartHandshake,
  Laptop,
  Wrench,
  Lock,
  Check,
  Radio,
  FileText,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NoDataYet } from "@/components/ui/not-connected"
import {
  createEmployee,
  type Employee,
  type EmployeeCreate,
} from "@/lib/hr-api"

// Curated professional employee avatar images
const AVATAR_PALETTE = [
  "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150&auto=format&fit=crop&q=80",
  "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=150&auto=format&fit=crop&q=80",
]

export function getEmployeeAvatar(name: string, index: number): string {
  const charCode = name.charCodeAt(0) || 0
  return AVATAR_PALETTE[(charCode + index) % AVATAR_PALETTE.length]
}

// All 31 OmniDome Platform Modules grouped by operational domain
export const OMNIDOME_31_MODULES = [
  { id: "dashboard", label: "Executive Dashboard", category: "Core Platform" },
  { id: "identity_auth", label: "IAM & Single Sign-On", category: "Core Platform" },
  { id: "tenancy_memory", label: "Multi-Tenant Memory", category: "Core Platform" },
  { id: "audit_ledger", label: "Security & Audit Logs", category: "Core Platform" },

  { id: "network_noc", label: "NOC 24/7 Monitoring", category: "Network & Infrastructure" },
  { id: "fno_intel", label: "FNO Fiber Feeds & GIS", category: "Network & Infrastructure" },
  { id: "core_peering", label: "BGP Peering & Transit", category: "Network & Infrastructure" },
  { id: "iot_telemetry", label: "IoT Environmental Sensors", category: "Network & Infrastructure" },
  { id: "coverage_engine", label: "FTTH Feasibility & Map", category: "Network & Infrastructure" },

  { id: "field_dispatch", label: "Field Tech Dispatch", category: "Field & Fleet Ops" },
  { id: "van_stock", label: "Mobile Van Stock Inventory", category: "Field & Fleet Ops" },
  { id: "fleet_tracking", label: "GPS Fleet & Telematics", category: "Field & Fleet Ops" },
  { id: "asset_hardware", label: "Splicer & Optical Hardware", category: "Field & Fleet Ops" },

  { id: "crm_subscribers", label: "CRM & Subscriber 360", category: "Commercial & Customer" },
  { id: "sales_pipeline", label: "Sales Pipeline & Leads", category: "Commercial & Customer" },
  { id: "sales_commission", label: "Sales Commissions Engine", category: "Commercial & Customer" },
  { id: "ai_lead_warming", label: "AI Lead Warming & Agent", category: "Commercial & Customer" },
  { id: "marketing_hub", label: "Ad Campaigns & Inbound", category: "Commercial & Customer" },

  { id: "call_center", label: "Omni-Channel Call Center", category: "Support & Voice" },
  { id: "voicebox_ai", label: "VoiceBox Conversational AI", category: "Support & Voice" },
  { id: "ticketing_desk", label: "Service Desk & SLA Mgmt", category: "Support & Voice" },
  { id: "customer_portal", label: "Subscriber Self-Service", category: "Support & Voice" },

  { id: "billing_engine", label: "Automated Invoicing & Debicheck", category: "Finance & Billing" },
  { id: "finance_ledger", label: "General Ledger & Cost Allocation", category: "Finance & Billing" },
  { id: "procurement", label: "Central Warehouse & Purchasing", category: "Finance & Billing" },

  { id: "talent_pim", label: "Personnel Information (PIM)", category: "Human Capital & Talent" },
  { id: "leave_management", label: "BCEA Statutory Leave", category: "Human Capital & Talent" },
  { id: "shift_rostering", label: "Hourly Demand & Shift Rosters", category: "Human Capital & Talent" },
  { id: "payroll_tax", label: "SARS PAYE & Payslip Engine", category: "Human Capital & Talent" },
  { id: "training_lms", label: "Training & Fiber Certifications", category: "Human Capital & Talent" },
  { id: "compliance_rica", label: "RICA & Regulatory Audit", category: "Human Capital & Talent" },
]

interface PimDirectoryViewProps {
  employees: Employee[]
  loading: boolean
  error: string | null
  onRefresh: () => void
}

export function PimDirectoryView({
  employees,
  loading,
  error,
  onRefresh,
}: PimDirectoryViewProps) {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid")
  const [search, setSearch] = useState("")
  const [deptFilter, setDeptFilter] = useState<string>("ALL")
  const [statusFilter, setStatusFilter] = useState<string>("ALL")
  const [selectedEmp, setSelectedEmp] = useState<Employee | null>(null)
  const [profileTab, setProfileTab] = useState<"overview" | "kpis" | "kudos" | "disciplinary" | "training" | "succession">("overview")
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addModalStep, setAddModalStep] = useState<1 | 2 | 3 | 4 | 5>(1)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Add Employee Form State
  const [formName, setFormName] = useState("")
  const [formEmpCode, setFormEmpCode] = useState("")
  const [formEmail, setFormEmail] = useState("")
  const [formPhone, setFormPhone] = useState("")
  const [formDept, setFormDept] = useState("Network Operations")
  const [formJobTitle, setFormJobTitle] = useState("")
  const [formHireDate, setFormHireDate] = useState(new Date().toISOString().split("T")[0])
  const [formManagerId, setFormManagerId] = useState<string>("")
  const [formGender, setFormGender] = useState("Female")
  const [formAge, setFormAge] = useState("30")
  const [formIdNumber, setFormIdNumber] = useState("")
  const [formTaxNumber, setFormTaxNumber] = useState("")

  // Next of Kin & Banking
  const [formNokName, setFormNokName] = useState("")
  const [formNokRelation, setFormNokRelation] = useState("Spouse")
  const [formNokPhone, setFormNokPhone] = useState("")
  const [formBankName, setFormBankName] = useState("Standard Bank")
  const [formBankAccount, setFormBankAccount] = useState("")
  const [formBranchCode, setFormBranchCode] = useState("051001")
  const [formAccountType, setFormAccountType] = useState("Cheque")

  // Benefits & Beneficiaries
  const [formMedicalAid, setFormMedicalAid] = useState("Discovery Health Classic")
  const [formProvidentFund, setFormProvidentFund] = useState("7.5%")
  const [formFuneralCover, setFormFuneralCover] = useState("Tier 2 - R50,000")
  const [formBeneficiaryName, setFormBeneficiaryName] = useState("")
  const [formBeneficiaryShare, setFormBeneficiaryShare] = useState("100%")

  // Equipment
  const [formWorkstation, setFormWorkstation] = useState("Dell Latitude 5540")
  const [formToolKit, setFormToolKit] = useState("Optical Power Meter + Fiber Stripper")
  const [formSimCard, setFormSimCard] = useState("OmniDome APN SIM (Unlimited)")
  const [formVanId, setFormVanId] = useState("None")

  // 31 Module Access Selection
  const [selectedModules, setSelectedModules] = useState<string[]>([
    "dashboard",
    "network_noc",
    "talent_pim",
    "leave_management",
  ])

  const [submitting, setSubmitting] = useState(false)

  const departments = useMemo(() => {
    const set = new Set(employees.map((e) => e.department).filter(Boolean))
    return Array.from(set).sort()
  }, [employees])

  const filtered = useMemo(() => {
    return employees.filter((e) => {
      const matchSearch =
        e.full_name.toLowerCase().includes(search.toLowerCase()) ||
        e.employee_id.toLowerCase().includes(search.toLowerCase()) ||
        e.job_title.toLowerCase().includes(search.toLowerCase()) ||
        (e.email && e.email.toLowerCase().includes(search.toLowerCase()))
      const matchDept = deptFilter === "ALL" || e.department === deptFilter
      const matchStatus = statusFilter === "ALL" || e.status === statusFilter
      return matchSearch && matchDept && matchStatus
    })
  }, [employees, search, deptFilter, statusFilter])

  // Presets for Module Access Selection
  const applyModulePreset = (preset: "field" | "noc" | "sales" | "admin") => {
    switch (preset) {
      case "field":
        setSelectedModules([
          "dashboard",
          "field_dispatch",
          "van_stock",
          "fleet_tracking",
          "asset_hardware",
          "coverage_engine",
          "leave_management",
          "shift_rostering",
        ])
        break
      case "noc":
        setSelectedModules([
          "dashboard",
          "network_noc",
          "fno_intel",
          "core_peering",
          "iot_telemetry",
          "ticketing_desk",
          "leave_management",
          "shift_rostering",
        ])
        break
      case "sales":
        setSelectedModules([
          "dashboard",
          "crm_subscribers",
          "sales_pipeline",
          "sales_commission",
          "ai_lead_warming",
          "marketing_hub",
          "coverage_engine",
          "leave_management",
        ])
        break
      case "admin":
        setSelectedModules(OMNIDOME_31_MODULES.map((m) => m.id))
        break
    }
  }

  const toggleModule = (modId: string) => {
    setSelectedModules((prev) =>
      prev.includes(modId) ? prev.filter((id) => id !== modId) : [...prev, modId]
    )
  }

  // Handle Add Employee Submit
  const handleAddEmployee = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) {
      alert("Employee full name is required.")
      return
    }

    setSubmitting(true)
    try {
      const code = formEmpCode.trim() || `ISP-${String(employees.length + 1).padStart(3, "0")}`
      const payload: EmployeeCreate = {
        employee_id: code,
        full_name: formName.trim(),
        job_title: formJobTitle.trim(),
        department: formDept,
        hire_date: formHireDate,
        email: formEmail.trim() || undefined,
        phone: formPhone.trim() || undefined,
        manager_id: formManagerId || undefined,
        status: "ACTIVE",
        id_number: formIdNumber.trim() || undefined,
        tax_number: formTaxNumber.trim() || undefined,
      }

      await createEmployee(payload)
      setToastMessage(`Employee ${payload.full_name} (${payload.employee_id}) successfully enrolled!`)
      setTimeout(() => setToastMessage(null), 4000)
      setAddModalOpen(false)
      setAddModalStep(1)
      setFormName("")
      setFormEmpCode("")
      setFormEmail("")
      setFormJobTitle("")
      onRefresh()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to register employee.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/90 px-4 py-3 text-sm text-emerald-200 shadow-xl backdrop-blur">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-bold tracking-tight text-foreground">Personnel Directory (PIM)</h1>
            <Badge variant="outline" className="border-primary/30 text-primary bg-primary/10 text-xs">
              {employees.length} Active Staff
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Centralized workforce records, 360 profile dossiers, statutory compliance, and granular system permissions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="default"
            className="h-8 gap-1.5 text-xs font-medium"
            onClick={() => {
              setFormEmpCode(`ISP-${String(employees.length + 1).padStart(3, "0")}`)
              setAddModalOpen(true)
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            Add Employee
          </Button>

          <div className="flex items-center rounded-lg border border-border bg-card/60 p-0.5">
            <Button
              variant={viewMode === "grid" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setViewMode("grid")}
              title="Grid View"
            >
              <Grid className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant={viewMode === "list" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setViewMode("list")}
              title="Table View"
            >
              <List className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card className="border-border">
        <CardContent className="p-3 sm:p-4">
          <div className="grid gap-3 sm:grid-cols-12">
            <div className="relative sm:col-span-6 lg:col-span-5">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by name, employee code, role, or email…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-9 text-xs"
              />
            </div>

            <div className="sm:col-span-3 lg:col-span-4">
              <select
                value={deptFilter}
                onChange={(e) => setDeptFilter(e.target.value)}
                className="w-full h-9 rounded-md border border-border bg-background px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="ALL">All Departments ({departments.length})</option>
                {departments.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div className="sm:col-span-3 lg:col-span-3">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full h-9 rounded-md border border-border bg-background px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="ALL">All Statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="ONBOARDING">Onboarding</option>
                <option value="EXITING">Exiting</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Directory Grid View */}
      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading personnel records…</div>
      ) : error ? (
        <div className="py-8 text-center text-sm text-red-400">Error: {error}</div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">No personnel records matching your filter criteria.</div>
      ) : viewMode === "grid" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((emp, idx) => {
            const avatarUrl = getEmployeeAvatar(emp.full_name, idx)
            const isExiting = emp.status === "EXITING"
            return (
              <div
                key={emp.id}
                className="group relative flex flex-col justify-between rounded-xl border border-border bg-card/80 p-4 shadow-sm hover:border-primary/50 hover:shadow-md transition-all cursor-pointer backdrop-blur"
                onClick={() => {
                  setSelectedEmp(emp)
                  setProfileTab("overview")
                }}
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <img
                          src={avatarUrl}
                          alt={emp.full_name}
                          className="h-12 w-12 rounded-full object-cover ring-2 ring-border group-hover:ring-primary/50 transition-all"
                        />
                        <span
                          className={`absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-background ${
                            isExiting ? "bg-amber-500" : "bg-emerald-500"
                          }`}
                        />
                      </div>
                      <div>
                        <h3 className="font-semibold text-foreground text-sm group-hover:text-primary transition-colors">
                          {emp.full_name}
                        </h3>
                        <p className="text-xs text-muted-foreground line-clamp-1">{emp.job_title}</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-3.5 space-y-1.5 border-t border-border/50 pt-2.5 text-xs text-muted-foreground">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] text-primary">{emp.employee_id}</span>
                      <Badge variant="outline" className="text-[10px] py-0 px-1.5 font-medium border-border/80">
                        {emp.department}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-1.5 truncate pt-0.5">
                      <Mail className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="truncate">{emp.email || "No email assigned"}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <Phone className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span>{emp.phone || "+27 (011) 884-1000"}</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-border/40 pt-2.5 text-[11px]">
                  <span className="text-muted-foreground">
                    Hired {emp.hire_date ? emp.hire_date.slice(0, 7) : "2024-01"}
                  </span>
                  <span className="font-medium text-primary flex items-center gap-0.5 group-hover:translate-x-0.5 transition-transform">
                    View 360 <ChevronRight className="h-3 w-3" />
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* Table View */
        <Card className="border-border">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="py-2.5 px-4 font-medium">Employee</th>
                    <th className="py-2.5 px-4 font-medium">Code</th>
                    <th className="py-2.5 px-4 font-medium">Department</th>
                    <th className="py-2.5 px-4 font-medium">Role</th>
                    <th className="py-2.5 px-4 font-medium">Status</th>
                    <th className="py-2.5 px-4 font-medium">Hire Date</th>
                    <th className="py-2.5 px-4 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {filtered.map((emp, idx) => (
                    <tr
                      key={emp.id}
                      className="hover:bg-muted/30 transition-colors cursor-pointer"
                      onClick={() => {
                        setSelectedEmp(emp)
                        setProfileTab("overview")
                      }}
                    >
                      <td className="py-2.5 px-4">
                        <div className="flex items-center gap-2.5">
                          <img
                            src={getEmployeeAvatar(emp.full_name, idx)}
                            alt=""
                            className="h-7 w-7 rounded-full object-cover ring-1 ring-border"
                          />
                          <span className="font-semibold text-foreground">{emp.full_name}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 font-mono text-primary">{emp.employee_id}</td>
                      <td className="py-2.5 px-4 text-muted-foreground">{emp.department}</td>
                      <td className="py-2.5 px-4 text-foreground">{emp.job_title}</td>
                      <td className="py-2.5 px-4">
                        <Badge
                          variant="outline"
                          className={
                            emp.status === "ACTIVE"
                              ? "border-emerald-500/40 text-emerald-400"
                              : "border-amber-500/40 text-amber-400"
                          }
                        >
                          {emp.status}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">{emp.hire_date}</td>
                      <td className="py-2.5 px-4 text-right">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-xs text-primary"
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedEmp(emp)
                            setProfileTab("overview")
                          }}
                        >
                          View 360
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── EMPLOYEE 360 DOSSIER DRAWER ─────────────────────────────────── */}
      {selectedEmp && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-all">
          <div className="h-full w-full max-w-2xl bg-card border-l border-border p-6 shadow-2xl overflow-y-auto space-y-6">
            {/* Drawer Header */}
            <div className="flex items-start justify-between border-b border-border pb-4">
              <div className="flex items-center gap-3.5">
                <img
                  src={getEmployeeAvatar(selectedEmp.full_name, 0)}
                  alt=""
                  className="h-16 w-16 rounded-full object-cover ring-2 ring-primary/40 shadow-sm"
                />
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-foreground">{selectedEmp.full_name}</h2>
                    <Badge variant="outline" className="border-primary/40 text-primary font-mono text-xs">
                      {selectedEmp.employee_id}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">{selectedEmp.job_title} • {selectedEmp.department}</p>
                  <p className="text-[11px] text-muted-foreground">Hire Date: {selectedEmp.hire_date}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setSelectedEmp(null)}
                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Navigation Tabs inside 360 */}
            <div className="flex flex-wrap items-center gap-1 border-b border-border pb-2 text-xs">
              {[
                { id: "overview", label: "Overview & Bio" },
                { id: "kpis", label: "KPIs & Performance" },
                { id: "kudos", label: "Kudos & Culture" },
                { id: "disciplinary", label: "Disciplinary Log" },
                { id: "training", label: "Training & Skills" },
                { id: "succession", label: "Succession Plan" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setProfileTab(tab.id as typeof profileTab)}
                  className={`rounded-md px-2.5 py-1.5 font-medium transition-colors ${
                    profileTab === tab.id
                      ? "bg-primary/15 text-primary border border-primary/30"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* TAB CONTENT: Overview (real fields only; redacted fields show a dash) */}
            {profileTab === "overview" && (
              <div className="space-y-4 text-xs">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-border bg-background/40 p-3 space-y-1">
                    <span className="text-muted-foreground">Contact Email</span>
                    <p className="font-semibold text-foreground text-sm">{selectedEmp.email || "—"}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/40 p-3 space-y-1">
                    <span className="text-muted-foreground">Contact Phone</span>
                    <p className="font-semibold text-foreground text-sm">{selectedEmp.phone || "—"}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/40 p-3 space-y-1">
                    <span className="text-muted-foreground">Employment Status</span>
                    <p className="font-semibold text-foreground text-sm">{selectedEmp.status || "—"}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background/40 p-3 space-y-1">
                    <span className="text-muted-foreground">Hire Date</span>
                    <p className="font-semibold text-foreground text-sm">{selectedEmp.hire_date || "—"}</p>
                  </div>
                </div>

                <div className="rounded-lg border border-border bg-muted/20 p-4 space-y-3">
                  <span className="font-semibold text-foreground flex items-center gap-1.5">
                    <Shield className="h-4 w-4 text-cyan-400" /> Identity & Tax (as returned by the HR service; masked for non-admins)
                  </span>
                  <div className="grid gap-2 sm:grid-cols-2 text-muted-foreground">
                    <div>ID Number: <span className="text-foreground font-mono">{selectedEmp.id_number || "—"}</span></div>
                    <div>Tax Number: <span className="text-foreground font-mono">{selectedEmp.tax_number || "—"}</span></div>
                  </div>
                </div>
              </div>
            )}

            {profileTab === "kpis" && (
              <NoDataYet message="KPI scores live in Performance & Objectives. No per-employee operational metrics (SLA, FTF, CSAT) are connected here." />
            )}
            {profileTab === "kudos" && <NoDataYet message="No recognition records are connected for this employee." />}
            {profileTab === "disciplinary" && <NoDataYet message="Open Disciplinary & Grievances for this employee's real records." />}
            {profileTab === "training" && <NoDataYet message="Open Training & Development for this employee's real enrolments." />}
            {profileTab === "succession" && <NoDataYet message="No succession plan is recorded for this employee." />}
          </div>
        </div>
      )}

      {/* ── ADD EMPLOYEE MULTI-STEP WIZARD MODAL ───────────────────────── */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-3xl border-border shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3 bg-muted/20">
              <div>
                <CardTitle className="text-base font-bold">New Personnel Registration</CardTitle>
                <CardDescription className="text-xs">
                  Step {addModalStep} of 5: {
                    addModalStep === 1 ? "Core Details & Role" :
                    addModalStep === 2 ? "Next of Kin & Banking Information" :
                    addModalStep === 3 ? "Benefits, Medical Aid & Beneficiaries" :
                    addModalStep === 4 ? "Equipment & Assigned Hardware Assets" :
                    "OmniDome 31-Module Permissions Matrix"
                  }
                </CardDescription>
              </div>
              <button
                type="button"
                onClick={() => setAddModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>

            {/* Stepper Progress Indicator */}
            <div className="flex border-b border-border bg-card px-4 py-2 text-xs">
              {[
                { step: 1, label: "Core Profile" },
                { step: 2, label: "Kin & Banking" },
                { step: 3, label: "Benefits" },
                { step: 4, label: "Equipment" },
                { step: 5, label: "31 Modules" },
              ].map((s) => (
                <button
                  key={s.step}
                  type="button"
                  onClick={() => setAddModalStep(s.step as typeof addModalStep)}
                  className={`flex-1 py-1 text-center font-medium border-b-2 transition-all ${
                    addModalStep === s.step
                      ? "border-primary text-primary font-bold"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {s.step}. {s.label}
                </button>
              ))}
            </div>

            <form onSubmit={handleAddEmployee} className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* STEP 1: Core Profile */}
              {addModalStep === 1 && (
                <div className="space-y-4 text-xs">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Full Name *</label>
                      <Input
                        required
                        placeholder="e.g. Sipho Sithole"
                        value={formName}
                        onChange={(e) => setFormName(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Employee ID Code *</label>
                      <Input
                        required
                        value={formEmpCode}
                        onChange={(e) => setFormEmpCode(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Corporate Email</label>
                      <Input
                        type="email"
                        placeholder="s.sithole@omnidome.co.za"
                        value={formEmail}
                        onChange={(e) => setFormEmail(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Mobile Phone</label>
                      <Input
                        placeholder="+27 (072) 123-4567"
                        value={formPhone}
                        onChange={(e) => setFormPhone(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Department</label>
                      <select
                        value={formDept}
                        onChange={(e) => setFormDept(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="Network Operations">Network Operations (NOC)</option>
                        <option value="Core Infrastructure">Core Infrastructure</option>
                        <option value="Field Operations">Field Operations</option>
                        <option value="Customer Support">Customer Support</option>
                        <option value="Sales">Sales & Commercial</option>
                        <option value="Marketing">Marketing</option>
                        <option value="Finance">Finance & Billing</option>
                        <option value="Human Resources">Human Resources</option>
                        <option value="Executive">Executive</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Job Title</label>
                      <Input
                        placeholder="e.g. Senior Optical Splicer"
                        value={formJobTitle}
                        onChange={(e) => setFormJobTitle(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Gender</label>
                      <select
                        value={formGender}
                        onChange={(e) => setFormGender(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="Female">Female</option>
                        <option value="Male">Male</option>
                        <option value="Non-Binary">Non-Binary</option>
                        <option value="Prefer not to say">Prefer not to say</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Age</label>
                      <Input
                        type="number"
                        value={formAge}
                        onChange={(e) => setFormAge(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Hire Date</label>
                      <Input
                        type="date"
                        value={formHireDate}
                        onChange={(e) => setFormHireDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">RSA ID Number</label>
                      <Input
                        placeholder="890412 5082 083"
                        value={formIdNumber}
                        onChange={(e) => setFormIdNumber(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">SARS Tax Reference</label>
                      <Input
                        placeholder="9842109482"
                        value={formTaxNumber}
                        onChange={(e) => setFormTaxNumber(e.target.value)}
                        className="h-8 text-xs font-mono"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 2: Kin & Banking */}
              {addModalStep === 2 && (
                <div className="space-y-4 text-xs">
                  <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <HeartHandshake className="h-4 w-4 text-cyan-400" /> Next of Kin (Emergency Contact)
                    </span>
                    <div className="grid gap-3 sm:grid-cols-3 pt-1">
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Full Name</label>
                        <Input
                          placeholder="e.g. Nandi Sithole"
                          value={formNokName}
                          onChange={(e) => setFormNokName(e.target.value)}
                          className="h-8 text-xs"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Relationship</label>
                        <select
                          value={formNokRelation}
                          onChange={(e) => setFormNokRelation(e.target.value)}
                          className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                        >
                          <option value="Spouse">Spouse</option>
                          <option value="Parent">Parent</option>
                          <option value="Sibling">Sibling</option>
                          <option value="Child">Child</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Contact Phone</label>
                        <Input
                          placeholder="+27 (083) 987-6543"
                          value={formNokPhone}
                          onChange={(e) => setFormNokPhone(e.target.value)}
                          className="h-8 text-xs"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <CreditCard className="h-4 w-4 text-primary" /> Banking & Payout Details
                    </span>
                    <div className="grid gap-3 sm:grid-cols-2 pt-1">
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Bank Name</label>
                        <select
                          value={formBankName}
                          onChange={(e) => setFormBankName(e.target.value)}
                          className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                        >
                          <option value="Standard Bank">Standard Bank</option>
                          <option value="First National Bank (FNB)">First National Bank (FNB)</option>
                          <option value="ABSA Bank">ABSA Bank</option>
                          <option value="Nedbank">Nedbank</option>
                          <option value="Capitec Bank">Capitec Bank</option>
                        </select>
                      </div>
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Account Number</label>
                        <Input
                          placeholder="1012938472"
                          value={formBankAccount}
                          onChange={(e) => setFormBankAccount(e.target.value)}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Branch Code</label>
                        <Input
                          value={formBranchCode}
                          onChange={(e) => setFormBranchCode(e.target.value)}
                          className="h-8 text-xs font-mono"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="font-medium text-muted-foreground">Account Type</label>
                        <select
                          value={formAccountType}
                          onChange={(e) => setFormAccountType(e.target.value)}
                          className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                        >
                          <option value="Cheque">Cheque / Current</option>
                          <option value="Savings">Savings</option>
                          <option value="Transmission">Transmission</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 3: Benefits */}
              {addModalStep === 3 && (
                <div className="space-y-4 text-xs">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Medical Aid Scheme</label>
                      <select
                        value={formMedicalAid}
                        onChange={(e) => setFormMedicalAid(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="Discovery Health Classic">Discovery Health Classic Comprehensive</option>
                        <option value="Discovery Health Essential">Discovery Health Essential Delta</option>
                        <option value="Momentum Custom">Momentum Custom Option</option>
                        <option value="Opt-Out">Opt-Out / Private Scheme</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Provident / Pension Contribution</label>
                      <select
                        value={formProvidentFund}
                        onChange={(e) => setFormProvidentFund(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="5.0%">5.0% Employee / 5.0% Employer</option>
                        <option value="7.5%">7.5% Employee / 7.5% Employer (Recommended)</option>
                        <option value="10.0%">10.0% Employee / 10.0% Employer</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Group Life & Funeral Cover</label>
                      <select
                        value={formFuneralCover}
                        onChange={(e) => setFormFuneralCover(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="Tier 1 - R30,000">Tier 1 - R30,000 Principal + Spouse</option>
                        <option value="Tier 2 - R50,000">Tier 2 - R50,000 Comprehensive Family</option>
                        <option value="Tier 3 - R100,000">Tier 3 - R100,000 Executive Extended</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Primary Beneficiary Name</label>
                      <Input
                        placeholder="e.g. Nandi Sithole"
                        value={formBeneficiaryName}
                        onChange={(e) => setFormBeneficiaryName(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 4: Equipment */}
              {addModalStep === 4 && (
                <div className="space-y-4 text-xs">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Assigned Workstation / Laptop</label>
                      <select
                        value={formWorkstation}
                        onChange={(e) => setFormWorkstation(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="Dell Latitude 5540">Dell Latitude 5540 (Core i7, 32GB RAM)</option>
                        <option value="MacBook Pro 14 M3">Apple MacBook Pro 14" M3</option>
                        <option value="Lenovo ThinkPad T14">Lenovo ThinkPad T14 Gen 4</option>
                        <option value="NOC Rugged Field Laptop">NOC Ruggedized Panasonic Toughbook</option>
                        <option value="None">None (Fixed Workstation)</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Field Tools & Testing Hardware</label>
                      <select
                        value={formToolKit}
                        onChange={(e) => setFormToolKit(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="Optical Power Meter + Fiber Stripper">Optical Power Meter + VFL + Cleaver</option>
                        <option value="Fujikura 90S Fusion Splicer Kit">Fujikura 90S+ Core-Alignment Fusion Splicer</option>
                        <option value="EXFO OTDR Optical Reflectometer">EXFO FTB-1v2 OTDR Testing Kit</option>
                        <option value="None">None (Office Based)</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Mobile SIM & APN Access</label>
                      <select
                        value={formSimCard}
                        onChange={(e) => setFormSimCard(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="OmniDome APN SIM (Unlimited)">OmniDome Private APN (Unlimited 5G)</option>
                        <option value="Standard MTN 50GB">MTN Business Corporate 50GB</option>
                        <option value="Standard Vodacom 50GB">Vodacom Business Corporate 50GB</option>
                        <option value="None">None</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="font-medium text-foreground">Assigned Fleet Service Van</label>
                      <select
                        value={formVanId}
                        onChange={(e) => setFormVanId(e.target.value)}
                        className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                      >
                        <option value="None">None (Unassigned / Office)</option>
                        <option value="VAN-ISP-001">VAN-ISP-001 (Toyota Quantum Fiber 1)</option>
                        <option value="VAN-ISP-002">VAN-ISP-002 (Toyota Quantum Fiber 2)</option>
                        <option value="VAN-ISP-003">VAN-ISP-003 (Isuzu D-Max Splicer)</option>
                        <option value="VAN-ISP-004">VAN-ISP-004 (Ford Ranger Rapid Response)</option>
                      </select>
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 5: 31 Module Access Matrix */}
              {addModalStep === 5 && (
                <div className="space-y-4 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
                    <div>
                      <p className="font-semibold text-foreground">Select Eligible OmniDome Modules (31 Total)</p>
                      <p className="text-muted-foreground text-[11px]">
                        Choose from role presets or individually check module entitlements for this staff member.
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-[11px]"
                        onClick={() => applyModulePreset("field")}
                      >
                        Field Ops Preset
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-[11px]"
                        onClick={() => applyModulePreset("noc")}
                      >
                        NOC Preset
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-[11px]"
                        onClick={() => applyModulePreset("sales")}
                      >
                        Sales Preset
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 text-[11px]"
                        onClick={() => applyModulePreset("admin")}
                      >
                        All 31 Modules
                      </Button>
                    </div>
                  </div>

                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 max-h-[300px] overflow-y-auto pr-1">
                    {OMNIDOME_31_MODULES.map((m) => {
                      const isSelected = selectedModules.includes(m.id)
                      return (
                        <div
                          key={m.id}
                          onClick={() => toggleModule(m.id)}
                          className={`flex items-start gap-2.5 rounded-lg border p-2.5 transition-all cursor-pointer ${
                            isSelected
                              ? "border-primary/60 bg-primary/10 text-foreground"
                              : "border-border/60 bg-muted/10 text-muted-foreground hover:border-border hover:bg-muted/30"
                          }`}
                        >
                          <div
                            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                              isSelected
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-muted-foreground/40"
                            }`}
                          >
                            {isSelected && <Check className="h-3 w-3" />}
                          </div>
                          <div>
                            <p className="font-semibold text-foreground text-xs">{m.label}</p>
                            <p className="text-[10px] text-muted-foreground">{m.category}</p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Modal Navigation Buttons */}
              <div className="flex items-center justify-between border-t border-border pt-4">
                {addModalStep > 1 ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setAddModalStep((s) => (s - 1) as typeof addModalStep)}
                  >
                    Back
                  </Button>
                ) : (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setAddModalOpen(false)}>
                    Cancel
                  </Button>
                )}

                {addModalStep < 5 ? (
                  <Button
                    type="button"
                    variant="default"
                    size="sm"
                    onClick={() => setAddModalStep((s) => (s + 1) as typeof addModalStep)}
                  >
                    Next: {
                      addModalStep === 1 ? "Kin & Banking" :
                      addModalStep === 2 ? "Benefits" :
                      addModalStep === 3 ? "Equipment" : "31 Modules"
                    }
                  </Button>
                ) : (
                  <Button type="submit" variant="default" size="sm" disabled={submitting}>
                    {submitting ? "Creating Staff Profile…" : "Complete Registration"}
                  </Button>
                )}
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
