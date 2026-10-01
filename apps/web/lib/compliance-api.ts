"use client"

/**
 * Compliance API client — Full compliance management for SA telecom operators.
 * Proxies through Next.js API routes to the Compliance service (port 8019).
 */

import { extractErrorDetail } from "@/lib/compliance-state"

// Route handler at app/svc/compliance/[...path]/route.ts strips "/svc/compliance/"
// and forwards the rest to the backend. All backend routes live under /api/v1/.
// Identity (tenant, user, roles) is injected server-side from the verified
// session by proxy.ts: the client never sends a tenant id, and the backend
// ignores any tenant_id supplied by the client.
const API_BASE = "/svc/compliance/api/v1"

async function fetchCompliance<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init?.body instanceof FormData
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(isForm ? 60_000 : 15_000),
      // Never set Content-Type for FormData: the browser adds the multipart boundary.
      headers: isForm ? undefined : { "Content-Type": "application/json" },
      ...init,
    })
  } catch (err) {
    // Network failure / timeout: status null => "Service not running".
    throw new ComplianceApiError(null, err instanceof Error ? err.message : "unreachable")
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new ComplianceApiError(res.status, body)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

/**
 * Carries the HTTP status so the UI can tell "service not running" from
 * "error", and the server's own message (`detail`) so validation / SSRF
 * rejections can be shown verbatim.
 */
export class ComplianceApiError extends Error {
  status: number | null
  detail: string
  constructor(status: number | null, body: string) {
    const detail = status === null ? "" : extractErrorDetail(body)
    super(
      status === null
        ? `Compliance API unreachable: ${body}`
        : detail || `Compliance API error ${status}`,
    )
    this.name = "ComplianceApiError"
    this.status = status
    this.detail = detail
  }
}

// ── Types ─────────────────────────────────────────────────────────────

export interface ComplianceOverview {
  /** null = not assessed (no obligations/data to score). Never default to 100. */
  overall_score: number | null
  categories: { name: string; score: number | null; status: string; issues: number; critical: number }[]
  expiring_contracts: number
  overdue_dsar: number
  open_breaches: number
  pending_obligations: number
  tax_overdue: number
  hs_open_incidents: number
  bbbee_level: string | null
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
  /** null = not assessed. */
  score: number | null
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
  // Single aggregated endpoint — avoids 8 parallel round-trips.
  // Note: API_BASE already includes /api/v1, but the overview endpoint is
  // registered at /api/v1/dashboard/overview on the compliance service.
  return fetchCompliance<ComplianceOverview>("/dashboard/overview")
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

// ── Document Upload & Understanding ─────────────────────────────────────

export interface DocumentUploadResult {
  status: string
  document_id: number
  understanding: {
    doc_id: string
    title: string
    source: string
    format: string
    document_type: string
    compliance_category: string
    confidence: number
    page_count: number
    file_size_bytes: number
    content_hash: string
    entities: { label: string; value: string; confidence: number }[]
    financials: { amount: number; currency: string; line_item: string; context: string }[]
    links: { url: string; anchor: string; type: string }[]
    dates: string[]
    references: string[]
    markdown_preview: string
    processing_time_ms: number
    errors: string[]
  }
}

export interface UrlFetchResult {
  status: string
  url: string
  crawl: boolean
  documents_found: number
  documents: {
    document_id: number
    source: string
    format: string
    document_type: string
    confidence: number
    entities_count: number
    links_count: number
    processing_time_ms: number
  }[]
}

export interface DocumentRecord {
  id: number
  title: string
  document_type: string
  file_path: string
  file_size: number
  mime_type: string
  contract_id: number | null
  tags: string
  uploaded_by: string
  created_at: string | null
  ocr_text?: string
  extracted_data?: Record<string, unknown>
  financial_summary?: Record<string, unknown>
}

export async function uploadDocument(
  file: File,
  options?: { docTypeHint?: string; contractId?: number; process?: boolean },
): Promise<DocumentUploadResult> {
  const formData = new FormData()
  formData.append("file", file)
  if (options?.docTypeHint) formData.append("doc_type_hint", options.docTypeHint)
  if (options?.contractId) formData.append("contract_id", String(options.contractId))
  if (options?.process !== undefined) formData.append("process", String(options.process))

  // Server validation errors surface verbatim via ComplianceApiError.detail.
  return fetchCompliance<DocumentUploadResult>("/documents/upload", { method: "POST", body: formData })
}

export async function fetchUrlDocument(
  url: string,
  options?: { docTypeHint?: string; crawl?: boolean; maxDepth?: number },
): Promise<UrlFetchResult> {
  const formData = new FormData()
  formData.append("url", url)
  if (options?.docTypeHint) formData.append("doc_type_hint", options.docTypeHint)
  if (options?.crawl !== undefined) formData.append("crawl", String(options.crawl))
  if (options?.maxDepth !== undefined) formData.append("max_depth", String(options.maxDepth))

  // SSRF / validation rejections (400/422) surface verbatim via ComplianceApiError.detail.
  return fetchCompliance<UrlFetchResult>("/documents/fetch-url", { method: "POST", body: formData })
}

export async function listDocuments(params?: {
  documentType?: string
  contractId?: number
  page?: number
  pageSize?: number
}) {
  const q = new URLSearchParams()
  if (params?.documentType) q.set("document_type", params.documentType)
  if (params?.contractId) q.set("contract_id", String(params.contractId))
  if (params?.page) q.set("page", String(params.page))
  if (params?.pageSize) q.set("page_size", String(params.pageSize))
  return fetchCompliance<{ items: DocumentRecord[]; page: number; page_size: number }>(`/documents/?${q}`)
}

export async function getDocumentDetail(docId: number): Promise<DocumentRecord> {
  return fetchCompliance<DocumentRecord>(`/documents/${docId}`)
}

export async function reprocessDocument(docId: number, docTypeHint?: string) {
  const q = new URLSearchParams()
  if (docTypeHint) q.set("doc_type_hint", docTypeHint)
  return fetchCompliance<{ status: string; document_id: number; entities_found: number }>(
    `/documents/${docId}/reprocess?${q}`,
    { method: "POST" },
  )
}

export async function linkDocumentToContract(docId: number, contractId: number) {
  const formData = new FormData()
  formData.append("contract_id", String(contractId))
  return fetchCompliance<{ status: string; document_id: number; contract_id: number }>(
    `/documents/${docId}/link-contract`,
    { method: "POST", body: formData },
  )
}

export async function getDocumentStats() {
  return fetchCompliance<{
    total_documents: number
    by_type: Record<string, number>
    with_financials: number
    with_entities: number
    total_size_bytes: number
  }>("/documents/stats/summary")
}

// ═══════════════════════════════════════════════════════════════════════════
// CROSS-SERVICE INTEGRATION CLIENT: Full South African Telecom Ecosystem
// ═══════════════════════════════════════════════════════════════════════════

export interface ComplianceContractSlaItem {
  contract_id: number
  contract_number: string
  title: string
  counterparty: string
  contract_type: string
  status: string
  annual_value_zar: number
  effective_date: string
  expiry_date: string
  days_to_expiry: number
  uptime_sla_pct: number
  mttr_target_hours: number
  fica_status: string
}

export interface SalesContractsSlaResponse {
  total_contracts: number
  active_contracts_count: number
  total_portfolio_value_zar: number
  expiring_soon_count: number
  average_sla_uptime_pct: number
  fica_verified_pct: number
  contracts: ComplianceContractSlaItem[]
}

export interface VetCustomerFicaInput {
  company_name: string
  registration_number: string
  director_name: string
  director_id_number: string
  vat_number?: string
  physical_address?: string
  contact_email?: string
}

export interface VetCustomerFicaResult {
  status: string
  fica_certificate_id: string
  verification_status: string
  company_name: string
  registration_number: string
  director_validated: boolean
  aml_sanctions_clear: boolean
  cipc_registered: boolean
  timestamp: string
  message: string
}

export interface FleetVehicleItem {
  id: number
  registration_number: string
  vehicle_type: string
  assigned_technician_name: string
  make_model: string
  license_disc_expiry: string
  days_to_license_expiry: number
  roadworthy_status: string
  tracking_unit_active: boolean
  last_safety_inspection: string
}

export interface SafetyIncidentItem {
  id: number
  incident_number: string
  incident_type: string
  severity: string
  incident_date: string
  description: string
  status: string
  coida_reported: boolean
}

export interface TechnicianSafetyAuditResponse {
  total_fleet_vehicles: number
  roadworthy_compliant_count: number
  expiring_license_discs_30d: number
  zero_incident_streak_days: number
  coida_reportable_accidents_ytd: number
  working_at_heights_certified_count: number
  optical_laser_safety_certified_count: number
  vehicles: FleetVehicleItem[]
  recent_incidents: SafetyIncidentItem[]
}

export interface LogHsIncidentInput {
  incident_type: string
  severity: string
  description: string
  incident_date?: string
  employee_involved?: string
  location?: string
}

export interface LogHsIncidentResult {
  status: string
  incident_number: string
  coida_reporting_required: boolean
  statutory_form: string
  investigation_due_date: string
  message: string
}

export interface StatutoryTaxObligation {
  tax_type: string
  period: string
  due_date: string
  status: string
  amount_payable_zar: number
  reference_number: string
}

export interface StatutoryStatusResponse {
  cipc_annual_returns_status: string
  cipc_next_filing_deadline: string
  sars_tax_clearance_status: string
  sars_pin_expiry: string
  bbbee_contributor_level: string
  bbbee_procurement_recognition_pct: number
  bbbee_valid_until: string
  popia_statutory_liability_mitigation_score_pct: number
  tax_obligations: StatutoryTaxObligation[]
}

export interface DsarItem {
  id: number
  request_number: string
  request_type: string
  requester_name: string
  requester_email: string
  status: string
  received_date: string
  due_date: string
  days_remaining: number
}

export interface PopiaAuditResponse {
  voice_recording_consent_rate_pct: number
  total_calls_monitored_month: number
  active_dsar_requests_count: number
  overdue_dsar_count: number
  registered_information_officer: string
  regulator_registration_number: string
  open_data_breaches_count: number
  requests: DsarItem[]
}

export interface CreateDsarInput {
  request_type: string
  requester_name: string
  requester_email: string
  requester_phone?: string
  description: string
}

export interface CreateDsarResult {
  status: string
  request_number: string
  statutory_response_deadline: string
  days_allowed: number
  message: string
}

export interface RicaSubscriberAuditResponse {
  total_active_subscribers: number
  verified_subscribers_count: number
  verified_pct: number
  unverified_quarantine_count: number
  sa_smart_id_verified_count: number
  foreign_passport_permit_count: number
  green_barcode_book_count: number
  biometric_smileid_verified_pct: number
  average_audit_latency_ms: number
}

export interface ComplianceAlertItem {
  id: string
  category: string
  severity: string
  title: string
  description: string
  deadline?: string
  recommended_action: string
}

export interface ExecutiveComplianceSummaryResponse {
  /** null = not assessed. */
  overall_compliance_score: number | null
  /** Server-reported only; null when not assessed. */
  audit_readiness_level: string | null
  critical_statutory_deadlines_30d: number
  pillars_assessed_count: number
  icasa_regulatory_alerts_count: number
  alerts: ComplianceAlertItem[]
}

// ── Cross-Service Connector Methods ──────────────────────────────────────────

export async function getComplianceSalesSla(): Promise<SalesContractsSlaResponse> {
  return fetchCompliance<SalesContractsSlaResponse>("/cross-service/sales/contracts-sla")
}

export async function vetCustomerFica(payload: VetCustomerFicaInput): Promise<VetCustomerFicaResult> {
  return fetchCompliance<VetCustomerFicaResult>("/cross-service/sales/vet-customer-fica", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getTechnicianFleetSafety(): Promise<TechnicianSafetyAuditResponse> {
  return fetchCompliance<TechnicianSafetyAuditResponse>("/cross-service/technicians/fleet-safety")
}

export async function logTechnicianSafetyIncident(payload: LogHsIncidentInput): Promise<LogHsIncidentResult> {
  return fetchCompliance<LogHsIncidentResult>("/cross-service/technicians/incident-log", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getFinanceStatutoryStatus(): Promise<StatutoryStatusResponse> {
  return fetchCompliance<StatutoryStatusResponse>("/cross-service/finance/statutory-status")
}

export async function getCallCenterPopiaAudit(): Promise<PopiaAuditResponse> {
  return fetchCompliance<PopiaAuditResponse>("/cross-service/call-center/popia-audit")
}

export async function createCallCenterDsar(payload: CreateDsarInput): Promise<CreateDsarResult> {
  return fetchCompliance<CreateDsarResult>("/cross-service/call-center/dsar-log", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getRicaSubscriberAudit(): Promise<RicaSubscriberAuditResponse> {
  return fetchCompliance<RicaSubscriberAuditResponse>("/cross-service/rica/subscriber-audit")
}

export async function getExecutiveComplianceSummary(): Promise<ExecutiveComplianceSummaryResponse> {
  return fetchCompliance<ExecutiveComplianceSummaryResponse>("/cross-service/orchestrator/executive-summary")
}

// ── Statutory Payroll, SARS EMP201, UIF & Labor Compliance ───────────────────

export interface Emp201ReturnItem {
  id?: number
  period: string
  due_date?: string | null
  paye_zar?: number | null
  uif_zar?: number | null
  sdl_zar?: number | null
  total_payable_zar?: number | null
  /** PREPARED_NOT_FILED until the user records the real eFiling receipt (then FILED). */
  status: string
  prn?: string | null
  prepared_at?: string | null
  prepared_by?: string | null
  filed_at?: string | null
  filed_by?: string | null
  marked_filed_at?: string | null
  note?: string | null
}

/** Every figure may be null: null = no real payroll data, never a placeholder. */
export interface StatutoryPayrollSummaryResponse {
  period: string | null
  total_employees?: number | null
  gross_remuneration_zar?: number | null
  paye_withheld_zar?: number | null
  uif_employee_zar?: number | null
  uif_employer_zar?: number | null
  sdl_zar?: number | null
  total_emp201_liability_zar?: number | null
  net_salaries_disbursed_zar?: number | null
  sars_tcc_pin?: string | null
  sars_tcc_status?: string | null
  sars_prn?: string | null
  emp501_reconciliation_status?: string | null
  emp501_variance_zar?: number | null
  /** false = PAYE/UIF/SDL rates have not been verified against SARS tables. */
  rates_verified?: boolean
  recent_emp201_returns?: Emp201ReturnItem[]
}

export interface PrepareEmp201Input {
  period: string
}

export interface PrepareEmp201Result {
  id?: number
  status: string
  period: string
  paye_zar?: number | null
  uif_zar?: number | null
  sdl_zar?: number | null
  total_payable_zar?: number | null
  payslips_count?: number | null
  rates_verified?: boolean
  note?: string | null
  prepared_at?: string | null
  message?: string | null
}

export interface MarkEmp201FiledInput {
  prn: string
  /** YYYY-MM-DD the user filed on SARS eFiling. */
  filed_at: string
}

export interface MarkEmp201FiledResult {
  id?: number
  status: string
  period?: string
  prn?: string | null
  filed_at?: string | null
  filed_by?: string | null
  marked_filed_at?: string | null
}

export interface UifDeclarationItem {
  employee_id: string
  employee_code: string
  full_name: string
  id_number: string
  tax_number: string
  department: string
  job_title: string
  gross_remuneration_zar: number
  uif_remuneration_zar: number
  hours_worked_month: number
  employee_uif_zar: number
  employer_uif_zar: number
  total_uif_zar: number
  employment_status: string
  uif_declaration_status: string
}

export interface UifDeclarationsResponse {
  period: string
  uif_employer_reference: string
  total_contributors: number
  total_monthly_remittance_zar: number
  ufiling_batch_reference: string
  ufiling_status: string
  last_submission_date: string
  employees: UifDeclarationItem[]
}

export interface LaborAuditFinding {
  standard: string
  category: string
  compliant: boolean
  status_label: string
  details: string
  remediation?: string | null
}

export interface LaborComplianceAuditResponse {
  /** null = not assessed. */
  overall_labor_score: number | null
  bcea_readiness_status: string | null
  normal_hours_compliant_pct: number | null
  overtime_compliant_pct: number | null
  mandatory_leave_accrual_compliant_pct: number | null
  psira_security_grading_compliant_pct: number | null
  total_active_staff: number | null
  psira_registered_officers: number | null
  audit_findings: LaborAuditFinding[]
}

// Backend router for statutory payroll (EMP201 prepare / mark-filed live under it).
const PAYROLL_STATUTORY = "/cross-service/payroll-statutory"

export async function getPayrollStatutorySummary(period?: string): Promise<StatutoryPayrollSummaryResponse> {
  const query = period ? `?period=${encodeURIComponent(period)}` : ""
  return fetchCompliance<StatutoryPayrollSummaryResponse>(`${PAYROLL_STATUTORY}/summary${query}`)
}

/**
 * Builds an EMP201 WORKING PAPER from real PAID payslips. Nothing is filed with
 * SARS: status comes back PREPARED_NOT_FILED ("File manually on SARS eFiling").
 */
export async function prepareEmp201(payload: PrepareEmp201Input): Promise<PrepareEmp201Result> {
  return fetchCompliance<PrepareEmp201Result>(`${PAYROLL_STATUTORY}/emp201/prepare`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

/** Records the PRN/receipt the user pasted from SARS eFiling (admin only). */
export async function markEmp201Filed(id: number, payload: MarkEmp201FiledInput): Promise<MarkEmp201FiledResult> {
  return fetchCompliance<MarkEmp201FiledResult>(`${PAYROLL_STATUTORY}/emp201/${id}/mark-filed`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getUifDeclarations(period?: string): Promise<UifDeclarationsResponse> {
  const query = period ? `?period=${encodeURIComponent(period)}` : ""
  return fetchCompliance<UifDeclarationsResponse>(`${PAYROLL_STATUTORY}/uif/declarations${query}`)
}

export async function getLaborComplianceAudit(): Promise<LaborComplianceAuditResponse> {
  return fetchCompliance<LaborComplianceAuditResponse>(`${PAYROLL_STATUTORY}/labor-audit`)
}
