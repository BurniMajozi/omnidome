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
import { getEmployeeAvatar } from "./pim-directory-view"

interface LeaveJourneyViewProps {
  employees: Employee[]
  leaveRequests: LeaveRequest[]
  loading: boolean
  error: string | null
  onRefresh: () => void
}

export function LeaveJourneyView({
  employees,
  leaveRequests: initialLeaveRequests,
  loading,
  error,
  onRefresh,
}: LeaveJourneyViewProps) {
  const [activeTab, setActiveTab] = useState<"queue" | "balances" | "policy">("queue")
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState("ALL")
  const [applyModalOpen, setApplyModalOpen] = useState(false)
  const [actingLeaveId, setActingLeaveId] = useState<string | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Local leave requests cache for immediate optimistic updates
  const [localRequests, setLocalRequests] = useState<LeaveRequest[]>(initialLeaveRequests)

  React.useEffect(() => {
    setLocalRequests(initialLeaveRequests)
  }, [initialLeaveRequests])

  // Apply Leave Form State
  const [selectedEmpId, setSelectedEmpId] = useState<string>(employees[0]?.id || "")
  const [leaveType, setLeaveType] = useState<string>("ANNUAL")
  const [startDate, setStartDate] = useState<string>(new Date().toISOString().split("T")[0])
  const [endDate, setEndDate] = useState<string>(new Date().toISOString().split("T")[0])
  const [leaveReason, setLeaveReason] = useState<string>("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Calculate working days excluding Saturdays & Sundays
  const calculatedDays = useMemo(() => {
    if (!startDate || !endDate) return 1
    const start = new Date(startDate)
    const end = new Date(endDate)
    if (end < start) return 0

    let count = 0
    const cur = new Date(start)
    while (cur <= end) {
      const dayOfWeek = cur.getDay()
      if (dayOfWeek !== 0 && dayOfWeek !== 6) {
        count++
      }
      cur.setDate(cur.getDate() + 1)
    }
    return Math.max(1, count)
  }, [startDate, endDate])

  // Approve leave
  const handleApprove = async (id: string) => {
    setActingLeaveId(id)
    try {
      await approveLeave(id)
      setLocalRequests((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: "Approved" } : r))
      )
      setToastMessage("Leave request approved successfully.")
      setTimeout(() => setToastMessage(null), 3000)
      onRefresh()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to approve leave request.")
    } finally {
      setActingLeaveId(null)
    }
  }

  // Decline leave
  const handleDecline = async (id: string) => {
    setActingLeaveId(id)
    try {
      await declineLeave(id)
      setLocalRequests((prev) =>
        prev.map((r) => (r.id === id ? { ...r, status: "Declined" } : r))
      )
      setToastMessage("Leave request declined.")
      setTimeout(() => setToastMessage(null), 3000)
      onRefresh()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to decline leave request.")
    } finally {
      setActingLeaveId(null)
    }
  }

  // Submit new leave request
  const handleApplySubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedEmpId) {
      alert("Please select an employee.")
      return
    }
    setIsSubmitting(true)
    try {
      await createLeaveRequest(selectedEmpId, {
        leave_type: leaveType,
        start_date: startDate,
        end_date: endDate,
        reason: leaveReason || "Statutory Leave",
      })
      setToastMessage("Leave application submitted successfully.")
      setTimeout(() => setToastMessage(null), 3000)
      setApplyModalOpen(false)
      setLeaveReason("")
      onRefresh()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to submit leave request.")
    } finally {
      setIsSubmitting(false)
    }
  }

  // Filtered requests
  const filteredRequests = useMemo(() => {
    return localRequests.filter((req) => {
      const emp = employees.find((e) => e.id === req.employee_id)
      const empName = emp?.full_name || ""
      const matchesSearch =
        empName.toLowerCase().includes(search.toLowerCase()) ||
        req.leave_type.toLowerCase().includes(search.toLowerCase())
      const matchesStatus =
        statusFilter === "ALL" ||
        (statusFilter === "PENDING" && (req.status === "Pending" || req.status === "PENDING")) ||
        (statusFilter === "APPROVED" && (req.status === "Approved" || req.status === "APPROVED")) ||
        (statusFilter === "DECLINED" && (req.status === "Declined" || req.status === "DECLINED"))
      return matchesSearch && matchesStatus
    })
  }, [localRequests, employees, search, statusFilter])

  // Accrued Leave Liability Calculations (ZAR)
  const leaveLiabilityData = useMemo(() => {
    return employees.map((emp) => {
      const dailyRateZAR = 1250 // Average daily wage for ISP telecom staff
      const accruedDays = 15 // Standard accrued
      const liabilityZAR = accruedDays * dailyRateZAR
      return {
        emp,
        accruedDays,
        liabilityZAR,
      }
    })
  }, [employees])

  const totalLiabilityZAR = useMemo(() => {
    return leaveLiabilityData.reduce((acc, curr) => acc + curr.liabilityZAR, 0)
  }, [leaveLiabilityData])

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/90 px-4 py-3 text-sm text-emerald-200 shadow-xl backdrop-blur">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Leave Header Banner */}
      <div className="rounded-xl border border-border bg-card/60 p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-primary/40 bg-primary/10 text-primary">
              <CalendarDays className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Statutory Leave Management</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  BCEA Compliant
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                South Africa Basic Conditions of Employment Act (BCEA) quotas, supervisor approval queue, and liability provisioning.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="default"
              className="h-8 gap-1.5 text-xs font-semibold"
              onClick={() => setApplyModalOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              Apply for Leave
            </Button>
            <Button size="sm" variant="outline" className="h-8 w-8 p-0" onClick={onRefresh} title="Refresh">
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* BCEA Entitlement Indicator Chips */}
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 pt-3 border-t border-border/60 text-xs">
          <div className="rounded-lg border border-border/80 bg-background/50 p-2.5">
            <span className="text-[11px] text-muted-foreground">Annual Leave (Sec 20)</span>
            <p className="font-bold text-foreground mt-0.5">21 Consec. Days / yr</p>
            <p className="text-[10px] text-emerald-400">1 day per 17 worked</p>
          </div>
          <div className="rounded-lg border border-border/80 bg-background/50 p-2.5">
            <span className="text-[11px] text-muted-foreground">Sick Leave (Sec 22)</span>
            <p className="font-bold text-foreground mt-0.5">30 Days / 36-mo cycle</p>
            <p className="text-[10px] text-primary">Medical cert required &gt; 2d</p>
          </div>
          <div className="rounded-lg border border-border/80 bg-background/50 p-2.5">
            <span className="text-[11px] text-muted-foreground">Family Responsibility</span>
            <p className="font-bold text-foreground mt-0.5">3 Days / yr</p>
            <p className="text-[10px] text-muted-foreground">Child birth / illness / death</p>
          </div>
          <div className="rounded-lg border border-border/80 bg-background/50 p-2.5">
            <span className="text-[11px] text-muted-foreground">Maternity Leave (Sec 25)</span>
            <p className="font-bold text-foreground mt-0.5">4 Months Unpaid</p>
            <p className="text-[10px] text-muted-foreground">UIF benefit claimable</p>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-center gap-1 border-b border-border pb-2 text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("queue")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "queue"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Leave Requests & Approval Queue ({localRequests.filter((r) => r.status === "Pending").length} Pending)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("balances")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "balances"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Staff Leave Balances & Accrued Liabilities (R {totalLiabilityZAR.toLocaleString()})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("policy")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "policy"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          BCEA Statutory Regulations Guide
        </button>
      </div>

      {/* ── TAB 1: Approval Queue ────────────────────────────────────── */}
      {activeTab === "queue" && (
        <div className="space-y-4">
          {/* Controls Bar */}
          <Card className="border-border">
            <CardContent className="p-3">
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
                <div className="relative w-full sm:w-80">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search applicant or leave type…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="pl-8 h-8 text-xs"
                  />
                </div>

                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <span className="text-muted-foreground shrink-0">Status:</span>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="PENDING">Pending Approval</option>
                    <option value="APPROVED">Approved</option>
                    <option value="DECLINED">Declined</option>
                  </select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Table */}
          <Card className="border-border">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Applicant</th>
                      <th className="py-2.5 px-4 font-medium">Department</th>
                      <th className="py-2.5 px-4 font-medium">Leave Type</th>
                      <th className="py-2.5 px-4 font-medium">Duration</th>
                      <th className="py-2.5 px-4 font-medium">Reason / Note</th>
                      <th className="py-2.5 px-4 font-medium">Status</th>
                      <th className="py-2.5 px-4 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {loading ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-muted-foreground">
                          Loading leave records…
                        </td>
                      </tr>
                    ) : filteredRequests.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-muted-foreground">
                          No leave applications found.
                        </td>
                      </tr>
                    ) : (
                      filteredRequests.map((req, idx) => {
                        const emp = employees.find((e) => e.id === req.employee_id)
                        const empName = emp?.full_name || "Telecom Specialist"
                        const empDept = emp?.department || "Operations"
                        const isPending = req.status === "Pending" || req.status === "PENDING"
                        const isApproved = req.status === "Approved" || req.status === "APPROVED"

                        return (
                          <tr key={req.id} className="hover:bg-muted/30 transition-colors">
                            <td className="py-3 px-4">
                              <div className="flex items-center gap-2.5">
                                <img
                                  src={getEmployeeAvatar(empName, idx)}
                                  alt=""
                                  className="h-7 w-7 rounded-full object-cover ring-1 ring-border"
                                />
                                <div>
                                  <p className="font-semibold text-foreground">{empName}</p>
                                  <p className="text-[10px] text-muted-foreground font-mono">{emp?.employee_id || "STF"}</p>
                                </div>
                              </div>
                            </td>
                            <td className="py-3 px-4 text-muted-foreground">{empDept}</td>
                            <td className="py-3 px-4">
                              <Badge variant="outline" className="border-border text-foreground font-medium">
                                {req.leave_type}
                              </Badge>
                            </td>
                            <td className="py-3 px-4">
                              <div className="text-foreground font-medium">
                                {req.start_date} <span className="text-muted-foreground">to</span> {req.end_date}
                              </div>
                              <span className="text-[10px] text-muted-foreground">Working days</span>
                            </td>
                            <td className="py-3 px-4 text-muted-foreground max-w-[200px] truncate" title={req.reason}>
                              {req.reason || "BCEA Entitlement"}
                            </td>
                            <td className="py-3 px-4">
                              <Badge
                                variant="outline"
                                className={
                                  isApproved
                                    ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                                    : isPending
                                    ? "border-amber-500/40 text-amber-400 bg-amber-500/10"
                                    : "border-red-500/40 text-red-400 bg-red-500/10"
                                }
                              >
                                {req.status}
                              </Badge>
                            </td>
                            <td className="py-3 px-4 text-right">
                              {isPending ? (
                                <div className="flex items-center justify-end gap-1.5">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 px-2 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 gap-1 text-[11px]"
                                    disabled={actingLeaveId === req.id}
                                    onClick={() => handleApprove(req.id)}
                                  >
                                    <Check className="h-3 w-3" />
                                    Approve
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 px-2 border-red-500/40 text-red-400 hover:bg-red-500/10 gap-1 text-[11px]"
                                    disabled={actingLeaveId === req.id}
                                    onClick={() => handleDecline(req.id)}
                                  >
                                    <X className="h-3 w-3" />
                                    Decline
                                  </Button>
                                </div>
                              ) : (
                                <span className="text-[11px] text-muted-foreground">Processed</span>
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
        </div>
      )}

      {/* ── TAB 2: Balances & Accrued Liabilities ─────────────────────── */}
      {activeTab === "balances" && (
        <div className="space-y-4">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Coins className="h-4 w-4 text-primary" /> Staff Accrued Leave & Financial Provisioning
                  </CardTitle>
                  <CardDescription className="text-xs">
                    South African accounting standard (IAS 19 / BCEA) leave balance sheet provision.
                  </CardDescription>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Total Financial Provision</p>
                  <p className="text-lg font-bold text-foreground">R {totalLiabilityZAR.toLocaleString()} ZAR</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Employee</th>
                      <th className="py-2.5 px-4 font-medium">Department</th>
                      <th className="py-2.5 px-4 font-medium">Annual Quota</th>
                      <th className="py-2.5 px-4 font-medium">Days Taken</th>
                      <th className="py-2.5 px-4 font-medium">Accrued Balance</th>
                      <th className="py-2.5 px-4 font-medium text-right">ZAR Provision</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {leaveLiabilityData.map((row, idx) => (
                      <tr key={row.emp.id} className="hover:bg-muted/30">
                        <td className="py-2.5 px-4">
                          <div className="flex items-center gap-2">
                            <img
                              src={getEmployeeAvatar(row.emp.full_name, idx)}
                              alt=""
                              className="h-6 w-6 rounded-full object-cover"
                            />
                            <span className="font-semibold text-foreground">{row.emp.full_name}</span>
                          </div>
                        </td>
                        <td className="py-2.5 px-4 text-muted-foreground">{row.emp.department}</td>
                        <td className="py-2.5 px-4 text-foreground">21 Days</td>
                        <td className="py-2.5 px-4 text-muted-foreground">6 Days</td>
                        <td className="py-2.5 px-4 font-semibold text-emerald-400">{row.accruedDays} Days</td>
                        <td className="py-2.5 px-4 text-right font-mono font-semibold text-foreground">
                          R {row.liabilityZAR.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 3: Policy Guide ───────────────────────────────────────── */}
      {activeTab === "policy" && (
        <div className="grid gap-4 sm:grid-cols-2 text-xs">
          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
                <FileText className="h-4 w-4 text-primary" /> Section 20: Annual Leave
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-muted-foreground">
              <p>
                Employees are entitled to 21 consecutive days of annual leave with full pay on each annual leave cycle (12 consecutive months of employment).
              </p>
              <p>
                Alternatively, leave is calculated at 1 day for every 17 days worked, or 1 hour for every 17 hours worked.
              </p>
              <p className="text-foreground font-medium">
                Annual leave cannot be replaced with cash payment except upon termination of employment.
              </p>
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
                <Shield className="h-4 w-4 text-cyan-400" /> Section 22: Sick Leave
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-muted-foreground">
              <p>
                A sick leave cycle means the period of 36 months of continuous employment. An employee is entitled to 30 days of paid sick leave per 3-year cycle.
              </p>
              <p>
                During the first six months of employment, an employee is entitled to one day’s paid sick leave for every 26 days worked.
              </p>
              <p className="text-foreground font-medium">
                Medical certificates are mandatory if an employee is absent for more than two consecutive days or more than twice in an 8-week period.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── APPLY FOR LEAVE MODAL ─────────────────────────────────────── */}
      {applyModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Apply for Leave</CardTitle>
                <CardDescription className="text-xs">
                  Submit a statutory leave request into the approval queue.
                </CardDescription>
              </div>
              <button
                type="button"
                onClick={() => setApplyModalOpen(false)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleApplySubmit}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Select Employee *</label>
                  <select
                    value={selectedEmpId}
                    onChange={(e) => setSelectedEmpId(e.target.value)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.full_name} ({emp.department} — {emp.job_title})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Leave Entitlement Type</label>
                    <select
                      value={leaveType}
                      onChange={(e) => setLeaveType(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value="ANNUAL">Annual Leave (21-Day Statutory)</option>
                      <option value="SICK">Sick Leave (Medical Certificate)</option>
                      <option value="FAMILY">Family Responsibility (3 Days)</option>
                      <option value="STUDY">Study / Certification Leave</option>
                      <option value="UNPAID">Unpaid Leave</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Calculated Working Days</label>
                    <div className="h-8 rounded-md border border-border bg-muted/40 px-3 flex items-center font-bold text-foreground">
                      {calculatedDays} Working Day{calculatedDays > 1 ? "s" : ""}
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Start Date *</label>
                    <Input
                      type="date"
                      required
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">End Date *</label>
                    <Input
                      type="date"
                      required
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Reason / Handover Note</label>
                  <Textarea
                    placeholder="Brief description of leave reason or on-call handover arrangements…"
                    value={leaveReason}
                    onChange={(e) => setLeaveReason(e.target.value)}
                    rows={3}
                    className="text-xs"
                  />
                </div>
              </CardContent>

              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setApplyModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" disabled={isSubmitting}>
                  {isSubmitting ? "Submitting Application…" : "Submit Application"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
