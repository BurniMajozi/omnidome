"use client"

/**
 * Compliance API client — Full compliance management for SA telecom operators.
 * Proxies through Next.js API routes to the Compliance service (port 8019).
 */

const API_BASE = "/svc/compliance"
const TENANT_ID = "00000000-0000-0000-0000-000000000001"

async function fetchCompliance<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: { "x-tenant-id": TENANT_ID, "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new Error(`Compliance API error ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────

export interface ComplianceOverview {
  overall_score: number
  categories: { name: string; score: number; status: string; issues: number; critical: number }[]
  expiring_contracts: number
  overdue_dsar: number
  open_breaches: number
  pending_obligations: number
  tax_overdue: number
  hs_open_incidents: number
  bbbee_level: string
  funding_matched: number
}

export interface Contract {
  id: number
  contract_number: string
  title: string
  contract_type: string
  status: string
  counterparty_name: string
  effective_date: string
  expiry_date: string
  value_zar: number
  compliance_score: number
  risk_rating: string
  tenant_id: string
}

export interface ContractSLA {
  id: number
  contract_id: number
  name: string
  metric: string
  target_value: number
  unit: string
  is_active: boolean
}

export interface TaxReturn {
  id: number
  tax_type: string
  period_start: string
  period_end: string
  status: string
  amount_payable: number
  submission_date: string
}

export interface HsIncident {
  id: number
  incident_number: string
  incident_type: string
  severity: string
  incident_date: string
  description: string
  status: string
  coida_reported: boolean
}

export interface BbbeeScorecard {
  id: number
  financial_year: string
  overall_level: string
  overall_score: number
  ownership_score: number
  management_control_score: number
  skills_development_score: number
  enterprise_supplier_dev_score: number
  socio_economic_dev_score: number
  certificate_number: string
  certificate_expiry_date: string
  is_verified: boolean
}

export interface LeaveApplication {
  id: number
  employee_id: string
  employee_name: string
  leave_type: string
  status: string
  start_date: string
  end_date: string
  days_requested: number
  approver_name: string
}

export interface VehicleRegistration {
  id: number
  registration_number: string
  make: string
  model: string
  status: string
  license_expiry: string
  insurance_expiry: string
  assigned_driver: string
}

export interface ForeignWorkerPermit {
  id: number
  employee_id: string
  employee_name: string
  nationality: string
  permit_type: string
  status: string
  expiry_date: string
}

export interface TravelReadiness {
  id: number
  employee_id: string
  employee_name: string
  destination_country: string
  visa_type: string
  visa_status: string
  departure_date: string
  overall_status: string
}

export interface DrBcpPlan {
  id: number
  plan_name: string
  plan_type: string
  status: string
  rto_hours: number
  rpo_hours: number
  last_test_date: string
  next_test_date: string
}

export interface ComplianceScore {
  id: number
  category: string
  score: number
  status: string
  issues_count: number
  critical_issues: number
  calculated_at: string
}

export interface EserviceSubmission {
  id: number
  platform: string
  form_name: string
  status: string
  submission_date: string
  reference_number: string
}

export interface FinancialScenario {
  id: number
  name: string
  scenario_type: string
  period_start: string
  period_end: string
  compliance_cost_impact: number
  is_active: boolean
}

export interface IcasaSubmission {
  id: number
  submission_type: string
  title: string
  status: string
  submission_date: string
  icasa_reference: string
}

export interface PopiDsar {
  id: number
  request_reference: string
  data_subject_name: string
  request_type: string
  status: string
  due_date: string
  received_date: string
}

export interface BreachRegister {
  id: number
  breach_number: string
  title: string
  category: string
  severity: string
  status: string
  identified_date: string
  icasa_notified: boolean
  popi_commission_notified: boolean
  financial_impact: number
}

export interface FundingOpportunity {
  id: number
  name: string
  source: string
  funding_type: string
  max_funding_amount: number
  min_compliance_score: number
  required_bbbee_level: string
  application_deadline: string
  status: string
}

export interface ComplianceObligation {
  id: number
  category: string
  title: string
  status: string
  due_date: string
  responsible_person: string
  responsible_department: string
}

// ── Overview Dashboard ─────────────────────────────────────────────────

export async function getComplianceOverview(): Promise<ComplianceOverview> {
  const [scores, contracts, dsar, breaches, obligations, tax, hs, funding] = await Promise.all([
    fetchCompliance<{ items: ComplianceScore[] }>("/scores/"),
    fetchCompliance<{ items: Contract[]; cutoff: string }>("/contracts/dashboard/expiring?days=90"),
    fetchCompliance<{ total: number; overdue: number; pending: number; completed: number }>("/popi/dsar/dashboard"),
    fetchCompliance<{ total: number; open: number; critical: number }>("/breaches/dashboard"),
    fetchCompliance<{ items: ComplianceObligation[] }>("/scores/obligations?status=pending_review"),
    fetchCompliance<{ overdue: number; pending: number }>("/tax/dashboard"),
    fetchCompliance<{ open: number; critical: number }>("/health-safety/dashboard"),
    fetchCompliance<{ items: FundingOpportunity[] }>("/funding/?status=identified"),
  ])

  const categories = scores.items.map((s) => ({
    name: s.category,
    score: s.score,
    status: s.status,
    issues: s.issues_count,
    critical: s.critical_issues,
  }))

  const overall_score = categories.length > 0
    ? Math.round(categories.reduce((sum, c) => sum + c.score, 0) / categories.length)
    : 0

  return {
    overall_score,
    categories,
    expiring_contracts: contracts.items?.length ?? 0,
    overdue_dsar: dsar.overdue ?? 0,
    open_breaches: breaches.open ?? 0,
    pending_obligations: obligations.items?.length ?? 0,
    tax_overdue: tax.overdue ?? 0,
    hs_open_incidents: hs.open ?? 0,
    bbbee_level: "pending",
    funding_matched: funding.items?.length ?? 0,
  }
}

// ── Contracts & SLAs ───────────────────────────────────────────────────

export async function listContracts(params?: { contract_type?: string; status?: string; page?: number }) {
  const q = new URLSearchParams()
  if (params?.contract_type) q.set("contract_type", params.contract_type)
  if (params?.status) q.set("status", params.status)
  if (params?.page) q.set("page", String(params.page))
  return fetchCompliance<{ items: Contract[]; page: number }>(`/contracts/?${q}`)
}

export async function getContract(id: number) {
  return fetchCompliance<Contract>(`/contracts/${id}`)
}

export async function createContract(body: Partial<Contract>) {
  return fetchCompliance<Contract>("/contracts/", { method: "POST", body: JSON.stringify(body) })
}

export async function updateContract(id: number, body: Partial<Contract>) {
  return fetchCompliance<Contract>(`/contracts/${id}`, { method: "PUT", body: JSON.stringify(body) })
}

export async function getContractSLAs(contractId: number) {
  return fetchCompliance<{ items: ContractSLA[] }>(`/contracts/${contractId}/slas`)
}

export async function getExpiringContracts(days = 90) {
  return fetchCompliance<{ items: Contract[]; cutoff: string }>(`/contracts/dashboard/expiring?days=${days}`)
}

// ── Tax Compliance ─────────────────────────────────────────────────────

export async function listTaxReturns(params?: { tax_type?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.tax_type) q.set("tax_type", params.tax_type)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: TaxReturn[] }>(`/tax/returns?${q}`)
}

export async function getTaxDashboard() {
  return fetchCompliance<{ total: number; overdue: number; pending: number; submitted: number; total_payable: number }>("/tax/dashboard")
}

export async function submitTaxReturn(id: number) {
  return fetchCompliance<{ status: string; id: number }>(`/tax/returns/${id}/submit`, { method: "PUT" })
}

// ── Health & Safety ────────────────────────────────────────────────────

export async function listHsIncidents(params?: { severity?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.severity) q.set("severity", params.severity)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: HsIncident[] }>(`/health-safety/incidents?${q}`)
}

export async function getHsDashboard() {
  return fetchCompliance<{ total: number; open: number; critical: number; coida_reported: number }>("/health-safety/dashboard")
}

export async function createHsIncident(body: Partial<HsIncident>) {
  return fetchCompliance<HsIncident>("/health-safety/incidents", { method: "POST", body: JSON.stringify(body) })
}

// ── BBBEE ──────────────────────────────────────────────────────────────

export async function listBbbeeScorecards() {
  return fetchCompliance<{ items: BbbeeScorecard[] }>("/bbbee/scorecards")
}

export async function calculateBbbeeScore(body: {
  ownership_score: number
  management_control_score: number
  skills_development_score: number
  enterprise_supplier_dev_score: number
  socio_economic_dev_score: number
}) {
  return fetchCompliance<{
    overall_score: number
    overall_level: string
    element_scores: Record<string, number>
    weights: Record<string, number>
  }>("/bbbee/scorecards/calculate", { method: "POST", body: JSON.stringify(body) })
}

// ── Leave Management ───────────────────────────────────────────────────

export async function listLeaveApplications(params?: { employee_id?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: LeaveApplication[] }>(`/leave/applications?${q}`)
}

export async function approveLeave(id: number, body: { approver_id?: string; approver_name?: string; days_approved?: number }) {
  return fetchCompliance<{ status: string; id: number }>(`/leave/applications/${id}/approve`, { method: "PUT", body: JSON.stringify(body) })
}

export async function rejectLeave(id: number, body: { rejection_reason?: string }) {
  return fetchCompliance<{ status: string; id: number }>(`/leave/applications/${id}/reject`, { method: "PUT", body: JSON.stringify(body) })
}

// ── Vehicles ───────────────────────────────────────────────────────────

export async function listVehicles(params?: { status?: string }) {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: VehicleRegistration[] }>(`/vehicles/?${q}`)
}

export async function getExpiringVehicles(days = 30) {
  return fetchCompliance<{ items: VehicleRegistration[] }>(`/vehicles/dashboard/expiring?days=${days}`)
}

// ── Foreign Workers ────────────────────────────────────────────────────

export async function listForeignWorkers(params?: { status?: string }) {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: ForeignWorkerPermit[] }>(`/foreign-workers/?${q}`)
}

export async function getExpiringPermits(days = 60) {
  return fetchCompliance<{ items: ForeignWorkerPermit[] }>(`/foreign-workers/dashboard/expiring?days=${days}`)
}

// ── Travel Readiness ───────────────────────────────────────────────────

export async function listTravelReadiness(params?: { employee_id?: string }) {
  const q = new URLSearchParams()
  if (params?.employee_id) q.set("employee_id", params.employee_id)
  return fetchCompliance<{ items: TravelReadiness[] }>(`/travel/?${q}`)
}

// ── DR/BCP ─────────────────────────────────────────────────────────────

export async function listDrBcpPlans(params?: { plan_type?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.plan_type) q.set("plan_type", params.plan_type)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: DrBcpPlan[] }>(`/dr-bcp/plans?${q}`)
}

export async function getDrBcpDashboard() {
  return fetchCompliance<{ total: number; tested: number; approved: number; failed: number }>("/dr-bcp/dashboard")
}

// ── Compliance Scoring ─────────────────────────────────────────────────

export async function listComplianceScores(params?: { category?: string }) {
  const q = new URLSearchParams()
  if (params?.category) q.set("category", params.category)
  return fetchCompliance<{ items: ComplianceScore[] }>(`/scores/?${q}`)
}

export async function calculateAllScores() {
  return fetchCompliance<{ scores: { category: string; score: number; status: string }[]; calculated_at: string }>("/scores/calculate", { method: "POST" })
}

export async function listObligations(params?: { category?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.category) q.set("category", params.category)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: ComplianceObligation[] }>(`/scores/obligations?${q}`)
}

// ── e-Services ─────────────────────────────────────────────────────────

export async function listEserviceSubmissions(params?: { platform?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.platform) q.set("platform", params.platform)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: EserviceSubmission[] }>(`/eservices/submissions?${q}`)
}

export async function submitEserviceForm(id: number) {
  return fetchCompliance<{ status: string; id: number; platform: string }>(`/eservices/submissions/${id}/submit`, { method: "POST" })
}

export async function getEservicePlatforms() {
  return fetchCompliance<{ platforms: string[] }>("/eservices/platforms")
}

// ── Financial Scenarios ────────────────────────────────────────────────

export async function listFinancialScenarios(params?: { scenario_type?: string }) {
  const q = new URLSearchParams()
  if (params?.scenario_type) q.set("scenario_type", params.scenario_type)
  return fetchCompliance<{ items: FinancialScenario[] }>(`/financial-scenarios/?${q}`)
}

// ── ICASA ──────────────────────────────────────────────────────────────

export async function listIcasaSubmissions(params?: { submission_type?: string; status?: string }) {
  const q = new URLSearchParams()
  if (params?.submission_type) q.set("submission_type", params.submission_type)
  if (params?.status) q.set("status", params.status)
  return fetchCompliance<{ items: IcasaSubmission[] }>(`/icasa/submissions?${q}`)
}

export async function createIcasaSubmission(body: Partial<IcasaSubmission>) {
  return fetchCompliance<IcasaSubmission>("/icasa/submissions", { method: "POST", body: JSON.stringify(body) })
}

// ── POPI ───────────────────────────────────────────────────────────────

export async function listDsar(params?: { status?: string }) {
  return fetchCompliance<{ items: PopiDsar[] }>(`/popi/dsar?${params?.status ? `status=${params.status}` : ""}`)
}

export async function getDsarDashboard() {
  return fetchCompliance<{ total: number; overdue: number; pending: number; completed: number }>("/popi/dsar/dashboard")
}

export async function createDsar(body: Partial<PopiDsar>) {
  return fetchCompliance<PopiDsar>("/popi/dsar", { method: "POST", body: JSON.stringify(body) })
}

// ── Breaches ───────────────────────────────────────────────────────────

export async function listBreaches(params?: { severity?: string; status?: string; category?: string }) {
  const q = new URLSearchParams()
  if (params?.severity) q.set("severity", params.severity)
  if (params?.status) q.set("status", params.status)
  if (params?.category) q.set("category", params.category)
  return fetchCompliance<{ items: BreachRegister[] }>(`/breaches/?${q}`)
}

export async function getBreachDashboard() {
  return fetchCompliance<{ total: number; open: number; critical: number; icasa_notified: number; popi_notified: number; total_financial_impact: number }>("/breaches/dashboard")
}

export async function createBreach(body: Partial<BreachRegister>) {
  return fetchCompliance<BreachRegister>("/breaches/", { method: "POST", body: JSON.stringify(body) })
}

// ── Funding ────────────────────────────────────────────────────────────

export async function listFundingOpportunities(params?: { status?: string; funding_type?: string }) {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.funding_type) q.set("funding_type", params.funding_type)
  return fetchCompliance<{ items: FundingOpportunity[] }>(`/funding/?${q}`)
}

export async function matchFundingByScore(minScore: number) {
  return fetchCompliance<{ items: FundingOpportunity[]; min_score: number }>(`/funding/match?min_score=${minScore}`)
}

// ── CIPC ───────────────────────────────────────────────────────────────

export async function listCipcFilings() {
  return fetchCompliance<{ items: { id: number; filing_type: string; status: string; due_date: string }[] }>("/cipc/filings")
}

// ── Bylaw ──────────────────────────────────────────────────────────────

export async function listBylawObligations(params?: { municipality?: string }) {
  const q = new URLSearchParams()
  if (params?.municipality) q.set("municipality", params.municipality)
  return fetchCompliance<{ items: { id: number; municipality: string; title: string; status: string }[] }>(`/bylaw/obligations?${q}`)
}
