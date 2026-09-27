"use client"

import React, { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  LogOut,
  UserX,
  ShieldAlert,
  Key,
  Laptop,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Plus,
  Lock,
  Search,
  Check,
  X,
  RefreshCw,
  TrendingDown,
} from "lucide-react"
import type { Employee, ExitRecord } from "@/lib/hr-api"
import { getEmployeeAvatar } from "./pim-directory-view"

interface TalentExitViewProps {
  employees: Employee[]
  exits: ExitRecord[]
  onRefresh: () => void
}

interface DeactivationTask {
  id: string
  systemName: string
  category: "Identity & SSO" | "Network & VPN" | "Hardware Assets" | "Building Access"
  isRevoked: boolean
}

export function TalentExitView({
  employees,
  exits: initialExits,
  onRefresh,
}: TalentExitViewProps) {
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [newExitModalOpen, setNewExitModalOpen] = useState(false)

  // Exit Form State
  const [selectedEmpId, setSelectedEmpId] = useState(employees[0]?.id || "")
  const [exitType, setExitType] = useState("Resignation")
  const [noticeDate, setNoticeDate] = useState(new Date().toISOString().split("T")[0])
  const [lastWorkingDate, setLastWorkingDate] = useState(
    new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0]
  )
  const [exitReason, setExitReason] = useState("Better career opportunity at multinational carrier")
  const [exitInterviewDone, setExitInterviewDone] = useState(true)

  // System Deactivation Checklists per Exit
  const [systemTasks, setSystemTasks] = useState<DeactivationTask[]>([
    { id: "1", systemName: "Google Workspace & SSO Identity", category: "Identity & SSO", isRevoked: true },
    { id: "2", systemName: "RADIUS & MikroTik Router VPN Access", category: "Network & VPN", isRevoked: true },
    { id: "3", systemName: "OmniDome ERP, Billing & CRM Accounts", category: "Identity & SSO", isRevoked: true },
    { id: "4", systemName: "Company Laptop & Charger Recovery", category: "Hardware Assets", isRevoked: true },
    { id: "5", systemName: "Fusion Splicer & OTDR Equipment Depot Check-in", category: "Hardware Assets", isRevoked: false },
    { id: "6", systemName: "Fleet Service Van Keys & Fuel Card Return", category: "Hardware Assets", isRevoked: false },
    { id: "7", systemName: "Building Biometric & RFID Keycard Revocation", category: "Building Access", isRevoked: true },
  ])

  const [localExits, setLocalExits] = useState<ExitRecord[]>([
    {
      id: "EXT-001",
      employee_id: employees[0]?.id || "EMP-001",
      exit_type: "Resignation",
      notice_date: "2026-09-10",
      last_working_date: "2026-10-10",
      status: "In Progress",
      reason: "Relocating to Western Cape region",
      created_at: "2026-09-10",
    },
  ])

  const toggleTask = (id: string) => {
    setSystemTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, isRevoked: !t.isRevoked } : t))
    )
  }

  const handleCreateExit = (e: React.FormEvent) => {
    e.preventDefault()
    const targetEmp = employees.find((e) => e.id === selectedEmpId)
    const newEx: ExitRecord = {
      id: `EXT-${Date.now()}`,
      employee_id: selectedEmpId,
      exit_type: exitType,
      notice_date: noticeDate,
      last_working_date: lastWorkingDate,
      status: "In Progress",
      reason: exitReason,
      created_at: new Date().toISOString(),
    }
    setLocalExits((prev) => [newEx, ...prev])
    setToastMessage(`Offboarding journey initiated for ${targetEmp?.full_name || "Employee"}!`)
    setTimeout(() => setToastMessage(null), 3500)
    setNewExitModalOpen(false)
  }

  const completedCount = systemTasks.filter((t) => t.isRevoked).length
  const totalCount = systemTasks.length

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/90 px-4 py-3 text-sm text-emerald-200 shadow-xl backdrop-blur">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Banner */}
      <div className="rounded-xl border border-border bg-card/60 p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-red-500/40 bg-red-500/10 text-red-400">
              <LogOut className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Staff Exit & System Deactivation</h2>
                <Badge variant="outline" className="border-red-500/40 text-red-400 bg-red-500/10 text-[10px] font-semibold">
                  Zero Trust Offboarding
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Manage employee departures, automated SSO/VPN deactivation, hardware recovery, and exit clearance interviews.
              </p>
            </div>
          </div>

          <Button
            size="sm"
            variant="default"
            className="gap-1.5 text-xs font-semibold"
            onClick={() => setNewExitModalOpen(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            Initiate Staff Offboarding
          </Button>
        </div>
      </div>

      {/* ── SECTION 1: System Deactivation & Asset Recovery Checklist ──── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Lock className="h-4 w-4 text-cyan-400" />
                Zero-Trust Systems Deactivation & Hardware Recovery
              </CardTitle>
              <CardDescription className="text-xs">
                Ensure all enterprise credentials, router VPNs, and physical assets are revoked before last working date.
              </CardDescription>
            </div>
            <Badge variant="outline" className="border-primary/40 text-primary">
              {completedCount} / {totalCount} Cleared
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-4 space-y-3 text-xs">
          <div className="grid gap-2 sm:grid-cols-2">
            {systemTasks.map((task) => (
              <div
                key={task.id}
                onClick={() => toggleTask(task.id)}
                className={`flex items-center justify-between rounded-lg border p-3 cursor-pointer transition-all ${
                  task.isRevoked
                    ? "border-emerald-500/40 bg-emerald-500/5 text-foreground"
                    : "border-amber-500/40 bg-amber-500/5 text-muted-foreground hover:border-amber-500"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border ${
                      task.isRevoked
                        ? "border-emerald-500 bg-emerald-500 text-white"
                        : "border-border bg-background"
                    }`}
                  >
                    {task.isRevoked && <Check className="h-3 w-3" />}
                  </div>
                  <div>
                    <p className="font-semibold text-foreground">{task.systemName}</p>
                    <p className="text-[10px] text-muted-foreground">{task.category}</p>
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={
                    task.isRevoked
                      ? "border-emerald-500/40 text-emerald-400 text-[10px]"
                      : "border-amber-500/40 text-amber-400 text-[10px]"
                  }
                >
                  {task.isRevoked ? "Deactivated" : "Pending Return"}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ── SECTION 2: Active Offboarding Cases ────────────────────────── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <CardTitle className="text-base">Active Offboarding Roster</CardTitle>
          <CardDescription className="text-xs">
            Staff currently serving notice periods or completing clearance handovers.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                  <th className="py-2.5 px-4 font-medium">Employee</th>
                  <th className="py-2.5 px-4 font-medium">Exit Type</th>
                  <th className="py-2.5 px-4 font-medium">Notice Date</th>
                  <th className="py-2.5 px-4 font-medium">Last Working Day</th>
                  <th className="py-2.5 px-4 font-medium">Primary Reason</th>
                  <th className="py-2.5 px-4 font-medium text-right">Clearance Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {localExits.map((ex) => {
                  const emp = employees.find((e) => e.id === ex.employee_id) || employees[0]
                  return (
                    <tr key={ex.id} className="hover:bg-muted/30">
                      <td className="py-3 px-4">
                        <p className="font-semibold text-foreground">{emp?.full_name || "Staff Member"}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">{emp?.employee_id || "STF"}</p>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="border-border text-foreground">
                          {ex.exit_type}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground font-mono">{ex.notice_date}</td>
                      <td className="py-3 px-4 font-semibold text-foreground font-mono">{ex.last_working_date}</td>
                      <td className="py-3 px-4 text-muted-foreground max-w-[200px] truncate" title={ex.reason}>
                        {ex.reason}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Badge variant="outline" className="border-amber-500/40 text-amber-400">
                          {ex.status}
                        </Badge>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* ── INITIATE EXIT MODAL ───────────────────────────────────────── */}
      {newExitModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Initiate Staff Offboarding</CardTitle>
                <CardDescription className="text-xs">Schedule departure and trigger IT deactivation.</CardDescription>
              </div>
              <button type="button" onClick={() => setNewExitModalOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateExit}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Select Employee *</label>
                  <select
                    value={selectedEmpId}
                    onChange={(e) => setSelectedEmpId(e.target.value)}
                    className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                  >
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.full_name} ({emp.department} — {emp.job_title})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Exit Type</label>
                    <select
                      value={exitType}
                      onChange={(e) => setExitType(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="Resignation">Voluntary Resignation</option>
                      <option value="Retirement">Retirement</option>
                      <option value="End of Contract">End of Fixed-Term Contract</option>
                      <option value="Redundancy">Retrenchment / Redundancy</option>
                      <option value="Dismissal">Dismissal</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Notice Date</label>
                    <Input
                      type="date"
                      value={noticeDate}
                      onChange={(e) => setNoticeDate(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Last Working Day</label>
                    <Input
                      type="date"
                      value={lastWorkingDate}
                      onChange={(e) => setLastWorkingDate(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Exit Reason & Handover Notes</label>
                  <Textarea
                    placeholder="Details from notice letter or exit interview..."
                    value={exitReason}
                    onChange={(e) => setExitReason(e.target.value)}
                    rows={3}
                    className="text-xs"
                  />
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setNewExitModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default">
                  Confirm Offboarding
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
