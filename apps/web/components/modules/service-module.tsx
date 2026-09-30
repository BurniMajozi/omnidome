"use client"

import React, { useState, type JSX } from "react"
import { ModuleLayout } from "./module-layout"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ServiceComplaintsRadar } from "./service/service-complaints-radar"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts"
import { Headset, Clock, CheckCircle, AlertCircle, Radio, RefreshCw } from "lucide-react"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { tileLabel, type Loadable } from "@/lib/service-state"
import { loadCommTasks, loadEscalations, useOps } from "@/lib/ops-api"
import {
  allSettled,
  escalationStats,
  fmtInt,
  normPriority,
  normTaskStatus,
  relativeTime,
  type EscalationRow,
} from "@/lib/ops-derive"

/**
 * Service. Tickets are the customer escalations and tasks in the Communication
 * service (the only ticket store that runs). CSAT, SLA compliance and shift
 * rostering have no backing service yet and say so instead of showing numbers.
 */

const STATUS_COLORS: Record<string, string> = {
  open: "#ef4444",
  in_progress: "#f97316",
  resolved: "#4ade80",
  closed: "#60a5fa",
}

const tooltipStyle = {
  backgroundColor: "#262626",
  border: "1px solid #404040",
  borderRadius: "8px",
  color: "#fff",
}

const tableColumns = [
  { key: "ticket", label: "Ticket" },
  { key: "reason", label: "Reason" },
  { key: "status", label: "Status" },
  { key: "created", label: "Created" },
  { key: "updated", label: "Updated" },
]

const serviceKpiIconMap: Record<string, JSX.Element> = {
  open: <AlertCircle className="h-5 w-5 text-amber-400" />,
  resolution: <Clock className="h-5 w-5 text-blue-400" />,
  csat: <CheckCircle className="h-5 w-5 text-emerald-400" />,
  sla: <Headset className="h-5 w-5 text-purple-400" />,
}

const NOT_CONNECTED_TILE = "Not connected"

const tile = (l: Loadable<unknown>, value: () => string) => (l.state === "ready" ? value() : (tileLabel(l) ?? "—"))

export function ServiceModule() {
  const [activeTab, setActiveTab] = useState<"operations" | "scheduling" | "complaints">("operations")
  const escalations = useOps(loadEscalations)
  const commTasks = useOps(loadCommTasks)

  const reloadAll = () => {
    escalations.reload()
    commTasks.reload()
  }

  const settled = allSettled(escalations.value, commTasks.value)
  const rows: EscalationRow[] = escalations.value.state === "ready" ? escalations.value.data.rows : []
  const total = escalations.value.state === "ready" ? escalations.value.data.total : 0
  const stats = escalationStats(rows)
  const taskRows: any[] = commTasks.value.state === "ready" ? commTasks.value.data.rows : []
  const sample = rows.length < total ? ` (latest ${fmtInt(rows.length)} of ${fmtInt(total)} loaded)` : ""

  const statusPie = Object.entries(stats.byStatus).map(([name, value]) => ({ name, value, fill: STATUS_COLORS[name] ?? "#737373" }))

  const flashcardKPIs = [
    {
      id: "1",
      title: "Open Escalations",
      value: tile(escalations.value, () => fmtInt(stats.open + stats.inProgress)),
      change: "",
      changeType: "neutral" as const,
      iconKey: "open",
      backTitle: "Escalation Status",
      backDetails: [
        { label: "Open", value: fmtInt(stats.open) },
        { label: "In progress", value: fmtInt(stats.inProgress) },
        { label: "Resolved / closed", value: fmtInt(stats.resolved) },
      ],
      backInsight: `${fmtInt(total)} escalations on record${sample}.`,
    },
    {
      id: "2",
      title: "Avg Resolution Time",
      value: tile(escalations.value, () =>
        stats.avgResolutionHours === null ? "No data yet" : `${stats.avgResolutionHours.toFixed(1)}h`,
      ),
      change: "",
      changeType: "neutral" as const,
      iconKey: "resolution",
      backTitle: "Resolution",
      backDetails: [{ label: "Resolved / closed", value: fmtInt(stats.resolved) }],
      backInsight: "Time from creation to last update of resolved escalations.",
    },
    {
      id: "3",
      title: "CSAT Score",
      value: NOT_CONNECTED_TILE,
      change: "",
      changeType: "neutral" as const,
      iconKey: "csat",
      backTitle: "Satisfaction",
      backDetails: [],
      backInsight: "No survey source is connected, so no CSAT figure is shown.",
    },
    {
      id: "4",
      title: "SLA Compliance",
      value: NOT_CONNECTED_TILE,
      change: "",
      changeType: "neutral" as const,
      iconKey: "sla",
      backTitle: "SLA",
      backDetails: [],
      backInsight: "Tickets carry no SLA targets yet, so no compliance figure is shown.",
    },
  ].map((kpi) => ({ ...kpi, icon: serviceKpiIconMap[kpi.iconKey] ?? null }))

  const summary =
    escalations.value.state === "ready"
      ? `${fmtInt(total)} customer escalations on record${sample}: ${fmtInt(stats.open)} open, ${fmtInt(stats.inProgress)} in progress and ${fmtInt(stats.resolved)} resolved or closed. ` +
        `${fmtInt(taskRows.length)} support tasks are tracked in the Communication hub. CSAT and SLA compliance are not connected.`
      : "Ticket figures are unavailable because the Communication service could not be read. Nothing is estimated in its place."

  return (
    <div className="space-y-6">
      {/* Service Top Navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between border-b border-border/80 pb-3 gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant={activeTab === "operations" ? "default" : "outline"}
            size="sm"
            className="h-8 gap-2 text-xs font-semibold"
            onClick={() => setActiveTab("operations")}
          >
            <Headset className="h-3.5 w-3.5" />
            Service Operations & Tickets
          </Button>
          <Button
            variant={activeTab === "scheduling" ? "default" : "outline"}
            size="sm"
            className={`h-8 gap-2 text-xs font-semibold ${
              activeTab === "scheduling"
                ? "bg-cyan-600 hover:bg-cyan-500 text-white"
                : "border-cyan-500/40 text-cyan-400 hover:bg-cyan-950/20"
            }`}
            onClick={() => setActiveTab("scheduling")}
          >
            <Clock className="h-3.5 w-3.5" />
            Staff Demand & Shift Rostering
            <Badge variant="outline" className="text-[9px] py-0 px-1 border-cyan-400 text-cyan-300">
              Not connected
            </Badge>
          </Button>
          <Button
            variant={activeTab === "complaints" ? "default" : "outline"}
            size="sm"
            className={`h-8 gap-2 text-xs font-semibold ${
              activeTab === "complaints"
                ? "bg-red-600 hover:bg-red-500 text-white"
                : "border-red-500/40 text-red-400 hover:bg-red-950/20"
            }`}
            onClick={() => setActiveTab("complaints")}
          >
            <Radio className="h-3.5 w-3.5 text-red-400" />
            External Complaints & Sentiment Radar
            <Badge variant="outline" className="text-[9px] py-0 px-1 border-red-400 text-red-300">
              Not connected
            </Badge>
          </Button>
        </div>
      </div>

      {/* Tab 1: Service Operations & Tickets */}
      {activeTab === "operations" && !settled && (
        <div className="space-y-4" aria-busy="true" aria-label="Loading service data">
          <div className="h-16 animate-pulse rounded-lg bg-muted/50" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-lg bg-muted/50" />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-lg bg-muted/50" />
        </div>
      )}

      {activeTab === "operations" && settled && (
        <ModuleLayout
          title="Service"
          icon={<Headset className="h-5 w-5" />}
          subtitle="Tickets, SLAs, field service, and customer satisfaction scores"
          headerActions={
            <Button variant="outline" size="sm" onClick={reloadAll}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          }
          flashcardKPIs={flashcardKPIs}
          activities={[...rows]
            .sort((a, b) => b.created_at.localeCompare(a.created_at))
            .slice(0, 15)
            .map((e) => ({
              id: e.id,
              user: "Escalation",
              action: `${e.status.replace("_", " ")} -`,
              target: e.ticket_id || e.reason || e.id.slice(0, 8),
              time: relativeTime(e.created_at),
              type: "update" as const,
            }))}
          issues={rows
            .filter((e) => e.status === "open" || e.status === "in_progress")
            .slice(0, 20)
            .map((e) => ({
              id: e.id,
              title: e.reason || `Escalation ${e.ticket_id ?? e.id.slice(0, 8)}`,
              severity: "medium" as const,
              status: (e.status === "in_progress" ? "in-progress" : "open") as "open" | "in-progress",
              assignee: e.assigned_to ? "Assigned" : "Unassigned",
              time: relativeTime(e.created_at),
            }))}
          summary={summary}
          tasks={taskRows.map((t: any) => ({
            id: String(t.id),
            title: String(t.title ?? ""),
            priority: normPriority(t.priority),
            status: normTaskStatus(t.status),
            dueDate: t.due_date ? new Date(t.due_date).toLocaleDateString("en-ZA") : "No date",
            assignee: t.assignee_id ? "Assigned" : "Unassigned",
          }))}
          aiRecommendations={[]}
          tableData={rows.map((e) => ({
            id: e.id,
            ticket: e.ticket_id || e.id.slice(0, 8),
            reason: e.reason ?? "—",
            status: e.status,
            created: new Date(e.created_at).toLocaleDateString("en-ZA"),
            updated: new Date(e.updated_at).toLocaleDateString("en-ZA"),
          }))}
          tableColumns={tableColumns}
        >
          {escalations.value.state !== "ready" ? (
            <NotConnected loadable={escalations.value} service="Communication" onRetry={escalations.reload} />
          ) : (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                {/* Ticket Trend */}
                <div className="surface-card p-5">
                  <h3 className="section-title mb-4">Daily Escalation Activity (last 7 days)</h3>
                  {rows.length === 0 ? (
                    <NoDataYet message="No escalations yet" />
                  ) : (
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={stats.days}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#404040" />
                          <XAxis dataKey="day" tick={{ fill: "#737373", fontSize: 12 }} />
                          <YAxis allowDecimals={false} tick={{ fill: "#737373", fontSize: 12 }} />
                          <Tooltip contentStyle={tooltipStyle} />
                          <Legend />
                          <Bar dataKey="open" fill="#ef4444" name="Raised" />
                          <Bar dataKey="resolved" fill="#4ade80" name="Resolved" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>

                {/* By status */}
                <div className="surface-card p-5">
                  <h3 className="section-title mb-4">Escalations by Status</h3>
                  {statusPie.length === 0 ? (
                    <NoDataYet message="No escalations yet" />
                  ) : (
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={statusPie}
                            cx="50%"
                            cy="50%"
                            labelLine={false}
                            label={({ name, value }) => `${String(name).replace("_", " ")}: ${value}`}
                            outerRadius={80}
                            dataKey="value"
                          >
                            {statusPie.map((entry) => (
                              <Cell key={entry.name} fill={entry.fill} />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={tooltipStyle} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              </div>

              {/* Resolution Time by Priority */}
              <div className="surface-card p-5">
                <h3 className="section-title mb-4">Avg Resolution Time by Priority</h3>
                <NoDataYet message="Not connected: escalations carry no priority field, so a per-priority resolution time cannot be computed." />
              </div>
            </>
          )}
        </ModuleLayout>
      )}

      {/* Tab 2: Staff Demand & Shift Rostering */}
      {activeTab === "scheduling" && (
        <div className="surface-card p-6">
          <h3 className="section-title mb-4">Staff Demand & Shift Rostering</h3>
          <NoDataYet message="Not connected: no rostering or workforce-demand service exists yet. Rosters, headcount and demand forecasts are not shown until one is wired in." />
        </div>
      )}

      {/* Tab 3: Customer Experience & External Complaints Radar */}
      {activeTab === "complaints" && <ServiceComplaintsRadar />}
    </div>
  )
}
