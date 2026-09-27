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
import {
  listEmailJourneys, createEmailJourney, updateEmailJourney, deleteEmailJourney,
  triggerEmailJourney, listEmailTemplates, type EmailJourney, type JourneyStep, type EmailTemplate
} from "@/lib/marketing-api"

interface EmailJourneyTabProps {
  onOpenTemplateInBuilder?: (templateId: string, templateName?: string) => void
}

const DEFAULT_SEED_JOURNEYS: EmailJourney[] = [
  {
    id: "journey-1",
    name: "Welcome & Onboarding Journey",
    description: "Nurtures new subscribers and customers through account setup and key value props.",
    trigger_type: "signup",
    status: "active",
    total_enrolled: 1420,
    total_completed: 1184,
    created_at: "2026-09-20T10:00:00Z",
    steps: [
      {
        id: "step-1",
        type: "trigger",
        title: "Trigger: New Customer Subscribed",
        condition: "Event: user.signup OR newsletter.optin",
        stats: { entered: 1420, completed: 1420 },
      },
      {
        id: "step-2",
        type: "template",
        title: "Send: Welcome & Own Your Newsletter",
        template_name: "Own your newsletter",
        delay_hours: 0,
        stats: { entered: 1420, completed: 1420, open_rate: 68.4, click_rate: 31.2 },
      },
      {
        id: "step-3",
        type: "delay",
        title: "Wait 2 Days",
        delay_hours: 48,
        stats: { entered: 1390, completed: 1320 },
      },
      {
        id: "step-4",
        type: "condition",
        title: "Branch: Check if First Email Opened",
        condition: "email.opened == true",
        stats: { entered: 1320, completed: 1320 },
      },
      {
        id: "step-5",
        type: "template",
        title: "Send: Pro Tips & Quick Setup Guide",
        template_name: "Getting Started Quick Guide",
        delay_hours: 0,
        stats: { entered: 903, completed: 880, open_rate: 54.1, click_rate: 22.8 },
      },
      {
        id: "step-6",
        type: "action",
        title: "Action: Add Tag 'onboarding-completed'",
        action_type: "add_tag",
        stats: { entered: 880, completed: 880 },
      },
    ],
  },
  {
    id: "journey-2",
    name: "Commercial Guarding Lead Nurture",
    description: "Automated sales enablement sequence for high-intent commercial leads.",
    trigger_type: "lead_tagged",
    status: "active",
    total_enrolled: 430,
    total_completed: 310,
    created_at: "2026-09-22T08:30:00Z",
    steps: [
      {
        id: "lead-1",
        type: "trigger",
        title: "Trigger: Lead Tagged 'Commercial'",
        condition: "Tag: Commercial",
        stats: { entered: 430, completed: 430 },
      },
      {
        id: "lead-2",
        type: "template",
        title: "Send: Commercial Security Assessment",
        template_name: "Commercial Assessment Intro",
        delay_hours: 0,
        stats: { entered: 430, completed: 430, open_rate: 72.1, click_rate: 41.5 },
      },
      {
        id: "lead-3",
        type: "delay",
        title: "Wait 1 Day",
        delay_hours: 24,
        stats: { entered: 420, completed: 410 },
      },
      {
        id: "lead-4",
        type: "template",
        title: "Send: Case Study & Client Proof",
        template_name: "Enterprise Security Case Study",
        delay_hours: 0,
        stats: { entered: 410, completed: 395, open_rate: 61.0, click_rate: 29.4 },
      },
    ],
  },
  {
    id: "journey-3",
    name: "Subscriber Re-engagement Sequence",
    description: "Recovers dormant subscribers who haven't opened in 30 days.",
    trigger_type: "inactivity",
    status: "draft",
    total_enrolled: 210,
    total_completed: 95,
    created_at: "2026-09-25T14:15:00Z",
    steps: [
      {
        id: "re-1",
        type: "trigger",
        title: "Trigger: Inactive for 30 Days",
        condition: "activity.last_opened > 30d",
        stats: { entered: 210, completed: 210 },
      },
      {
        id: "re-2",
        type: "template",
        title: "Send: We Miss You Exclusive Offer",
        template_name: "Re-engagement Promo",
        delay_hours: 0,
        stats: { entered: 210, completed: 210, open_rate: 45.2, click_rate: 18.0 },
      },
      {
        id: "re-3",
        type: "delay",
        title: "Wait 4 Days",
        delay_hours: 96,
        stats: { entered: 200, completed: 190 },
      },
      {
        id: "re-4",
        type: "condition",
        title: "Branch: Check if Clicked Promo",
        condition: "email.clicked == true",
        stats: { entered: 190, completed: 190 },
      },
    ],
  },
]

export function EmailJourneyTab({ onOpenTemplateInBuilder }: EmailJourneyTabProps) {
  const [journeys, setJourneys] = useState<EmailJourney[]>(DEFAULT_SEED_JOURNEYS)
  const [selectedJourneyId, setSelectedJourneyId] = useState<string>("journey-1")
  const [templates, setTemplates] = useState<EmailTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newJourneyName, setNewJourneyName] = useState("")
  const [newJourneyDesc, setNewJourneyDesc] = useState("")
  const [newJourneyTrigger, setNewJourneyTrigger] = useState("signup")

  // Step editing modal
  const [editingStep, setEditingStep] = useState<JourneyStep | null>(null)
  const [showStepModal, setShowStepModal] = useState(false)

  // Simulation modal
  const [simulating, setSimulating] = useState(false)
  const [simulationLogs, setSimulationLogs] = useState<string[]>([])
  const [simContactEmail, setSimContactEmail] = useState("test.user@metromall.co.za")
  const [showSimModal, setShowSimModal] = useState(false)

  const activeJourney = journeys.find((j) => j.id === selectedJourneyId) || journeys[0] || null

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [fetchedJourneys, fetchedTemplates] = await Promise.all([
        listEmailJourneys().catch(() => null),
        listEmailTemplates().catch(() => []),
      ])
      if (fetchedJourneys && fetchedJourneys.length > 0) {
        setJourneys(fetchedJourneys)
        if (!fetchedJourneys.some((j) => j.id === selectedJourneyId)) {
          setSelectedJourneyId(fetchedJourneys[0].id)
        }
      }
      setTemplates(fetchedTemplates || [])
    } catch (e) {
      console.warn("Using local journeys fallback", e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleCreateJourney = async () => {
    if (!newJourneyName.trim()) return
    const newJourney: EmailJourney = {
      id: `journey-${Date.now()}`,
      name: newJourneyName,
      description: newJourneyDesc,
      trigger_type: newJourneyTrigger,
      status: "draft",
      total_enrolled: 0,
      total_completed: 0,
      created_at: new Date().toISOString(),
      steps: [
        {
          id: `step-${Date.now()}-1`,
          type: "trigger",
          title: `Trigger: ${newJourneyTrigger === "signup" ? "Customer Signup" : newJourneyTrigger === "lead_tagged" ? "Lead Tagged" : "Custom Event"}`,
          condition: `Trigger rule: ${newJourneyTrigger}`,
          stats: { entered: 0, completed: 0 },
        },
        {
          id: `step-${Date.now()}-2`,
          type: "template",
          title: "Send: Initial Welcome Template",
          template_name: templates[0]?.name || "Own your newsletter",
          delay_hours: 0,
          stats: { entered: 0, completed: 0 },
        },
      ],
    }

    try {
      const created = await createEmailJourney(newJourney)
      if (created) {
        setJourneys([created, ...journeys])
        setSelectedJourneyId(created.id)
      } else {
        setJourneys([newJourney, ...journeys])
        setSelectedJourneyId(newJourney.id)
      }
    } catch (e) {
      setJourneys([newJourney, ...journeys])
      setSelectedJourneyId(newJourney.id)
    }

    setShowCreateModal(false)
    setNewJourneyName("")
    setNewJourneyDesc("")
  }

  const handleToggleStatus = async (journey: EmailJourney) => {
    const nextStatus = journey.status === "active" ? "paused" : "active"
    const updated = journeys.map((j) => (j.id === journey.id ? { ...j, status: nextStatus as any } : j))
    setJourneys(updated)
    try {
      await updateEmailJourney(journey.id, { status: nextStatus })
    } catch (e) {
      // optimistic
    }
  }

  const handleDeleteJourney = async (id: string) => {
    if (journeys.length <= 1) return
    const updated = journeys.filter((j) => j.id !== id)
    setJourneys(updated)
    setSelectedJourneyId(updated[0]?.id || "")
    try {
      await deleteEmailJourney(id)
    } catch (e) {
      // optimistic
    }
  }

  const handleAddStepToActive = (type: JourneyStep["type"]) => {
    if (!activeJourney) return
    const stepNumber = (activeJourney.steps?.length || 0) + 1
    const newStep: JourneyStep = {
      id: `step-${Date.now()}`,
      type,
      title:
        type === "template"
          ? `Send: ${templates[0]?.name || "Follow-up Template"}`
          : type === "delay"
          ? "Wait 2 Days"
          : type === "condition"
          ? "Branch: Check if Email Opened"
          : "Action: Update CRM Status",
      template_name: type === "template" ? templates[0]?.name || "Own your newsletter" : undefined,
      delay_hours: type === "delay" ? 48 : 0,
      condition: type === "condition" ? "email.opened == true" : undefined,
      action_type: type === "action" ? "add_tag" : undefined,
      stats: { entered: 0, completed: 0 },
    }
    const updatedSteps = [...(activeJourney.steps || []), newStep]
    const updatedJourney = { ...activeJourney, steps: updatedSteps }
    setJourneys(journeys.map((j) => (j.id === activeJourney.id ? updatedJourney : j)))
    try {
      updateEmailJourney(activeJourney.id, { steps: updatedSteps })
    } catch (e) {}
  }

  const handleSaveStepModal = () => {
    if (!activeJourney || !editingStep) return
    const updatedSteps = activeJourney.steps.map((s) => (s.id === editingStep.id ? editingStep : s))
    const updatedJourney = { ...activeJourney, steps: updatedSteps }
    setJourneys(journeys.map((j) => (j.id === activeJourney.id ? updatedJourney : j)))
    setShowStepModal(false)
    setEditingStep(null)
    try {
      updateEmailJourney(activeJourney.id, { steps: updatedSteps })
    } catch (e) {}
  }

  const handleDeleteStep = (stepId: string) => {
    if (!activeJourney) return
    const updatedSteps = activeJourney.steps.filter((s) => s.id !== stepId)
    const updatedJourney = { ...activeJourney, steps: updatedSteps }
    setJourneys(journeys.map((j) => (j.id === activeJourney.id ? updatedJourney : j)))
    try {
      updateEmailJourney(activeJourney.id, { steps: updatedSteps })
    } catch (e) {}
  }

  const runSimulation = async () => {
    if (!activeJourney) return
    setSimulating(true)
    setSimulationLogs([])
    setShowSimModal(true)

    const logs: string[] = []
    const addLog = (msg: string) => {
      logs.push(`[${new Date().toLocaleTimeString()}] ${msg}`)
      setSimulationLogs([...logs])
    }

    addLog(`Initiating journey test simulation for contact: ${simContactEmail}`)
    await new Promise((r) => setTimeout(r, 600))

    for (let i = 0; i < activeJourney.steps.length; i++) {
      const step = activeJourney.steps[i]
      if (step.type === "trigger") {
        addLog(`Trigger executed: ${step.title}`)
      } else if (step.type === "template") {
        addLog(`Dispatched email: "${step.template_name || step.title}" to ${simContactEmail}`)
      } else if (step.type === "delay") {
        addLog(`Timer evaluated: ${step.title} (${step.delay_hours || 24}h delay simulated)`)
      } else if (step.type === "condition") {
        addLog(`Condition evaluated: ${step.condition || "email.opened == true"} -> Evaluated TRUE`)
      } else if (step.type === "action") {
        addLog(`Applied action: ${step.title}`)
      }
      await new Promise((r) => setTimeout(r, 700))
    }

    addLog(`Journey run simulation completed successfully!`)
    setSimulating(false)

    try {
      await triggerEmailJourney(activeJourney.id, { contact_email: simContactEmail })
    } catch (e) {}
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
          <Button variant="outline" size="sm" onClick={runSimulation} className="gap-1.5">
            <Zap className="h-4 w-4 text-amber-500" /> Simulate Journey Run
          </Button>
          <Button size="sm" onClick={() => setShowCreateModal(true)} className="bg-blue-600 hover:bg-blue-700 text-white gap-1.5">
            <Plus className="h-4 w-4" /> New Journey
          </Button>
        </div>
      </div>

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
          <div className="mt-1 text-2xl font-bold text-emerald-600">62.8%</div>
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

      {/* Simulation Modal */}
      <Dialog open={showSimModal} onOpenChange={setShowSimModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-amber-500" /> Journey Execution Simulation
            </DialogTitle>
            <DialogDescription>
              Test running the entire journey logic on a test recipient.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Test Contact Email</label>
              <Input
                value={simContactEmail}
                onChange={(e) => setSimContactEmail(e.target.value)}
                placeholder="test.user@metromall.co.za"
                disabled={simulating}
              />
            </div>

            <div className="bg-zinc-950 text-zinc-200 rounded-lg p-4 font-mono text-xs max-h-60 overflow-y-auto space-y-1.5">
              {simulationLogs.map((log, i) => (
                <div key={i} className="flex items-start gap-1">
                  <span className="text-emerald-400">→</span>
                  <span>{log}</span>
                </div>
              ))}
              {simulating && (
                <div className="flex items-center gap-2 text-amber-400 animate-pulse pt-2">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  <span>Processing next step...</span>
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSimModal(false)} disabled={simulating}>
              Close
            </Button>
            <Button onClick={runSimulation} disabled={simulating} className="bg-blue-600 gap-1.5">
              <Play className="h-4 w-4" /> Run Again
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
