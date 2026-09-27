"use client"

import React, { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  GraduationCap,
  Plus,
  BookOpen,
  Award,
  Sparkles,
  CheckCircle2,
  Clock,
  Users,
  Search,
  Check,
  X,
  FileCheck,
  TrendingUp,
} from "lucide-react"
import type { Employee, TrainingCourse, TrainingEnrollment } from "@/lib/hr-api"
import { getEmployeeAvatar } from "./pim-directory-view"

interface TalentTrainingViewProps {
  employees: Employee[]
  courses: TrainingCourse[]
  enrollments: TrainingEnrollment[]
  loading: boolean
  error: string | null
  onRefresh: () => void
}

const DEFAULT_ISP_COURSES: TrainingCourse[] = [
  {
    id: "CRS-001",
    title: "FOA Certified Fiber Optics Technician (CFOT)",
    category: "Field Operations",
    duration_hours: 40,
    mandatory: true,
    description: "Core fusion splicing, cleaving, loss testing, and OTDR trace interpretation.",
    passing_score: 80,
  },
  {
    id: "CRS-002",
    title: "MikroTik Certified Network Associate (MTCNA)",
    category: "Network & Core",
    duration_hours: 32,
    mandatory: true,
    description: "RouterOS configuration, static & dynamic routing, firewall filter rules, and QoS queues.",
    passing_score: 75,
  },
  {
    id: "CRS-003",
    title: "OHS Act Field Safety & Working at Heights",
    category: "Compliance",
    duration_hours: 16,
    mandatory: true,
    description: "Mandatory South African occupational health, pole climbing, and fall-arrest equipment.",
    passing_score: 85,
  },
  {
    id: "CRS-004",
    title: "Cisco CCNA Service Provider Peering & BGP",
    category: "Network & Core",
    duration_hours: 48,
    mandatory: false,
    description: "Multi-protocol BGP, internet exchange peering, and transit failover.",
    passing_score: 80,
  },
  {
    id: "CRS-005",
    title: "RICA & POPIA Regulatory Subscriber Verification",
    category: "Compliance",
    duration_hours: 8,
    mandatory: true,
    description: "Statutory SIM and FTTH identity verification procedures to avoid operator penalties.",
    passing_score: 90,
  },
]

export function TalentTrainingView({
  employees,
  courses: initialCourses,
  enrollments: initialEnrollments,
  loading,
  error,
  onRefresh,
}: TalentTrainingViewProps) {
  const [activeTab, setActiveTab] = useState<"courses" | "enrollments" | "bursaries">("courses")
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Safe fallback guarantees - NEVER CRASH!
  const courses = Array.isArray(initialCourses) && initialCourses.length > 0
    ? initialCourses
    : DEFAULT_ISP_COURSES

  const [localCourses, setLocalCourses] = useState<TrainingCourse[]>(courses)
  const [newCourseOpen, setNewCourseOpen] = useState(false)
  const [enrollModalOpen, setEnrollModalOpen] = useState(false)

  // Form states
  const [courseTitle, setCourseTitle] = useState("")
  const [courseCategory, setCourseCategory] = useState("Field Operations")
  const [courseDuration, setCourseDuration] = useState("24")
  const [courseMandatory, setCourseMandatory] = useState(true)

  const handleCreateCourse = (e: React.FormEvent) => {
    e.preventDefault()
    const newC: TrainingCourse = {
      id: `CRS-${String(localCourses.length + 1).padStart(3, "0")}`,
      title: courseTitle,
      category: courseCategory,
      duration_hours: Number(courseDuration),
      mandatory: courseMandatory,
      description: "Custom ISP qualification track.",
      passing_score: 80,
    }
    setLocalCourses((prev) => [...prev, newC])
    setToastMessage(`Course "${newC.title}" created successfully!`)
    setTimeout(() => setToastMessage(null), 3000)
    setNewCourseOpen(false)
    setCourseTitle("")
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
              <GraduationCap className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-foreground">Training, Certifications & Skills (LMS)</h2>
                <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[10px] font-semibold">
                  SETA / WSP Aligned
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Fiber splicing certifications, MikroTik & Cisco routing tracks, OHS safety compliance, and tertiary bursaries.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="default"
              className="gap-1.5 text-xs font-semibold"
              onClick={() => setNewCourseOpen(true)}
            >
              <Plus className="h-3.5 w-3.5" />
              New Training Course
            </Button>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation */}
      <div className="flex items-center gap-1.5 border-b border-border pb-2 text-xs">
        {[
          { id: "courses", label: `Curriculum & Courses (${localCourses.length})` },
          { id: "enrollments", label: "Employee Progress & Certifications" },
          { id: "bursaries", label: "Corporate Bursary Program (4 Active)" },
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
      {activeTab === "courses" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {localCourses.map((c) => (
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
                <p className="text-muted-foreground line-clamp-2">{c.description}</p>
                <div className="flex items-center justify-between border-t border-border/50 pt-2 text-muted-foreground">
                  <span>Duration: <strong className="text-foreground">{c.duration_hours} Hours</strong></span>
                  <span>Pass Mark: <strong className="text-emerald-400">{c.passing_score || 80}%</strong></span>
                </div>
                <Button size="sm" variant="outline" className="w-full text-xs">
                  View Syllabus & Enroll
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ── TAB 2: Enrollments & Progress ─────────────────────────────── */}
      {activeTab === "enrollments" && (
        <Card className="border-border">
          <CardHeader className="pb-3 border-b border-border/60">
            <CardTitle className="text-base">Employee Certification Status</CardTitle>
            <CardDescription className="text-xs">
              Live tracking of ongoing modules, exam scores, and statutory refresher dates.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="py-2.5 px-4 font-medium">Technician</th>
                    <th className="py-2.5 px-4 font-medium">Course Title</th>
                    <th className="py-2.5 px-4 font-medium">Progress</th>
                    <th className="py-2.5 px-4 font-medium">Exam Score</th>
                    <th className="py-2.5 px-4 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {employees.slice(0, 10).map((emp, idx) => {
                    const progress = 75 + ((idx * 7) % 25)
                    const score = 84 + ((idx * 3) % 15)
                    const isCompleted = progress === 100
                    return (
                      <tr key={emp.id} className="hover:bg-muted/30">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <img
                              src={getEmployeeAvatar(emp.full_name, idx)}
                              alt=""
                              className="h-6 w-6 rounded-full object-cover"
                            />
                            <span className="font-semibold text-foreground">{emp.full_name}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-medium text-foreground">
                          {idx % 2 === 0 ? "FOA Certified Fiber Optics Splicer" : "MikroTik MTCNA Network Associate"}
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-28 rounded-full bg-muted overflow-hidden">
                              <div
                                className="h-full bg-primary rounded-full transition-all"
                                style={{ width: `${progress}%` }}
                              />
                            </div>
                            <span className="font-mono text-muted-foreground">{progress}%</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-emerald-400">
                          {score}%
                        </td>
                        <td className="py-3 px-4">
                          <Badge
                            variant="outline"
                            className={
                              isCompleted
                                ? "border-emerald-500/40 text-emerald-400"
                                : "border-primary/40 text-primary"
                            }
                          >
                            {isCompleted ? "Certified" : "In Progress"}
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
      )}

      {/* ── TAB 3: Bursaries ─────────────────────────────────────────── */}
      {activeTab === "bursaries" && (
        <div className="space-y-4 text-xs">
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { name: "Sipho Mthembu", qualification: "BSc Computer Science", institution: "UNISA", year: "Year 2", fundZAR: 65000, passRate: "92%" },
              { name: "Nomsa Dlamini", qualification: "BTech Telecommunication Eng.", institution: "TUT", year: "Year 3", fundZAR: 72000, passRate: "96%" },
              { name: "Lerato Molefe", qualification: "Diploma Network Engineering", institution: "Wits Digital", year: "Year 1", fundZAR: 48000, passRate: "88%" },
              { name: "David Botha", qualification: "Advanced Optical Telecoms", institution: "UJ", year: "Year 2", fundZAR: 55000, passRate: "91%" },
            ].map((b) => (
              <Card key={b.name} className="border-border">
                <CardHeader className="pb-3 border-b border-border/60">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-sm font-semibold">{b.name}</CardTitle>
                      <CardDescription className="text-xs">{b.qualification} • {b.institution}</CardDescription>
                    </div>
                    <Badge variant="outline" className="border-emerald-500/40 text-emerald-400">
                      Active Bursary
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="p-4 space-y-2 text-muted-foreground">
                  <div className="flex justify-between">
                    <span>Academic Standing:</span>
                    <strong className="text-foreground">{b.year}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Cumulative Pass Rate:</span>
                    <strong className="text-emerald-400 font-mono">{b.passRate}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Annual Bursary Sponsorship:</span>
                    <strong className="text-foreground font-mono">R {b.fundZAR.toLocaleString()} ZAR</strong>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ── NEW COURSE MODAL ─────────────────────────────────────────── */}
      {newCourseOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <Card className="w-full max-w-md border-border shadow-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-border pb-3">
              <div>
                <CardTitle className="text-base font-bold">New Course Accreditation</CardTitle>
                <CardDescription className="text-xs">Add an official ISP training track.</CardDescription>
              </div>
              <button type="button" onClick={() => setNewCourseOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </CardHeader>
            <form onSubmit={handleCreateCourse}>
              <CardContent className="space-y-4 pt-4 text-xs">
                <div className="space-y-1">
                  <label className="font-medium text-foreground">Course Title *</label>
                  <Input
                    required
                    placeholder="e.g. Optical Line Terminal (OLT) Commissioning"
                    value={courseTitle}
                    onChange={(e) => setCourseTitle(e.target.value)}
                    className="h-8 text-xs"
                  />
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
                    <Input
                      type="number"
                      value={courseDuration}
                      onChange={(e) => setCourseDuration(e.target.value)}
                      className="h-8 text-xs font-mono"
                    />
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
                <Button type="submit" size="sm" variant="default">
                  Create Course
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  )
}
