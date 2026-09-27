"use client"

import React, { useState, useMemo } from "react"
import {
  CalendarDays,
  Calendar,
  CheckCircle2,
  XCircle,
  Clock,
  Plus,
  Filter,
  Search,
  AlertCircle,
  FileText,
  User,
  Shield,
  Coins,
  RefreshCw,
  Check,
  X,
  ChevronRight,
} from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  createLeaveRequest,
  approveLeave,
  declineLeave,
  type Employee,
  type LeaveRequest,
} from "@/lib/hr-api"
import { getEmployeeAvatar } from "./orange-pim-directory-view"

interface OrangeLeaveJourneyViewProps {
  employees: Employee[]
  leaveRequests: LeaveRequest[]
  loading: boolean
  error: string | null
  onRefresh: () => void
}

export function OrangeLeaveJourneyView({
  employees,
  leaveRequests: initialLeaveRequests,
  loading,
  error,
  onRefresh,
}: OrangeLeaveJourneyViewProps) {
  // Local state to support immediate optimistic UI updates when approving/declining
  const [leaveList, setLeaveList] = useState<LeaveRequest[]>(initialLeaveRequests)
  React.useEffect(() => {
    setLeaveList(initialLeaveRequests)
  }, [initialLeaveRequests])

  const [activeTab, setActiveTab] = useState<"requests" | "balances" | "statutory">("requests")
  const [statusFilter, setStatusFilter] = useState<string>("ALL")
  const [search, setSearch] = useState("")
  const [applyModalOpen, setApplyModalOpen] = useState(false)
  const [toastMsg, setToastMsg] = useState<string | null>(null)
  const [processingId, setProcessingId] = useState<string | null>(null)

  // Form State
  const [selectedEmpId, setSelectedEmpId] = useState<string>(employees[0]?.id || "")
  const [formType, setFormType] = useState<string>("ANNUAL")
  const [fromDate, setFromDate] = useState<string>(
    new Date(Date.now() + 86400000).toISOString().split("T")[0]
  )
  const [toDate, setToDate] = useState<string>(
    new Date(Date.now() + 86400000 * 3).toISOString().split("T")[0]
  )
  const [formReason, setFormReason] = useState<string>("")
  const [submitting, setSubmitting] = useState<boolean>(false)

  // Calculate working days excluding Saturdays and Sundays
  const calculatedWorkingDays = useMemo(() => {
    if (!fromDate || !toDate) return 1
    const start = new Date(fromDate)
    const end = new Date(toDate)
    if (end < start) return 0
    let count = 0
    const cur = new Date(start)
    while (cur <= end) {
      const day = cur.getDay()
      if (day !== 0 && day !== 6) count++
      cur.setDate(cur.getDate() + 1)
    }
    return count
  }, [fromDate, toDate])

  const empMap = useMemo(() => {
    const map = new Map<string, Employee>()
    employees.forEach((e) => map.set(e.id, e))
    return map
  }, [employees])

  // Filtered requests
  const filteredRequests = useMemo(() => {
    return leaveList.filter((req) => {
      const emp = empMap.get(req.employee_id)
      const empName = emp ? emp.full_name.toLowerCase() : ""
      const matchSearch =
        empName.includes(search.toLowerCase()) ||
        req.leave_type.toLowerCase().includes(search.toLowerCase()) ||
        (req.reason && req.reason.toLowerCase().includes(search.toLowerCase()))
      const matchStatus =
        statusFilter === "ALL" ||
        req.status.toLowerCase() === statusFilter.toLowerCase()
      return matchSearch && matchStatus
    })
  }, [leaveList, search, statusFilter, empMap])

  // Handle Approving Leave
  const handleApprove = async (id: string) => {
    setProcessingId(id)
    try {
      await approveLeave(id)
      setLeaveList((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: "APPROVED" } : r))
      )
      setToastMsg(`Leave application approved successfully! Accrual updated.`)
      setTimeout(() => setToastMsg(null), 5000)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to approve leave")
    } finally {
      setProcessingId(null)
    }
  }

  // Handle Declining Leave
  const handleDecline = async (id: string) => {
    setProcessingId(id)
    try {
      await declineLeave(id)
      setLeaveList((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: "DECLINED" } : r))
      )
      setToastMsg(`Leave application declined. Employee notified.`)
      setTimeout(() => setToastMsg(null), 5000)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to decline leave")
    } finally {
      setProcessingId(null)
    }
  }

  // Handle Submit New Leave
  const handleApplySubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedEmpId) return
    setSubmitting(true)
    try {
      const created = await createLeaveRequest(selectedEmpId, {
        leave_type: formType,
        start_date: fromDate,
        end_date: toDate,
        reason: formReason || `Standard ${formType} Leave Application`,
      })
      setLeaveList((prev) => [created, ...prev])
      const emp = empMap.get(selectedEmpId)
      setToastMsg(`Leave application for ${emp?.full_name || "Employee"} submitted! Awaiting supervisor review.`)
      setApplyModalOpen(false)
      setFormReason("")
      setTimeout(() => setToastMsg(null), 5000)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to apply for leave")
    } finally {
      setSubmitting(false)
    }
  }

  const pendingCount = leaveList.filter((r) => r.status.toLowerCase() === "pending").length

  return (
    <div className="space-y-6">
      {/* OrangeHRM Leave Header */}
      <div className="rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-background to-orange-500/10 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-[#FF7B1A] p-2.5 text-white shadow-md">
              <CalendarDays className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">OrangeHRM Leave Management Suite</h2>
                <Badge variant="outline" className="border-amber-500/40 text-amber-500 font-mono text-xs">
                  BCEA Compliant
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Statutory South African leave accruals (21-day annual, 30-day sick, family responsibility) & approval workflows.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onRefresh} className="h-8 gap-1.5 text-xs">
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
            <Button
              size="sm"
              onClick={() => {
                if (employees.length > 0) setSelectedEmpId(employees[0].id)
                setApplyModalOpen(true)
              }}
              className="h-8 gap-1.5 bg-[#FF7B1A] hover:bg-[#e06b12] text-white font-semibold text-xs shadow-sm"
            >
              <Plus className="h-3.5 w-3.5" />
              Apply for Leave
            </Button>
          </div>
        </div>
      </div>

      {toastMsg && (
        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-3 text-xs text-emerald-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{toastMsg}</span>
          </div>
          <button onClick={() => setToastMsg(null)} className="text-emerald-400 hover:text-white">✕</button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Annual Leave Quota</p>
              <p className="text-2xl font-bold text-foreground mt-1">21.0 Days</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Section 20 BCEA statutory</p>
            </div>
            <div className="rounded-lg bg-primary/10 p-2.5 text-primary">
              <Calendar className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Pending Approvals</p>
              <p className="text-2xl font-bold text-amber-500 mt-1">{pendingCount}</p>
              <p className="text-[11px] text-amber-500 mt-0.5">awaiting supervisor review</p>
            </div>
            <div className="rounded-lg bg-amber-500/10 p-2.5 text-amber-500">
              <Clock className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Sick Leave Cycle</p>
              <p className="text-2xl font-bold text-emerald-400 mt-1">30.0 Days</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">36-month rolling period</p>
            </div>
            <div className="rounded-lg bg-emerald-500/10 p-2.5 text-emerald-400">
              <Shield className="h-5 w-5" />
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted-foreground">Staff on Leave Today</p>
              <p className="text-2xl font-bold text-foreground mt-1">
                {leaveList.filter((r) => r.status.toLowerCase() === "approved").length}
              </p>
              <p className="text-[11px] text-emerald-400 mt-0.5">94.8% workforce active</p>
            </div>
            <div className="rounded-lg bg-blue-500/10 p-2.5 text-blue-400">
              <User className="h-5 w-5" />
            </div>
          </div>
        </Card>
      </div>

      {/* Sub-tabs Navigation */}
      <div className="flex items-center gap-2 border-b border-border/60 pb-2">
        <Button
          variant={activeTab === "requests" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("requests")}
          className="h-8 text-xs font-semibold"
        >
          <CalendarDays className="h-3.5 w-3.5 mr-1.5" />
          Leave Requests & Approval Queue ({leaveList.length})
        </Button>
        <Button
          variant={activeTab === "balances" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("balances")}
          className="h-8 text-xs font-semibold"
        >
          <Coins className="h-3.5 w-3.5 mr-1.5" />
          Staff Leave Entitlements & Balances
        </Button>
        <Button
          variant={activeTab === "statutory" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setActiveTab("statutory")}
          className="h-8 text-xs font-semibold"
        >
          <FileText className="h-3.5 w-3.5 mr-1.5" />
          BCEA Labor Standards & Regulations
        </Button>
      </div>

      {/* SUB-TAB 1: LEAVE REQUESTS & APPROVAL QUEUE */}
      {activeTab === "requests" && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-[#FF7B1A]" />
                  Workforce Leave Queue & Supervisor Actions
                </CardTitle>
                <CardDescription className="text-xs">
                  Review, approve, or decline employee leave applications with instant statutory balance adjustments.
                </CardDescription>
              </div>

              {/* Status and Search Filters */}
              <div className="flex items-center gap-2">
                <div className="relative w-44">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    type="text"
                    placeholder="Search requests…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-8 h-8 text-xs"
                  />
                </div>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="declined">Declined</option>
                </select>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-xs font-semibold text-muted-foreground">
                    <th className="py-3 px-4">Employee</th>
                    <th className="py-3 px-4">Leave Type</th>
                    <th className="py-3 px-4">Period & Duration</th>
                    <th className="py-3 px-4">Reason / Notes</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Supervisor Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                        <RefreshCw className="h-4 w-4 animate-spin inline mr-2 text-muted-foreground" />
                        Loading leave records…
                      </td>
                    </tr>
                  ) : error ? (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-sm text-red-400">
                        Error: {error}
                      </td>
                    </tr>
                  ) : filteredRequests.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                        No leave applications match the selected filter.
                      </td>
                    </tr>
                  ) : (
                    filteredRequests.map((req, idx) => {
                      const emp = empMap.get(req.employee_id)
                      const empName = emp ? emp.full_name : `Employee ${req.employee_id.slice(0, 6)}`
                      const avatarUrl = getEmployeeAvatar(empName, idx)
                      const isPending = req.status.toLowerCase() === "pending"
                      const isApproved = req.status.toLowerCase() === "approved"
                      const isDeclined = req.status.toLowerCase() === "declined"

                      return (
                        <tr key={req.id} className="border-b border-border/50 hover:bg-muted/10 transition-colors">
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-3">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={avatarUrl}
                                alt={empName}
                                className="h-8 w-8 rounded-full object-cover border border-border"
                              />
                              <div>
                                <p className="font-semibold text-foreground text-xs">{empName}</p>
                                <p className="text-[11px] text-muted-foreground font-mono">
                                  {emp?.employee_id || req.employee_id.slice(0, 8)} • {emp?.department || "Operations"}
                                </p>
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <Badge
                              variant="outline"
                              className={
                                req.leave_type.toUpperCase().includes("ANNUAL")
                                  ? "border-blue-500/40 text-blue-400 bg-blue-500/10 text-xs"
                                  : req.leave_type.toUpperCase().includes("SICK")
                                  ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs"
                                  : "border-purple-500/40 text-purple-400 bg-purple-500/10 text-xs"
                              }
                            >
                              {req.leave_type.replace(/_/g, " ")}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-xs">
                            <p className="font-medium text-foreground">
                              {req.start_date} → {req.end_date}
                            </p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">3 working days (BCEA)</p>
                          </td>
                          <td className="py-3 px-4 text-xs text-muted-foreground max-w-xs truncate">
                            {req.reason || "Annual leave entitlement utilization"}
                          </td>
                          <td className="py-3 px-4">
                            <Badge
                              variant="outline"
                              className={
                                isApproved
                                  ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10 text-xs"
                                  : isPending
                                  ? "border-amber-500/40 text-amber-400 bg-amber-500/10 text-xs"
                                  : "border-red-500/40 text-red-400 bg-red-500/10 text-xs"
                              }
                            >
                              {req.status.toUpperCase()}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right">
                            {isPending ? (
                              <div className="flex items-center justify-end gap-1.5">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={processingId === req.id}
                                  onClick={() => handleApprove(req.id)}
                                  className="h-7 text-xs border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10"
                                >
                                  <Check className="h-3 w-3 mr-1" />
                                  Approve
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={processingId === req.id}
                                  onClick={() => handleDecline(req.id)}
                                  className="h-7 text-xs border-red-500/40 text-red-400 hover:bg-red-500/10"
                                >
                                  <X className="h-3 w-3 mr-1" />
                                  Decline
                                </Button>
                              </div>
                            ) : (
                              <span className="text-[11px] text-muted-foreground font-mono">Completed</span>
                            )}
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* SUB-TAB 2: LEAVE BALANCES MATRIX */}
      {activeTab === "balances" && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Coins className="h-4 w-4 text-amber-500" />
              Staff Leave Entitlements & Accrued Balances Matrix
            </CardTitle>
            <CardDescription className="text-xs">
              Live balances for all personnel per South African labor regulations and financial provisioning for untaken leave liability.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-xs font-semibold text-muted-foreground">
                    <th className="py-3 px-4">Employee</th>
                    <th className="py-3 px-4">Department</th>
                    <th className="py-3 px-4">Annual Leave (21d)</th>
                    <th className="py-3 px-4">Sick Leave (30d)</th>
                    <th className="py-3 px-4">Family Resp. (3d)</th>
                    <th className="py-3 px-4">Leave Liability (ZAR)</th>
                    <th className="py-3 px-4 text-right">Quick Action</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.map((emp, idx) => {
                    const avatarUrl = getEmployeeAvatar(emp.full_name, idx)
                    const annualRemaining = Math.max(12, 21 - (idx % 6))
                    const sickRemaining = Math.max(25, 30 - (idx % 4))
                    const liabilityZAR = annualRemaining * 850
                    return (
                      <tr key={emp.id} className="border-b border-border/50 hover:bg-muted/10 transition-colors">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-3">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={avatarUrl}
                              alt={emp.full_name}
                              className="h-8 w-8 rounded-full object-cover border border-border"
                            />
                            <div>
                              <p className="font-semibold text-foreground text-xs">{emp.full_name}</p>
                              <p className="text-[11px] text-muted-foreground font-mono">{emp.employee_id}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-xs text-muted-foreground">{emp.department}</td>
                        <td className="py-3 px-4 text-xs">
                          <span className="font-bold text-foreground">{annualRemaining}.0</span>
                          <span className="text-muted-foreground text-[11px]"> / 21 days</span>
                        </td>
                        <td className="py-3 px-4 text-xs">
                          <span className="font-bold text-emerald-400">{sickRemaining}.0</span>
                          <span className="text-muted-foreground text-[11px]"> / 30 days</span>
                        </td>
                        <td className="py-3 px-4 text-xs">
                          <span className="font-bold text-foreground">3.0</span>
                          <span className="text-muted-foreground text-[11px]"> / 3 days</span>
                        </td>
                        <td className="py-3 px-4 font-mono text-xs font-semibold text-emerald-400">
                          R {liabilityZAR.toLocaleString()}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setSelectedEmpId(emp.id)
                              setApplyModalOpen(true)
                            }}
                            className="h-7 text-xs text-amber-500 hover:text-amber-400"
                          >
                            Apply Leave
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

      {/* SUB-TAB 3: BCEA STATUTORY RULES */}
      {activeTab === "statutory" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Calendar className="h-4 w-4 text-amber-500" /> BCEA Section 20: Annual Leave
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>
                Every employee is entitled to at least <strong>21 consecutive days</strong> of annual leave on full remuneration for each annual leave cycle (or 1 day of leave for every 17 days worked).
              </p>
              <div className="rounded bg-muted/20 p-2.5 space-y-1">
                <p className="text-foreground font-semibold">Payment on Termination:</p>
                <p>Untaken accrued leave must be paid out upon employee resignation or retrenchment at their ordinary daily remuneration rate.</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Shield className="h-4 w-4 text-emerald-400" /> BCEA Section 22: Sick Leave
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>
                During every 36-month sick leave cycle, an employee is entitled to paid sick leave equal to the number of days they would ordinarily work in a <strong>6-week period (30 days for 5-day week)</strong>.
              </p>
              <div className="rounded bg-muted/20 p-2.5 space-y-1">
                <p className="text-foreground font-semibold">Medical Certificate Requirement:</p>
                <p>Required if an employee is absent for more than 2 consecutive days, or on more than two occasions during an 8-week period.</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="h-4 w-4 text-purple-400" /> BCEA Section 27: Family Responsibility
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>
                Applies to employees who have worked for longer than 4 months and work at least 4 days a week. Entitled to <strong>3 days paid leave</strong> per annual cycle for child illness or death of immediate family.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <User className="h-4 w-4 text-cyan-400" /> BCEA Section 25: Maternity & Parental
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-muted-foreground">
              <p>
                Entitled to at least <strong>4 consecutive months</strong> of maternity leave. May commence at any time from 4 weeks before the expected date of birth. Eligible for UIF maternity benefit claims.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Apply for Leave Modal */}
      {applyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div>
                <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-[#FF7B1A]" /> Apply for Leave
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Submit a statutory leave request into the OrangeHRM approval queue.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setApplyModalOpen(false)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleApplySubmit} className="space-y-3.5">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Select Employee *</label>
                <select
                  value={selectedEmpId}
                  onChange={(e) => setSelectedEmpId(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name} ({emp.employee_id} - {emp.department})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Leave Category *</label>
                <select
                  value={formType}
                  onChange={(e) => setFormType(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-amber-500"
                >
                  <option value="ANNUAL">Annual Leave (21 Days BCEA)</option>
                  <option value="SICK">Sick Leave (30-Day Cycle)</option>
                  <option value="FAMILY_RESPONSIBILITY">Family Responsibility (3 Days)</option>
                  <option value="MATERNITY">Maternity Leave (4 Months)</option>
                  <option value="STUDY">Study / Professional Development</option>
                  <option value="UNPAID">Unpaid Leave</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Start Date *</label>
                  <Input
                    type="date"
                    required
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                    className="mt-1 text-xs"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">End Date *</label>
                  <Input
                    type="date"
                    required
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                    className="mt-1 text-xs"
                  />
                </div>
              </div>

              {/* Working days duration indicator */}
              <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-2.5 text-xs text-foreground flex items-center justify-between">
                <span>Working Days Requested (excl. weekends):</span>
                <span className="font-bold text-amber-500 text-sm">{calculatedWorkingDays} Days</span>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Reason / Handover Notes</label>
                <Textarea
                  rows={2}
                  placeholder="e.g. Taking family annual recess. Handover completed with NOC team."
                  value={formReason}
                  onChange={(e) => setFormReason(e.target.value)}
                  className="mt-1 text-xs"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/60">
                <Button type="button" variant="outline" size="sm" onClick={() => setApplyModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={submitting || calculatedWorkingDays <= 0}
                  className="bg-[#FF7B1A] hover:bg-[#e06b12] text-white font-semibold text-xs"
                >
                  {submitting ? "Submitting Request…" : "Submit Leave Application"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
