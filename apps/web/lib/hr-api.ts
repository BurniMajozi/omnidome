"use client"

/**
 * HR API client — employees, leave, performance, schedules, training,
 * benefits, disciplinary, exits, onboarding, and analytics.
 * Proxies through the Next.js API routes to the HR service (port 8009).
 */

import { supabase } from "@/lib/supabase/client"

const API_BASE = "/svc/hr"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"

async function getTenantId(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  return (
    data.session?.user?.user_metadata?.tenant_id ??
    data.session?.user?.app_metadata?.tenant_id ??
    FALLBACK_TENANT_ID
  )
}

async function fetchHR<T>(path: string, init?: RequestInit): Promise<T> {
  const tenantId = await getTenantId()
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "x-tenant-id": tenantId, "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`HR API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export interface Employee {
  id: string
  tenant_id: string
  employee_id: string
  full_name: string
  job_title: string
  department: string
  hire_date: string
  email?: string
  phone?: string
  status: string
  created_at: string
  updated_at?: string
}

export interface EmployeeCreate {
  employee_id: string
  full_name: string
  job_title: string
  department: string
  hire_date: string
  email?: string
  phone?: string
}

export interface LeaveRequest {
  id: string
  employee_id: string
  leave_type: string
  start_date: string
  end_date: string
  reason?: string
  status: string
  created_at: string
  updated_at?: string
}

export interface LeaveRequestCreate {
  leave_type: string
  start_date: string
  end_date: string
  reason?: string
}

export interface PerformanceReview {
  id: string
  employee_id: string
  review_period: string
  tickets_resolved?: number
  avg_resolution_time?: number
  fcr_rate?: number
  kpi_score?: number
  sentiment_score?: number
  attrition_risk?: string
  reviewer_notes?: string
  created_at: string
}

export interface PerformanceReviewCreate {
  review_period: string
  tickets_resolved?: number
  avg_resolution_time?: number
  fcr_rate?: number
  kpi_score?: number
  sentiment_score?: number
  attrition_risk?: string
  reviewer_notes?: string
}

export interface Schedule {
  id: string
  employee_id: string
  schedule_date: string
  shift_start: string
  shift_end: string
  shift_type?: string
  department: string
  notes?: string
  status: string
  created_at: string
  updated_at?: string
}

export interface ScheduleCreate {
  employee_id: string
  schedule_date: string
  shift_start: string
  shift_end: string
  shift_type?: string
  department: string
  notes?: string
}

export interface TrainingCourse {
  id: string
  title: string
  description?: string
  category: string
  duration_hours?: number
  mandatory?: boolean
  created_at: string
}

export interface TrainingCourseCreate {
  title: string
  description?: string
  category: string
  duration_hours?: number
  mandatory?: boolean
}

export interface TrainingEnrollment {
  id: string
  employee_id: string
  course_id: string
  progress_pct: number
  score?: number
  status: string
  enrolled_at: string
  completed_at?: string
}

export interface Benefit {
  id: string
  employee_id: string
  benefit_type: string
  created_at: string
}

export interface BenefitCreate {
  employee_id: string
  benefit_type: string
  [key: string]: unknown
}

export interface DisciplinaryAction {
  id: string
  employee_id: string
  action_type: string
  incident_date: string
  description: string
  outcome?: string
  suspension_days?: number
  status: string
  created_at: string
}

export interface DisciplinaryCreate {
  employee_id: string
  action_type: string
  incident_date: string
  description: string
  outcome?: string
  suspension_days?: number
}

export interface ExitRecord {
  id: string
  employee_id: string
  exit_type: string
  reason?: string
  notice_date: string
  last_working_date: string
  status: string
  created_at: string
}

export interface ExitCreate {
  employee_id: string
  exit_type: string
  reason?: string
  notice_date: string
  last_working_date: string
}

export interface ExitChecklist {
  exit_interview_done?: boolean
  assets_returned?: boolean
  access_revoked?: boolean
  final_payout_zar?: number
}

export interface OnboardingTask {
  id: string
  employee_id: string
  task_name: string
  description?: string
  owner_department: string
  due_date?: string
  sort_order?: number
  status: string
  created_at: string
}

export interface OnboardingTaskCreate {
  employee_id: string
  task_name: string
  description?: string
  owner_department: string
  due_date?: string
  sort_order?: number
}

export interface OnboardingTaskBulkItem {
  task_name: string
  description?: string
  owner_department: string
  due_date?: string
  sort_order?: number
}

// ── API methods ──────────────────────────────────────────────────────

// Employees
export const listEmployees = (params?: { department?: string; status?: string }) => {
  const q = new URLSearchParams()
  if (params?.department) q.set("department", params.department)
  if (params?.status) q.set("status", params.status)
  return fetchHR<Employee[]>(`/employees?${q}`)
}

export const createEmployee = (data: EmployeeCreate) =>
  fetchHR<Employee>("/employees", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getEmployee = (id: string) =>
  fetchHR<Employee>(`/employees/${id}`)

export const updateEmployee = (id: string, data: Partial<Employee>) =>
  fetchHR<Employee>(`/employees/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deactivateEmployee = (id: string) =>
  fetchHR<{ status: string }>(`/employees/${id}`, {
    method: "DELETE",
  })

export const linkEmployeeToAgent = (empId: string, agentId: string) =>
  fetchHR<{ status: string }>(`/employees/${empId}/link-call-center?agent_id=${encodeURIComponent(agentId)}`, {
    method: "PUT",
  })

// Leave
export const listLeaveRequests = (empId: string) =>
  fetchHR<LeaveRequest[]>(`/employees/${empId}/leave`)

export const createLeaveRequest = (empId: string, data: LeaveRequestCreate) =>
  fetchHR<LeaveRequest>(`/employees/${empId}/leave`, {
    method: "POST",
    body: JSON.stringify(data),
  })

export const approveLeave = (leaveId: string) =>
  fetchHR<{ status: string }>(`/leave/${leaveId}/approve`, {
    method: "PUT",
  })

export const declineLeave = (leaveId: string) =>
  fetchHR<{ status: string }>(`/leave/${leaveId}/decline`, {
    method: "PUT",
  })

// Performance
export const getEmployeePerformance = (empId: string) =>
  fetchHR<PerformanceReview[]>(`/employees/${empId}/performance`)

export const createPerformanceReview = (empId: string, data: PerformanceReviewCreate) =>
  fetchHR<PerformanceReview>(`/employees/${empId}/performance`, {
    method: "POST",
    body: JSON.stringify(data),
  })

// Schedules
export const listSchedules = (params?: { from_date?: string; to_date?: string; employee_id?: string; department?: string }) => {
  const q = new URLSearchParams()
  if (params?.from_date) q.set("from_date", params.from_date)
  if (params?.to_date) q.set("to_date", params.to_date)
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  if (params?.department) q.set("department", params.department)
  return fetchHR<Schedule[]>(`/schedules?${q}`)
}

export const createSchedule = (data: ScheduleCreate) =>
  fetchHR<Schedule>("/schedules", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const confirmSchedule = (schedId: string) =>
  fetchHR<{ status: string }>(`/schedules/${schedId}/confirm`, {
    method: "PUT",
  })

export const deleteSchedule = (schedId: string) =>
  fetchHR<{ status: string }>(`/schedules/${schedId}`, {
    method: "DELETE",
  })

export const getDemandForecast = (days?: number) => {
  const q = new URLSearchParams()
  if (days != null) q.set("days", String(days))
  return fetchHR<unknown>(`/schedules/demand-forecast?${q}`)
}

// Training
export const listTrainingCourses = (params?: { category?: string }) => {
  const q = new URLSearchParams()
  if (params?.category) q.set("category", params.category)
  return fetchHR<TrainingCourse[]>(`/training/courses?${q}`)
}

export const createTrainingCourse = (data: TrainingCourseCreate) =>
  fetchHR<TrainingCourse>("/training/courses", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const enrollEmployee = (data: { employee_id: string; course_id: string }) =>
  fetchHR<TrainingEnrollment>("/training/enroll", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateTrainingProgress = (enrollmentId: string, progress_pct: number, score?: number) =>
  fetchHR<{ status: string }>(`/training/enrollment/${enrollmentId}/progress`, {
    method: "PUT",
    body: JSON.stringify({ progress_pct, score }),
  })

export const getEmployeeTraining = (empId: string) =>
  fetchHR<TrainingEnrollment[]>(`/employees/${empId}/training`)

// Benefits
export const listBenefits = (params?: { employee_id?: string; benefit_type?: string }) => {
  const q = new URLSearchParams()
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  if (params?.benefit_type) q.set("benefit_type", params.benefit_type)
  return fetchHR<Benefit[]>(`/benefits?${q}`)
}

export const createBenefitEnrollment = (data: BenefitCreate) =>
  fetchHR<Benefit>("/benefits", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getEmployeeBenefits = (empId: string) =>
  fetchHR<Benefit[]>(`/employees/${empId}/benefits`)

// Disciplinary
export const listDisciplinary = (params?: { employee_id?: string; status?: string }) => {
  const q = new URLSearchParams()
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  if (params?.status) q.set("status", params.status)
  return fetchHR<DisciplinaryAction[]>(`/disciplinary?${q}`)
}

export const createDisciplinary = (data: DisciplinaryCreate) =>
  fetchHR<DisciplinaryAction>("/disciplinary", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const resolveDisciplinary = (actionId: string, outcome: string, reviewed_by: string) =>
  fetchHR<{ status: string }>(`/disciplinary/${actionId}/resolve`, {
    method: "PUT",
    body: JSON.stringify({ outcome, reviewed_by }),
  })

// Exits
export const listExits = (params?: { status?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  return fetchHR<ExitRecord[]>(`/exits?${q}`)
}

export const createExit = (data: ExitCreate) =>
  fetchHR<ExitRecord>("/exits", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateExitChecklist = (exitId: string, data: ExitChecklist) =>
  fetchHR<ExitChecklist>(`/exits/${exitId}/checklist`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const getExitChecklist = (exitId: string) =>
  fetchHR<ExitChecklist>(`/exits/${exitId}/checklist`)

// Onboarding
export const getOnboardingTasks = (empId: string) =>
  fetchHR<OnboardingTask[]>(`/onboarding/${empId}`)

export const createOnboardingTask = (data: OnboardingTaskCreate) =>
  fetchHR<OnboardingTask>("/onboarding/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const bulkCreateOnboardingTasks = (
  employee_id: string,
  tasks: OnboardingTaskBulkItem[],
) =>
  fetchHR<OnboardingTask[]>("/onboarding/tasks/bulk", {
    method: "POST",
    body: JSON.stringify({ employee_id, tasks }),
  })

export const completeOnboardingTask = (taskId: string) =>
  fetchHR<{ status: string }>(`/onboarding/tasks/${taskId}/complete`, {
    method: "PUT",
  })

export const getOnboardingProgress = (empId: string) =>
  fetchHR<{ total: number; completed: number; progress_pct: number }>(`/onboarding/${empId}/progress`)

// Analytics
export const getAttritionRisk = () =>
  fetchHR<unknown>("/analytics/attrition-risk")

export const getHeadcountAnalytics = () =>
  fetchHR<unknown>("/analytics/headcount")
