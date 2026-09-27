"use client"

import React, { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  AlertTriangle,
  Plus,
  ShieldAlert,
  MessageSquare,
  CheckCircle2,
  Clock,
  UserX,
  FileText,
  Search,
  Check,
  X,
  Lock,
  HeartHandshake,
} from "lucide-react"
import type { Employee, DisciplinaryAction } from "@/lib/hr-api"
import { getEmployeeAvatar } from "./pim-directory-view"

interface TalentDisciplinaryViewProps {
  employees: Employee[]
  actions: DisciplinaryAction[]
  onRefresh: () => void
}

interface EmployeeGrievance {
  id: string
  complainantName: string
  isAnonymous: boolean
  department: string
  category: "Workplace Harassment" | "Safety Hazard / OHS" | "Shift Unfairness" | "Managerial Dispute" | "Wage Discrepancy"
  incidentDate: string
  description: string
  status: "Logged" | "Under Investigation" | "Informal Mediation" | "Resolved"
  resolutionNotes?: string
}

export function TalentDisciplinaryView({
  employees,
  actions: initialActions,
  onRefresh,
}: TalentDisciplinaryViewProps) {
  const [activeTab, setActiveTab] = useState<"disciplinary" | "grievances">("disciplinary")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Disciplinary Actions state
  const [localActions, setLocalActions] = useState<DisciplinaryAction[]>(initialActions)
  const [newActionOpen, setNewActionOpen] = useState(false)
  const [selectedEmpId, setSelectedEmpId] = useState(employees[0]?.id || "")
  const [actionType, setActionType] = useState("WRITTEN_WARNING")
  const [incidentDate, setIncidentDate] = useState(new Date().toISOString().split("T")[0])
  const [actionDescription, setActionDescription] = useState("")

  // Grievances & Employee Complaints state
  const [grievances, setGrievances] = useState<EmployeeGrievance[]>([
    {
      id: "GRV-001",
      complainantName: "Anonymous Field Tech",
      isAnonymous: true,
      department: "Field Operations",
      category: "Safety Hazard / OHS",
      incidentDate: "2026-09-20",
      description: "Ladder safety harness clip in Van #3 has worn latching teeth. Poses risk during pole splicing.",
      status: "Resolved",
      resolutionNotes: "Replaced harness kit and issued central depot safety recall.",
    },
    {
      id: "GRV-002",
      complainantName: "Zanele Khumalo",
      isAnonymous: false,
      department: "Customer Support",
      category: "Shift Unfairness",
      incidentDate: "2026-09-22",
      description: "Weekend standby rotation was assigned to the same agent for 3 consecutive cycles.",
      status: "Informal Mediation",
      resolutionNotes: "Mediation scheduled with supervisor to rebalance scheduling roster.",
    },
  ])
  const [newGrievanceOpen, setNewGrievanceOpen] = useState(false)
  const [grvName, setGrvName] = useState("")
  const [grvAnonymous, setGrvAnonymous] = useState(false)
  const [grvDept, setGrvDept] = useState("Field Operations")
  const [grvCategory, setGrvCategory] = useState<EmployeeGrievance["category"]>("Workplace Harassment")
  const [grvDate, setGrvDate] = useState(new Date().toISOString().split("T")[0])
  const [grvDescription, setGrvDescription] = useState("")

  const handleCreateAction = (e: React.FormEvent) => {
    e.preventDefault()
    const newAct: DisciplinaryAction = {
      id: `DISC-${Date.now()}`,
      employee_id: selectedEmpId,
      action_type: actionType,
      incident_date: incidentDate,
      description: actionDescription,
      status: "Active",
      outcome: "Formal Warning Issued",
      created_at: new Date().toISOString(),
    }
    setLocalActions((prev) => [newAct, ...prev])
    setToastMessage("Disciplinary action successfully recorded and logged.")
    setTimeout(() => setToastMessage(null), 3000)
    setNewActionOpen(false)
    setActionDescription("")
  }

  const handleCreateGrievance = (e: React.FormEvent) => {
    e.preventDefault()
    const newG: EmployeeGrievance = {
      id: `GRV-${String(grievances.length + 1).padStart(3, "0")}`,
      complainantName: grvAnonymous ? "Anonymous Whistleblower" : grvName || "Staff Member",
      isAnonymous: grvAnonymous,
      department: grvDept,
      category: grvCategory,
      incidentDate: grvDate,
      description: grvDescription,
      status: "Logged",
    }
    setGrievances((prev) => [newG, ...prev])
    setToastMessage("Confidential grievance submitted and assigned to HR mediation.")
    setTimeout(() => setToastMessage(null), 3500)
    setNewGrievanceOpen(false)
    setGrvDescription("")
    setGrvName("")
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

      {/* Top Banner */}
      <div className="rounded-xl border border-border bg-card/60 p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-400">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Disciplinary & Employee Grievances</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  BCEA & CCMA Aligned
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Statutory progressive discipline, written warnings, hearings, and confidential employee complaints portal.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={() => setNewGrievanceOpen(true)}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              File Employee Complaint
            </Button>
            <Button
              size="sm"
              variant="default"
              className="gap-1.5 text-xs font-semibold"
              onClick={() => setNewActionOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              New Disciplinary Action
            </Button>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2 text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("disciplinary")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "disciplinary"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Disciplinary Records & Warnings ({localActions.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("grievances")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "grievances"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Employee Grievance & Whistleblower Complaints ({grievances.length})
        </button>
      </div>

      {/* ── TAB 1: Disciplinary Records ───────────────────────────────── */}
      {activeTab === "disciplinary" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base">Progressive Disciplinary Log</CardTitle>
            <CardDescription className="text-xs">
              Verbal, written, and final warnings issued under the South African Labor Relations Act (LRA).
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="py-2.5 px-4 font-medium">Employee</th>
                    <th className="py-2.5 px-4 font-medium">Action Type</th>
                    <th className="py-2.5 px-4 font-medium">Incident Date</th>
                    <th className="py-2.5 px-4 font-medium">Description</th>
                    <th className="py-2.5 px-4 font-medium">Outcome</th>
                    <th className="py-2.5 px-4 font-medium text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {localActions.length === 0 ? (
                    <tr><td colSpan={6} className="py-8 text-center text-muted-foreground">No disciplinary actions logged. Clean record!</td></tr>
                  ) : (
                    localActions.map((act) => {
                      const emp = employees.find((e) => e.id === act.employee_id)
                      return (
                        <tr key={act.id} className="hover:bg-muted/30">
                          <td className="py-3 px-4 font-semibold text-foreground">
                            {emp?.full_name || "Telecom Specialist"}
                          </td>
                          <td className="py-3 px-4">
                            <Badge variant="outline" className="border-amber-500/40 text-amber-400">
                              {act.action_type.replace(/_/g, " ")}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-muted-foreground font-mono">{act.incident_date}</td>
                          <td className="py-3 px-4 text-muted-foreground max-w-[240px] truncate" title={act.description}>
                            {act.description}
                          </td>
                          <td className="py-3 px-4 text-foreground">{act.outcome || "Hearing Pending"}</td>
                          <td className="py-3 px-4 text-right">
                            <Badge variant="outline" className="border-border text-foreground">
                              {act.status}
                            </Badge>
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

      {/* ── TAB 2: Employee Grievances & Complaints ───────────────────── */}
      {activeTab === "grievances" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-primary" />
              Confidential Grievance Portal & Whistleblowing Log
            </CardTitle>
            <CardDescription className="text-xs">
              Employees can lodge confidential or anonymous workplace complaints, tracked until mediation or resolution.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="py-2.5 px-4 font-medium">Case ID</th>
                    <th className="py-2.5 px-4 font-medium">Lodged By</th>
                    <th className="py-2.5 px-4 font-medium">Department</th>
                    <th className="py-2.5 px-4 font-medium">Category</th>
                    <th className="py-2.5 px-4 font-medium">Incident Summary</th>
                    <th className="py-2.5 px-4 font-medium">Resolution Notes</th>
                    <th className="py-2.5 px-4 font-medium text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {grievances.map((g) => (
                    <tr key={g.id} className="hover:bg-muted/30">
                      <td className="py-3 px-4 font-mono font-bold text-foreground">{g.id}</td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          {g.isAnonymous ? (
                            <Badge variant="outline" className="border-primary/40 text-primary gap-1">
                              <Lock className="h-3 w-3" /> Anonymous
                            </Badge>
                          ) : (
                            <span className="font-semibold text-foreground">{g.complainantName}</span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground">{g.department}</td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="border-border text-foreground">
                          {g.category}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground max-w-[200px] truncate" title={g.description}>
                        {g.description}
                      </td>
                      <td className="py-3 px-4 text-muted-foreground max-w-[200px] truncate" title={g.resolutionNotes}>
                        {g.resolutionNotes || "Awaiting investigator notes"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Badge
                          variant="outline"
                          className={
                            g.status === "Resolved"
                              ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                              : "border-amber-500/40 text-amber-400 bg-amber-500/10"
                          }
                        >
                          {g.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── NEW DISCIPLINARY MODAL ────────────────────────────────────── */}
      {newActionOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">New Disciplinary Proceeding</CardTitle>
                <CardDescription className="text-xs">Labor Relations Act (LRA) statutory warning wizard.</CardDescription>
              </div>
              <button type="button" onClick={() => setNewActionOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateAction}>
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

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Action Type</label>
                    <select
                      value={actionType}
                      onChange={(e) => setActionType(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="VERBAL_WARNING">Verbal Warning (Valid 3 months)</option>
                      <option value="WRITTEN_WARNING">Written Warning (Valid 6 months)</option>
                      <option value="FINAL_WARNING">Final Written Warning (Valid 12 months)</option>
                      <option value="DISCIPLINARY_HEARING">Formal Disciplinary Hearing</option>
                      <option value="PRECAUTIONARY_SUSPENSION">Precautionary Suspension with Pay</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Incident Date</label>
                    <Input
                      type="date"
                      value={incidentDate}
                      onChange={(e) => setIncidentDate(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Incident Description & Evidence</label>
                  <Textarea
                    required
                    placeholder="Details of the breach (e.g. repeated unauthorized absence from NOC shift, failure to follow fiber safety protocols)..."
                    value={actionDescription}
                    onChange={(e) => setActionDescription(e.target.value)}
                    rows={4}
                    className="text-xs"
                  />
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setNewActionOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default">
                  Record Action
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── FILE GRIEVANCE / COMPLAINT MODAL ──────────────────────────── */}
      {newGrievanceOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Lodge Workplace Grievance / Complaint</CardTitle>
                <CardDescription className="text-xs">Confidential submission to Human Resources & Employee Relations.</CardDescription>
              </div>
              <button type="button" onClick={() => setNewGrievanceOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateGrievance}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 p-3">
                  <input
                    type="checkbox"
                    id="anon"
                    checked={grvAnonymous}
                    onChange={(e) => setGrvAnonymous(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary"
                  />
                  <label htmlFor="anon" className="font-medium text-foreground cursor-pointer">
                    Submit as Anonymous Whistleblower (Name will not be recorded)
                  </label>
                </div>

                {!grvAnonymous && (
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Complainant Name</label>
                    <Input
                      placeholder="Your name..."
                      value={grvName}
                      onChange={(e) => setGrvName(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                )}

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Department</label>
                    <select
                      value={grvDept}
                      onChange={(e) => setGrvDept(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="Field Operations">Field Operations</option>
                      <option value="Network Operations">Network Operations</option>
                      <option value="Customer Support">Customer Support</option>
                      <option value="Sales">Sales</option>
                      <option value="Finance">Finance</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Grievance Category</label>
                    <select
                      value={grvCategory}
                      onChange={(e) => setGrvCategory(e.target.value as EmployeeGrievance["category"])}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="Workplace Harassment">Workplace Harassment / Bullying</option>
                      <option value="Safety Hazard / OHS">Safety Hazard / OHS Protocol</option>
                      <option value="Shift Unfairness">Shift / Roster Unfairness</option>
                      <option value="Managerial Dispute">Managerial Dispute</option>
                      <option value="Wage Discrepancy">Wage / Overtime Discrepancy</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Incident Date</label>
                  <Input
                    type="date"
                    value={grvDate}
                    onChange={(e) => setGrvDate(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Description of Grievance & Requested Outcome</label>
                  <Textarea
                    required
                    placeholder="Describe what occurred, witnesses, and your requested resolution..."
                    value={grvDescription}
                    onChange={(e) => setGrvDescription(e.target.value)}
                    rows={4}
                    className="text-xs"
                  />
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setNewGrievanceOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default">
                  Submit Grievance
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
