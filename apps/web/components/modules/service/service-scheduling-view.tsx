"use client"

import React, { useState, useEffect, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Calendar,
  Clock,
  Send,
  CheckCircle2,
  AlertTriangle,
  UserCheck,
  TrendingUp,
  Plus,
  Trash2,
  Edit3,
  Users,
  Sparkles,
  PhoneCall,
  PhoneIncoming,
  PhoneOutgoing,
  DollarSign,
  Wallet,
  ShieldAlert,
  Building2,
  Check,
  X,
  RefreshCw,
  Layers,
  Zap,
} from "lucide-react"
import type { ShiftAssignment, DemandTimelineSlot } from "@/app/api/service/schedule/route"

export function ServiceSchedulingView() {
  const [timeline, setTimeline] = useState<"realtime" | "yesterday" | "month_end_peak" | "storm_outage">("realtime")
  const [selectedDept, setSelectedDept] = useState("ALL")
  const [roster, setRoster] = useState<ShiftAssignment[]>([])
  const [demandSlots, setDemandSlots] = useState<DemandTimelineSlot[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [broadcastState, setBroadcastState] = useState<"idle" | "sending" | "sent">("idle")

  // Modal states
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingShift, setEditingShift] = useState<ShiftAssignment | null>(null)

  // Add/Edit Form State
  const [formName, setFormName] = useState("")
  const [formDept, setFormDept] = useState<ShiftAssignment["department"]>("Customer Support")
  const [formShiftType, setFormShiftType] = useState<ShiftAssignment["shiftType"]>("Peak Support (08:00 - 17:00)")
  const [formStartTime, setFormStartTime] = useState("08:00")
  const [formEndTime, setFormEndTime] = useState("17:00")
  const [formStation, setFormStation] = useState("Inbound Queue & Live Chat")
  const [formIsOutsourced, setFormIsOutsourced] = useState(false)
  const [formBrokerName, setFormBrokerName] = useState("CCI South Africa")
  const [formHourlyRate, setFormHourlyRate] = useState(125)
  const [formMttr, setFormMttr] = useState(15)
  const [formFtr, setFormFtr] = useState(92)
  const [formSkills, setFormSkills] = useState("PPPoE Setup, Customer Empathy, English & Zulu")
  const [formOnLeave, setFormOnLeave] = useState(false)
  const [formLeaveReason, setFormLeaveReason] = useState("")
  const [formOutboundDials, setFormOutboundDials] = useState(0)
  const [formCommission, setFormCommission] = useState(0)

  const fetchScheduleData = async () => {
    try {
      setLoading(true)
      const res = await fetch(`/api/service/schedule?timeline=${timeline}&department=${selectedDept}`)
      if (res.ok) {
        const json = await res.json()
        setRoster(json.roster || [])
        setDemandSlots(json.demandTimeline || [])
        setSummary(json.summary || null)
      }
    } catch (err) {
      console.error("Failed to fetch service schedule:", err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchScheduleData()
  }, [timeline, selectedDept])

  const handleOpenAdd = () => {
    setFormName("")
    setFormDept("Customer Support")
    setFormShiftType("Peak Support (08:00 - 17:00)")
    setFormStartTime("08:00")
    setFormEndTime("17:00")
    setFormStation("Inbound Queue & Live Chat")
    setFormIsOutsourced(false)
    setFormBrokerName("CCI South Africa")
    setFormHourlyRate(125)
    setFormMttr(15)
    setFormFtr(92)
    setFormSkills("PPPoE Setup, Customer Empathy")
    setFormOnLeave(false)
    setFormLeaveReason("")
    setFormOutboundDials(0)
    setFormCommission(0)
    setAddModalOpen(true)
  }

  const handleOpenEdit = (shift: ShiftAssignment) => {
    setEditingShift(shift)
    setFormName(shift.employeeName)
    setFormDept(shift.department)
    setFormShiftType(shift.shiftType)
    setFormStartTime(shift.startTime)
    setFormEndTime(shift.endTime)
    setFormStation(shift.station)
    setFormIsOutsourced(shift.isOutsourced)
    setFormBrokerName(shift.brokerName || "CCI South Africa")
    setFormHourlyRate(shift.hourlyRateZar)
    setFormMttr(shift.mttrMinutes)
    setFormFtr(shift.ftrPercent)
    setFormSkills(shift.skillTags.join(", "))
    setFormOnLeave(shift.onLeave)
    setFormLeaveReason(shift.leaveReason || "")
    setFormOutboundDials(shift.outboundCallsToday)
    setFormCommission(shift.commissionEarnedZar)
    setEditModalOpen(true)
  }

  const handleSaveAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const payload = {
        employeeName: formName,
        department: formDept,
        shiftType: formShiftType,
        startTime: formStartTime,
        endTime: formEndTime,
        station: formStation,
        isOutsourced: formIsOutsourced,
        brokerName: formIsOutsourced ? formBrokerName : undefined,
        hourlyRateZar: Number(formHourlyRate),
        overtimeHours: 0,
        onLeave: formOnLeave,
        leaveReason: formLeaveReason,
        mttrMinutes: Number(formMttr),
        ftrPercent: Number(formFtr),
        skillTags: formSkills.split(",").map((s) => s.trim()).filter(Boolean),
        outboundCallsToday: Number(formOutboundDials),
        commissionEarnedZar: Number(formCommission),
      }

      const res = await fetch("/api/service/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        setToastMessage(`Assigned ${formName} to ${formShiftType}!`)
        setAddModalOpen(false)
        fetchScheduleData()
        setTimeout(() => setToastMessage(null), 3000)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingShift) return
    try {
      const payload = {
        id: editingShift.id,
        employeeName: formName,
        department: formDept,
        shiftType: formShiftType,
        startTime: formStartTime,
        endTime: formEndTime,
        station: formStation,
        isOutsourced: formIsOutsourced,
        brokerName: formIsOutsourced ? formBrokerName : undefined,
        hourlyRateZar: Number(formHourlyRate),
        onLeave: formOnLeave,
        leaveReason: formLeaveReason,
        mttrMinutes: Number(formMttr),
        ftrPercent: Number(formFtr),
        skillTags: formSkills.split(",").map((s) => s.trim()).filter(Boolean),
        outboundCallsToday: Number(formOutboundDials),
        commissionEarnedZar: Number(formCommission),
      }

      const res = await fetch("/api/service/schedule", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        setToastMessage(`Updated shift details for ${formName}!`)
        setEditModalOpen(false)
        setEditingShift(null)
        fetchScheduleData()
        setTimeout(() => setToastMessage(null), 3000)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleDeleteShift = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to remove ${name} from today's active shift roster?`)) return
    try {
      const res = await fetch(`/api/service/schedule?id=${id}`, { method: "DELETE" })
      if (res.ok) {
        setToastMessage(`Removed ${name} from shift roster.`)
        fetchScheduleData()
        setTimeout(() => setToastMessage(null), 3000)
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleAutoBalance = () => {
    setToastMessage("AI Shift Balancer: Matched 4 outsourced backup agents (CCI) to cover the 14:00 - 16:00 peak gap!")
    setTimeout(() => setToastMessage(null), 4000)
  }

  const handleBroadcastRoster = () => {
    setBroadcastState("sending")
    setTimeout(() => {
      setBroadcastState("sent")
      setToastMessage("Shift roster dispatched via SMS & WhatsApp to all rostered technicians & support agents!")
      setTimeout(() => {
        setBroadcastState("idle")
        setToastMessage(null)
      }, 4000)
    }, 1200)
  }

  return (
    <div className="space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-950/95 px-4 py-3 text-sm text-emerald-200 shadow-2xl backdrop-blur animate-in fade-in">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Banner Header */}
      <div className="rounded-xl border border-border bg-gradient-to-r from-card/90 via-card/70 to-cyan-950/20 p-5 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 shadow-sm">
              <Clock className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold text-foreground">Service Demand & Shift Rostering Engine</h2>
                <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 bg-cyan-500/10 text-[10px] font-semibold">
                  SLA Level Driver
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 max-w-2xl">
                Staff demand schedules directly drive customer service levels, MTTR, and first-contact resolution. Incorporates leave tracking, outsourced BPO brokers, MTTR skills, and outbound commissions.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="default"
              className="gap-1.5 text-xs font-semibold h-9"
              onClick={handleOpenAdd}
            >
              <Plus className="h-4 w-4" />
              Add Shift Assignment
            </Button>

            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs h-9 border-cyan-500/40 text-cyan-400 hover:bg-cyan-950/20"
              onClick={handleAutoBalance}
            >
              <Zap className="h-3.5 w-3.5" />
              Auto-Balance Gaps
            </Button>

            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs h-9"
              disabled={broadcastState === "sending"}
              onClick={handleBroadcastRoster}
            >
              <Send className="h-3.5 w-3.5" />
              {broadcastState === "sending" ? "Broadcasting..." : "Broadcast SMS / WhatsApp"}
            </Button>
          </div>
        </div>
      </div>

      {/* KPI Stats Grid: Inbound, Outbound, MTTR, Cost & Leave */}
      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {/* Card 1: Inbound Call Telemetry */}
          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Inbound Answer Rate</span>
                <PhoneIncoming className="h-4 w-4 text-emerald-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-foreground font-mono">
                  {summary.inboundCallMetrics.answerRatePercent}%
                </span>
                <span className="text-[11px] text-emerald-400 font-semibold">
                  {summary.inboundCallMetrics.answeredCalls} / {summary.inboundCallMetrics.offeredCalls}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Abandonment: {summary.inboundCallMetrics.abandonmentRatePercent}%</span>
                <span>ASA: {summary.inboundCallMetrics.averageSpeedOfAnswerSec}s</span>
              </div>
            </CardContent>
          </Card>

          {/* Card 2: MTTR & FTR Resolution Skills */}
          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Skills MTTR & FTR</span>
                <TrendingUp className="h-4 w-4 text-cyan-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-foreground font-mono">
                  {summary.avgMttrMinutes}m
                </span>
                <span className="text-[11px] text-cyan-400 font-semibold">
                  FTR: {summary.avgFtrPercent}%
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Avg CSAT: ★ {summary.avgCsatScore}/5.0</span>
                <span>Surveys: {summary.inboundCallMetrics.postCallSurveysReceived}</span>
              </div>
            </CardContent>
          </Card>

          {/* Card 3: Outbound Dials & Commissions */}
          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Outbound Cold Calling</span>
                <PhoneOutgoing className="h-4 w-4 text-violet-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-foreground font-mono">
                  {summary.totalOutboundDials}
                </span>
                <span className="text-[11px] text-violet-400 font-semibold">
                  {summary.totalOutboundConversions} Wins
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Commission Pool:</span>
                <strong className="text-emerald-400 font-mono">R {summary.totalCommissionPoolZar.toLocaleString()}</strong>
              </div>
            </CardContent>
          </Card>

          {/* Card 4: Cost & Outsourced Broker Model */}
          <Card className="border-border bg-card/60">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Daily Workforce Cost</span>
                <Wallet className="h-4 w-4 text-amber-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold text-foreground font-mono">
                  R {summary.costSummary.totalDailyZar.toLocaleString()}
                </span>
                <span className="text-[11px] text-amber-400 font-semibold">
                  {summary.outsourcedCount} Outsourced BPO
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>On Leave: <strong className="text-pink-400">{summary.onLeaveCount}</strong></span>
                <span>Overtime: {summary.totalOvertimeHours} hrs</span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── SECTION 1: 24-HOUR OPERATIONAL DEMAND WITH TIMELINE HISTORY ─── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Layers className="h-4 w-4 text-cyan-400" />
                Granular 24-Hour Operational Demand & Staffing Gaps
              </CardTitle>
              <CardDescription className="text-xs">
                Hourly requirement vs. scheduled headcount. Select historical scenarios to adjust staffing for month-end billing spikes or physical storm outages.
              </CardDescription>
            </div>

            {/* Timeline History Scenario Selector */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-muted-foreground mr-1">Demand Timeline:</span>
              <button
                type="button"
                onClick={() => setTimeline("realtime")}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  timeline === "realtime"
                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 font-semibold"
                    : "text-muted-foreground hover:bg-muted/40"
                }`}
              >
                Today (Live)
              </button>
              <button
                type="button"
                onClick={() => setTimeline("yesterday")}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  timeline === "yesterday"
                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 font-semibold"
                    : "text-muted-foreground hover:bg-muted/40"
                }`}
              >
                Yesterday Actual
              </button>
              <button
                type="button"
                onClick={() => setTimeline("month_end_peak")}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  timeline === "month_end_peak"
                    ? "bg-amber-500/20 text-amber-400 border border-amber-500/40 font-semibold"
                    : "text-muted-foreground hover:bg-muted/40"
                }`}
              >
                Month-End Billing Peak
              </button>
              <button
                type="button"
                onClick={() => setTimeline("storm_outage")}
                className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                  timeline === "storm_outage"
                    ? "bg-red-500/20 text-red-400 border border-red-500/40 font-semibold"
                    : "text-muted-foreground hover:bg-muted/40"
                }`}
              >
                Major Storm / Outage Spike
              </button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-4 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 text-xs">
            {demandSlots.map((slot) => {
              const gap = slot.required - slot.scheduled
              const isShort = gap > 0
              return (
                <div
                  key={slot.hour}
                  className={`rounded-lg border p-3 transition-all ${
                    isShort
                      ? "border-red-500/50 bg-red-500/10 shadow-sm"
                      : "border-border/80 bg-background/50 hover:border-cyan-500/30"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-foreground text-sm">{slot.hour}</span>
                    <Badge
                      variant="outline"
                      className={`text-[9px] py-0 px-1 font-bold ${
                        isShort ? "border-red-500 text-red-400" : "border-emerald-500/40 text-emerald-400"
                      }`}
                    >
                      {isShort ? `GAP (-${gap})` : "BALANCED"}
                    </Badge>
                  </div>

                  <div className="mt-2 flex justify-between text-muted-foreground text-[11px]">
                    <span>Req: <strong className="text-foreground font-mono">{slot.required}</strong></span>
                    <span>Sched: <strong className={isShort ? "text-red-400 font-mono" : "text-emerald-400 font-mono"}>{slot.scheduled}</strong></span>
                  </div>

                  {/* Predicted Ticket Mix preview */}
                  <div className="mt-2 pt-2 border-t border-border/50 text-[10px] space-y-0.5 text-muted-foreground">
                    <div className="flex justify-between">
                      <span>Fibre/Hardware:</span>
                      <strong className="text-foreground">{slot.ticketMix.fiberHardware}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Billing & Finance:</span>
                      <strong className={timeline === "month_end_peak" ? "text-amber-400 font-bold" : "text-foreground"}>
                        {slot.ticketMix.billingFinance}
                      </strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Cold Calls:</span>
                      <strong className="text-violet-400">{slot.ticketMix.outboundColdCalls}</strong>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── SECTION 2: INTERACTIVE STAFF ROSTER TABLE WITH CRUD & SKILLS ── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Users className="h-4 w-4 text-emerald-400" />
                Active Shift Roster, Skills Matrix & Agent Capabilities
              </CardTitle>
              <CardDescription className="text-xs">
                Mean Time to Resolve (MTTR), First Contact Resolution (FTR), Employment Model (Internal vs HR Broker), and Outbound Commissions.
              </CardDescription>
            </div>

            {/* Department Filter */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Department:</span>
              <select
                value={selectedDept}
                onChange={(e) => setSelectedDept(e.target.value)}
                className="h-8 rounded-md border border-border bg-background px-2.5 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="ALL">All Departments</option>
                <option value="Customer Support">Customer Support</option>
                <option value="Finance & Billing">Finance & Billing</option>
                <option value="NOC & Core Infra">NOC & Core Infra</option>
                <option value="Field Operations">Field Operations</option>
                <option value="Outbound Sales">Outbound Sales</option>
              </select>
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                  <th className="py-2.5 px-4 font-medium">Employee / Agent</th>
                  <th className="py-2.5 px-4 font-medium">Department</th>
                  <th className="py-2.5 px-4 font-medium">Shift Type & Queue</th>
                  <th className="py-2.5 px-4 font-medium">Workforce Model</th>
                  <th className="py-2.5 px-4 font-medium">MTTR</th>
                  <th className="py-2.5 px-4 font-medium">FTR %</th>
                  <th className="py-2.5 px-4 font-medium">Outbound Dials / Wins</th>
                  <th className="py-2.5 px-4 font-medium">Status / Leave</th>
                  <th className="py-2.5 px-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {roster.map((shift) => (
                  <tr key={shift.id} className="hover:bg-muted/30 transition-colors">
                    {/* Employee Name */}
                    <td className="py-3 px-4">
                      <div>
                        <p className="font-semibold text-foreground text-sm">{shift.employeeName}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">
                          R {shift.hourlyRateZar}/hr • OT: {shift.overtimeHours}h
                        </p>
                      </div>
                    </td>

                    {/* Department */}
                    <td className="py-3 px-4 text-muted-foreground">
                      <span className="font-medium text-foreground">{shift.department}</span>
                    </td>

                    {/* Shift Type & Station */}
                    <td className="py-3 px-4">
                      <p className="font-medium text-foreground">{shift.shiftType}</p>
                      <p className="text-[10px] text-muted-foreground truncate max-w-[180px]">{shift.station}</p>
                    </td>

                    {/* Workforce Model (Internal vs Broker) */}
                    <td className="py-3 px-4">
                      {shift.isOutsourced ? (
                        <Badge variant="outline" className="border-amber-500/40 text-amber-400 bg-amber-950/20 text-[10px]">
                          Broker: {shift.brokerName || "BPO Contractor"}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="border-cyan-500/40 text-cyan-400 bg-cyan-950/20 text-[10px]">
                          Internal Direct
                        </Badge>
                      )}
                    </td>

                    {/* MTTR */}
                    <td className="py-3 px-4 font-mono font-bold text-foreground">
                      <span className={shift.mttrMinutes < 15 ? "text-emerald-400" : "text-amber-400"}>
                        {shift.mttrMinutes} min
                      </span>
                    </td>

                    {/* FTR */}
                    <td className="py-3 px-4 font-mono font-bold">
                      <span className={shift.ftrPercent >= 90 ? "text-emerald-400" : "text-amber-400"}>
                        {shift.ftrPercent}%
                      </span>
                    </td>

                    {/* Outbound & Commission */}
                    <td className="py-3 px-4">
                      {shift.outboundCallsToday > 0 ? (
                        <div>
                          <p className="font-semibold text-foreground">
                            {shift.outboundCallsToday} dials ({shift.outboundConversions} closed)
                          </p>
                          <p className="text-[10px] text-emerald-400 font-mono font-bold">
                            + R {shift.commissionEarnedZar.toLocaleString()} Comm.
                          </p>
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-[11px]">— Inbound Queue</span>
                      )}
                    </td>

                    {/* Leave Status */}
                    <td className="py-3 px-4">
                      {shift.onLeave ? (
                        <div>
                          <Badge variant="outline" className="border-pink-500 text-pink-400 bg-pink-950/20 text-[10px] font-bold">
                            ON LEAVE
                          </Badge>
                          <p className="text-[9px] text-muted-foreground mt-0.5 truncate max-w-[120px]">{shift.leaveReason}</p>
                        </div>
                      ) : (
                        <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                          Active Rostered
                        </Badge>
                      )}
                    </td>

                    {/* Actions (Edit / Delete) */}
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-cyan-400"
                          onClick={() => handleOpenEdit(shift)}
                          title="Edit Shift Assignment"
                        >
                          <Edit3 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                          onClick={() => handleDeleteShift(shift.id, shift.employeeName)}
                          title="Remove from Roster"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* ── MODAL 1: ADD SHIFT ASSIGNMENT ───────────────────────────────── */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-lg border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Add Shift Assignment</CardTitle>
                <CardDescription className="text-xs">Schedule an employee or outsourced broker contractor into the roster.</CardDescription>
              </div>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => setAddModalOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <form onSubmit={handleSaveAdd}>
              <CardContent className="space-y-3 p-4 text-xs">
                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Staff Member / Contractor Name *</label>
                  <Input value={formName} onChange={(e) => setFormName(e.target.value)} required placeholder="e.g. Kagiso Ndlovu" className="h-8 text-xs" />
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Department</label>
                    <select
                      value={formDept}
                      onChange={(e) => setFormDept(e.target.value as any)}
                      className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
                    >
                      <option value="Customer Support">Customer Support</option>
                      <option value="Finance & Billing">Finance & Billing</option>
                      <option value="NOC & Core Infra">NOC & Core Infra</option>
                      <option value="Field Operations">Field Operations</option>
                      <option value="Outbound Sales">Outbound Sales</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Shift Type</label>
                    <select
                      value={formShiftType}
                      onChange={(e) => setFormShiftType(e.target.value as any)}
                      className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
                    >
                      <option value="Morning (06:00 - 15:00)">Morning (06:00 - 15:00)</option>
                      <option value="Peak Support (08:00 - 17:00)">Peak Support (08:00 - 17:00)</option>
                      <option value="Evening Standby (16:00 - 00:00)">Evening Standby (16:00 - 00:00)</option>
                      <option value="NOC Night Watch (22:00 - 06:00)">NOC Night Watch (22:00 - 06:00)</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Assigned Station / Desk / Van</label>
                  <Input value={formStation} onChange={(e) => setFormStation(e.target.value)} placeholder="e.g. Month-End Billing Queue" className="h-8 text-xs" />
                </div>

                {/* Outsourced Broker Checkbox */}
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="addOutsourced"
                    checked={formIsOutsourced}
                    onChange={(e) => setFormIsOutsourced(e.target.checked)}
                    className="rounded border-border"
                  />
                  <label htmlFor="addOutsourced" className="font-semibold text-foreground">
                    Outsourced Staff (via HR Broker / BPO Contractor)
                  </label>
                </div>

                {formIsOutsourced && (
                  <div className="grid grid-cols-2 gap-2 pl-4 border-l-2 border-amber-500/50">
                    <div className="space-y-1">
                      <label className="font-semibold text-muted-foreground">HR Broker Name</label>
                      <Input value={formBrokerName} onChange={(e) => setFormBrokerName(e.target.value)} placeholder="e.g. CCI South Africa" className="h-8 text-xs" />
                    </div>
                    <div className="space-y-1">
                      <label className="font-semibold text-muted-foreground">Broker Hourly Rate (ZAR)</label>
                      <Input type="number" value={formHourlyRate} onChange={(e) => setFormHourlyRate(Number(e.target.value))} className="h-8 text-xs" />
                    </div>
                  </div>
                )}

                {/* Skills & Metrics */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Expected MTTR (Minutes)</label>
                    <Input type="number" value={formMttr} onChange={(e) => setFormMttr(Number(e.target.value))} className="h-8 text-xs" />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">First-Time Resolution %</label>
                    <Input type="number" value={formFtr} onChange={(e) => setFormFtr(Number(e.target.value))} className="h-8 text-xs" />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Skill Tags (Comma-separated)</label>
                  <Input value={formSkills} onChange={(e) => setFormSkills(e.target.value)} placeholder="e.g. Debit Order Reversals, MikroTik, English & Zulu" className="h-8 text-xs" />
                </div>

                {/* Leave toggle */}
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="addOnLeave"
                    checked={formOnLeave}
                    onChange={(e) => setFormOnLeave(e.target.checked)}
                    className="rounded border-border"
                  />
                  <label htmlFor="addOnLeave" className="font-semibold text-pink-400">
                    Currently On Approved Leave
                  </label>
                </div>
                {formOnLeave && (
                  <Input value={formLeaveReason} onChange={(e) => setFormLeaveReason(e.target.value)} placeholder="Leave Reason (e.g. Annual Leave 25-30 Sep)" className="h-8 text-xs" />
                )}
              </CardContent>

              <div className="flex justify-end gap-2 border-t border-border p-3 bg-muted/20">
                <Button type="button" variant="ghost" size="sm" onClick={() => setAddModalOpen(false)}>Cancel</Button>
                <Button type="submit" variant="default" size="sm" className="font-semibold">Assign to Roster</Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── MODAL 2: EDIT SHIFT ASSIGNMENT ──────────────────────────────── */}
      {editModalOpen && editingShift && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-in fade-in">
          <Card className="w-full max-w-lg border-border shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Edit Shift: {editingShift.employeeName}</CardTitle>
                <CardDescription className="text-xs">Modify hours, station, broker contract details, or leave status.</CardDescription>
              </div>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => setEditModalOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <form onSubmit={handleSaveEdit}>
              <CardContent className="space-y-3 p-4 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Department</label>
                    <select
                      value={formDept}
                      onChange={(e) => setFormDept(e.target.value as any)}
                      className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
                    >
                      <option value="Customer Support">Customer Support</option>
                      <option value="Finance & Billing">Finance & Billing</option>
                      <option value="NOC & Core Infra">NOC & Core Infra</option>
                      <option value="Field Operations">Field Operations</option>
                      <option value="Outbound Sales">Outbound Sales</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Shift Type</label>
                    <select
                      value={formShiftType}
                      onChange={(e) => setFormShiftType(e.target.value as any)}
                      className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
                    >
                      <option value="Morning (06:00 - 15:00)">Morning (06:00 - 15:00)</option>
                      <option value="Peak Support (08:00 - 17:00)">Peak Support (08:00 - 17:00)</option>
                      <option value="Evening Standby (16:00 - 00:00)">Evening Standby (16:00 - 00:00)</option>
                      <option value="NOC Night Watch (22:00 - 06:00)">NOC Night Watch (22:00 - 06:00)</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-muted-foreground">Station / Queue</label>
                  <Input value={formStation} onChange={(e) => setFormStation(e.target.value)} className="h-8 text-xs" />
                </div>

                {/* Outsourced Broker */}
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="editOutsourced"
                    checked={formIsOutsourced}
                    onChange={(e) => setFormIsOutsourced(e.target.checked)}
                    className="rounded border-border"
                  />
                  <label htmlFor="editOutsourced" className="font-semibold text-foreground">
                    Outsourced Staff (via HR Broker)
                  </label>
                </div>
                {formIsOutsourced && (
                  <div className="grid grid-cols-2 gap-2 pl-4 border-l-2 border-amber-500/50">
                    <div className="space-y-1">
                      <label className="font-semibold text-muted-foreground">Broker Name</label>
                      <Input value={formBrokerName} onChange={(e) => setFormBrokerName(e.target.value)} className="h-8 text-xs" />
                    </div>
                    <div className="space-y-1">
                      <label className="font-semibold text-muted-foreground">Rate (ZAR/hr)</label>
                      <Input type="number" value={formHourlyRate} onChange={(e) => setFormHourlyRate(Number(e.target.value))} className="h-8 text-xs" />
                    </div>
                  </div>
                )}

                {/* MTTR and FTR */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">MTTR (min)</label>
                    <Input type="number" value={formMttr} onChange={(e) => setFormMttr(Number(e.target.value))} className="h-8 text-xs" />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">FTR %</label>
                    <Input type="number" value={formFtr} onChange={(e) => setFormFtr(Number(e.target.value))} className="h-8 text-xs" />
                  </div>
                </div>

                {/* Outbound cold calling metrics */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Outbound Calls Today</label>
                    <Input type="number" value={formOutboundDials} onChange={(e) => setFormOutboundDials(Number(e.target.value))} className="h-8 text-xs" />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-muted-foreground">Commission Earned (ZAR)</label>
                    <Input type="number" value={formCommission} onChange={(e) => setFormCommission(Number(e.target.value))} className="h-8 text-xs" />
                  </div>
                </div>

                {/* Leave Toggle */}
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="editOnLeave"
                    checked={formOnLeave}
                    onChange={(e) => setFormOnLeave(e.target.checked)}
                    className="rounded border-border"
                  />
                  <label htmlFor="editOnLeave" className="font-semibold text-pink-400">
                    On Approved Leave
                  </label>
                </div>
                {formOnLeave && (
                  <Input value={formLeaveReason} onChange={(e) => setFormLeaveReason(e.target.value)} placeholder="Reason for leave" className="h-8 text-xs" />
                )}
              </CardContent>

              <div className="flex justify-end gap-2 border-t border-border p-3 bg-muted/20">
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditModalOpen(false)}>Cancel</Button>
                <Button type="submit" variant="default" size="sm" className="font-semibold">Save Changes</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
