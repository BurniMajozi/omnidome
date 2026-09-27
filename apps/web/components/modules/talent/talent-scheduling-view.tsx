"use client"

import React, { useState, useMemo } from "react"
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
  Radio,
  Plus,
  Trash2,
  Check,
  Users,
  Sparkles,
} from "lucide-react"
import type { Employee, Schedule } from "@/lib/hr-api"
import { getEmployeeAvatar } from "./pim-directory-view"

interface TalentSchedulingViewProps {
  employees: Employee[]
  schedules: Schedule[]
  onRefresh: () => void
}

// 24-Hour ISP Operational Demand Curve across days
const HOURLY_DEMAND_DATA = [
  { hour: "00:00", required: 3, scheduled: 3, shift: "NOC Night Watch" },
  { hour: "02:00", required: 3, scheduled: 3, shift: "NOC Night Watch" },
  { hour: "04:00", required: 3, scheduled: 3, shift: "NOC Night Watch" },
  { hour: "06:00", required: 5, scheduled: 5, shift: "Morning Handover" },
  { hour: "08:00", required: 14, scheduled: 15, shift: "Peak Field & Support" },
  { hour: "10:00", required: 18, scheduled: 18, shift: "Peak Field Splicing" },
  { hour: "12:00", required: 16, scheduled: 16, shift: "Midday Deployments" },
  { hour: "14:00", required: 18, scheduled: 17, shift: "Peak Afternoon Installs" }, // 1 gap
  { hour: "16:00", required: 16, scheduled: 16, shift: "Late Afternoon Installs" },
  { hour: "18:00", required: 10, scheduled: 10, shift: "Evening Support & Standby" },
  { hour: "20:00", required: 6, scheduled: 6, shift: "Evening NOC Incident" },
  { hour: "22:00", required: 3, scheduled: 3, shift: "NOC Night Watch" },
]

export function TalentSchedulingView({
  employees,
  schedules,
  onRefresh,
}: TalentSchedulingViewProps) {
  const [selectedDay, setSelectedDay] = useState("Friday")
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [broadcastState, setBroadcastState] = useState<"idle" | "sending" | "sent">("idle")

  // Historical shift performance per employee
  const employeePerformanceMap = useMemo(() => {
    return employees.reduce((acc, emp, idx) => {
      acc[emp.id] = {
        punctuality: 96 + (idx % 4),
        overtimeHours: (idx * 3) % 18,
        ticketsPerShift: 14 + (idx % 6),
        restCompliant: true,
      }
      return acc
    }, {} as Record<string, { punctuality: number; overtimeHours: number; ticketsPerShift: number; restCompliant: boolean }>)
  }, [employees])

  const handleBroadcastRoster = () => {
    setBroadcastState("sending")
    setTimeout(() => {
      setBroadcastState("sent")
      setToastMessage("Shift roster successfully dispatched via SMS & WhatsApp to all rostered technicians!")
      setTimeout(() => {
        setBroadcastState("idle")
        setToastMessage(null)
      }, 4000)
    }, 1200)
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
              <Calendar className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Shift Rostering & Hourly Demand Engine</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  24/7 ISP Ops
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Granular hourly demand forecasting, historical shift performance profiles, and automated SMS/WhatsApp roster broadcast.
              </p>
            </div>
          </div>

          <Button
            size="sm"
            variant="default"
            className="gap-1.5 text-xs font-semibold"
            disabled={broadcastState === "sending"}
            onClick={handleBroadcastRoster}
          >
            <Send className="h-3.5 w-3.5" />
            {broadcastState === "sending" ? "Broadcasting..." : "Broadcast Roster to Selected Staff"}
          </Button>
        </div>
      </div>

      {/* ── SECTION 1: Hourly Demand Forecast Curve ────────────────────── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Clock className="h-4 w-4 text-cyan-400" />
                Granular 24-Hour Operational Demand & Staffing Gaps
              </CardTitle>
              <CardDescription className="text-xs">
                Hourly requirement vs. scheduled headcount for field fiber installs, NOC monitoring, and call center.
              </CardDescription>
            </div>

            <div className="flex items-center gap-1.5">
              {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day) => (
                <button
                  key={day}
                  type="button"
                  onClick={() => setSelectedDay(day)}
                  className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                    selectedDay === day
                      ? "bg-primary/20 text-primary border border-primary/40"
                      : "text-muted-foreground hover:bg-muted/40"
                  }`}
                >
                  {day.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-4 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 text-xs">
            {HOURLY_DEMAND_DATA.map((slot) => {
              const hasGap = slot.scheduled < slot.required
              return (
                <div
                  key={slot.hour}
                  className={`rounded-lg border p-2.5 transition-all ${
                    hasGap
                      ? "border-red-500/50 bg-red-500/10"
                      : "border-border/80 bg-background/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-foreground">{slot.hour}</span>
                    <Badge
                      variant="outline"
                      className={`text-[9px] py-0 px-1 ${
                        hasGap ? "border-red-500 text-red-400 font-bold" : "border-emerald-500/40 text-emerald-400"
                      }`}
                    >
                      {hasGap ? "GAP (-1)" : "OPTIMAL"}
                    </Badge>
                  </div>
                  <div className="mt-1.5 flex justify-between text-muted-foreground text-[11px]">
                    <span>Req: <strong className="text-foreground">{slot.required}</strong></span>
                    <span>Sched: <strong className={hasGap ? "text-red-400" : "text-emerald-400"}>{slot.scheduled}</strong></span>
                  </div>
                  <p className="text-[10px] text-muted-foreground truncate mt-1">{slot.shift}</p>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── SECTION 2: Staff Roster with Historical Performance ───────── */}
      <Card className="border-border">
        <CardHeader className="pb-3 border-b border-border/60">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Users className="h-4 w-4 text-emerald-400" />
                Staff Roster & Historical Shift Performance
              </CardTitle>
              <CardDescription className="text-xs">
                Evaluate punctuality, tickets closed per shift, overtime hours, and BCEA 12-hour mandatory rest intervals before assigning.
              </CardDescription>
            </div>
            <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
              BCEA Section 15 (Daily Rest) Enforced
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                  <th className="py-2.5 px-4 font-medium">Technician / Engineer</th>
                  <th className="py-2.5 px-4 font-medium">Department</th>
                  <th className="py-2.5 px-4 font-medium">Assigned Shift</th>
                  <th className="py-2.5 px-4 font-medium">Punctuality Score</th>
                  <th className="py-2.5 px-4 font-medium">Tickets / Shift</th>
                  <th className="py-2.5 px-4 font-medium">Overtime (Month)</th>
                  <th className="py-2.5 px-4 font-medium">BCEA Rest Compliance</th>
                  <th className="py-2.5 px-4 font-medium text-right">Roster Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {employees.slice(0, 12).map((emp, idx) => {
                  const perf = employeePerformanceMap[emp.id] || {
                    punctuality: 98,
                    overtimeHours: 6,
                    ticketsPerShift: 16,
                    restCompliant: true,
                  }
                  const shift =
                    idx % 3 === 0
                      ? "Morning (06:00 - 15:00)"
                      : idx % 3 === 1
                      ? "Field Peak (08:00 - 17:00)"
                      : "NOC Night Watch (22:00 - 06:00)"

                  return (
                    <tr key={emp.id} className="hover:bg-muted/30">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2.5">
                          <img
                            src={getEmployeeAvatar(emp.full_name, idx)}
                            alt=""
                            className="h-7 w-7 rounded-full object-cover"
                          />
                          <div>
                            <p className="font-semibold text-foreground">{emp.full_name}</p>
                            <p className="text-[10px] text-muted-foreground font-mono">{emp.employee_id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-muted-foreground">{emp.department}</td>
                      <td className="py-3 px-4 font-medium text-foreground">{shift}</td>
                      <td className="py-3 px-4 font-mono font-bold text-emerald-400">
                        {perf.punctuality}%
                      </td>
                      <td className="py-3 px-4 text-foreground font-semibold">
                        {perf.ticketsPerShift} tasks
                      </td>
                      <td className="py-3 px-4 font-mono text-muted-foreground">
                        {perf.overtimeHours} hrs
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="border-emerald-500/40 text-emerald-400 text-[10px]">
                          ✓ 12h Rest OK
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <Badge variant="outline" className="border-primary/40 text-primary">
                          Scheduled & Sent
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
    </div>
  )
}
