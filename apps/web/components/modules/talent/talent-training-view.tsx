"use client"

import React, { useMemo, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NoDataYet } from "@/components/ui/not-connected"
import { GraduationCap, Plus, CheckCircle2, X } from "lucide-react"
import {
  createTrainingCourse,
  enrollEmployee,
  type Employee,
  type TrainingCourse,
  type TrainingEnrollment,
} from "@/lib/hr-api"
import { formatHrError } from "@/lib/talent-derive"
import { getEmployeeAvatar } from "./pim-directory-view"

interface TalentTrainingViewProps {
  employees: Employee[]
  courses: TrainingCourse[]
  enrollments: TrainingEnrollment[]
  /** Set when enrolments could not be loaded (e.g. "Not permitted: ..."); courses can still be real. */
  enrollmentsNote?: string | null
  onRefresh: () => void
}

export function TalentTrainingView({ employees, courses, enrollments, enrollmentsNote, onRefresh }: TalentTrainingViewProps) {
  const [activeTab, setActiveTab] = useState<"courses" | "enrollments" | "bursaries">("courses")
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [newCourseOpen, setNewCourseOpen] = useState(false)
  const [enrollCourse, setEnrollCourse] = useState<TrainingCourse | null>(null)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // New course form
  const [courseTitle, setCourseTitle] = useState("")
  const [courseCategory, setCourseCategory] = useState("Field Operations")
  const [courseDuration, setCourseDuration] = useState("")
  const [courseMandatory, setCourseMandatory] = useState(false)

  // Enrol form
  const [enrollEmpId, setEnrollEmpId] = useState("")

  const empById = useMemo(() => new Map(employees.map((e, i) => [e.id, { emp: e, idx: i }])), [employees])
  const courseById = useMemo(() => new Map(courses.map((c) => [c.id, c])), [courses])

  const toast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3000)
  }

  const handleCreateCourse = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setFormError(null)
    try {
      await createTrainingCourse({
        title: courseTitle.trim(),
        category: courseCategory,
        duration_hours: courseDuration.trim() === "" ? undefined : Number(courseDuration),
        mandatory: courseMandatory,
      })
      toast(`Course "${courseTitle.trim()}" created`)
      setNewCourseOpen(false)
      setCourseTitle("")
      setCourseDuration("")
      onRefresh()
    } catch (err) {
      setFormError(formatHrError(err))
    } finally {
      setBusy(false)
    }
  }

  const handleEnroll = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!enrollCourse || !enrollEmpId) return
    setBusy(true)
    setFormError(null)
    try {
      await enrollEmployee({ employee_id: enrollEmpId, course_id: enrollCourse.id })
      toast(`Enrolled in "${enrollCourse.title}"`)
      setEnrollCourse(null)
      setEnrollEmpId("")
      onRefresh()
    } catch (err) {
      setFormError(formatHrError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
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
              <GraduationCap className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-foreground">Training, Certifications & Skills (LMS)</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Courses and employee enrolments from the HR service.</p>
            </div>
          </div>
          <Button
            size="sm"
            variant="default"
            className="gap-1.5 text-xs font-semibold"
            onClick={() => {
              setFormError(null)
              setNewCourseOpen(true)
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            New Training Course
          </Button>
        </div>
      </div>

      {/* Sub-Tab Navigation */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2 text-xs">
        {[
          { id: "courses", label: `Curriculum & Courses (${courses.length})` },
          { id: "enrollments", label: `Employee Progress (${enrollments.length})` },
          { id: "bursaries", label: "Corporate Bursary Program" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-primary/15 text-primary border border-primary/30"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Courses ────────────────────────────────────────────── */}
      {activeTab === "courses" &&
        (courses.length === 0 ? (
          <NoDataYet message="No training courses defined yet. Use New Training Course to add one." />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((c) => (
              <Card key={c.id} className="border-border flex flex-col justify-between">
                <CardHeader className="pb-3 border-b border-border/60">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <Badge variant="outline" className="text-[10px] mb-1.5 border-border">
                        {c.category}
                      </Badge>
                      <CardTitle className="text-sm font-semibold line-clamp-1">{c.title}</CardTitle>
                    </div>
                    {c.mandatory && (
                      <Badge variant="outline" className="border-red-500/40 text-red-400 text-[10px]">
                        Mandatory
                      </Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-3 text-xs">
                  {c.description && <p className="text-muted-foreground line-clamp-2">{c.description}</p>}
                  <div className="flex items-center justify-between border-t border-border/50 pt-2 text-muted-foreground">
                    <span>Duration: <strong className="text-foreground">{c.duration_hours != null ? `${c.duration_hours} Hours` : "—"}</strong></span>
                    <span>Pass Mark: <strong className="text-foreground">{c.passing_score != null ? `${c.passing_score}%` : "—"}</strong></span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-xs"
                    disabled={employees.length === 0}
                    onClick={() => {
                      setFormError(null)
                      setEnrollEmpId("")
                      setEnrollCourse(c)
                    }}
                  >
                    Enrol employee
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        ))}

      {/* ── TAB 2: Enrollments & Progress ─────────────────────────────── */}
      {activeTab === "enrollments" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base">Employee Certification Status</CardTitle>
            <CardDescription className="text-xs">Enrolments, progress and exam scores as recorded in the HR service.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {enrollmentsNote && (
              <p className="m-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-400" role="status">
                Enrolments could not be loaded. {enrollmentsNote}
              </p>
            )}
            {!enrollmentsNote && enrollments.length === 0 ? (
              <div className="p-4">
                <NoDataYet message="No enrolments yet." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                      <th className="py-2.5 px-4 font-medium">Employee</th>
                      <th className="py-2.5 px-4 font-medium">Course Title</th>
                      <th className="py-2.5 px-4 font-medium">Progress</th>
                      <th className="py-2.5 px-4 font-medium">Exam Score</th>
                      <th className="py-2.5 px-4 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {enrollments.map((en) => {
                      const hit = empById.get(en.employee_id)
                      const course = courseById.get(en.course_id)
                      const progress = Math.max(0, Math.min(100, Number(en.progress_pct) || 0))
                      return (
                        <tr key={en.id} className="hover:bg-muted/30">
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              {hit && <img src={getEmployeeAvatar(hit.emp.full_name, hit.idx)} alt="" className="h-6 w-6 rounded-full object-cover" />}
                              <span className="font-semibold text-foreground">{hit?.emp.full_name ?? "Unknown employee"}</span>
                            </div>
                          </td>
                          <td className="py-3 px-4 font-medium text-foreground">{course?.title ?? "Unknown course"}</td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-28 rounded-full bg-muted overflow-hidden">
                                <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${progress}%` }} />
                              </div>
                              <span className="font-mono text-muted-foreground">{progress}%</span>
                            </div>
                          </td>
                          <td className="py-3 px-4 font-mono font-semibold text-foreground">{en.score != null ? `${en.score}%` : "—"}</td>
                          <td className="py-3 px-4">
                            <Badge variant="outline" className="border-primary/40 text-primary">
                              {en.status}
                            </Badge>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── TAB 3: Bursaries ─────────────────────────────────────────── */}
      {activeTab === "bursaries" && <NoDataYet message="No bursary records are tracked yet." />}

      {/* ── NEW COURSE MODAL ─────────────────────────────────────────── */}
      {newCourseOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-md border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">New Training Course</CardTitle>
                <CardDescription className="text-xs">Saved to the HR service.</CardDescription>
              </div>
              <button type="button" onClick={() => setNewCourseOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateCourse}>
              <CardContent className="space-y-4 pt-4 text-xs">
                {formError && <p className="rounded border border-red-400/20 bg-red-400/10 p-2 text-red-400" role="alert">{formError}</p>}
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Course Title *</label>
                  <Input required placeholder="Course title" value={courseTitle} onChange={(e) => setCourseTitle(e.target.value)} className="h-8 text-xs" />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Category</label>
                    <select
                      value={courseCategory}
                      onChange={(e) => setCourseCategory(e.target.value)}
                      className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                    >
                      <option value="Field Operations">Field Operations</option>
                      <option value="Network & Core">Network & Core</option>
                      <option value="Compliance">Compliance</option>
                      <option value="Customer Support">Customer Support</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="font-medium text-foreground">Duration (Hours)</label>
                    <Input type="number" min={0} value={courseDuration} onChange={(e) => setCourseDuration(e.target.value)} className="h-8 text-xs font-mono" />
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="mand"
                    checked={courseMandatory}
                    onChange={(e) => setCourseMandatory(e.target.checked)}
                    className="rounded border-border text-primary focus:ring-primary"
                  />
                  <label htmlFor="mand" className="text-xs font-medium text-foreground">
                    Mandatory for relevant department
                  </label>
                </div>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setNewCourseOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" disabled={busy || !courseTitle.trim()}>
                  {busy ? "Creating…" : "Create Course"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ── ENROL MODAL ─────────────────────────────────────────────── */}
      {enrollCourse && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-md border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">Enrol employee</CardTitle>
                <CardDescription className="text-xs">{enrollCourse.title}</CardDescription>
              </div>
              <button type="button" onClick={() => setEnrollCourse(null)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleEnroll}>
              <CardContent className="space-y-4 pt-4 text-xs">
                {formError && <p className="rounded border border-red-400/20 bg-red-400/10 p-2 text-red-400" role="alert">{formError}</p>}
                <select
                  value={enrollEmpId}
                  onChange={(e) => setEnrollEmpId(e.target.value)}
                  className="w-full h-8 rounded-md border border-border bg-background px-3 text-xs text-foreground"
                >
                  <option value="">Select an employee…</option>
                  {employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name}
                    </option>
                  ))}
                </select>
              </CardContent>
              <div className="flex items-center justify-end gap-2 border-t border-border p-4 bg-muted/10">
                <Button type="button" variant="ghost" size="sm" onClick={() => setEnrollCourse(null)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" variant="default" disabled={busy || !enrollEmpId}>
                  {busy ? "Enrolling…" : "Enrol"}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
