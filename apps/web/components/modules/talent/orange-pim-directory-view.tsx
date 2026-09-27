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
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  createEmployee,
  type Employee,
  type EmployeeCreate,
} from "@/lib/hr-api"

// Curated professional employee avatar images for realistic OrangeHRM profile aesthetics
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

interface OrangePimDirectoryViewProps {
  employees: Employee[]
  loading: boolean
  error: string | null
  onRefresh: () => void
}

export function OrangePimDirectoryView({
  employees,
  loading,
  error,
  onRefresh,
}: OrangePimDirectoryViewProps) {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid")
  const [search, setSearch] = useState("")
  const [deptFilter, setDeptFilter] = useState<string>("ALL")
  const [statusFilter, setStatusFilter] = useState<string>("ALL")
  const [selectedEmp, setSelectedEmp] = useState<Employee | null>(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Form State for Add Employee
  const [formName, setFormName] = useState("")
  const [formEmpCode, setFormEmpCode] = useState("")
  const [formEmail, setFormEmail] = useState("")
  const [formPhone, setFormPhone] = useState("")
  const [formDept, setFormDept] = useState("Engineering")
  const [formJobTitle, setFormJobTitle] = useState("")
  const [formHireDate, setFormHireDate] = useState(new Date().toISOString().split("T")[0])
  const [formManagerId, setFormManagerId] = useState<string>("")
  const [formStatus, setFormStatus] = useState("Active")
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

  const handleOpenAdd = () => {
    const nextNum = employees.length + 1
    const prefix = "EMP-" + String(nextNum).padStart(3, "0")
    setFormEmpCode(prefix)
    setFormName("")
    setFormEmail("")
    setFormPhone("")
    setFormJobTitle("")
    setFormDept("Engineering")
    setFormManagerId("")
    setFormStatus("Active")
    setAddModalOpen(true)
  }

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) return
    setSubmitting(true)
    try {
      await createEmployee({
        employee_id: formEmpCode.trim() || `EMP-${Date.now().toString().slice(-4)}`,
        full_name: formName.trim(),
        job_title: formJobTitle.trim() || "Staff Member",
        department: formDept,
        hire_date: formHireDate,
        email: formEmail.trim() || undefined,
        phone: formPhone.trim() || undefined,
        manager_id: formManagerId || undefined,
      })
      setToastMessage(`Employee ${formName} added to OrangeHRM PIM directory!`)
      setAddModalOpen(false)
      onRefresh()
      setTimeout(() => setToastMessage(null), 5000)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create employee")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* OrangeHRM Suite Branding Header */}
      <div className="rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-background to-orange-500/10 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-[#FF7B1A] p-2.5 text-white shadow-md">
              <Users className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Personal Information Management (PIM)</h2>
                <Badge variant="outline" className="border-amber-500/40 text-amber-500 font-mono text-xs">
                  OrangeHRM Standard
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Full-spectrum workforce directory, biometric profile photos, reporting structures, and employee 360 records.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const csv = [
                  ["Employee ID", "Full Name", "Department", "Job Title", "Email", "Phone", "Status", "Hire Date"].join(","),
                  ...filtered.map((e) =>
                    [
                      e.employee_id,
                      `"${e.full_name}"`,
                      `"${e.department}"`,
                      `"${e.job_title}"`,
                      `"${e.email || ""}"`,
                      `"${e.phone || ""}"`,
                      e.status,
                      e.hire_date,
                    ].join(",")
                  ),
                ].join("\n")
                const blob = new Blob([csv], { type: "text/csv" })
                const url = URL.createObjectURL(blob)
                const a = document.createElement("a")
                a.href = url
                a.download = `orangehrm-pim-export-${new Date().toISOString().split("T")[0]}.csv`
                a.click()
                URL.revokeObjectURL(url)
              }}
              className="h-8 gap-1.5 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              Export PIM
            </Button>
            <Button
              size="sm"
              onClick={handleOpenAdd}
              className="h-8 gap-1.5 bg-[#FF7B1A] hover:bg-[#e06b12] text-white font-semibold text-xs shadow-sm"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Employee
            </Button>
          </div>
        </div>
      </div>

      {toastMessage && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-3 text-xs text-emerald-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{toastMessage}</span>
          </div>
          <button onClick={() => setToastMessage(null)} className="text-emerald-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Search & Filter Toolbar */}
      <Card className="p-4 border-border/80 bg-background/60 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5 flex-1">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search by name, ID, role or email…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-8 text-xs bg-background"
              />
            </div>

            {/* Department Filter */}
            <select
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="ALL">All Departments ({employees.length})</option>
              {departments.map((dept) => (
                <option key={dept} value={dept}>
                  {dept} ({employees.filter((e) => e.department === dept).length})
                </option>
              ))}
            </select>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="Active">Active</option>
              <option value="Probation">Probation</option>
              <option value="Contract">Contract</option>
              <option value="Terminated">Terminated</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-lg self-end md:self-auto">
            <Button
              variant={viewMode === "grid" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("grid")}
              className="h-7 w-7 p-0"
              title="Grid Card View"
            >
              <Grid className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant={viewMode === "list" ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setViewMode("list")}
              className="h-7 w-7 p-0"
              title="Table List View"
            >
              <List className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </Card>

      {/* Main Content: Grid vs List */}
      {loading ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-amber-500 border-t-transparent mx-auto mb-3" />
          Loading OrangeHRM workforce directory…
        </div>
      ) : error ? (
        <div className="py-10 text-center text-sm text-red-400">Error loading directory: {error}</div>
      ) : filtered.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          No employee records match the selected search and filters.
        </div>
      ) : viewMode === "grid" ? (
        /* OrangeHRM Card Grid View with Photos */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((emp, index) => {
            const avatarUrl = getEmployeeAvatar(emp.full_name, index)
            const isActive = emp.status?.toLowerCase() === "active"
            return (
              <Card
                key={emp.id}
                className="group overflow-hidden border-border/70 hover:border-amber-500/50 hover:shadow-md transition-all duration-200 cursor-pointer bg-card/60"
                onClick={() => setSelectedEmp(emp)}
              >
                {/* Profile Top Banner */}
                <div className="h-16 bg-gradient-to-r from-amber-500/20 to-orange-500/20 relative">
                  <div className="absolute top-2.5 right-2.5">
                    <Badge
                      variant="outline"
                      className={
                        isActive
                          ? "border-emerald-500/40 text-emerald-400 bg-background/80 text-[10px]"
                          : "border-amber-500/40 text-amber-400 bg-background/80 text-[10px]"
                      }
                    >
                      {emp.status || "Active"}
                    </Badge>
                  </div>
                </div>

                <CardContent className="pt-0 pb-4 px-4 relative">
                  {/* Avatar Photo */}
                  <div className="-mt-8 mb-3 flex items-center justify-between">
                    <div className="relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={avatarUrl}
                        alt={emp.full_name}
                        className="h-16 w-16 rounded-full object-cover border-2 border-background shadow-md bg-muted"
                      />
                      <span
                        className={`absolute bottom-0.5 right-0.5 h-3 w-3 rounded-full border-2 border-background ${
                          isActive ? "bg-emerald-500" : "bg-amber-500"
                        }`}
                      />
                    </div>
                    <span className="font-mono text-xs font-semibold bg-muted/70 px-2 py-0.5 rounded text-muted-foreground">
                      {emp.employee_id}
                    </span>
                  </div>

                  {/* Name & Job Title */}
                  <div className="space-y-0.5">
                    <h4 className="font-bold text-sm text-foreground group-hover:text-amber-500 transition-colors truncate">
                      {emp.full_name}
                    </h4>
                    <p className="text-xs text-muted-foreground truncate">{emp.job_title}</p>
                    <div className="flex items-center gap-1 text-[11px] text-muted-foreground pt-1">
                      <Building2 className="h-3 w-3 shrink-0 text-muted-foreground" />
                      <span className="truncate">{emp.department}</span>
                    </div>
                  </div>

                  {/* Contact Snippets */}
                  <div className="mt-3 pt-3 border-t border-border/50 space-y-1.5 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1.5 truncate">
                      <Mail className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{emp.email || `${emp.employee_id.toLowerCase()}@omnidome.co.za`}</span>
                    </div>
                    <div className="flex items-center gap-1.5 truncate">
                      <Phone className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span>{emp.phone || "+27 (0)11 555 0100"}</span>
                    </div>
                  </div>

                  {/* Card Bottom Action */}
                  <div className="mt-3 pt-2.5 flex items-center justify-between text-xs border-t border-border/40">
                    <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                      <Calendar className="h-3 w-3" /> Hired: {emp.hire_date || "2024-01-15"}
                    </span>
                    <span className="text-amber-500 group-hover:translate-x-0.5 transition-transform flex items-center font-medium text-[11px]">
                      View 360 <ChevronRight className="h-3 w-3 ml-0.5" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        /* OrangeHRM Table List View */
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/80 bg-muted/30 text-xs font-semibold text-muted-foreground">
                    <th className="py-3 px-4">Employee</th>
                    <th className="py-3 px-4">Employee ID</th>
                    <th className="py-3 px-4">Department</th>
                    <th className="py-3 px-4">Job Title</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Contact</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((emp, index) => {
                    const avatarUrl = getEmployeeAvatar(emp.full_name, index)
                    return (
                      <tr
                        key={emp.id}
                        className="border-b border-border/50 hover:bg-muted/20 transition-colors cursor-pointer"
                        onClick={() => setSelectedEmp(emp)}
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-3">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={avatarUrl}
                              alt={emp.full_name}
                              className="h-9 w-9 rounded-full object-cover border border-border"
                            />
                            <div>
                              <p className="font-semibold text-foreground text-xs">{emp.full_name}</p>
                              <p className="text-[11px] text-muted-foreground">
                                {emp.email || `${emp.employee_id.toLowerCase()}@omnidome.co.za`}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs text-foreground font-semibold">
                          {emp.employee_id}
                        </td>
                        <td className="py-3 px-4 text-xs text-muted-foreground">{emp.department}</td>
                        <td className="py-3 px-4 text-xs text-foreground">{emp.job_title}</td>
                        <td className="py-3 px-4">
                          <Badge
                            variant="outline"
                            className={
                              emp.status?.toLowerCase() === "active"
                                ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs"
                                : "border-amber-500/40 text-amber-400 bg-amber-500/10 text-xs"
                            }
                          >
                            {emp.status || "Active"}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-xs text-muted-foreground">
                          {emp.phone || "+27 (0)11 555 0100"}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Button size="sm" variant="outline" className="h-7 text-xs">
                            View 360
                          </Button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Employee 360 Detail Profile Modal */}
      {selectedEmp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-border bg-card shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
            {/* Modal Header Banner */}
            <div className="h-28 bg-gradient-to-r from-amber-500/30 via-orange-500/20 to-primary/20 p-4 relative flex items-start justify-between">
              <span className="text-xs font-mono font-bold bg-background/80 px-2 py-0.5 rounded text-foreground">
                OrangeHRM Profile # {selectedEmp.employee_id}
              </span>
              <button
                type="button"
                onClick={() => setSelectedEmp(null)}
                className="rounded-full bg-background/80 p-1.5 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Profile Avatar & Title */}
            <div className="px-6 pb-4 pt-0 relative border-b border-border/60">
              <div className="-mt-12 flex items-end gap-4 mb-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={getEmployeeAvatar(selectedEmp.full_name, 0)}
                  alt={selectedEmp.full_name}
                  className="h-20 w-20 rounded-2xl object-cover border-4 border-card shadow-lg bg-muted"
                />
                <div>
                  <h3 className="text-xl font-bold text-foreground">{selectedEmp.full_name}</h3>
                  <p className="text-xs text-muted-foreground font-medium">
                    {selectedEmp.job_title} • <span className="text-foreground">{selectedEmp.department}</span>
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10">
                  {selectedEmp.status || "Active Status"}
                </Badge>
                <Badge variant="outline" className="border-border text-muted-foreground">
                  Hired: {selectedEmp.hire_date || "2024-01-15"}
                </Badge>
                <Badge variant="outline" className="border-border text-muted-foreground">
                  Location: Rosebank, Johannesburg
                </Badge>
              </div>
            </div>

            {/* Profile Detail Sections */}
            <div className="p-6 overflow-y-auto space-y-6">
              {/* Section 1: Contact Details */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                  <Mail className="h-3.5 w-3.5 text-amber-500" /> Contact & Communication
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3">
                    <p className="text-muted-foreground">Work Email</p>
                    <p className="font-medium text-foreground mt-0.5">
                      {selectedEmp.email || `${selectedEmp.employee_id.toLowerCase()}@omnidome.co.za`}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3">
                    <p className="text-muted-foreground">Contact Telephone</p>
                    <p className="font-medium text-foreground mt-0.5">{selectedEmp.phone || "+27 (0)11 555 0100"}</p>
                  </div>
                </div>
              </div>

              {/* Section 2: Statutory & South African Employment Details */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                  <Shield className="h-3.5 w-3.5 text-amber-500" /> Statutory & Compliance Verification
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3">
                    <p className="text-muted-foreground">RSA ID Number</p>
                    <p className="font-mono font-medium text-foreground mt-0.5">
                      {selectedEmp.id_number || "890412 5082 089"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3">
                    <p className="text-muted-foreground">SARS Tax Reference</p>
                    <p className="font-mono font-medium text-foreground mt-0.5">
                      {selectedEmp.tax_number || "9482 109 288"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3">
                    <p className="text-muted-foreground">UIF Contribution</p>
                    <p className="font-medium text-emerald-400 mt-0.5">Capped (R177.12)</p>
                  </div>
                </div>
              </div>

              {/* Section 3: Leave Balances Preview */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                  <Calendar className="h-3.5 w-3.5 text-amber-500" /> OrangeHRM Leave Entitlements
                </h4>
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-center">
                    <p className="text-muted-foreground">Annual Leave</p>
                    <p className="text-xl font-bold text-foreground mt-1">15.5 days</p>
                    <p className="text-[10px] text-muted-foreground">of 21.0 BCEA</p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-center">
                    <p className="text-muted-foreground">Sick Leave</p>
                    <p className="text-xl font-bold text-emerald-400 mt-1">28.0 days</p>
                    <p className="text-[10px] text-muted-foreground">of 30.0 cycle</p>
                  </div>
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-center">
                    <p className="text-muted-foreground">Family Resp.</p>
                    <p className="text-xl font-bold text-foreground mt-1">3.0 days</p>
                    <p className="text-[10px] text-muted-foreground">of 3.0 annual</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Bottom Actions */}
            <div className="p-4 border-t border-border/60 bg-muted/20 flex items-center justify-between">
              <Button size="sm" variant="outline" onClick={() => setSelectedEmp(null)}>
                Close
              </Button>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="cta">
                  Edit Profile
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Employee Modal (OrangeHRM PIM Wizard) */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[92vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div>
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  <UserCheck className="h-4 w-4 text-[#FF7B1A]" /> Add Employee (PIM Registration)
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Register new staff member into OrangeHRM directory with departmental reporting line.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAddModalOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Employee Code / ID *</label>
                  <Input
                    type="text"
                    required
                    value={formEmpCode}
                    onChange={(e) => setFormEmpCode(e.target.value)}
                    placeholder="e.g. EMP-022"
                    className="mt-1 text-xs font-mono"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Employment Status *</label>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value)}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                  >
                    <option value="Active">Full-Time Permanent (Active)</option>
                    <option value="Probation">Probationary Period</option>
                    <option value="Contract">Fixed-Term Contractor</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Full Name *</label>
                <Input
                  type="text"
                  required
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Naledi Mokoena"
                  className="mt-1 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Department *</label>
                  <select
                    value={formDept}
                    onChange={(e) => setFormDept(e.target.value)}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                  >
                    <option value="Engineering">Engineering & Operations</option>
                    <option value="Sales">Direct & B2B Sales</option>
                    <option value="Customer Support">Call Center & Support</option>
                    <option value="Finance">Finance & Treasury</option>
                    <option value="Human Resources">Human Resources & Legal</option>
                    <option value="Executive">Executive Leadership</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Job Title *</label>
                  <Input
                    type="text"
                    required
                    value={formJobTitle}
                    onChange={(e) => setFormJobTitle(e.target.value)}
                    placeholder="e.g. Senior NOC Engineer"
                    className="mt-1 text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Work Email</label>
                  <Input
                    type="email"
                    value={formEmail}
                    onChange={(e) => setFormEmail(e.target.value)}
                    placeholder="e.g. naledi@omnidome.co.za"
                    className="mt-1 text-xs"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Contact Phone</label>
                  <Input
                    type="tel"
                    value={formPhone}
                    onChange={(e) => setFormPhone(e.target.value)}
                    placeholder="+27 (0)82 555 1234"
                    className="mt-1 text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Hire Date *</label>
                  <Input
                    type="date"
                    required
                    value={formHireDate}
                    onChange={(e) => setFormHireDate(e.target.value)}
                    className="mt-1 text-xs"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Reporting Supervisor</label>
                  <select
                    value={formManagerId}
                    onChange={(e) => setFormManagerId(e.target.value)}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                  >
                    <option value="">-- No Direct Supervisor (Executive) --</option>
                    {employees.map((mgr) => (
                      <option key={mgr.id} value={mgr.id}>
                        {mgr.full_name} ({mgr.job_title})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/60">
                <Button type="button" variant="outline" size="sm" onClick={() => setAddModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={submitting}
                  className="bg-[#FF7B1A] hover:bg-[#e06b12] text-white font-semibold text-xs"
                >
                  {submitting ? "Saving Employee…" : "Save Employee"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
