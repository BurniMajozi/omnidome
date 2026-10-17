/**
 * Ticket desk client for the support service (/svc/support is a next.config rewrite; identity is attached by
 * AuthFetchInit and signed at the edge, so no tenant is ever sent from here).
 */

const SUPPORT_API = "/svc/support"

export class SupportApiError extends Error {
  status: number | null
  constructor(message: string, status: number | null) {
    super(message)
    this.name = "SupportApiError"
    this.status = status
  }
}

export type TicketStatus = "OPEN" | "IN_PROGRESS" | "ESCALATED" | "ON_HOLD" | "PENDING" | "RESOLVED" | "CLOSED"
export type TicketPriority = "LOW" | "NORMAL" | "HIGH" | "URGENT"
export type SlaState = "ok" | "due_soon" | "breached" | "met" | "missed" | null

export interface Ticket {
  id: string
  ticket_no: number | null
  ticket_ref: string | null
  customer_id: string | null
  customer_name?: string
  customer_phone?: string
  subject: string
  description: string | null
  priority: TicketPriority
  status: TicketStatus
  category: string | null
  assigned_to: string | null
  resolution_notes: string | null
  resolved_at: string | null
  created_at: string | null
  updated_at: string | null
  source: string
  source_ref_type: string | null
  source_ref_id: string | null
  source_link: string | null
  event_type: string | null
  queue: string | null
  occurrence_count: number
  last_occurrence_at: string | null
  sla_due_at: string | null
  sla_state: SlaState
  first_response_at: string | null
  context: Record<string, unknown>
  timeline?: TimelineEntry[]
  /** The lifecycle log (detail only): who did what and when, oldest first. */
  events?: TicketEvent[]
  /** Jev's recent proposals and reviews for this ticket (detail only), newest first. */
  jev?: JevDecision[]
  // time dimension
  first_assigned_at: string | null
  last_activity_at: string | null
  escalated_at: string | null
  assignment_count: number
  modification_count: number
  transfer_count: number
  reopen_count: number
  reply_channel: string | null
  overdue: boolean
  stale: boolean
  hours_to_first_response: number | null
  hours_to_resolve: number | null
}

export type TicketEventType =
  | "created" | "assigned" | "reassigned" | "unassigned" | "transferred" | "modified" | "status_changed" | "note_added"
  | "reply_sent" | "customer_notified" | "escalated" | "resolved" | "closed" | "reopened" | "sla_breached" | "repeated"
  | "jev_suggested" | "jev_applied" | "jev_review"

export interface TicketEvent {
  id: string
  event_type: TicketEventType
  actor_id: string | null
  actor_name: string | null
  actor_type: "agent" | "system" | "customer" | "jev"
  from_value: string | null
  to_value: string | null
  note: string | null
  visibility: "internal" | "public"
  channel: string | null
  data: Record<string, unknown>
  created_at: string | null
}

export interface JevDecision {
  id: string
  stage: "route" | "review" | "stage"
  proposal: Record<string, unknown>
  confidence: Record<string, number>
  disposition: "suggested" | "applied" | "dismissed" | "ignored" | "flagged" | "passed"
  reason: string | null
  evaluated_by_jev: boolean
  created_at: string | null
  decided_at: string | null
}

export interface KpiBlock {
  opened: number
  resolved: number
  still_open: number
  mean_hours_to_respond: number | null
  median_hours_to_respond: number | null
  mean_hours_to_assign: number | null
  mean_hours_to_resolve: number | null
  median_hours_to_resolve: number | null
  first_touch_resolution_pct: number | null
  sla_met_pct: number | null
}

export interface TicketKpis {
  window_days: number
  assignee: string | null
  overall: KpiBlock
  now: { open_now: number; unassigned_now: number; escalated_now: number; overdue_now: number; stale_now: number }
  by_assignee: (KpiBlock & { id: string; name: string | null })[]
  by_queue: (KpiBlock & { key: string })[]
  by_category: (KpiBlock & { key: string })[]
  time_in_stage: { status: string; tickets: number; avg_hours: number | null }[]
}

export interface LateTicket {
  id: string
  ref: string | null
  subject: string
  priority: TicketPriority
  status: TicketStatus
  queue: string | null
  category: string | null
  assigned_to: string | null
  overdue: boolean
  stale: boolean
  hours_overdue: number
  hours_idle: number | null
  age_hours: number | null
}

export interface TicketSettings {
  notify_enabled: boolean
  notify_on_assigned: boolean
  notify_on_modified: boolean
  notify_on_note: boolean
  notify_on_resolved: boolean
  jev_routing_mode: "off" | "suggest" | "auto"
  jev_review_on_close: boolean
  jev_modes?: string[]
  deliverable_channels?: string[]
  can_edit?: boolean
}

export type RuleOutcome = "ticket" | "task" | "escalation" | "schedule"

export interface RuleCondition {
  field: string
  op: "eq" | "neq" | "contains" | "exists"
  value: string | null
}

export interface CustomRule {
  id: string
  name: string
  event_pattern: string
  conditions: RuleCondition[]
  source: string
  category: string
  priority: string
  queue: string
  outcome: RuleOutcome
  assigned_to: string | null
  title_template: string | null
  enabled: boolean
  created_at: string | null
}

export type CustomRuleInput = Omit<CustomRule, "id" | "created_at">

export interface CustomRuleList {
  rules: CustomRule[]
  outcomes: RuleOutcome[]
  outcome_labels: Record<RuleOutcome, string>
  condition_ops: string[]
  can_edit: boolean
  can_delete: boolean
  limits: { rules: number; conditions: number }
}

export interface EventChoice {
  event: string
  label: string
  seen_30d: number
  last_seen: string | null
  built_in: boolean
}

export interface TimelineEntry {
  id: string
  kind: "comment" | "event" | "status" | "assignment"
  author_type: string
  author_id: string | null
  message: string
  is_private: boolean
  created_at: string | null
}

export interface TicketSearch {
  items: Ticket[]
  total: number
  limit: number
  offset: number
}

export interface TicketFilters {
  q?: string
  status?: string
  priority?: string
  source?: string
  queue?: string
  category?: string
  assigned?: string
  sla?: string
  open_only?: boolean
  sort?: "newest" | "oldest" | "priority" | "sla" | "updated"
  limit?: number
  offset?: number
}

export interface TicketSummary {
  avg_response_hours?: number | null
  stale?: number
  total: number
  open: number
  unassigned: number
  mine: number
  breached: number
  closed: number
  avg_resolution_hours: number | null
  by_status: Record<string, number>
  open_by_priority: Record<string, number>
  open_by_source: Record<string, number>
}

export interface TicketMeta {
  statuses: string[]
  priorities: string[]
  categories: string[]
  queues: string[]
  sources: string[]
  sla_hours: Record<string, number>
  user_id: string
}

export interface Assignee {
  id: string
  name: string
}

export interface TicketRule {
  key: string
  label: string
  source: string
  enabled: boolean
  category: string
  priority: string
  queue: string
  assigned_to: string | null
  outcome: RuleOutcome
  overridden: boolean
  defaults: { enabled: boolean; category: string; priority: string; queue: string; outcome: RuleOutcome }
}

export interface CreateTicketInput {
  subject: string
  description?: string
  category?: string
  priority?: string
  source?: string
  queue?: string | null
  customer_id?: string | null
  assigned_to?: string | null
  reply_channel?: string | null
  reply_ref?: string | null
}

function detailOf(body: unknown): string {
  const d = (body as { detail?: unknown } | null)?.detail
  if (typeof d === "string") return d
  if (Array.isArray(d)) return d.map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x))).join("; ")
  return ""
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${SUPPORT_API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
      signal: init?.signal ?? AbortSignal.timeout(20_000),
    })
  } catch {
    throw new SupportApiError("The support service did not respond", null)
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const message = detailOf(body) || (res.status === 403 ? "You do not have permission to do that" : `Support service error ${res.status}`)
    throw new SupportApiError(message, res.status)
  }
  return (res.status === 204 ? null : await res.json()) as T
}

function qs(params: object): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params as Record<string, unknown>)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ""
}

export const supportApi = {
  search: (filters: TicketFilters) => call<TicketSearch>(`/tickets/search${qs(filters)}`),
  summary: () => call<TicketSummary>("/tickets/summary"),
  meta: () => call<TicketMeta>("/tickets/meta"),
  assignees: () => call<Assignee[]>("/tickets/assignees"),
  get: (id: string) => call<Ticket>(`/tickets/${id}`),
  create: (input: CreateTicketInput) => call<Ticket>("/tickets", { method: "POST", body: JSON.stringify(input) }),
  update: (id: string, patch: { status?: string; priority?: string; category?: string; queue?: string; note?: string }) =>
    call<Ticket>(`/tickets/${id}`, { method: "PUT", body: JSON.stringify(patch) }),
  comment: (id: string, message: string, isPrivate: boolean) =>
    call<TimelineEntry>(`/tickets/${id}/comments`, { method: "POST", body: JSON.stringify({ message, is_private: isPrivate }) }),
  assign: (id: string, assignedTo: string | null, queue?: string) =>
    call<Ticket>(`/tickets/${id}/assign`, { method: "POST", body: JSON.stringify({ assigned_to: assignedTo, queue }) }),
  rules: () => call<{ rules: TicketRule[]; noise: string[]; outcomes: RuleOutcome[]; outcome_labels: Record<RuleOutcome, string> }>("/ticket-rules"),
  saveRule: (key: string, patch: Partial<Pick<TicketRule, "enabled" | "category" | "priority" | "queue" | "outcome">> & { reset?: boolean }) =>
    call<TicketRule>(`/ticket-rules/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify(patch) }),

  // time dimension
  events: (id: string) => call<{ items: TicketEvent[] }>(`/tickets/${id}/events`),
  kpis: (days: number, assignee?: string) => call<TicketKpis>(`/tickets/kpis${qs({ days, assignee })}`),
  late: (limit = 25) => call<{ items: LateTicket[] }>(`/tickets/late${qs({ limit })}`),
  settings: () => call<TicketSettings>("/tickets/settings"),
  saveSettings: (patch: Partial<TicketSettings>) => call<TicketSettings>("/tickets/settings", { method: "PUT", body: JSON.stringify(patch) }),

  // the rules a workspace adds itself
  customRules: () => call<CustomRuleList>("/ticket-automation"),
  eventChoices: () => call<{ events: EventChoice[] }>("/ticket-automation/events"),
  createCustomRule: (input: Partial<CustomRuleInput> & { name: string; event_pattern: string }) =>
    call<CustomRule>("/ticket-automation", { method: "POST", body: JSON.stringify(input) }),
  updateCustomRule: (id: string, patch: Partial<CustomRuleInput> & { clear_assignee?: boolean }) =>
    call<CustomRule>(`/ticket-automation/${id}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteCustomRule: (id: string) => call<null>(`/ticket-automation/${id}`, { method: "DELETE" }),

  // Jev
  askJev: (id: string) => call<{ status: string; reason?: string; applied?: Record<string, string>; suggested?: Record<string, string> }>(
    `/tickets/${id}/jev/route`, { method: "POST" }),
  applyJev: (id: string, decisionId: string) => call<{ changed: string[]; ticket: Ticket }>(`/tickets/${id}/jev/${decisionId}/apply`, { method: "POST" }),
  dismissJev: (id: string, decisionId: string) => call<{ dismissed: boolean }>(`/tickets/${id}/jev/${decisionId}/dismiss`, { method: "POST" }),
}
