"use client"

/**
 * HR API client — employees, leave, performance, schedules, training,
 * benefits, disciplinary, exits, onboarding, and analytics.
 * Proxies through the Next.js API routes to the HR service (port 8009).
 */

import { getSessionSafe } from "@/lib/supabase/client"

const API_BASE = "/svc/hr"
const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"

async function getTenantId(): Promise<string> {
  const { data } = await getSessionSafe()
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
  manager_id?: string | null
  id_number?: string
  tax_number?: string
  status: string
  created_at: string
  updated_at?: string
  financial_limit?: number
  is_agent?: boolean
  llm_model?: string
}

export interface EmployeeCreate {
  employee_id: string
  full_name: string
  job_title: string
  department: string
  hire_date: string
  email?: string
  phone?: string
  manager_id?: string | null
  id_number?: string
  tax_number?: string
  status?: string
  financial_limit?: number
  is_agent?: boolean
  llm_model?: string
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
  passing_score?: number
  created_at?: string
}

export interface TrainingCourseCreate {
  title: string
  description?: string
  category: string
  duration_hours?: number
  mandatory?: boolean
  passing_score?: number
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
  employee_name?: string
  employee_code?: string
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

export interface KnowledgeArticle {
  id: string
  tenant_id?: string
  title: string
  content: string
  category: string
  tags: string[]
  is_published: boolean
  created_at?: string
  snippet?: string
}

export interface CommissionRule {
  id: string
  tenant_id?: string
  tier_name: string
  product_name: string
  department: string
  min_deals: number
  max_deals?: number | null
  rate_percent: number
  min_threshold_zar: number
  is_active: boolean
  sort_order?: number
  description?: string
  created_at?: string
}

export interface CommissionRecord {
  id: string
  tenant_id?: string
  employee_id?: string
  employee_name?: string
  employee_code?: string
  deal_name?: string
  product_name?: string
  amount_zar: number
  rate_percent: number
  status: string
  created_at?: string
}

export interface PayslipRecord {
  id: string
  run_id: string
  employee_id: string
  employee_name: string
  employee_code: string
  job_title: string
  department: string
  id_number?: string
  tax_number?: string
  bank_code?: string
  account_number?: string
  account_name?: string
  gross: number
  basic_salary: number
  commission: number
  allowances: number
  tax: number
  tax_rebate: number
  annual_taxable: number
  uif: number
  uif_employer: number
  sdl: number
  other_deductions: number
  net: number
  currency: string
  payout_status: string
  paystack_transfer_code?: string
  paystack_reference?: string
  payout_message?: string
  created_at: string
}

export interface SalaryPreviewResult {
  gross_salary: number
  basic_salary: number
  allowances: number
  annual_gross: number
  tax_annual: number
  annual_primary_rebate: number
  monthly_paye_tax: number
  medical_tax_credit: number
  uif_employee_contribution: number
  uif_employer_contribution: number
  sdl_employer_contribution: number
  total_statutory_deductions: number
  total_company_contributions: number
  net_take_home_pay: number
  statutory_compliance: string
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
export const listAllOnboardingTasks = (params?: { employee_id?: string; owner_department?: string; status?: string }) => {
  const q = new URLSearchParams()
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  if (params?.owner_department) q.set("owner_department", params.owner_department)
  if (params?.status) q.set("status", params.status)
  return fetchHR<OnboardingTask[]>(`/onboarding/tasks?${q}`)
}

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

export const deleteOnboardingTask = (taskId: string) =>
  fetchHR<{ status?: string }>(`/onboarding/tasks/${taskId}`, {
    method: "DELETE",
  })

export const getOnboardingProgress = (empId: string) =>
  fetchHR<{ total: number; completed: number; progress_pct: number }>(`/onboarding/${empId}/progress`)

// Analytics
export const getAttritionRisk = () =>
  fetchHR<unknown>("/analytics/attrition-risk")

export const getHeadcountAnalytics = () =>
  fetchHR<unknown>("/analytics/headcount")

// ── Cross-Service Connectors (Sales, Technicians, Marketing, Finance, Compliance, Orchestrator) ──

export interface SalesRepMetric {
  employee_id: string
  employee_code: string
  full_name: string
  job_title: string
  department: string
  deals_count: number
  deals_won_count: number
  deals_won_zar: number
  pipeline_zar: number
  pending_commission_zar: number
  earned_commission_zar: number
  win_rate_pct: number
}

export interface SalesOverviewResponse {
  sales_rep_count: number
  total_pipeline_zar: number
  total_won_zar: number
  total_commissions_pending_zar: number
  total_commissions_paid_zar: number
  top_performers: SalesRepMetric[]
}

export interface VanStockItem {
  product_sku: string
  product_name: string
  quantity: number
  safety_stock: number
  status: string
  unit_cost_zar: number
}

export interface FieldTechnicianProfile {
  employee_id: string
  employee_code: string
  full_name: string
  job_title: string
  department: string
  shift_today?: string
  shift_status?: string
  certifications: string[]
  van_stock: VanStockItem[]
  total_equipment_value_zar: number
  installations_completed: number
  active_work_orders: number
}

export interface MarketingStaffAttribution {
  employee_id: string
  employee_name: string
  job_title: string
  active_campaigns_count: number
  total_budget_managed_zar: number
  total_conversions_delivered: number
  campaign_names: string[]
}

export interface DepartmentCostItem {
  department: string
  headcount: number
  total_salary_zar: number
  pct_of_total: number
}

export interface DepartmentCostAllocation {
  total_active_headcount: number
  total_monthly_payroll_zar: number
  departments: DepartmentCostItem[]
}

export interface StaffComplianceSummary {
  total_staff: number
  popia_certified_count: number
  popia_compliance_pct: number
  rica_accredited_officers_count: number
  rica_verifications_completed: number
  health_and_safety_incidents: number
  foreign_workers_with_permits: number
  expiring_permits_count: number
  bcea_leave_compliance_pct: number
  overall_readiness_score: number
}

export interface OrchestratorWellnessAlert {
  id: string
  employee_name: string
  department: string
  alert_type: string
  severity: string
  message: string
  recommendation: string
}

export const getSalesTalentOverview = () =>
  fetchHR<SalesOverviewResponse>("/cross-service/sales/overview")

export const listSalesRepsMetrics = () =>
  fetchHR<SalesRepMetric[]>("/cross-service/sales/reps")

export const claimSalesCommission = (data: {
  employee_id: string
  commission_id?: string
  amount_zar?: number
  bonus_period?: string
  description?: string
}) =>
  fetchHR<{ status: string; bonus_id?: string; benefit_id?: string; message: string }>("/cross-service/sales/commissions/claim-to-payroll", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const listFieldTechniciansRoster = () =>
  fetchHR<FieldTechnicianProfile[]>("/cross-service/technicians/roster")

export const getMarketingStaffAttribution = () =>
  fetchHR<MarketingStaffAttribution[]>("/cross-service/marketing/attribution")

export const postPayrollRunToFinance = (data?: {
  payroll_run_id?: string
  run_name?: string
  total_gross_zar?: number
  currency?: string
  reference_prefix?: string
}) =>
  fetchHR<{
    status: string
    journal_entry_id: string
    reference: string
    dr_salaries_expense: number
    cr_bank_cash: number
    cr_sars_paye_liability: number
    cr_uif_liability?: number
    message: string
  }>("/cross-service/finance/post-payroll-run", {
    method: "POST",
    body: JSON.stringify(data || {}),
  })

export const getDepartmentCostAllocation = () =>
  fetchHR<DepartmentCostAllocation>("/cross-service/finance/department-cost-allocation")

export const getStaffComplianceAudit = () =>
  fetchHR<StaffComplianceSummary>("/cross-service/compliance/audit")

export const getOrchestratorWellnessInsights = () =>
  fetchHR<OrchestratorWellnessAlert[]>("/cross-service/orchestrator/wellness")

export const executeOrchestratorAction = (alertId: string, actionType?: string, overrideNotes?: string) =>
  fetchHR<{ status: string; alert_id: string; action: string; employee_name: string; message: string }>(
    `/cross-service/orchestrator/wellness/${alertId}/execute`,
    {
      method: "POST",
      body: JSON.stringify({ action_type: actionType, override_notes: overrideNotes }),
    }
  )

// ── Knowledge Base (Markdown, Search, Categories) ─────────────────────

export const listKnowledgeArticles = (params?: { q?: string; category?: string }) => {
  const q = new URLSearchParams()
  if (params?.q) q.set("q", params.q)
  if (params?.category) q.set("category", params.category)
  return fetchHR<KnowledgeArticle[]>(`/cross-service/knowledge-base?${q}`)
}

export const getKnowledgeArticle = (id: string) =>
  fetchHR<KnowledgeArticle>(`/cross-service/knowledge-base/${id}`)

export const createKnowledgeArticle = (data: { title: string; content: string; category?: string; tags?: string[]; is_published?: boolean }) =>
  fetchHR<KnowledgeArticle>("/cross-service/knowledge-base", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateKnowledgeArticle = (id: string, data: Partial<KnowledgeArticle>) =>
  fetchHR<{ id: string; status: string }>(`/cross-service/knowledge-base/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteKnowledgeArticle = (id: string) =>
  fetchHR<{ status?: string }>(`/cross-service/knowledge-base/${id}`, {
    method: "DELETE",
  })

// ── Commission Rules & Transactions Journey ───────────────────────────

export const listCommissionRules = (params?: { department?: string; product_name?: string }) => {
  const q = new URLSearchParams()
  if (params?.department) q.set("department", params.department)
  if (params?.product_name) q.set("product_name", params.product_name)
  return fetchHR<CommissionRule[]>(`/cross-service/sales/commissions/rules?${q}`)
}

export const createCommissionRule = (data: {
  tier_name: string
  product_name?: string
  department?: string
  rate_percent: number
  min_threshold_zar?: number
  min_deals?: number
  max_deals?: number | null
  description?: string
}) =>
  fetchHR<CommissionRule>("/cross-service/sales/commissions/rules", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateCommissionRule = (id: string, data: Partial<CommissionRule>) =>
  fetchHR<{ id: string; status: string }>(`/cross-service/sales/commissions/rules/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const deleteCommissionRule = (id: string) =>
  fetchHR<{ status?: string }>(`/cross-service/sales/commissions/rules/${id}`, {
    method: "DELETE",
  })

export const listCommissionLedger = (params?: { status?: string; employee_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  return fetchHR<CommissionRecord[]>(`/cross-service/sales/commissions/ledger?${q}`)
}

export const createCommissionRecord = (data: {
  employee_id?: string
  deal_name?: string
  product_name?: string
  amount_zar: number
  rate_percent?: number
  status?: string
}) =>
  fetchHR<CommissionRecord>("/cross-service/sales/commissions/ledger", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateCommissionStatus = (commId: string, status: string) =>
  fetchHR<{ id: string; status: string }>(`/cross-service/sales/commissions/ledger/${commId}/status?status=${encodeURIComponent(status)}`, {
    method: "PUT",
  })

export const deleteCommissionRecord = (commId: string) =>
  fetchHR<{ status?: string }>(`/cross-service/sales/commissions/ledger/${commId}`, {
    method: "DELETE",
  })

// ── Payroll & Detailed Payslips (SARS PAYE & UIF) ─────────────────────

export const listPayslips = (params?: { run_id?: string; employee_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.run_id) q.set("run_id", params.run_id)
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  return fetchHR<PayslipRecord[]>(`/payroll/payslips?${q}`)
}

export const getPayslip = (payslipId: string) =>
  fetchHR<PayslipRecord>(`/payroll/payslips/${payslipId}`)

export const calculateSalaryPreview = (data: {
  gross_salary: number
  allowances?: number
  medical_aid_members?: number
}) =>
  fetchHR<SalaryPreviewResult>("/payroll/calculate-preview", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const updateReportingLine = (employeeId: string, managerId: string | null) =>
  fetchHR<Employee>(`/employees/${employeeId}`, {
    method: "PUT",
    body: JSON.stringify({ manager_id: managerId }),
  })

// ── Company & Individual KPI / Objectives Management ───────────────────

export interface SmartLevelCriterion {
  label?: string
  timeline: string
  measurable: string
  requirement: string
}

export interface LiveActualsSourceOption {
  id: string
  label: string
  value: number
  unit: string
  type: "actual" | "percentage"
}

export interface LiveActualsMetric {
  metric_name: string
  current_value: number
  unit: string
  table_source: string
  mode?: string
  /** 'live' = read from a real table, 'unavailable' = source not connected, 'manual' = manually entered */
  source?: "live" | "unavailable" | "manual"
  options?: LiveActualsSourceOption[]
}

export interface LiveActualsResponse {
  sources: {
    sales: LiveActualsMetric
    cost: LiveActualsMetric
    profit: LiveActualsMetric
    support?: LiveActualsMetric
    subscribers?: LiveActualsMetric
    [key: string]: LiveActualsMetric | undefined
  }
  synced_at: string
}

export interface IndividualKPIItem {
  id: string
  title: string
  category: string
  weight_pct: number
  timeline: string
  measurable: string
  requirement: string
  current_level?: number
  score?: number
  source_mode?: "LIVE_TABLE" | "PERCENTAGE" | "MANUAL"
  source_metric_id?: string
  actual_value?: number
  target_value?: number
  unit?: string
  smart_criteria?: {
    level_1: SmartLevelCriterion
    level_2: SmartLevelCriterion
    level_3: SmartLevelCriterion
    level_4: SmartLevelCriterion
    level_5: SmartLevelCriterion
  }
}

export interface CompanyKPIConfig {
  id: string
  fiscal_year: string
  sales_budget_zar: number
  sales_actual_zar: number
  sales_achievement_pct: number
  cost_budget_zar: number
  cost_actual_zar: number
  cost_efficiency_pct: number
  profit_budget_zar: number
  profit_actual_zar: number
  profit_achievement_pct: number
  company_shared_score_pct: number
  /** Backend-computed corporate attainment index (preferred over any local formula) */
  corporate_attainment_index?: number
  values_weight_pct: number
  values_description: string
  level_weights: {
    EXECUTIVE: number
    DIRECTOR: number
    MANAGER: number
    STAFF: number
    [key: string]: number
  }
  sales_source_mode?: "LIVE_TABLE" | "PERCENTAGE" | "MANUAL"
  cost_source_mode?: "LIVE_TABLE" | "PERCENTAGE" | "MANUAL"
  profit_source_mode?: "LIVE_TABLE" | "PERCENTAGE" | "MANUAL"
  sales_source_option_id?: string
  cost_source_option_id?: string
  profit_source_option_id?: string
}

export interface EmployeeKPISheet {
  id: string
  employee_id: string
  employee_name?: string
  job_title?: string
  department?: string
  fiscal_year: string
  position_level: "EXECUTIVE" | "DIRECTOR" | "MANAGER" | "STAFF" | string
  company_shared_weight_pct: number
  values_weight_pct: number
  individual_target_weight_pct: number
  total_weight_pct: number
  status: "DRAFT" | "SUBMITTED" | "APPROVED" | "CALIBRATED" | string
  kpis: IndividualKPIItem[]
  overall_score?: number | null
  reviewer_notes?: string | null
  company_benchmarks?: Partial<CompanyKPIConfig>
}

export interface AISmartCriteriaResult {
  title: string
  job_title: string
  department: string
  suggested_measurable: string
  suggested_timeline: string
  suggested_requirement: string
  smart_criteria: {
    level_1: SmartLevelCriterion
    level_2: SmartLevelCriterion
    level_3: SmartLevelCriterion
    level_4: SmartLevelCriterion
    level_5: SmartLevelCriterion
  }
}

export const getCompanyKPIConfig = () =>
  fetchHR<CompanyKPIConfig>("/kpis/company")

export const updateCompanyKPIConfig = (data: Partial<CompanyKPIConfig>) =>
  fetchHR<CompanyKPIConfig>("/kpis/company", {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const cascadeSharedKPIs = (fiscalYear: string = "FY 2026/2027") =>
  fetchHR<{
    success: boolean
    employees_cascaded: number
    fiscal_year: string
    level_weights_applied: Record<string, number>
    values_weight_pct: number
  }>("/kpis/cascade", {
    method: "POST",
    body: JSON.stringify({ fiscal_year: fiscalYear }),
  })

export const getEmployeeKPISheet = (empId: string) =>
  fetchHR<EmployeeKPISheet>(`/employees/${empId}/kpi-sheet`)

export const updateEmployeeKPISheet = (empId: string, data: Partial<EmployeeKPISheet>) =>
  fetchHR<{
    success: boolean
    sheet_id: string
    status: string
    total_weight_pct: number
    overall_score?: number | null
  }>(`/employees/${empId}/kpi-sheet`, {
    method: "PUT",
    body: JSON.stringify(data),
  })

export const generateAISmartCriteria = (data: {
  title: string
  category?: string
  job_title?: string
  department?: string
}) =>
  fetchHR<AISmartCriteriaResult>("/kpis/ai-smart-generate", {
    method: "POST",
    body: JSON.stringify(data),
  })

export const getKpisLiveActuals = () =>
  fetchHR<LiveActualsResponse>("/kpis/live-actuals")




export interface CorporateSalesSnapshot {
  budget: number | null
  actual: number | null
  achievementPct: number | null
  varianceZar: number | null
}

/**
 * Corporate sales actual vs target budget for dashboard tiles.
 * Any value that is not backed by a connected source is returned as null
 * so callers can show "Not connected" instead of a number.
 */
export async function getCorporateSalesSnapshot(): Promise<CorporateSalesSnapshot> {
  const [cfg, live] = await Promise.all([
    getCompanyKPIConfig().catch(() => null),
    getKpisLiveActuals().catch(() => null),
  ])
  const budgetRaw = cfg ? Number(cfg.sales_budget_zar) : NaN
  const budget = Number.isFinite(budgetRaw) && budgetRaw > 0 ? budgetRaw : null
  const sales = live?.sources?.sales
  const actualRaw = sales && sales.source !== "unavailable" ? Number(sales.current_value) : NaN
  const actual = Number.isFinite(actualRaw) ? actualRaw : null
  if (budget === null || actual === null) {
    return { budget, actual, achievementPct: null, varianceZar: null }
  }
  return {
    budget,
    actual,
    achievementPct: (actual / budget) * 100,
    varianceZar: actual - budget,
  }
}
