"use client"

import { useState, useEffect, type ReactNode } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Clock,
  AlertCircle,
  FileText,
  CheckSquare,
  Sparkles,
  Download,
  Filter,
  RefreshCw,
  MoreVertical,
  AlertTriangle,
  Info,
  TrendingUp,
  TrendingDown,
  ArrowRight,
  CheckCircle,
} from "lucide-react"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"

interface FlashcardKPI {
  id: string
  title: string
  value: string
  change: string
  changeType: "positive" | "negative" | "neutral"
  icon: ReactNode
  backTitle: string
  backDetails: {
    label: string
    value: string
  }[]
  backInsight: string
}

function FlipCard({ kpi }: { kpi: FlashcardKPI }) {
  const [isFlipped, setIsFlipped] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div className="h-40 cursor-pointer" onClick={() => setIsFlipped(!isFlipped)}>
      {!isFlipped ? (
        // Front
        <div className="h-full rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/50">
          <div className="flex h-full flex-col justify-between">
            <div className="flex items-start justify-between">
              <div className="rounded-lg bg-primary/20 p-2">{kpi.icon}</div>
              <Badge
                variant="outline"
                className={
                  kpi.changeType === "positive"
                    ? "border-emerald-500/50 text-emerald-400"
                    : kpi.changeType === "negative"
                      ? "border-red-500/50 text-red-400"
                      : "border-muted text-muted-foreground"
                }
              >
                {kpi.changeType === "positive" ? (
                  <TrendingUp className="mr-1 h-3 w-3" />
                ) : kpi.changeType === "negative" ? (
                  <TrendingDown className="mr-1 h-3 w-3" />
                ) : null}
                {kpi.change}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">{kpi.title}</p>
              <p className="text-2xl font-bold text-foreground">{!mounted ? "--" : kpi.value}</p>
            </div>
            <p className="text-xs text-muted-foreground">Click to see details</p>
          </div>
        </div>
      ) : (
        // Back
        <div className="h-full rounded-xl border border-primary/50 bg-card p-4 transition-all">
          <div className="flex h-full flex-col justify-between">
            <div>
              <h4 className="font-semibold text-foreground">{kpi.backTitle}</h4>
              <div className="mt-2 space-y-1">
                {kpi.backDetails.map((detail, idx) => (
                  <div key={idx} className="flex justify-between text-sm">
                    <span className="text-muted-foreground">{detail.label}</span>
                    <span className="font-medium text-foreground">{!mounted ? "--" : detail.value}</span>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-xs text-emerald-400">{kpi.backInsight}</p>
          </div>
        </div>
      )}
    </div>
  )
}

interface ActivityItem {
  id: string
  user: string
  action: string
  target: string
  time: string
  type: "create" | "update" | "delete" | "comment" | "assign"
}

interface IssueItem {
  id: string
  title: string
  severity: "critical" | "high" | "medium" | "low"
  status: "open" | "in-progress" | "resolved"
  assignee: string
  time: string
}

interface TaskItem {
  id: string
  title: string
  priority: "urgent" | "high" | "normal" | "low"
  status: "todo" | "in-progress" | "done"
  dueDate: string
  assignee: string
}

interface AIRecommendation {
  id: string
  title: string
  description: string
  impact: "high" | "medium" | "low"
  category: string
}

interface TableRow {
  id: string
  [key: string]: string | number
}

interface ModuleLayoutProps {
  title: string
  children: ReactNode
  flashcardKPIs: FlashcardKPI[]
  activities: ActivityItem[]
  issues: IssueItem[]
  summary: string
  tasks: TaskItem[]
  aiRecommendations: AIRecommendation[]
  tableData: TableRow[]
  tableColumns: { key: string; label: string }[]
}

export function ModuleLayout({
  title,
  children,
  flashcardKPIs,
  activities,
  issues,
  summary,
  tasks,
  aiRecommendations,
  tableData,
  tableColumns,
}: ModuleLayoutProps) {
  const [activeInfoTab, setActiveInfoTab] = useState("activity")
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "critical":
        return <Badge className="bg-red-500/20 text-red-400">Critical</Badge>
      case "high":
        return <Badge className="bg-orange-500/20 text-orange-400">High</Badge>
      case "medium":
        return <Badge className="bg-amber-500/20 text-amber-400">Medium</Badge>
      case "low":
        return <Badge className="bg-emerald-500/20 text-emerald-400">Low</Badge>
      default:
        return <Badge variant="secondary">{severity}</Badge>
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "open":
        return <Badge className="bg-blue-500/20 text-blue-400">Open</Badge>
      case "in-progress":
        return <Badge className="bg-amber-500/20 text-amber-400">In Progress</Badge>
      case "resolved":
      case "done":
        return <Badge className="bg-emerald-500/20 text-emerald-400">{status === "done" ? "Done" : "Resolved"}</Badge>
      case "todo":
        return <Badge className="bg-slate-500/20 text-slate-400">To Do</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return <Badge className="bg-red-500/20 text-red-400">Urgent</Badge>
      case "high":
        return <Badge className="bg-orange-500/20 text-orange-400">High</Badge>
      case "normal":
        return <Badge className="bg-blue-500/20 text-blue-400">Normal</Badge>
      case "low":
        return <Badge className="bg-slate-500/20 text-slate-400">Low</Badge>
      default:
        return <Badge variant="secondary">{priority}</Badge>
    }
  }

  const getImpactBadge = (impact: string) => {
    switch (impact) {
      case "high":
        return <Badge className="bg-emerald-500/20 text-emerald-400">High Impact</Badge>
      case "medium":
        return <Badge className="bg-blue-500/20 text-blue-400">Medium Impact</Badge>
      case "low":
        return <Badge className="bg-slate-500/20 text-slate-400">Low Impact</Badge>
      default:
        return <Badge variant="secondary">{impact}</Badge>
    }
  }

  const handleExport = () => {
    const headers = tableColumns.map((col) => col.label).join(",")
    const rows = tableData.map((row) => tableColumns.map((col) => row[col.key]).join(",")).join("\n")
    const csv = `${headers}\n${rows}`
    const blob = new Blob([csv], { type: "text/csv" })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${title.toLowerCase().replace(/\s+/g, "-")}-export.csv`
    a.click()
  }

  return (
    <div className="space-y-6">
      {/* Flippable KPI Flashcards at the top */}
      <div>
        <h3 className="mb-4 text-lg font-semibold text-foreground">Key Performance Indicators</h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {flashcardKPIs.map((kpi) => (
            <FlipCard key={kpi.id} kpi={kpi} />
          ))}
        </div>
      </div>

      {/* Main Module Content */}
      {children}

      {/* Activity, Issues, Summary, Tasks */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="border-border bg-card">
            <CardHeader className="pb-2">
              <Tabs value={activeInfoTab} onValueChange={setActiveInfoTab}>
                <TabsList className="bg-secondary">
                  <TabsTrigger value="activity" className="gap-2">
                    <Clock className="h-4 w-4" />
                    Last Activity
                  </TabsTrigger>
                  <TabsTrigger value="issues" className="gap-2">
                    <AlertCircle className="h-4 w-4" />
                    Issues
                    {issues.filter((i) => i.status === "open").length > 0 && (
                      <Badge className="ml-1 bg-red-500/20 text-red-400">
                        {issues.filter((i) => i.status === "open").length}
                      </Badge>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="summary" className="gap-2">
                    <FileText className="h-4 w-4" />
                    Summary
                  </TabsTrigger>
                  <TabsTrigger value="tasks" className="gap-2">
                    <CheckSquare className="h-4 w-4" />
                    Tasks
                    {tasks.filter((t) => t.status !== "done").length > 0 && (
                      <Badge className="ml-1 bg-amber-500/20 text-amber-400">
                        {tasks.filter((t) => t.status !== "done").length}
                      </Badge>
                    )}
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="activity" className="mt-4">
                  <div className="max-h-80 space-y-3 overflow-y-auto">
                    {activities.map((activity) => (
                      <div
                        key={activity.id}
                        className="flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3"
                      >
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20">
                          <span className="text-xs font-medium text-primary">
                            {activity.user
                              .split(" ")
                              .map((n) => n[0])
                              .join("")}
                          </span>
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-foreground">
                            <span className="font-medium">{activity.user}</span>{" "}
                            <span className="text-muted-foreground">{activity.action}</span>{" "}
                            <span className="font-medium text-primary">{activity.target}</span>
                          </p>
                          <p className="text-xs text-muted-foreground">{activity.time}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="issues" className="mt-4">
                  <div className="max-h-80 space-y-3 overflow-y-auto">
                    {issues.map((issue) => (
                      <div
                        key={issue.id}
                        className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3"
                      >
                        <div className="flex items-center gap-3">
                          {issue.severity === "critical" ? (
                            <AlertTriangle className="h-5 w-5 text-red-400" />
                          ) : issue.severity === "high" ? (
                            <AlertCircle className="h-5 w-5 text-orange-400" />
                          ) : (
                            <Info className="h-5 w-5 text-amber-400" />
                          )}
                          <div>
                            <p className="font-medium text-foreground">{issue.title}</p>
                            <p className="text-xs text-muted-foreground">
                              Assigned to {issue.assignee} • {issue.time}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {getSeverityBadge(issue.severity)}
                          {getStatusBadge(issue.status)}
                        </div>
                      </div>
                    ))}
                  </div>
                </TabsContent>

                <TabsContent value="summary" className="mt-4">
                  <div className="rounded-lg border border-border bg-secondary/30 p-4">
                    <p className="text-sm leading-relaxed text-foreground">{summary}</p>
                  </div>
                </TabsContent>

                <TabsContent value="tasks" className="mt-4">
                  <div className="max-h-80 space-y-3 overflow-y-auto">
                    {tasks.map((task) => (
                      <div
                        key={task.id}
                        className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3"
                      >
                        <div className="flex items-center gap-3">
                          {task.status === "done" ? (
                            <CheckCircle className="h-5 w-5 text-emerald-400" />
                          ) : (
                            <CheckSquare className="h-5 w-5 text-muted-foreground" />
                          )}
                          <div>
                            <p
                              className={`font-medium ${task.status === "done" ? "text-muted-foreground line-through" : "text-foreground"}`}
                            >
                              {task.title}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Due {task.dueDate} • {task.assignee}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {getPriorityBadge(task.priority)}
                          {getStatusBadge(task.status)}
                        </div>
                      </div>
                    ))}
                  </div>
                </TabsContent>
              </Tabs>
            </CardHeader>
          </Card>
        </div>

        {/* AI Recommendations */}
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-5 w-5 text-amber-400" />
              AI Recommendations
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-80 space-y-3 overflow-y-auto">
              {aiRecommendations.map((rec) => (
                <div
                  key={rec.id}
                  className="rounded-lg border border-border bg-secondary/30 p-3 transition-colors hover:border-primary/50"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          {rec.category}
                        </Badge>
                        {getImpactBadge(rec.impact)}
                      </div>
                      <h4 className="mt-2 font-medium text-foreground">{rec.title}</h4>
                      <p className="mt-1 text-sm text-muted-foreground">{rec.description}</p>
                    </div>
                    <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0">
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Exportable Table View */}
      <Card className="border-border bg-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Data Table</CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm">
                <Filter className="mr-2 h-4 w-4" />
                Filter
              </Button>
              <Button variant="outline" size="sm">
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>
              <Button size="sm" className="bg-primary" onClick={handleExport}>
                <Download className="mr-2 h-4 w-4" />
                Export CSV
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  {tableColumns.map((col) => (
                    <th key={col.key} className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                      {col.label}
                    </th>
                  ))}
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tableData.slice(0, 10).map((row) => (
                  <tr key={row.id} className="border-b border-border last:border-0">
                    {tableColumns.map((col) => (
                      <td key={col.key} className="px-4 py-3 text-sm text-foreground">
                        {row[col.key]}
                      </td>
                    ))}
                    <td className="px-4 py-3">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem>View Details</DropdownMenuItem>
                          <DropdownMenuItem>Edit</DropdownMenuItem>
                          <DropdownMenuItem>Delete</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Showing 1-{Math.min(10, tableData.length)} of {tableData.length} entries
            </p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled>
                Previous
              </Button>
              <Button variant="outline" size="sm">
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
