"use client"

import { useState, type ReactNode } from "react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { KPICard, KPIGrid } from "@/components/ui/kpi-card"
import { PageHeader } from "@/components/ui/page-header"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Clock, AlertCircle, FileText, CheckSquare, Sparkles,
  Download, Filter, RefreshCw, MoreVertical, AlertTriangle,
  Info, ArrowRight, CheckCircle, ClipboardList, Reply,
  AtSign, Calendar, MessageSquare, Flag, Pin, UserPlus,
} from "lucide-react"
import { useIsClient } from "@/lib/use-is-client"
import { TableShell } from "@/components/ui/table-shell"
import { cn } from "@/lib/utils"

// ─── Types ───────────────────────────────────────────────────────────────────

interface FlashcardKPI {
  id: string; title: string; value: string; change: string
  changeType: "positive" | "negative" | "neutral"; icon: ReactNode
  backTitle: string; backDetails: { label: string; value: string }[]; backInsight: string
}
interface ActivityItem {
  id: string; user: string; action: string; target: string; time: string
  type: "create" | "update" | "delete" | "comment" | "assign"
}
interface IssueItem {
  id: string; title: string; severity: "critical" | "high" | "medium" | "low"
  status: "open" | "in-progress" | "resolved"; assignee: string; time: string
}
interface TaskItem {
  id: string; title: string; priority: "urgent" | "high" | "normal" | "low"
  status: "todo" | "in-progress" | "done"; dueDate: string; assignee: string
}
interface AIRecommendation {
  id: string; title: string; description: string; impact: "high" | "medium" | "low"; category: string
}
interface TableRow { id: string; [key: string]: string | number }

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
  /** Optional icon for the PageHeader */
  icon?: ReactNode
  /** Optional subtitle for the PageHeader */
  subtitle?: string
  /** Optional extra actions in the PageHeader (right of Export CSV) */
  headerActions?: ReactNode
}

// ─── Badge helpers ────────────────────────────────────────────────────────────

function SevBadge({ sev }: { sev: string }) {
  const cls =
    sev === "critical" ? "badge-danger" :
    sev === "high" ? "bg-orange-500/15 text-orange-400 border-orange-500/30" :
    sev === "medium" ? "badge-warning" : "badge-success"
  return <Badge variant="outline" className={cn("capitalize", cls)}>{sev}</Badge>
}
function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "open" ? "badge-info" :
    status === "in-progress" ? "badge-warning" :
    (status === "resolved" || status === "done") ? "badge-success" : "badge-neutral"
  const label = status === "done" ? "Done" : status === "in-progress" ? "In Progress" : status
  return <Badge variant="outline" className={cn("capitalize", cls)}>{label}</Badge>
}
function PriorityBadge({ priority }: { priority: string }) {
  const cls =
    priority === "urgent" ? "badge-danger" :
    priority === "high" ? "bg-orange-500/15 text-orange-400 border-orange-500/30" :
    priority === "normal" ? "badge-info" : "badge-neutral"
  return <Badge variant="outline" className={cn("capitalize", cls)}>{priority}</Badge>
}
function ImpactBadge({ impact }: { impact: string }) {
  const cls = impact === "high" ? "badge-success" : impact === "medium" ? "badge-info" : "badge-neutral"
  return <Badge variant="outline" className={cn("capitalize", cls)}>{impact} impact</Badge>
}

// ─── Main component ───────────────────────────────────────────────────────────

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
  icon,
  subtitle,
  headerActions,
}: ModuleLayoutProps) {
  const [activeInfoTab, setActiveInfoTab] = useState("activity")
  const [localTableData, setLocalTableData] = useState<TableRow[]>(tableData)
  const isClient = useIsClient()
  const openIssues = issues.filter((i) => i.status === "open").length
  const openTasks = tasks.filter((t) => t.status !== "done").length

  const handleExport = () => {
    const headers = tableColumns.map((c) => c.label).join(",")
    const rows = tableData.map((row) => tableColumns.map((c) => row[c.key]).join(",")).join("\n")
    const blob = new Blob([`${headers}\n${rows}`], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `${title.toLowerCase().replace(/\s+/g, "-")}-export.csv`,
    })
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title={title}
        subtitle={subtitle}
        icon={icon}
        actions={
          <>
            {headerActions}
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="h-3.5 w-3.5" />Export CSV
            </Button>
          </>
        }
      />

      {/* KPI Flashcards */}
      <section aria-label="Key metrics">
        <h2 className="section-title mb-3">Key Metrics</h2>
        <KPIGrid>
          {flashcardKPIs.map((kpi) => (
            <KPICard
              key={kpi.id}
              title={kpi.title}
              value={isClient ? kpi.value : "—"}
              trend={kpi.change}
              trendDir={kpi.changeType === "positive" ? "up" : kpi.changeType === "negative" ? "down" : "neutral"}
              positiveIsGood={kpi.changeType !== "negative"}
              icon={kpi.icon}
              detail={{ title: kpi.backTitle, rows: kpi.backDetails, note: kpi.backInsight }}
            />
          ))}
        </KPIGrid>
      </section>

      {/* Main content slot (charts, sub-tabs, etc.) */}
      {children}

      {/* Activity / Issues / Summary / Tasks + AI */}
      <section className="grid gap-6 lg:grid-cols-3">
        {/* Left: tabbed info panel */}
        <div className="lg:col-span-2">
          <Card className="border-border bg-card">
            <CardHeader className="pb-0">
              <Tabs value={activeInfoTab} onValueChange={setActiveInfoTab}>
                <TabsList className="w-full sm:w-auto">
                  <TabsTrigger value="activity" className="gap-1.5">
                    <Clock className="h-3.5 w-3.5" />Activity
                  </TabsTrigger>
                  <TabsTrigger value="issues" className="gap-1.5">
                    <AlertCircle className="h-3.5 w-3.5" />Issues
                    {openIssues > 0 && (
                      <Badge className="badge-danger ml-0.5 h-4 min-w-4 px-1 text-[10px]">{openIssues}</Badge>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="summary" className="gap-1.5">
                    <FileText className="h-3.5 w-3.5" />Summary
                  </TabsTrigger>
                  <TabsTrigger value="tasks" className="gap-1.5">
                    <CheckSquare className="h-3.5 w-3.5" />Tasks
                    {openTasks > 0 && (
                      <Badge className="badge-warning ml-0.5 h-4 min-w-4 px-1 text-[10px]">{openTasks}</Badge>
                    )}
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="activity" className="mt-4 pb-4">
                  <ul className="scrollbar-thin max-h-72 space-y-2 overflow-y-auto pr-1">
                    {activities.map((a) => (
                      <li key={a.id} className="flex items-start gap-3 rounded-lg border border-border bg-secondary/20 p-3 group">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
                          {a.user.split(" ").map((n: string) => n[0]).join("").slice(0, 2)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">
                            <span className="text-primary">{a.user}</span>{" "}
                            <span className="text-muted-foreground">{a.action}</span>{" "}
                            {a.target}
                          </p>
                          <p className="mt-0.5 text-xs text-muted-foreground">{a.time}</p>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon-sm" className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                              <MoreVertical className="h-3.5 w-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-44">
                            <DropdownMenuItem className="gap-2"><ClipboardList className="h-3.5 w-3.5" />Create Task</DropdownMenuItem>
                            <DropdownMenuItem className="gap-2"><Reply className="h-3.5 w-3.5" />Reply</DropdownMenuItem>
                            <DropdownMenuItem className="gap-2"><AtSign className="h-3.5 w-3.5" />Mention</DropdownMenuItem>
                            <DropdownMenuItem className="gap-2"><Calendar className="h-3.5 w-3.5" />Schedule</DropdownMenuItem>
                            <DropdownMenuItem className="gap-2"><MessageSquare className="h-3.5 w-3.5" />Reply Inline</DropdownMenuItem>
                            <DropdownMenuItem className="gap-2"><Flag className="h-3.5 w-3.5" />Escalate</DropdownMenuItem>
                            <DropdownMenuItem className="gap-2"><Pin className="h-3.5 w-3.5" />Pin</DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </li>
                    ))}
                  </ul>
                </TabsContent>

                <TabsContent value="issues" className="mt-4 pb-4">
                  <ul className="scrollbar-thin max-h-72 space-y-2 overflow-y-auto pr-1">
                    {issues.map((issue) => (
                      <li key={issue.id} className="rounded-lg border border-border bg-secondary/20 p-3 group">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            {issue.severity === "critical" || issue.severity === "high"
                              ? <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-400" />
                              : <Info className="h-3.5 w-3.5 shrink-0 text-amber-400" />}
                            <p className="text-sm font-medium text-foreground truncate">{issue.title}</p>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <SevBadge sev={issue.severity} />
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon-sm" className="opacity-0 group-hover:opacity-100 transition-opacity">
                                  <MoreVertical className="h-3.5 w-3.5" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" className="w-44">
                                <DropdownMenuItem className="gap-2"><CheckCircle className="h-3.5 w-3.5 text-emerald-400" />Mark Resolved</DropdownMenuItem>
                                <DropdownMenuItem className="gap-2"><UserPlus className="h-3.5 w-3.5" />Assign</DropdownMenuItem>
                                <DropdownMenuItem className="gap-2"><ClipboardList className="h-3.5 w-3.5" />Create Task</DropdownMenuItem>
                                <DropdownMenuItem className="gap-2"><Calendar className="h-3.5 w-3.5" />Schedule Fix</DropdownMenuItem>
                                <DropdownMenuItem className="gap-2"><Flag className="h-3.5 w-3.5 text-red-400" />Escalate</DropdownMenuItem>
                                <DropdownMenuItem className="gap-2"><Pin className="h-3.5 w-3.5" />Pin</DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </div>
                        <div className="mt-2 flex items-center gap-2">
                          <StatusBadge status={issue.status} />
                          <span className="text-xs text-muted-foreground">{issue.assignee} · {issue.time}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </TabsContent>

                <TabsContent value="summary" className="mt-4 pb-4">
                  <div className="surface-sunken rounded-lg p-4">
                    <p className="text-sm leading-relaxed text-muted-foreground">{summary}</p>
                  </div>
                </TabsContent>

                <TabsContent value="tasks" className="mt-4 pb-4">
                  <ul className="scrollbar-thin max-h-72 space-y-2 overflow-y-auto pr-1">
                    {tasks.map((task) => (
                      <li key={task.id} className="rounded-lg border border-border bg-secondary/20 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2">
                            {task.status === "done"
                              ? <CheckCircle className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                              : <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
                            <p className={cn(
                              "text-sm font-medium truncate",
                              task.status === "done" ? "line-through text-muted-foreground" : "text-foreground",
                            )}>{task.title}</p>
                          </div>
                          <PriorityBadge priority={task.priority} />
                        </div>
                        <div className="mt-2 flex items-center gap-2">
                          <StatusBadge status={task.status} />
                          <span className="text-xs text-muted-foreground">{task.assignee} · Due {task.dueDate}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </TabsContent>
              </Tabs>
            </CardHeader>
          </Card>
        </div>

        {/* Right: AI recommendations */}
        <div>
          <Card className="border-border bg-card h-full">
            <CardHeader className="pb-3">
              <h3 className="flex items-center gap-2 card-title">
                <Sparkles className="h-4 w-4 text-amber-400" />AI Recommendations
              </h3>
            </CardHeader>
            <CardContent className="space-y-3">
              {aiRecommendations.map((rec) => (
                <div key={rec.id} className="rounded-lg border border-border bg-secondary/20 p-3 group">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-foreground">{rec.title}</p>
                    <div className="flex items-center gap-1 shrink-0">
                      <ImpactBadge impact={rec.impact} />
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon-sm" className="opacity-0 group-hover:opacity-100 transition-opacity">
                            <MoreVertical className="h-3.5 w-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <DropdownMenuItem className="gap-2"><ClipboardList className="h-3.5 w-3.5" />Create Task</DropdownMenuItem>
                          <DropdownMenuItem className="gap-2"><Calendar className="h-3.5 w-3.5" />Schedule Action</DropdownMenuItem>
                          <DropdownMenuItem className="gap-2"><UserPlus className="h-3.5 w-3.5" />Assign to Agent</DropdownMenuItem>
                          <DropdownMenuItem className="gap-2"><Flag className="h-3.5 w-3.5" />Escalate</DropdownMenuItem>
                          <DropdownMenuItem className="gap-2"><Pin className="h-3.5 w-3.5" />Pin Insight</DropdownMenuItem>
                          <DropdownMenuItem className="gap-2 text-muted-foreground"><CheckCircle className="h-3.5 w-3.5" />Dismiss</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{rec.description}</p>
                  <Badge variant="outline" className="badge-neutral mt-2 text-[10px]">{rec.category}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Data Table */}
      <section aria-label="Data export">
        <TableShell
          title={`${title} Records`}
          columns={tableColumns.map((c) => ({ ...c, inputType: "text" as const }))}
          data={localTableData}
          addLabel="Add Record"
          onAdd={(rec) => setLocalTableData((prev) => [rec as TableRow, ...prev])}
          onDelete={(id) => setLocalTableData((prev) => prev.filter((r) => r.id !== id))}
          onEdit={(rec) => setLocalTableData((prev) => prev.map((r) => r.id === rec.id ? rec as TableRow : r))}
          onRefresh={() => setLocalTableData(tableData)}
          searchPlaceholder={`Search ${title.toLowerCase()}...`}
        />
      </section>
    </div>
  )
}
