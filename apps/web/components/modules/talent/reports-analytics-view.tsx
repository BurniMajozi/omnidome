"use client"

import React, { useEffect, useMemo, useState } from "react"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { NoDataYet, NotConnected } from "@/components/ui/not-connected"
import {
  BarChart3,
  TrendingUp,
  Calendar,
  AlertTriangle,
  GraduationCap,
  Download,
  Target,
  Smile,
  Building2,
  Users,
} from "lucide-react"
import {
  getAttritionRisk,
  listTrainingCourses,
  loadableFromError,
  type AttritionRiskOverview,
  type Employee,
  type ExitRecord,
  type TrainingCourse,
} from "@/lib/hr-api"
import { departmentCounts, hiresVsExits } from "@/lib/talent-derive"
import type { Loadable } from "@/lib/service-state"

interface ReportsAnalyticsViewProps {
  employees: Employee[]
  exits: Loadable<ExitRecord[]>
  onRetryExits?: () => void
}

const NOT_CONNECTED_COPY = {
  requisitions: "Not connected: no recruitment / requisition source is available, so open positions and applicant counts are not shown.",
  enps: "Not connected: no employee survey source is available, so eNPS and sentiment are not shown.",
  leave: "Not connected: there is no company-wide leave report or balance source. Leave liability is only shown once real leave balances and rates exist.",
  bursary: "No bursary records are tracked yet.",
}

export function ReportsAnalyticsView({ employees, exits, onRetryExits }: ReportsAnalyticsViewProps) {
  const [activeReportTab, setActiveReportTab] = useState<"pipeline" | "leave" | "skills" | "sentiment" | "attrition">("pipeline")

  // Attrition + courses are fetched once through the shared HR cache (only when their tab is opened).
  const [attrition, setAttrition] = useState<Loadable<AttritionRiskOverview>>({ state: "loading" })
  const [courses, setCourses] = useState<Loadable<TrainingCourse[]>>({ state: "loading" })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (activeReportTab !== "attrition") return
    let cancelled = false
    getAttritionRisk({ fresh: tick > 0 })
      .then((d) => !cancelled && setAttrition({ state: "ready", data: d }))
      .catch((err) => !cancelled && setAttrition(loadableFromError(err)))
    return () => {
      cancelled = true
    }
  }, [activeReportTab, tick])

  useEffect(() => {
    if (activeReportTab !== "skills") return
    let cancelled = false
    listTrainingCourses(undefined, { fresh: tick > 0 })
      .then((d) => !cancelled && setCourses({ state: "ready", data: d }))
      .catch((err) => !cancelled && setCourses(loadableFromError(err)))
    return () => {
      cancelled = true
    }
  }, [activeReportTab, tick])

  const departmentStaff = useMemo(
    () =>
      departmentCounts(employees).map((d) => ({
        department: d.department.length > 15 ? `${d.department.slice(0, 13)}…` : d.department,
        count: d.count,
      })),
    [employees],
  )

  // Real hires (employee hire dates) vs real exits (exit records), last 12 months.
  const pipeline = useMemo(
    () => (exits.state === "ready" ? hiresVsExits(employees, exits.data, new Date(), 12) : null),
    [employees, exits],
  )
  const netHires12m = pipeline ? pipeline.reduce((a, p) => a + p.net, 0) : null

  const handleExportCSV = () => {
    const rows: string[][] = [
      ["Metric", "Value", "Notes"],
      ["Total personnel (HR directory)", String(employees.length), "Real employee rows"],
    ]
    if (netHires12m !== null) rows.push(["Net headcount change (12m)", String(netHires12m), "Hire dates minus exit records"])
    const csvContent = rows.map((r) => r.map((v) => `"${v.replace(/"/g, '""')}"`).join(",")).join("\n")
    const blob = new Blob([csvContent], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `omnidome-workforce-analytics-${new Date().toISOString().split("T")[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const notConnectedValue = <span className="text-sm font-medium text-muted-foreground">Not connected</span>

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            <h1 className="text-xl font-bold tracking-tight text-foreground">Workforce Intelligence & Analytics</h1>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            HR figures computed from real records. Sections without a connected source say so instead of showing sample numbers.
          </p>
        </div>

        <Button size="sm" variant="outline" onClick={handleExportCSV} className="gap-1.5 text-xs">
          <Download className="h-3.5 w-3.5" />
          Export CSV
        </Button>
      </div>

      {/* KPI Cards Row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Headcount</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{employees.length}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {netHires12m === null ? "net change: exits not loaded" : `${netHires12m >= 0 ? "+" : ""}${netHires12m} net (12m)`}
                </p>
              </div>
              <TrendingUp className="h-8 w-8 text-emerald-400/50" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Open Requisitions</p>
                <p className="mt-1">{notConnectedValue}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">no recruitment source</p>
              </div>
              <Target className="h-8 w-8 text-primary/50" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Employee Sentiment</p>
                <p className="mt-1">{notConnectedValue}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">no survey source</p>
              </div>
              <Smile className="h-8 w-8 text-cyan-400/50" />
            </div>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Leave Liability</p>
                <p className="mt-1">{notConnectedValue}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">needs real leave balances</p>
              </div>
              <Calendar className="h-8 w-8 text-violet-400/50" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Analytics Sub-Tab Navigation */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border pb-2 text-xs">
        {[
          { id: "pipeline", label: "Staff Pipeline & Hires vs Exits" },
          { id: "leave", label: "Leave Days Trends & Accruals" },
          { id: "skills", label: "Training & Bursaries" },
          { id: "sentiment", label: "Surveys & Sentiment Analysis" },
          { id: "attrition", label: "Attrition Risk" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveReportTab(tab.id as typeof activeReportTab)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              activeReportTab === tab.id
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Staff Pipeline & Open Positions ───────────────────── */}
      {activeReportTab === "pipeline" && (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-emerald-400" />
                  Staff Pipeline (New Hires vs Exits)
                </CardTitle>
                <CardDescription className="text-xs">
                  Hires by employee hire date and exits from exit records, last 12 months.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {pipeline ? (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={pipeline}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis dataKey="month" tick={{ fill: "#888", fontSize: 11 }} />
                        <YAxis allowDecimals={false} tick={{ fill: "#888", fontSize: 11 }} />
                        <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444", borderRadius: "8px" }} />
                        <Legend />
                        <Bar dataKey="hires" name="New Hires" fill="#10b981" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="exits" name="Departures / Exits" fill="#f87171" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <NotConnected loadable={exits} service="Exit records" onRetry={onRetryExits} />
                )}
              </CardContent>
            </Card>

            <Card className="border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-primary" />
                  Headcount Distribution by Department
                </CardTitle>
                <CardDescription className="text-xs">Staff in the HR directory per department.</CardDescription>
              </CardHeader>
              <CardContent>
                {departmentStaff.length === 0 ? (
                  <NoDataYet message="No employees yet" />
                ) : (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={departmentStaff} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis type="number" allowDecimals={false} tick={{ fill: "#888", fontSize: 11 }} />
                        <YAxis type="category" dataKey="department" tick={{ fill: "#888", fontSize: 11 }} width={90} />
                        <Tooltip contentStyle={{ backgroundColor: "#1e1e1e", border: "1px solid #444", borderRadius: "8px" }} />
                        <Bar dataKey="count" name="Staff Count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="h-4 w-4 text-cyan-400" /> Open Positions & Requisition Pipeline
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <NoDataYet message={NOT_CONNECTED_COPY.requisitions} />
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 2: Leave Days Trends ─────────────────────────────────── */}
      {activeReportTab === "leave" && (
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Calendar className="h-4 w-4 text-violet-400" />
              Monthly Leave Days Utilization & Liability
            </CardTitle>
          </CardHeader>
          <CardContent>
            <NoDataYet message={NOT_CONNECTED_COPY.leave} />
          </CardContent>
        </Card>
      )}

      {/* ── TAB 3: Training & Bursaries ──────────────────────────────── */}
      {activeReportTab === "skills" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <GraduationCap className="h-4 w-4 text-emerald-400" />
                Training Courses
              </CardTitle>
              <CardDescription className="text-xs">Courses defined in the training module.</CardDescription>
            </CardHeader>
            <CardContent className="p-4 space-y-3 text-xs">
              {courses.state !== "ready" ? (
                <NotConnected loadable={courses} service="Training" onRetry={() => setTick((t) => t + 1)} />
              ) : courses.data.length === 0 ? (
                <NoDataYet message="No courses defined yet" />
              ) : (
                courses.data.map((c) => (
                  <div key={c.id} className="flex items-center justify-between border-b border-border/50 pb-2 last:border-0">
                    <div>
                      <p className="font-semibold text-foreground">{c.title}</p>
                      <p className="text-muted-foreground text-[11px]">{c.category}</p>
                    </div>
                    {c.mandatory && (
                      <Badge variant="outline" className="border-red-500/40 text-red-400">
                        Mandatory
                      </Badge>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="border-border">
            <CardHeader className="pb-3 border-b border-border/60">
              <CardTitle className="text-base flex items-center gap-2">
                <Users className="h-4 w-4 text-primary" />
                Bursary Programme
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <NoDataYet message={NOT_CONNECTED_COPY.bursary} />
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── TAB 4: Surveys & Sentiment Analysis ──────────────────────── */}
      {activeReportTab === "sentiment" && (
        <Card className="border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Smile className="h-4 w-4 text-emerald-400" />
              Employee Sentiment
            </CardTitle>
          </CardHeader>
          <CardContent>
            <NoDataYet message={NOT_CONNECTED_COPY.enps} />
          </CardContent>
        </Card>
      )}

      {/* ── TAB 5: Attrition ─────────────────────────────────────────── */}
      {activeReportTab === "attrition" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-400" />
              Attrition Risk (from latest performance reviews)
            </CardTitle>
            <CardDescription className="text-xs">
              Counts of active employees by the attrition risk recorded on their latest review. Employees with no review count as low.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4">
            {attrition.state !== "ready" ? (
              <NotConnected loadable={attrition} service="Attrition analytics" onRetry={() => setTick((t) => t + 1)} />
            ) : (
              <div className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-3 text-xs">
                  <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
                    <p className="text-muted-foreground">High risk</p>
                    <p className="text-2xl font-bold text-red-400">{attrition.data.high_risk_count}</p>
                  </div>
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
                    <p className="text-muted-foreground">Medium risk</p>
                    <p className="text-2xl font-bold text-amber-400">{attrition.data.medium_risk_count}</p>
                  </div>
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
                    <p className="text-muted-foreground">Low risk</p>
                    <p className="text-2xl font-bold text-emerald-400">{attrition.data.low_risk_count}</p>
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground">Active employees assessed: {attrition.data.total_employees}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
