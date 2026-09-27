"use client"

import React, { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  BookOpen,
  IdCard,
  Plus,
  Search,
  CheckCircle2,
  Clock,
  Trash2,
  Eye,
  FileText,
  Tag,
  Building,
  User,
  Sparkles,
  Layers,
  X,
  ExternalLink,
} from "lucide-react"
import {
  listAllOnboardingTasks,
  createOnboardingTask,
  bulkCreateOnboardingTasks,
  completeOnboardingTask,
  deleteOnboardingTask,
  listKnowledgeArticles,
  createKnowledgeArticle,
  deleteKnowledgeArticle,
  type OnboardingTask,
  type KnowledgeArticle,
  type Employee,
} from "@/lib/hr-api"

interface OnboardingKbViewProps {
  employees: Employee[]
}

const ONBOARDING_TEMPLATES = [
  {
    id: "sa_standard",
    name: "Standard South African New Hire (BCEA)",
    description: "Statutory contract, SARS tax verification, bank stamped confirmation, and IT setup.",
    tasks: [
      { task_name: "Sign BCEA Employment Contract & Job Description", owner_department: "HR" },
      { task_name: "Submit SARS Tax Number & Stamped Bank Confirmation", owner_department: "Payroll" },
      { task_name: "OHS Workplace Health & Safety Induction", owner_department: "Compliance" },
      { task_name: "Issue IT Hardware & Email / Slack Credentials", owner_department: "IT" },
    ],
  },
  {
    id: "psira_guard",
    name: "PSIRA Security & Armed Response Officer",
    description: "Private Security Industry Regulatory Authority checks and equipment handover.",
    tasks: [
      { task_name: "Verify PSIRA Grade C/B Certificate & SAPS Clearance", owner_department: "Compliance" },
      { task_name: "Firearm Competency & Range Shooting Certification", owner_department: "Operations" },
      { task_name: "Issue Bulletproof Vest, Uniform & Digital Radio Call Sign", owner_department: "Guarding" },
      { task_name: "Control Room Incident Dispatch Protocol Briefing", owner_department: "Control Room" },
    ],
  },
  {
    id: "field_tech",
    name: "Fiber Splicer & Field Installation Specialist",
    description: "Van inventory sign-off, splicing machine verification, and health & safety kit.",
    tasks: [
      { task_name: "Issue ThinkPad & Fujikura 90S Fusion Splicer Kit", owner_department: "Field Ops" },
      { task_name: "Sign-off Initial Van Stock & Tool Inventory Checklist", owner_department: "Inventory" },
      { task_name: "OTDR Fiber Test Equipment & Fault Finding Protocol Training", owner_department: "Engineering" },
      { task_name: "Vehicle Telematics & Tracker Safety Profile Activation", owner_department: "Fleet" },
    ],
  },
  {
    id: "sales_rep",
    name: "Enterprise B2B & FTTH Sales Executive",
    description: "CRM provisioning, sales commission tier sign-off, and VoIP softphone setup.",
    tasks: [
      { task_name: "Sign Sales Commission & Incentive Scheme Agreement", owner_department: "HR" },
      { task_name: "Provision HubSpot / CRM Pipeline & Deal Access", owner_department: "IT" },
      { task_name: "Configure WebRTC Softphone Extension & Call Center Route", owner_department: "IT Support" },
      { task_name: "Fiber Coverage Map & Feasibility Portal Training", owner_department: "Sales" },
    ],
  },
]

export function OnboardingKbView({ employees }: OnboardingKbViewProps) {
  // Onboarding state
  const [tasks, setTasks] = useState<OnboardingTask[]>([])
  const [loadingTasks, setLoadingTasks] = useState(true)
  const [taskError, setTaskError] = useState<string | null>(null)
  const [selectedEmpFilter, setSelectedEmpFilter] = useState<string>("ALL")
  const [deptFilter, setDeptFilter] = useState<string>("ALL")

  // Modals
  const [isAddTaskOpen, setIsAddTaskOpen] = useState(false)
  const [isBulkAddOpen, setIsBulkAddOpen] = useState(false)
  const [isNewArticleOpen, setIsNewArticleOpen] = useState(false)
  const [selectedArticle, setSelectedArticle] = useState<KnowledgeArticle | null>(null)

  // Add Task Form
  const [newTaskEmpId, setNewTaskEmpId] = useState<string>(employees[0]?.id || "")
  const [newTaskName, setNewTaskName] = useState("")
  const [newTaskDesc, setNewTaskDesc] = useState("")
  const [newTaskDept, setNewTaskDept] = useState("HR")
  const [newTaskDueDate, setNewTaskDueDate] = useState(
    new Date(Date.now() + 5 * 86400000).toISOString().split("T")[0]
  )
  const [isSubmittingTask, setIsSubmittingTask] = useState(false)

  // Bulk Add Form
  const [bulkEmpId, setBulkEmpId] = useState<string>(employees[0]?.id || "")
  const [bulkTemplateId, setBulkTemplateId] = useState<string>(ONBOARDING_TEMPLATES[0].id)
  const [isSubmittingBulk, setIsSubmittingBulk] = useState(false)

  // Knowledge Base state
  const [articles, setArticles] = useState<KnowledgeArticle[]>([])
  const [kbLoading, setKbLoading] = useState(true)
  const [kbSearch, setKbSearch] = useState("")
  const [kbCategory, setKbCategory] = useState("ALL")

  // New Article Form
  const [newArtTitle, setNewArtTitle] = useState("")
  const [newArtCategory, setNewArtCategory] = useState("Compliance & Labor")
  const [newArtTags, setNewArtTags] = useState("")
  const [newArtContent, setNewArtContent] = useState("")
  const [artEditorTab, setArtEditorTab] = useState<"write" | "preview">("write")
  const [isSubmittingArticle, setIsSubmittingArticle] = useState(false)

  useEffect(() => {
    if (employees.length > 0 && !newTaskEmpId) {
      setNewTaskEmpId(employees[0].id)
      setBulkEmpId(employees[0].id)
    }
  }, [employees, newTaskEmpId])

  // Fetch Onboarding Tasks
  const loadTasks = async () => {
    setLoadingTasks(true)
    setTaskError(null)
    try {
      const data = await listAllOnboardingTasks({
        employee_id: selectedEmpFilter !== "ALL" ? selectedEmpFilter : undefined,
        owner_department: deptFilter !== "ALL" ? deptFilter : undefined,
      })
      setTasks(data)
    } catch (err: unknown) {
      setTaskError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoadingTasks(false)
    }
  }

  useEffect(() => {
    loadTasks()
  }, [selectedEmpFilter, deptFilter])

  // Fetch Knowledge Base Articles
  const loadArticles = async () => {
    setKbLoading(true)
    try {
      const data = await listKnowledgeArticles({
        q: kbSearch || undefined,
        category: kbCategory !== "ALL" ? kbCategory : undefined,
      })
      setArticles(data)
    } catch (err: unknown) {
      console.error("Failed to load KB articles:", err)
    } finally {
      setKbLoading(false)
    }
  }

  useEffect(() => {
    loadArticles()
  }, [kbCategory])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    loadArticles()
  }

  // Complete Task Handler
  const handleToggleComplete = async (taskId: string, currentStatus: string) => {
    if (currentStatus === "DONE") return
    try {
      await completeOnboardingTask(taskId)
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: "DONE", completed_at: new Date().toISOString() } : t))
      )
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to complete task")
    }
  }

  // Delete Task Handler
  const handleDeleteTask = async (taskId: string) => {
    if (!confirm("Are you sure you want to remove this onboarding task?")) return
    try {
      await deleteOnboardingTask(taskId)
      setTasks((prev) => prev.filter((t) => t.id !== taskId))
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete task")
    }
  }

  // Submit Add Task
  const handleAddTaskSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTaskEmpId || !newTaskName) return
    setIsSubmittingTask(true)
    try {
      await createOnboardingTask({
        employee_id: newTaskEmpId,
        task_name: newTaskName,
        description: newTaskDesc || undefined,
        owner_department: newTaskDept,
        due_date: newTaskDueDate || undefined,
      })
      setIsAddTaskOpen(false)
      setNewTaskName("")
      setNewTaskDesc("")
      loadTasks()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to add task")
    } finally {
      setIsSubmittingTask(false)
    }
  }

  // Submit Bulk Add
  const handleBulkAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!bulkEmpId) return
    const template = ONBOARDING_TEMPLATES.find((t) => t.id === bulkTemplateId)
    if (!template) return
    setIsSubmittingBulk(true)
    try {
      const items = template.tasks.map((t, idx) => ({
        task_name: t.task_name,
        owner_department: t.owner_department,
        due_date: new Date(Date.now() + (idx + 2) * 86400000).toISOString().split("T")[0],
        sort_order: idx + 1,
      }))
      await bulkCreateOnboardingTasks(bulkEmpId, items)
      setIsBulkAddOpen(false)
      loadTasks()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to bulk create tasks")
    } finally {
      setIsSubmittingBulk(false)
    }
  }

  // Submit New Article
  const handleCreateArticleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newArtTitle || !newArtContent) return
    setIsSubmittingArticle(true)
    try {
      const tagsArray = newArtTags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
      await createKnowledgeArticle({
        title: newArtTitle,
        category: newArtCategory,
        tags: tagsArray,
        content: newArtContent,
        is_published: true,
      })
      setIsNewArticleOpen(false)
      setNewArtTitle("")
      setNewArtContent("")
      setNewArtTags("")
      loadArticles()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save article")
    } finally {
      setIsSubmittingArticle(false)
    }
  }

  // Delete Article
  const handleDeleteArticle = async (id: string) => {
    if (!confirm("Delete this article from the Knowledge Base?")) return
    try {
      await deleteKnowledgeArticle(id)
      setArticles((prev) => prev.filter((a) => a.id !== id))
      if (selectedArticle?.id === id) setSelectedArticle(null)
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete article")
    }
  }

  // Task KPI calculations
  const totalTasks = tasks.length
  const completedTasks = tasks.filter((t) => t.status === "DONE").length
  const pendingTasks = totalTasks - completedTasks
  const progressPct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0

  return (
    <div className="space-y-6">
      {/* ── ONBOARDING JOURNEY CARD ──────────────────────────────────── */}
      <Card className="border-border">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <IdCard className="h-5 w-5 text-sky-400" />
              Onboarding Checklist & Journey
            </CardTitle>
            <CardDescription>
              Orchestrate new hire pre-boarding, statutory compliance, equipment handover, and department tasks.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setIsBulkAddOpen(true)}>
              <Layers className="h-4 w-4 mr-1 text-muted-foreground" />
              Bulk Add (Templates)
            </Button>
            <Button size="sm" variant="cta" onClick={() => setIsAddTaskOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Add Task
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Progress & Quick Metrics */}
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-border bg-background/50 p-3">
              <p className="text-xs text-muted-foreground">Total Tasks</p>
              <p className="text-xl font-bold text-foreground mt-0.5">{totalTasks}</p>
            </div>
            <div className="rounded-lg border border-border bg-background/50 p-3">
              <p className="text-xs text-muted-foreground">Completed</p>
              <p className="text-xl font-bold text-emerald-400 mt-0.5">{completedTasks}</p>
            </div>
            <div className="rounded-lg border border-border bg-background/50 p-3">
              <p className="text-xs text-muted-foreground">Pending Action</p>
              <p className="text-xl font-bold text-amber-400 mt-0.5">{pendingTasks}</p>
            </div>
            <div className="rounded-lg border border-border bg-background/50 p-3">
              <p className="text-xs text-muted-foreground">Checklist Progress</p>
              <div className="flex items-center gap-2 mt-1">
                <div className="h-2 flex-1 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-emerald-500 transition-all duration-300"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="text-xs font-semibold text-foreground">{progressPct}%</span>
              </div>
            </div>
          </div>

          {/* Filters Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <User className="h-3.5 w-3.5" />
                <span>Employee:</span>
              </div>
              <select
                value={selectedEmpFilter}
                onChange={(e) => setSelectedEmpFilter(e.target.value)}
                className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-sky-500"
              >
                <option value="ALL">All Employees ({employees.length})</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.full_name} ({e.employee_id})
                  </option>
                ))}
              </select>

              <div className="flex items-center gap-1.5 text-xs text-muted-foreground ml-2">
                <Building className="h-3.5 w-3.5" />
                <span>Dept:</span>
              </div>
              <select
                value={deptFilter}
                onChange={(e) => setDeptFilter(e.target.value)}
                className="h-8 rounded-md border border-border bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-sky-500"
              >
                <option value="ALL">All Departments</option>
                <option value="HR">HR</option>
                <option value="IT">IT & Systems</option>
                <option value="Field Ops">Field Operations</option>
                <option value="Compliance">Compliance & PSIRA</option>
                <option value="Payroll">Payroll</option>
                <option value="Sales">Sales</option>
              </select>
            </div>
            <Button size="sm" variant="ghost" onClick={loadTasks} className="h-8 text-xs text-muted-foreground">
              Refresh Tasks
            </Button>
          </div>

          {/* Tasks Table */}
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[700px] text-sm">
              <thead className="bg-muted/40 text-xs text-muted-foreground border-b border-border">
                <tr>
                  <th className="py-2.5 px-3 text-left font-medium">Status</th>
                  <th className="py-2.5 px-3 text-left font-medium">Task & Details</th>
                  <th className="py-2.5 px-3 text-left font-medium">Assigned New Hire</th>
                  <th className="py-2.5 px-3 text-left font-medium">Owner Dept</th>
                  <th className="py-2.5 px-3 text-left font-medium">Due Date</th>
                  <th className="py-2.5 px-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {loadingTasks ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      Loading onboarding checklist…
                    </td>
                  </tr>
                ) : taskError ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-sm text-red-400">
                      Error: {taskError}
                    </td>
                  </tr>
                ) : tasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      No onboarding tasks found for this view. Click <strong>Add Task</strong> or <strong>Bulk Add</strong> to provision an onboarding journey.
                    </td>
                  </tr>
                ) : (
                  tasks.map((task) => {
                    const isDone = task.status === "DONE"
                    return (
                      <tr key={task.id} className={`hover:bg-muted/20 transition-colors ${isDone ? "opacity-75" : ""}`}>
                        <td className="py-3 px-3">
                          <button
                            type="button"
                            onClick={() => handleToggleComplete(task.id, task.status)}
                            className={`flex items-center justify-center h-6 w-6 rounded border transition-colors ${
                              isDone
                                ? "bg-emerald-500/20 border-emerald-500 text-emerald-400 cursor-default"
                                : "border-border hover:border-sky-400 text-transparent hover:text-sky-400"
                            }`}
                            title={isDone ? "Completed" : "Click to mark as done"}
                          >
                            <CheckCircle2 className="h-4 w-4 fill-current" />
                          </button>
                        </td>
                        <td className="py-3 px-3">
                          <p className={`font-medium ${isDone ? "line-through text-muted-foreground" : "text-foreground"}`}>
                            {task.task_name}
                          </p>
                          {task.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{task.description}</p>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <span className="font-medium text-foreground">{task.employee_name || "New Hire"}</span>
                          {task.employee_code && (
                            <span className="text-xs text-muted-foreground block">{task.employee_code}</span>
                          )}
                        </td>
                        <td className="py-3 px-3">
                          <Badge variant="outline" className="text-xs">
                            {task.owner_department}
                          </Badge>
                        </td>
                        <td className="py-3 px-3 text-xs text-muted-foreground">
                          {task.due_date ? (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {task.due_date}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {!isDone && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs"
                                onClick={() => handleToggleComplete(task.id, task.status)}
                              >
                                Complete
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0 text-muted-foreground hover:text-red-400"
                              onClick={() => handleDeleteTask(task.id)}
                              title="Delete task"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
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

      {/* ── KNOWLEDGE BASE & SEARCHABLE RAG CARD ─────────────────────── */}
      <Card className="border-border">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <BookOpen className="h-5 w-5 text-indigo-400" />
              HR Knowledge Base & Policies (Markdown / Searchable)
            </CardTitle>
            <CardDescription>
              Official labor policies, BCEA guidelines, OHS procedures, commission schemes, and staff SOPs.
            </CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={() => setIsNewArticleOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Article
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Search bar & Category filter */}
          <div className="flex flex-col sm:flex-row gap-3">
            <form onSubmit={handleSearchSubmit} className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={kbSearch}
                onChange={(e) => setKbSearch(e.target.value)}
                placeholder="Search policies, BCEA, tax rules, keywords…"
                className="pl-9 h-9"
              />
            </form>
            <div className="flex flex-wrap gap-1.5">
              {[
                { key: "ALL", label: "All Topics" },
                { key: "Compliance & Labor", label: "Compliance & Labor" },
                { key: "Finance & Payroll", label: "Finance & Tax" },
                { key: "Sales & Commercial", label: "Sales & Scheme" },
              ].map((c) => (
                <button
                  key={c.key}
                  type="button"
                  onClick={() => setKbCategory(c.key)}
                  className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
                    kbCategory === c.key
                      ? "border-indigo-500 bg-indigo-500/10 text-indigo-300 font-medium"
                      : "border-border bg-background hover:bg-muted/40 text-muted-foreground"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* Articles list */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {kbLoading ? (
              <p className="col-span-full py-8 text-center text-sm text-muted-foreground">Loading knowledge base…</p>
            ) : articles.length === 0 ? (
              <div className="col-span-full py-8 text-center text-sm text-muted-foreground">
                <FileText className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                No articles match your search. Click <strong>New Article</strong> to draft one.
              </div>
            ) : (
              articles.map((art) => (
                <div
                  key={art.id}
                  className="rounded-lg border border-border bg-background/50 hover:border-indigo-500/50 p-4 transition-all flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <Badge variant="outline" className="text-xs bg-indigo-500/5 border-indigo-500/30 text-indigo-300">
                        {art.category}
                      </Badge>
                      <button
                        type="button"
                        onClick={() => handleDeleteArticle(art.id)}
                        className="text-muted-foreground hover:text-red-400 transition-colors"
                        title="Delete article"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <h3 className="font-semibold text-foreground text-sm line-clamp-1">{art.title}</h3>
                    <p className="text-xs text-muted-foreground mt-1.5 line-clamp-3 leading-relaxed">
                      {art.content.replace(/^#+\s+/gm, "").replace(/\*\*/g, "")}
                    </p>
                  </div>

                  <div className="pt-3 mt-3 border-t border-border flex items-center justify-between">
                    <div className="flex flex-wrap gap-1">
                      {art.tags.slice(0, 2).map((t) => (
                        <span key={t} className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                          #{t}
                        </span>
                      ))}
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 text-xs text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 gap-1 px-2"
                      onClick={() => setSelectedArticle(art)}
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Read
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── MODAL: ADD ONBOARDING TASK ───────────────────────────────── */}
      {isAddTaskOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-background rounded-lg border border-border max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <IdCard className="h-4 w-4 text-sky-400" />
                Add Onboarding Task
              </h3>
              <Button size="icon" variant="ghost" onClick={() => setIsAddTaskOpen(false)} className="h-7 w-7">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <form onSubmit={handleAddTaskSubmit} className="space-y-3.5 text-sm">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Assignee (Employee)</label>
                <select
                  value={newTaskEmpId}
                  onChange={(e) => setNewTaskEmpId(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-sky-500"
                  required
                >
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} ({e.job_title} - {e.department})
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Task Title</label>
                <Input
                  value={newTaskName}
                  onChange={(e) => setNewTaskName(e.target.value)}
                  placeholder="e.g. Issue Fujikura 90S Splicer & Laptop"
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Description / Instructions</label>
                <textarea
                  value={newTaskDesc}
                  onChange={(e) => setNewTaskDesc(e.target.value)}
                  placeholder="Provide instructions, equipment serials, or document links…"
                  rows={2}
                  className="w-full rounded-md border border-border bg-background p-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Owner Department</label>
                  <select
                    value={newTaskDept}
                    onChange={(e) => setNewTaskDept(e.target.value)}
                    className="w-full h-9 rounded-md border border-border bg-background px-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-sky-500"
                  >
                    <option value="HR">HR</option>
                    <option value="IT">IT Support</option>
                    <option value="Field Ops">Field Operations</option>
                    <option value="Compliance">Compliance & Legal</option>
                    <option value="Payroll">Payroll & Finance</option>
                    <option value="Sales">Sales Management</option>
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Due Date</label>
                  <Input
                    type="date"
                    value={newTaskDueDate}
                    onChange={(e) => setNewTaskDueDate(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border">
                <Button type="button" variant="ghost" onClick={() => setIsAddTaskOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="cta" disabled={isSubmittingTask}>
                  {isSubmittingTask ? "Adding…" : "Save Task"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: BULK ADD TASKS (TEMPLATES) ───────────────────────── */}
      {isBulkAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-background rounded-lg border border-border max-w-lg w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <Layers className="h-4 w-4 text-sky-400" />
                Bulk Provision Onboarding Journey
              </h3>
              <Button size="icon" variant="ghost" onClick={() => setIsBulkAddOpen(false)} className="h-7 w-7">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <form onSubmit={handleBulkAddSubmit} className="space-y-4 text-sm">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Select New Hire</label>
                <select
                  value={bulkEmpId}
                  onChange={(e) => setBulkEmpId(e.target.value)}
                  className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-sky-500"
                  required
                >
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} ({e.job_title} - {e.department})
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">Choose Standard Journey Template</label>
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {ONBOARDING_TEMPLATES.map((tmpl) => (
                    <label
                      key={tmpl.id}
                      className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                        bulkTemplateId === tmpl.id
                          ? "border-sky-500 bg-sky-500/10 text-foreground"
                          : "border-border hover:bg-muted/30 text-muted-foreground"
                      }`}
                    >
                      <input
                        type="radio"
                        name="template"
                        value={tmpl.id}
                        checked={bulkTemplateId === tmpl.id}
                        onChange={() => setBulkTemplateId(tmpl.id)}
                        className="mt-1"
                      />
                      <div>
                        <p className="font-semibold text-sm text-foreground">{tmpl.name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{tmpl.description}</p>
                        <p className="text-[11px] text-sky-400 mt-1">{tmpl.tasks.length} checklist tasks will be created</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border">
                <Button type="button" variant="ghost" onClick={() => setIsBulkAddOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="cta" disabled={isSubmittingBulk}>
                  {isSubmittingBulk ? "Generating…" : "Generate Tasks"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: CREATE KNOWLEDGE BASE ARTICLE ────────────────────── */}
      {isNewArticleOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-background rounded-lg border border-border max-w-2xl w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-indigo-400" />
                New Knowledge Base Policy / Article (Markdown)
              </h3>
              <Button size="icon" variant="ghost" onClick={() => setIsNewArticleOpen(false)} className="h-7 w-7">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <form onSubmit={handleCreateArticleSubmit} className="space-y-3.5 text-sm">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Article Title</label>
                  <Input
                    value={newArtTitle}
                    onChange={(e) => setNewArtTitle(e.target.value)}
                    placeholder="e.g. Overtime & Weekend Standby Policy"
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Category</label>
                  <select
                    value={newArtCategory}
                    onChange={(e) => setNewArtCategory(e.target.value)}
                    className="w-full h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="Compliance & Labor">Compliance & Labor</option>
                    <option value="Finance & Payroll">Finance & Payroll</option>
                    <option value="Sales & Commercial">Sales & Commercial</option>
                    <option value="Technical & OHS">Technical & OHS</option>
                    <option value="General">General HR</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Tags (comma-separated)</label>
                <Input
                  value={newArtTags}
                  onChange={(e) => setNewArtTags(e.target.value)}
                  placeholder="e.g. BCEA, Overtime, Weekend, Guarding"
                />
              </div>

              {/* Editor Tabs: Write vs Preview */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-muted-foreground">Markdown Content</label>
                  <div className="flex rounded-md border border-border overflow-hidden text-xs">
                    <button
                      type="button"
                      onClick={() => setArtEditorTab("write")}
                      className={`px-3 py-1 ${artEditorTab === "write" ? "bg-muted text-foreground font-semibold" : "text-muted-foreground hover:bg-muted/40"}`}
                    >
                      Write
                    </button>
                    <button
                      type="button"
                      onClick={() => setArtEditorTab("preview")}
                      className={`px-3 py-1 ${artEditorTab === "preview" ? "bg-muted text-foreground font-semibold" : "text-muted-foreground hover:bg-muted/40"}`}
                    >
                      Preview
                    </button>
                  </div>
                </div>

                {artEditorTab === "write" ? (
                  <textarea
                    value={newArtContent}
                    onChange={(e) => setNewArtContent(e.target.value)}
                    placeholder="# Article Heading&#10;&#10;## Subheading&#10;- Key policy rule 1&#10;- Key policy rule 2&#10;&#10;**Statutory requirement**: Explanation..."
                    rows={8}
                    className="w-full font-mono text-xs rounded-md border border-border bg-background p-3 text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    required
                  />
                ) : (
                  <div className="rounded-md border border-border bg-muted/20 p-4 max-h-56 overflow-y-auto text-xs space-y-2 text-foreground">
                    {newArtContent ? (
                      <div className="whitespace-pre-wrap leading-relaxed">
                        {newArtContent}
                      </div>
                    ) : (
                      <p className="text-muted-foreground italic">Type markdown in the Write tab to see preview.</p>
                    )}
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-border">
                <Button type="button" variant="ghost" onClick={() => setIsNewArticleOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" variant="cta" disabled={isSubmittingArticle}>
                  {isSubmittingArticle ? "Publishing…" : "Publish Article"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: READ KNOWLEDGE BASE ARTICLE ──────────────────────── */}
      {selectedArticle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="bg-background rounded-lg border border-border max-w-3xl w-full max-h-[85vh] flex flex-col p-6 shadow-2xl">
            <div className="flex items-start justify-between border-b border-border pb-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="outline" className="text-xs bg-indigo-500/10 border-indigo-500/30 text-indigo-300">
                    {selectedArticle.category}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    Published: {selectedArticle.created_at?.slice(0, 10) || "Recent"}
                  </span>
                </div>
                <h2 className="text-xl font-bold text-foreground">{selectedArticle.title}</h2>
              </div>
              <Button size="icon" variant="ghost" onClick={() => setSelectedArticle(null)} className="h-8 w-8">
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex-1 overflow-y-auto py-4 space-y-4 text-sm leading-relaxed text-foreground/90">
              <div className="whitespace-pre-wrap font-sans bg-muted/10 p-4 rounded-lg border border-border/50">
                {selectedArticle.content}
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-border pt-3">
              <div className="flex items-center gap-1.5">
                <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Tags:</span>
                {selectedArticle.tags.map((t) => (
                  <span key={t} className="text-xs bg-muted px-2 py-0.5 rounded text-foreground">
                    {t}
                  </span>
                ))}
              </div>
              <Button variant="outline" size="sm" onClick={() => setSelectedArticle(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
