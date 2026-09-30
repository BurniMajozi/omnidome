"use client"

import React, { useState, useEffect } from "react"
import {
  Workflow, Plus, Play, Pause, Trash2, ArrowRight, Clock, Mail,
  CheckCircle2, AlertCircle, Sparkles, Edit3, ChevronRight, Zap,
  Users, TrendingUp, RefreshCw, Send, Check, Layers, Sliders
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { writeMarketing, type EmailJourney, type JourneyStep, type EmailTemplate } from "@/lib/marketing-api"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { describeMutationError } from "@/lib/marketing-state"
import { NotConnected } from "@/components/ui/not-connected"

interface EmailJourneyTabProps {
  onOpenTemplateInBuilder?: (templateId: string, templateName?: string) => void
}

export function EmailJourneyTab({ onOpenTemplateInBuilder }: EmailJourneyTabProps) {
  // Real journeys and templates only, each fetched once through the shared read cache.
  const { value: journeysLoad, reload: loadJourneys } = useMarketingLoad<EmailJourney[]>("/email/journeys")
  const { value: templatesLoad } = useMarketingLoad<EmailTemplate[]>("/templates")
  const journeys: EmailJourney[] = journeysLoad.state === "ready" ? journeysLoad.data : []
  const templates: EmailTemplate[] = templatesLoad.state === "ready" ? templatesLoad.data : []
  const [selectedJourneyId, setSelectedJourneyId] = useState<string>("")
  const [actionError, setActionError] = useState<string | null>(null)

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newJourneyName, setNewJourneyName] = useState("")
  const [newJourneyDesc, setNewJourneyDesc] = useState("")
  const [newJourneyTrigger, setNewJourneyTrigger] = useState("signup")

  // Step editing modal
  const [editingStep, setEditingStep] = useState<JourneyStep | null>(null)
  const [showStepModal, setShowStepModal] = useState(false)

  // Enrolment modal: a real call to the journey trigger endpoint, showing its real answer
  const [enrolling, setEnrolling] = useState(false)
  const [enrolResult, setEnrolResult] = useState<{ kind: "ok" | "error"; text: string } | null>(null)
  const [simContactEmail, setSimContactEmail] = useState("")
  const [showSimModal, setShowSimModal] = useState(false)

  const activeJourney = journeys.find((j) => j.id === selectedJourneyId) || journeys[0] || null

  const saveJourneySteps = async (journeyId: string, steps: JourneyStep[]) => {
    setActionError(null)
    const r = await writeMarketing("PUT", `/email/journeys/${journeyId}`, { steps })
    if (!r.ok) setActionError(describeMutationError(r.status, r.error))
    else loadJourneys()
  }

  const handleCreateJourney = async () => {
    if (!newJourneyName.trim()) return
    setActionError(null)
    const r = await writeMarketing<EmailJourney>("POST", "/email/journeys", {
      name: newJourneyName,
      description: newJourneyDesc,
      trigger_type: newJourneyTrigger,
      status: "draft",
      steps: [
        {
          id: `step-${Date.now()}-1`,
          type: "trigger",
          title: `Trigger: ${newJourneyTrigger === "signup" ? "Customer Signup" : newJourneyTrigger === "lead_tagged" ? "Lead Tagged" : "Custom Event"}`,
          condition: `Trigger rule: ${newJourneyTrigger}`,
        },
      ],
    })
    if (!r.ok) {
      setActionError(describeMutationError(r.status, r.error))
      return
    }
    if (r.data?.id) setSelectedJourneyId(r.data.id)
    setShowCreateModal(false)
    setNewJourneyName("")
    setNewJourneyDesc("")
    loadJourneys()
  }

  const handleToggleStatus = async (journey: EmailJourney) => {
    setActionError(null)
    const nextStatus = journey.status === "active" ? "paused" : "active"
    const r = await writeMarketing("PUT", `/email/journeys/${journey.id}`, { status: nextStatus })
    if (!r.ok) setActionError(describeMutationError(r.status, r.error))
    else loadJourneys()
  }

  const handleDeleteJourney = async (id: string) => {
    setActionError(null)
    const r = await writeMarketing("DELETE", `/email/journeys/${id}`)
    if (!r.ok) {
      setActionError(describeMutationError(r.status, r.error))
      return
    }
    setSelectedJourneyId("")
    loadJourneys()
  }

  const handleAddStepToActive = (type: JourneyStep["type"]) => {
    if (!activeJourney) return
    const newStep: JourneyStep = {
      id: `step-${Date.now()}`,
      type,
      title:
        type === "template"
          ? `Send: ${templates[0]?.name || "choose a template"}`
          : type === "delay"
          ? "Wait 2 Days"
          : type === "condition"
          ? "Branch: Check if Email Opened"
          : "Action: Update CRM Status",
      template_name: type === "template" ? templates[0]?.name : undefined,
      delay_hours: type === "delay" ? 48 : 0,
      condition: type === "condition" ? "email.opened == true" : undefined,
      action_type: type === "action" ? "add_tag" : undefined,
    }
    void saveJourneySteps(activeJourney.id, [...(activeJourney.steps || []), newStep])
  }

  const handleSaveStepModal = () => {
    if (!activeJourney || !editingStep) return
    const updatedSteps = activeJourney.steps.map((s) => (s.id === editingStep.id ? editingStep : s))
    setShowStepModal(false)
    setEditingStep(null)
    void saveJourneySteps(activeJourney.id, updatedSteps)
  }

  const handleDeleteStep = (stepId: string) => {
    if (!activeJourney) return
    void saveJourneySteps(activeJourney.id, activeJourney.steps.filter((s) => s.id !== stepId))
  }

  const runEnrolment = async () => {
    if (!activeJourney || !simContactEmail.trim()) return
    setEnrolling(true)
    setEnrolResult(null)
    setShowSimModal(true)
    const r = await writeMarketing<{ status: string; journey_id: string; enrolled_contact: string; message: string }>(
      "POST",
      `/email/journeys/${activeJourney.id}/trigger`,
      { contact_email: simContactEmail.trim() },
    )
    setEnrolling(false)
    if (!r.ok) {
      setEnrolResult({ kind: "error", text: describeMutationError(r.status, r.error) })
      return
    }
    setEnrolResult({ kind: "ok", text: r.data?.message || `Server response: ${r.data?.status ?? "no status returned"}` })
    loadJourneys()
  }

  const openRates = journeys.flatMap((j) => (j.steps || []).map((st) => st.stats?.open_rate).filter((v): v is number => typeof v === "number"))
  const avgOpenRate = openRates.length ? `${(openRates.reduce((a, b) => a + b, 0) / openRates.length).toFixed(1)}%` : "No data yet"

  if (journeysLoad.state !== "ready") {
    return <NotConnected loadable={journeysLoad} service="The marketing service" onRetry={loadJourneys} />
  }

  return (
    <div className="space-y-6">
      {/* Top Banner and Quick Stats */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Workflow className="h-5 w-5 text-blue-600" /> Templates Journey
          </h2>
          <p className="text-sm text-muted-foreground">
            Automated customer journeys and multi-step drip sequences connecting your visual email templates.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { setEnrolResult(null); setShowSimModal(true) }} disabled={!activeJourney} className="gap-1.5">
            <Zap className="h-4 w-4 text-amber-500" /> Enrol a contact
          </Button>
          <Button size="sm" onClick={() => setShowCreateModal(true)} className="bg-blue-600 hover:bg-blue-700 text-white gap-1.5">
            <Plus className="h-4 w-4" /> New Journey
          </Button>
        </div>
      </div>

      {actionError && <p role="alert" className="text-sm text-red-400">{actionError}</p>}

      {journeys.length === 0 && (
        <div className="rounded-xl border border-dashed bg-card/40 p-10 text-center text-sm text-muted-foreground">
          No journeys yet. Use New Journey to create one.
        </div>
      )}

      {/* Metrics Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Active Journeys</div>
          <div className="mt-1 text-2xl font-bold text-foreground">
            {journeys.filter((j) => j.status === "active").length}
          </div>
        </div>
        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Enrolled Contacts</div>
          <div className="mt-1 text-2xl font-bold text-foreground">
            {journeys.reduce((sum, j) => sum + (j.total_enrolled || 0), 0).toLocaleString()}
          </div>
        </div>
        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Completed Journeys</div>
          <div className="mt-1 text-2xl font-bold text-foreground">
            {journeys.reduce((sum, j) => sum + (j.total_completed || 0), 0).toLocaleString()}
          </div>
        </div>
        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Avg. Open Rate</div>
          <div className="mt-1 text-2xl font-bold text-foreground">{avgOpenRate}</div>
        </div>
      </div>

      {/* Journey Selection Tabs */}
      <div className="flex items-center gap-2 border-b pb-2 overflow-x-auto">
        {journeys.map((j) => (
          <button
            key={j.id}
            onClick={() => setSelectedJourneyId(j.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2 whitespace-nowrap transition-colors ${
              selectedJourneyId === j.id
                ? "bg-primary text-primary-foreground shadow-xs"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            <span>{j.name}</span>
            <Badge
              variant="outline"
              className={`text-[9px] px-1 py-0 uppercase ${
                j.status === "active"
                  ? "border-emerald-500 text-emerald-500 bg-emerald-500/10"
                  : "border-zinc-400 text-zinc-400"
              }`}
            >
              {j.status}
            </Badge>
          </button>
        ))}
      </div>

      {/* Active Journey Detail & Flowchart Builder */}
      {activeJourney && (
        <div className="space-y-6">
          <Card className="border-border bg-card">
            <CardHeader className="pb-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-lg">{activeJourney.name}</CardTitle>
                    <Badge
                      variant={activeJourney.status === "active" ? "default" : "secondary"}
                      className={activeJourney.status === "active" ? "bg-emerald-600" : ""}
                    >
                      {activeJourney.status.toUpperCase()}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">{activeJourney.description}</p>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleStatus(activeJourney)}
                    className="gap-1.5"
                  >
                    {activeJourney.status === "active" ? (
                      <>
                        <Pause className="h-4 w-4 text-amber-500" /> Pause Journey
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 text-emerald-500" /> Activate Journey
                      </>
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeleteJourney(activeJourney.id)}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>

            <CardContent>
              {/* Visual Workflow Steps Flow */}
              <div className="relative py-4 space-y-4">
                {activeJourney.steps?.map((step, index) => {
                  const isLast = index === activeJourney.steps.length - 1
                  return (
                    <div key={step.id} className="relative flex flex-col items-center">
                      {/* Step Card */}
                      <div className="w-full max-w-2xl bg-card border rounded-xl p-4 shadow-xs hover:border-blue-500/50 transition-all flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <div
                            className={`p-2 rounded-lg shrink-0 ${
                              step.type === "trigger"
                                ? "bg-purple-500/10 text-purple-600 dark:text-purple-400"
                                : step.type === "template"
                                ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                                : step.type === "delay"
                                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                                : step.type === "condition"
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                : "bg-zinc-500/10 text-zinc-600"
                            }`}
                          >
                            {step.type === "trigger" && <Zap className="h-5 w-5" />}
                            {step.type === "template" && <Mail className="h-5 w-5" />}
                            {step.type === "delay" && <Clock className="h-5 w-5" />}
                            {step.type === "condition" && <Sliders className="h-5 w-5" />}
                            {step.type === "action" && <CheckCircle2 className="h-5 w-5" />}
                          </div>

                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="text-xs uppercase font-mono tracking-wider text-muted-foreground">
                                Step {index + 1} · {step.type}
                              </span>
                            </div>
                            <h4 className="font-semibold text-sm text-foreground">{step.title}</h4>

                            {step.type === "template" && (
                              <div className="flex items-center gap-2 pt-1 text-xs">
                                <span className="text-muted-foreground">Template:</span>
                                <Badge variant="secondary" className="font-medium text-xs">
                                  {step.template_name || "Own your newsletter"}
                                </Badge>
                                {onOpenTemplateInBuilder && (
                                  <button
                                    onClick={() => onOpenTemplateInBuilder(step.template_id || "template-1", step.template_name)}
                                    className="text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 font-medium ml-2"
                                  >
                                    <Edit3 className="h-3 w-3" /> Edit in Visual Builder
                                  </button>
                                )}
                              </div>
                            )}

                            {step.type === "delay" && (
                              <p className="text-xs text-muted-foreground">
                                Waits {step.delay_hours || 24} hours before moving contact to next step.
                              </p>
                            )}

                            {step.type === "condition" && (
                              <p className="text-xs text-muted-foreground font-mono">
                                Rule: {step.condition || "email.opened == true"}
                              </p>
                            )}

                            {/* Performance statistics */}
                            {step.stats && (
                              <div className="flex items-center gap-3 pt-2 text-[11px] text-muted-foreground font-mono">
                                <span>Entered: {step.stats.entered}</span>
                                {step.stats.open_rate !== undefined && (
                                  <span className="text-emerald-600 font-semibold">
                                    Open: {step.stats.open_rate}%
                                  </span>
                                )}
                                {step.stats.click_rate !== undefined && (
                                  <span className="text-blue-600 font-semibold">
                                    Click: {step.stats.click_rate}%
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditingStep(step)
                              setShowStepModal(true)
                            }}
                            className="h-8 w-8 p-0"
                            title="Edit Step"
                          >
                            <Edit3 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteStep(step.id)}
                            className="h-8 w-8 p-0 text-destructive hover:bg-destructive/10"
                            title="Remove Step"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>

                      {/* Connecting Arrow */}
                      {!isLast && (
                        <div className="flex flex-col items-center my-1">
                          <div className="w-0.5 h-6 bg-border" />
                          <div className="w-2 h-2 border-r-2 border-b-2 border-border transform rotate-45 -mt-1" />
                        </div>
                      )}
                    </div>
                  )
                })}

                {/* Add Next Step Bar */}
                <div className="pt-4 flex justify-center">
                  <div className="inline-flex rounded-md shadow-xs border bg-card p-1 gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleAddStepToActive("template")}
                      className="text-xs gap-1.5"
                    >
                      <Plus className="h-3.5 w-3.5 text-blue-500" /> Add Email Template Step
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleAddStepToActive("delay")}
                      className="text-xs gap-1.5"
                    >
                      <Plus className="h-3.5 w-3.5 text-amber-500" /> Add Delay Timer
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleAddStepToActive("condition")}
                      className="text-xs gap-1.5"
                    >
                      <Plus className="h-3.5 w-3.5 text-emerald-500" /> Add Condition
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Create Journey Modal */}
      <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create Templates Journey</DialogTitle>
            <DialogDescription>
              Set up a new automated email sequence that triggers based on customer activity.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-3">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Journey Name</label>
              <Input
                placeholder="e.g. VIP Fibre Upgrade Journey"
                value={newJourneyName}
                onChange={(e) => setNewJourneyName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Description</label>
              <Input
                placeholder="Targeting residential clients for speed booster..."
                value={newJourneyDesc}
                onChange={(e) => setNewJourneyDesc(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Trigger Type</label>
              <select
                value={newJourneyTrigger}
                onChange={(e) => setNewJourneyTrigger(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="signup">New Subscriber / User Signup</option>
                <option value="lead_tagged">Lead Tagged (CRM segment)</option>
                <option value="inactivity">Dormant / Inactivity (30+ days)</option>
                <option value="custom">Custom Webhook Event</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button onClick={handleCreateJourney} disabled={!newJourneyName.trim()} className="bg-blue-600">
              Create Journey
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Step Modal */}
      <Dialog open={showStepModal} onOpenChange={setShowStepModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Journey Step</DialogTitle>
            <DialogDescription>Configure action, templates, or delay for this step.</DialogDescription>
          </DialogHeader>
          {editingStep && (
            <div className="space-y-4 py-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Step Title</label>
                <Input
                  value={editingStep.title}
                  onChange={(e) => setEditingStep({ ...editingStep, title: e.target.value })}
                />
              </div>

              {editingStep.type === "template" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Email Template</label>
                  <select
                    value={editingStep.template_name || ""}
                    onChange={(e) => setEditingStep({ ...editingStep, template_name: e.target.value })}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    <option value="Own your newsletter">Own your newsletter</option>
                    <option value="Getting Started Quick Guide">Getting Started Quick Guide</option>
                    <option value="Commercial Assessment Intro">Commercial Assessment Intro</option>
                    <option value="Enterprise Security Case Study">Enterprise Security Case Study</option>
                    <option value="Re-engagement Promo">Re-engagement Promo</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.name}>{t.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {editingStep.type === "delay" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Delay Duration (Hours)</label>
                  <Input
                    type="number"
                    value={editingStep.delay_hours || 24}
                    onChange={(e) => setEditingStep({ ...editingStep, delay_hours: Number(e.target.value) })}
                  />
                </div>
              )}

              {editingStep.type === "condition" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Condition Expression</label>
                  <Input
                    value={editingStep.condition || ""}
                    onChange={(e) => setEditingStep({ ...editingStep, condition: e.target.value })}
                    placeholder="email.opened == true"
                  />
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowStepModal(false)}>Cancel</Button>
            <Button onClick={handleSaveStepModal} className="bg-blue-600">Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Enrolment Modal */}
      <Dialog open={showSimModal} onOpenChange={setShowSimModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-amber-500" /> Enrol a contact
            </DialogTitle>
            <DialogDescription>
              Asks the marketing service to enrol this contact in the selected journey. The result below is the server&apos;s real answer.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Contact email</label>
              <Input
                value={simContactEmail}
                onChange={(e) => setSimContactEmail(e.target.value)}
                placeholder="contact@example.com"
                disabled={enrolling}
              />
            </div>

            {enrolling && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <RefreshCw className="h-3 w-3 animate-spin" /> Waiting for the server…
              </div>
            )}
            {enrolResult && (
              <p role={enrolResult.kind === "error" ? "alert" : "status"} className={`text-xs font-medium ${enrolResult.kind === "error" ? "text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                {enrolResult.text}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSimModal(false)} disabled={enrolling}>
              Close
            </Button>
            <Button onClick={runEnrolment} disabled={enrolling || !simContactEmail.trim()} className="bg-blue-600 gap-1.5">
              <Play className="h-4 w-4" /> Enrol
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
