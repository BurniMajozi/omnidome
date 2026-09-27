"use client"

import React, { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Briefcase,
  Plus,
  Search,
  CheckCircle2,
  Share2,
  Calendar,
  FileCheck,
  ShieldAlert,
  UserCheck,
  Award,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Filter,
  Check,
  X,
  Upload,
} from "lucide-react"

interface JobRequisition {
  id: string
  title: string
  department: string
  hiringManager: string
  salaryMinZAR: number
  salaryMaxZAR: number
  description: string
  requirements: string[]
  status: "Draft" | "Approved" | "Posted" | "Closed"
  postedChannels: string[]
}

interface Candidate {
  id: string
  name: string
  role: string
  jobId: string
  stage: "Applied" | "Screened" | "Shortlisted" | "Interview" | "Competence" | "Vetting" | "Offer"
  aiMatchScore: number
  keySkills: string[]
  interviewDate?: string
  interviewScore?: number
  competencyTestName?: string
  competencyScore?: number
  criminalCheckStatus: "Pending" | "Clear (AFISwitch/SAPS)" | "Flagged"
  educationCheckStatus: "Pending" | "Verified (MIE/SAQA)" | "Unverified"
}

export function TalentAtsView() {
  const [activeTab, setActiveTab] = useState<"pipeline" | "requisitions" | "vetting">("pipeline")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Requisitions State
  const [requisitions, setRequisitions] = useState<JobRequisition[]>([
    {
      id: "REQ-001",
      title: "Senior Core Network Engineer (BGP/MPLS)",
      department: "Network Operations",
      hiringManager: "Thabo Nkosi (CTO)",
      salaryMinZAR: 55000,
      salaryMaxZAR: 75000,
      description: "Architect and scale regional fiber core, BGP transit, and peering exchanges.",
      requirements: ["Cisco CCNP/CCIE", "BGP Peering", "MPLS Traffic Engineering", "MikroTik RouterOS"],
      status: "Posted",
      postedChannels: ["Careers Portal", "LinkedIn", "PNet"],
    },
    {
      id: "REQ-002",
      title: "Lead Optical Fiber Splicing Specialist",
      department: "Field Operations",
      hiringManager: "Willem Botha (Head of Field Ops)",
      salaryMinZAR: 32000,
      salaryMaxZAR: 45000,
      description: "Manage mobile van splicing teams, OTDR testing, and FTTH cabinet termination.",
      requirements: ["FOA CFOT Certified", "Fujikura 90S Fusion Splicer", "OTDR Trace Analysis", "Code 08 Driver's License"],
      status: "Posted",
      postedChannels: ["Careers Portal", "LinkedIn"],
    },
  ])

  // Candidates State
  const [candidates, setCandidates] = useState<Candidate[]>([
    {
      id: "CAN-001",
      name: "Andile Ndlovu",
      role: "Senior Core Network Engineer (BGP/MPLS)",
      jobId: "REQ-001",
      stage: "Interview",
      aiMatchScore: 94,
      keySkills: ["BGP Peering (96%)", "MPLS TE (92%)", "Cisco IOS-XR", "Python Netmiko"],
      interviewDate: "2026-09-28 10:00",
      interviewScore: 88,
      competencyTestName: "BGP Failover & Peering CLI Practical",
      competencyScore: 92,
      criminalCheckStatus: "Clear (AFISwitch/SAPS)",
      educationCheckStatus: "Verified (MIE/SAQA)",
    },
    {
      id: "CAN-002",
      name: "Kavita Patel",
      role: "Lead Optical Fiber Splicing Specialist",
      jobId: "REQ-002",
      stage: "Competence",
      aiMatchScore: 89,
      keySkills: ["Fusion Splicing (94%)", "OTDR Testing (90%)", "FOA Certified", "Civil Trenching"],
      interviewDate: "2026-09-26 14:00",
      interviewScore: 85,
      competencyTestName: "Fujikura Ribbon & Single Core Splicing Exam",
      competencyScore: 95,
      criminalCheckStatus: "Clear (AFISwitch/SAPS)",
      educationCheckStatus: "Verified (MIE/SAQA)",
    },
    {
      id: "CAN-003",
      name: "Siphesihle Maseko",
      role: "Senior Core Network Engineer (BGP/MPLS)",
      jobId: "REQ-001",
      stage: "Vetting",
      aiMatchScore: 91,
      keySkills: ["BGP", "MikroTik MTCRE", "Juniper JunOS", "DNS/DHCP"],
      interviewDate: "2026-09-24 11:00",
      interviewScore: 90,
      competencyTestName: "BGP Failover CLI Practical",
      competencyScore: 89,
      criminalCheckStatus: "Clear (AFISwitch/SAPS)",
      educationCheckStatus: "Verified (MIE/SAQA)",
    },
    {
      id: "CAN-004",
      name: "Tebogo Mokwena",
      role: "Lead Optical Fiber Splicing Specialist",
      jobId: "REQ-002",
      stage: "Screened",
      aiMatchScore: 78,
      keySkills: ["FTTH Drops", "Optical Power Meter", "Safety Protocol"],
      criminalCheckStatus: "Pending",
      educationCheckStatus: "Pending",
    },
  ])

  // New Requisition Modal State
  const [reqModalOpen, setReqModalOpen] = useState(false)
  const [newTitle, setNewTitle] = useState("")
  const [newDept, setNewDept] = useState("Network Operations")
  const [newHiringManager, setNewHiringManager] = useState("Thabo Nkosi (CTO)")
  const [newMinSalary, setNewMinSalary] = useState("40000")
  const [newMaxSalary, setNewMaxSalary] = useState("60000")
  const [newDescription, setNewDescription] = useState("")
  const [newRequirements, setNewRequirements] = useState("BGP, MPLS, Fiber Splicing, OHS Safety")

  const handleCreateRequisition = (e: React.FormEvent) => {
    e.preventDefault()
    const newReq: JobRequisition = {
      id: `REQ-${String(requisitions.length + 1).padStart(3, "0")}`,
      title: newTitle,
      department: newDept,
      hiringManager: newHiringManager,
      salaryMinZAR: Number(newMinSalary),
      salaryMaxZAR: Number(newMaxSalary),
      description: newDescription,
      requirements: newRequirements.split(",").map((s) => s.trim()),
      status: "Approved",
      postedChannels: ["Careers Portal"],
    }
    setRequisitions((prev) => [...prev, newReq])
    setToastMessage(`Job Requisition ${newReq.title} created & approved!`)
    setTimeout(() => setToastMessage(null), 3500)
    setReqModalOpen(false)
    setNewTitle("")
    setNewDescription("")
  }

  const handlePostJob = (reqId: string, channel: string) => {
    setRequisitions((prev) =>
      prev.map((r) => {
        if (r.id === reqId) {
          const channels = r.postedChannels.includes(channel)
            ? r.postedChannels
            : [...r.postedChannels, channel]
          return { ...r, status: "Posted", postedChannels: channels }
        }
        return r
      })
    )
    setToastMessage(`Job posted to ${channel}! Marketing tracking link activated.`)
    setTimeout(() => setToastMessage(null), 3000)
  }

  const handleAdvanceCandidate = (canId: string, nextStage: Candidate["stage"]) => {
    setCandidates((prev) =>
      prev.map((c) => (c.id === canId ? { ...c, stage: nextStage } : c))
    )
    setToastMessage(`Candidate moved to ${nextStage} stage!`)
    setTimeout(() => setToastMessage(null), 3000)
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
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-primary/40 bg-primary/10 text-primary">
              <Briefcase className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Applicant Tracking System (ATS)</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  End-to-End Recruitment
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Job descriptions & salary brackets, multi-channel marketing, AI CV scoring, interview scorecards, and criminal & education vetting.
              </p>
            </div>
          </div>

          <Button
            size="sm"
            variant="default"
            className="gap-1.5 text-xs font-semibold"
            onClick={() => setReqModalOpen(true)}
          >
            <Plus className="h-3.5 w-3.5" />
            Create Job Description
          </Button>
        </div>
      </div>

      {/* Sub-Tab Navigation */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2 text-xs">
        <button
          type="button"
          onClick={() => setActiveTab("pipeline")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "pipeline"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Candidate Pipeline & AI Scoring ({candidates.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("requisitions")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "requisitions"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Job Requisitions & Marketing Posts ({requisitions.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("vetting")}
          className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
            activeTab === "vetting"
              ? "bg-primary/15 text-primary border border-primary/30"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
          }`}
        >
          Criminal (SAPS) & Education (SAQA) Vetting
        </button>
      </div>

      {/* ── TAB 1: Candidate Pipeline & AI Scoring ─────────────────────── */}
      {activeTab === "pipeline" && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {["Applied", "Interview", "Competence", "Vetting"].map((stage) => {
              const count = candidates.filter((c) => c.stage === stage).length
              return (
                <div key={stage} className="rounded-lg border border-border bg-card/60 p-3 text-xs">
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>{stage} Stage</span>
                    <Badge variant="outline" className="text-[10px]">{count}</Badge>
                  </div>
                  <p className="mt-1 text-lg font-bold text-foreground">{count} Candidates</p>
                </div>
              )
            })}
          </div>

          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base">Candidate Pipeline Board</CardTitle>
              <CardDescription className="text-xs">
                Parsed technical CV match scores, scheduled interviews, and testing scorecards.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Candidate</th>
                      <th className="py-2.5 px-4 font-medium">Applying For</th>
                      <th className="py-2.5 px-4 font-medium">AI CV Match</th>
                      <th className="py-2.5 px-4 font-medium">Stage</th>
                      <th className="py-2.5 px-4 font-medium">Interview / Scorecard</th>
                      <th className="py-2.5 px-4 font-medium">Competency Practical</th>
                      <th className="py-2.5 px-4 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {candidates.map((c) => (
                      <tr key={c.id} className="hover:bg-muted/30">
                        <td className="py-3 px-4">
                          <p className="font-semibold text-foreground">{c.name}</p>
                          <p className="text-[10px] text-muted-foreground font-mono">{c.id}</p>
                        </td>
                        <td className="py-3 px-4 text-muted-foreground">{c.role}</td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5">
                            <span className="font-bold text-emerald-400 font-mono">{c.aiMatchScore}%</span>
                            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px] py-0">
                              High Match
                            </Badge>
                          </div>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {c.keySkills.slice(0, 2).map((s) => (
                              <span key={s} className="text-[10px] text-muted-foreground bg-muted/40 rounded px-1">{s}</span>
                            ))}
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant="outline" className="border-primary/40 text-primary">
                            {c.stage}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          {c.interviewDate ? (
                            <div>
                              <p className="text-foreground font-medium">{c.interviewDate}</p>
                              {c.interviewScore && (
                                <p className="text-[11px] text-emerald-400">Scorecard: {c.interviewScore}/100</p>
                              )}
                            </div>
                          ) : (
                            <Button size="sm" variant="outline" className="h-6 text-[10px]">
                              Schedule Interview
                            </Button>
                          )}
                        </td>
                        <td className="py-3 px-4">
                          {c.competencyTestName ? (
                            <div>
                              <p className="text-foreground font-medium truncate max-w-[160px]">{c.competencyTestName}</p>
                              {c.competencyScore && (
                                <p className="text-[11px] text-primary">Score: {c.competencyScore}% (Pass)</p>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted-foreground text-[11px]">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {c.stage === "Applied" && (
                              <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => handleAdvanceCandidate(c.id, "Interview")}>
                                Advance
                              </Button>
                            )}
                            {c.stage === "Interview" && (
                              <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => handleAdvanceCandidate(c.id, "Competence")}>
                                To Test
                              </Button>
                            )}
                            {c.stage === "Competence" && (
                              <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => handleAdvanceCandidate(c.id, "Vetting")}>
                                To Vetting
                              </Button>
                            )}
                            {c.stage === "Vetting" && (
                              <Button size="sm" variant="default" className="h-7 text-xs" onClick={() => handleAdvanceCandidate(c.id, "Offer")}>
                                Extend Offer
                              </Button>
                            )}
                          </div>
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

      {/* ── TAB 2: Job Requisitions & Marketing Posts ──────────────────── */}
      {activeTab === "requisitions" && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {requisitions.map((req) => (
              <Card key={req.id} className="border-border">
                <CardHeader className="pb-3 border-b border-border/60">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base font-semibold">{req.title}</CardTitle>
                      <CardDescription className="text-xs">{req.department} • Hiring Manager: {req.hiringManager}</CardDescription>
                    </div>
                    <Badge variant="outline" className="border-primary/40 text-primary">
                      {req.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-3 text-xs">
                  <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Authorized Salary Range:</span>
                      <span className="font-bold text-emerald-400 font-mono">
                        R {req.salaryMinZAR.toLocaleString()} - R {req.salaryMaxZAR.toLocaleString()} ZAR / mo
                      </span>
                    </div>
                    <p className="text-muted-foreground mt-1">{req.description}</p>
                  </div>

                  <div className="space-y-1">
                    <span className="font-semibold text-foreground">Required Competencies:</span>
                    <div className="flex flex-wrap gap-1">
                      {req.requirements.map((reqSkill) => (
                        <Badge key={reqSkill} variant="outline" className="border-border text-foreground text-[10px]">
                          {reqSkill}
                        </Badge>
                      ))}
                    </div>
                  </div>

                  <div className="border-t border-border/60 pt-3">
                    <p className="font-semibold text-foreground mb-1.5">Broadcast on Marketing Channels:</p>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {["LinkedIn", "PNet", "Careers Portal", "Social Campaign"].map((channel) => {
                        const isPosted = req.postedChannels.includes(channel)
                        return (
                          <Button
                            key={channel}
                            size="sm"
                            variant={isPosted ? "secondary" : "outline"}
                            className="h-7 text-xs gap-1"
                            onClick={() => handlePostJob(req.id, channel)}
                          >
                            <Share2 className="h-3 w-3" />
                            {isPosted ? `Posted on ${channel}` : `Post to ${channel}`}
                          </Button>
                        )
                      })}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ── TAB 3: Criminal & Education Vetting ─────────────────────────── */}
      {activeTab === "vetting" && (
        <div className="space-y-4">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4 text-cyan-400" /> Statutory Pre-Employment Vetting
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Automated background checks via AFISwitch (SAPS biometric criminal verification) & MIE / SAQA qualification verification.
                  </CardDescription>
                </div>
                <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                  AFISwitch & MIE API Connected
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Candidate</th>
                      <th className="py-2.5 px-4 font-medium">Position</th>
                      <th className="py-2.5 px-4 font-medium">SAPS Criminal Verification</th>
                      <th className="py-2.5 px-4 font-medium">SAQA Education Verification</th>
                      <th className="py-2.5 px-4 font-medium text-right">Certificate</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {candidates.map((can) => (
                      <tr key={can.id} className="hover:bg-muted/30">
                        <td className="py-3 px-4 font-semibold text-foreground">{can.name}</td>
                        <td className="py-3 px-4 text-muted-foreground">{can.role}</td>
                        <td className="py-3 px-4">
                          <Badge
                            variant="outline"
                            className={
                              can.criminalCheckStatus.includes("Clear")
                                ? "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                                : "border-amber-500/40 text-amber-400 bg-amber-500/10"
                            }
                          >
                            {can.criminalCheckStatus}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          <Badge
                            variant="outline"
                            className={
                              can.educationCheckStatus.includes("Verified")
                                ? "border-cyan-500/40 text-cyan-400 bg-cyan-500/10"
                                : "border-amber-500/40 text-amber-400 bg-amber-500/10"
                            }
                          >
                            {can.educationCheckStatus}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Button size="sm" variant="ghost" className="h-7 text-xs text-primary gap-1">
                            <FileCheck className="h-3.5 w-3.5" /> View Report
                          </Button>
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

      {/* ── CREATE JOB REQUISITION MODAL ──────────────────────────────── */}
      {reqModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-lg border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">New Job Description & Requisition</CardTitle>
                <CardDescription className="text-xs">Authorized by HR & Department Hiring Manager.</CardDescription>
              </div>
              <button type="button" onClick={() => setReqModalOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateRequisition}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Job Title *</label>
                  <Input
                    required
                    placeholder="e.g. Lead Core Network Engineer"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Department</label>
                    <select
                      value={newDept}
                      onChange={(e) => setNewDept(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="Network Operations">Network Operations</option>
                      <option value="Core Infrastructure">Core Infrastructure</option>
                      <option value="Field Operations">Field Operations</option>
                      <option value="Customer Support">Customer Support</option>
                      <option value="Sales">Sales</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Hiring Manager</label>
                    <Input
                      value={newHiringManager}
                      onChange={(e) => setNewHiringManager(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Min Salary (ZAR / mo)</label>
                    <Input
                      type="number"
                      value={newMinSalary}
                      onChange={(e) => setNewMinSalary(e.target.value)}
                      className="h-8 text-xs font-mono"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Max Salary (ZAR / mo)</label>
                    <Input
                      type="number"
                      value={newMaxSalary}
                      onChange={(e) => setNewMaxSalary(e.target.value)}
                      className="h-8 text-xs font-mono"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Job Description & Responsibilities</label>
                  <Textarea
                    placeholder="Key operational outcomes, uptime SLAs, and team leadership..."
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    rows={3}
                    className="text-xs"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-medium text-foreground">Required Skills & Certifications (Comma Separated)</label>
                  <Input
                    value={newRequirements}
                    onChange={(e) => setNewRequirements(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setReqModalOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default">
                  Create & Authorize Requisition
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
