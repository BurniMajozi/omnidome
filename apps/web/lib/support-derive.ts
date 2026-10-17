/** Pure helpers for the ticket desk (no React, no fetch), unit-tested with node. */

export const SOURCE_LABELS: Record<string, string> = {
  manual: "Manual",
  email: "Email",
  agent_task: "Agent task",
  call_center: "Call centre",
  finance: "Finance",
  iot: "HomeDome",
  system_error: "System error",
  api: "Service request",
}

export const CATEGORY_LABELS: Record<string, string> = {
  GENERAL: "General",
  TECHNICAL: "Technical",
  BILLING: "Billing",
  HOMEDOME: "HomeDome",
  AGENT: "Agent",
  CALLS: "Calls",
  SYSTEM: "System",
  RICA: "RICA",
  SALES: "Sales",
}

export const STATUS_LABELS: Record<string, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  ESCALATED: "Escalated",
  ON_HOLD: "On hold",
  PENDING: "Pending",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
}

export const CLOSED_STATUSES = ["RESOLVED", "CLOSED"]

export const isClosed = (status: string): boolean => CLOSED_STATUSES.includes(status)

export const labelOf = (map: Record<string, string>, key: string | null | undefined): string =>
  key ? (map[key] ?? key.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())) : "—"

/** "5m", "3h", "2d": compact age for list rows. */
export function ageLabel(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—"
  const ms = now - new Date(iso).getTime()
  if (!Number.isFinite(ms) || ms < 0) return "now"
  const m = Math.floor(ms / 60_000)
  if (m < 1) return "now"
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

export interface SlaView {
  label: string
  tone: "ok" | "warn" | "bad" | "muted"
}

/** SLA badge from the server's state plus the due time ("due in 3h", "overdue 2h"). */
export function slaView(state: string | null | undefined, dueIso: string | null | undefined, now: number = Date.now()): SlaView {
  if (!state || !dueIso) return { label: "No SLA", tone: "muted" }
  const diff = new Date(dueIso).getTime() - now
  const span = (ms: number) => {
    const abs = Math.abs(ms)
    const h = Math.round(abs / 3_600_000)
    return h < 1 ? `${Math.max(1, Math.round(abs / 60_000))}m` : h < 48 ? `${h}h` : `${Math.round(h / 24)}d`
  }
  switch (state) {
    case "breached":
      return { label: `Overdue ${span(diff)}`, tone: "bad" }
    case "due_soon":
      return { label: `Due in ${span(diff)}`, tone: "warn" }
    case "ok":
      return { label: `Due in ${span(diff)}`, tone: "ok" }
    case "met":
      return { label: "SLA met", tone: "ok" }
    case "missed":
      return { label: "SLA missed", tone: "bad" }
    default:
      return { label: "No SLA", tone: "muted" }
  }
}

export const PRIORITY_TONE: Record<string, string> = {
  URGENT: "bg-red-500/15 text-red-400 border-red-500/40",
  HIGH: "bg-orange-500/15 text-orange-400 border-orange-500/40",
  NORMAL: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  LOW: "bg-muted text-muted-foreground border-border",
}

export const SLA_TONE: Record<SlaView["tone"], string> = {
  ok: "text-emerald-400",
  warn: "text-amber-400",
  bad: "text-red-400",
  muted: "text-muted-foreground",
}

export type DeskView = "open" | "mine" | "unassigned" | "breached" | "closed" | "all"

/** Quick views map to server filters; the chip counts come from /tickets/summary. */
export function viewFilters(view: DeskView): { open_only?: boolean; assigned?: string; sla?: string; status?: string } {
  switch (view) {
    case "open":
      return { open_only: true }
    case "mine":
      return { open_only: true, assigned: "me" }
    case "unassigned":
      return { open_only: true, assigned: "unassigned" }
    case "breached":
      return { sla: "breached" }
    case "closed":
      return { status: "RESOLVED,CLOSED" }
    default:
      return {}
  }
}

/** Only in-app deep links from the backend are followed (relative /dashboard paths). */
export function safeInternalLink(link: string | null | undefined): string | null {
  if (!link || !link.startsWith("/dashboard") || link.includes("//") || link.includes("..")) return null
  return link
}

/** Status changes the desk offers from a given status. */
export function nextActions(status: string): { label: string; status: string; tone: "primary" | "ghost" }[] {
  if (isClosed(status)) return [{ label: "Reopen", status: "OPEN", tone: "primary" }]
  const actions: { label: string; status: string; tone: "primary" | "ghost" }[] = []
  if (status === "OPEN" || status === "ON_HOLD" || status === "PENDING") actions.push({ label: "Start work", status: "IN_PROGRESS", tone: "ghost" })
  if (status !== "ON_HOLD") actions.push({ label: "Put on hold", status: "ON_HOLD", tone: "ghost" })
  actions.push({ label: "Resolve", status: "RESOLVED", tone: "ghost" }, { label: "Close", status: "CLOSED", tone: "primary" })
  return actions
}

// ── time dimension ──────────────────────────────────────────────────────────

/** "45m", "3.5h", "2d": a duration in hours for KPI tiles and the handling summary. */
export function formatHours(h: number | null | undefined): string {
  if (h === null || h === undefined || !Number.isFinite(h)) return "—"
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m`
  if (h < 48) return `${Number.isInteger(h) ? h : Math.round(h * 10) / 10}h`
  return `${Math.round((h / 24) * 10) / 10}d`
}

export function formatPct(p: number | null | undefined): string {
  return p === null || p === undefined ? "—" : `${Math.round(p)}%`
}

export const OUTCOME_LABELS: Record<string, string> = {
  ticket: "Ticket only",
  task: "Ticket and a task",
  escalation: "Ticket and an escalation",
  schedule: "Ticket and a scheduled item",
}

export const JEV_MODE_LABELS: Record<string, string> = {
  off: "Off",
  suggest: "Suggest: a person decides",
  auto: "Automatic when sure",
}

export const NOTIFY_TRIGGERS: { key: "notify_on_assigned" | "notify_on_modified" | "notify_on_note" | "notify_on_resolved"; label: string; help: string }[] = [
  { key: "notify_on_assigned", label: "Someone picks it up", help: "“Your request is now being worked on.”" },
  { key: "notify_on_modified", label: "Its priority changes", help: "“Its priority is now High.”" },
  { key: "notify_on_note", label: "A customer-visible reply is added", help: "Sends that reply. Internal notes are never sent." },
  { key: "notify_on_resolved", label: "It is resolved", help: "Includes the resolution note, if any." },
]

interface DerivedEvent {
  id: string
  event_type: string
  actor_id?: string | null
  actor_name: string | null
  actor_type: string
  from_value: string | null
  to_value: string | null
  note: string | null
  visibility: string
  channel: string | null
  data: Record<string, unknown>
  created_at: string | null
}

interface DerivedTimelineEntry {
  id: string
  kind: string
  author_type: string
  message: string
  is_private: boolean
  created_at: string | null
}

export type ActivityTone = "note" | "reply" | "change" | "move" | "state" | "warn" | "jev" | "notify" | "system"

export interface ActivityItem {
  id: string
  at: string | null
  who: string
  title: string
  body?: string
  internal?: boolean
  tone: ActivityTone
  count?: number
}

const TRIGGER_WORDS: Record<string, string> = { assigned: "it was picked up", modified: "its priority changed", note: "a reply was added", resolved: "it was resolved" }

export function deliveryLabel(channel: string | null, delivery: unknown, trigger: unknown): string {
  const why = TRIGGER_WORDS[String(trigger)] ?? "it changed"
  const via = channel ? labelOf({ email: "email", call: "phone", agent: "agent", finance: "finance", system: "system" }, channel) : "its channel"
  if (delivery === "queued") return `Requester told by ${via} that ${why}`
  if (delivery === "no_outbound_path") return `Requester not told (${why}): ${via} has no way to send a reply from here`
  return `Requester not told (${why})`
}

const fieldName = (f: unknown) => (typeof f === "string" && f ? f : "value")

/** One lifecycle event as a human line. `nameOf` resolves user ids to names. */
export function describeEvent(e: DerivedEvent, nameOf: (id: string | null | undefined) => string): ActivityItem {
  const who = e.actor_type === "jev" ? "Jev" : e.actor_type === "system" ? "System" : e.actor_type === "customer" ? "Requester" : e.actor_name || "Agent"
  const base = { id: e.id, at: e.created_at, who }
  const val = (v: string | null) => (v === null ? "none" : labelOf(STATUS_LABELS, v) !== v ? labelOf(STATUS_LABELS, v) : labelOf({}, v))
  switch (e.event_type) {
    case "created":
      return { ...base, title: "Ticket opened", tone: "state" }
    case "assigned":
      return { ...base, title: `Assigned to ${nameOf(e.to_value)}`, body: e.note ?? undefined, tone: "move" }
    case "reassigned":
      return { ...base, title: `Reassigned from ${nameOf(e.from_value)} to ${nameOf(e.to_value)}`, body: e.note ?? undefined, tone: "move" }
    case "unassigned":
      return { ...base, title: `Released by ${nameOf(e.from_value)}`, tone: "move" }
    case "transferred":
      return { ...base, title: `Moved from the ${labelOf({}, e.from_value)} queue to ${labelOf({}, e.to_value)}`, body: e.note ?? undefined, tone: "move" }
    case "modified":
      return { ...base, title: `${labelOf({}, fieldName(e.data?.field))} changed from ${val(e.from_value)} to ${val(e.to_value)}`, body: e.note ?? undefined, tone: "change" }
    case "status_changed":
      return { ...base, title: `Status changed from ${val(e.from_value)} to ${val(e.to_value)}`, body: e.note ?? undefined, tone: "state" }
    case "note_added":
      return { ...base, title: "Internal note", body: e.note ?? undefined, internal: true, tone: "note" }
    case "reply_sent":
      return { ...base, title: "Reply to the requester", body: e.note ?? undefined, tone: "reply" }
    case "customer_notified":
      return { ...base, title: deliveryLabel(e.channel, e.data?.delivery, e.data?.trigger), tone: "notify" }
    case "escalated":
      return { ...base, title: "Escalated", body: e.note ?? undefined, tone: "warn" }
    case "resolved":
      return { ...base, title: "Resolved", body: e.note ?? undefined, tone: "state" }
    case "closed":
      return { ...base, title: "Closed", body: e.note ?? undefined, tone: "state" }
    case "reopened":
      return { ...base, title: "Reopened", body: e.note ?? undefined, tone: "warn" }
    case "sla_breached":
      return { ...base, title: "Passed its deadline while still open", body: e.note ?? undefined, tone: "warn" }
    case "repeated":
      return { ...base, title: "The same problem happened again", tone: "system" }
    case "jev_suggested":
      return { ...base, title: `Jev suggests changing ${e.to_value ?? "the routing"}`, body: e.note ?? undefined, tone: "jev" }
    case "jev_applied":
      return { ...base, title: `Jev changed ${e.to_value ?? "the routing"}`, tone: "jev" }
    case "jev_review":
      return { ...base, title: e.to_value === "flagged" ? "Jev thinks the resolution may not fully solve it" : "Jev checked the resolution", body: e.note ?? undefined, tone: "jev" }
    default:
      return { ...base, title: labelOf({}, e.event_type), tone: "system" }
  }
}

// What the older timeline rows (ticket_replies) already say, so these events are not shown twice next to them.
const EXTRA_EVENT_TYPES = new Set(["customer_notified", "sla_breached", "jev_suggested", "jev_applied", "jev_review"])

/**
 * The activity list, newest first. A ticket whose history is in the event log is shown from it (with who, from and to,
 * and repeats folded into one line). Older tickets keep their timeline rows and gain the events the timeline never had.
 */
export function buildActivity(
  timeline: DerivedTimelineEntry[] | undefined,
  events: DerivedEvent[] | undefined,
  nameOf: (id: string | null | undefined) => string,
): ActivityItem[] {
  const evs = events ?? []
  const logged = evs.some((e) => e.event_type === "created" && !e.data?.backfilled)
  const items: ActivityItem[] = []
  if (logged) {
    let run: ActivityItem | null = null
    for (const e of evs) {
      if (e.event_type === "repeated") {
        if (run) {
          run.count = (run.count ?? 1) + 1
          run.at = e.created_at
        } else {
          run = { ...describeEvent(e, nameOf), count: 1 }
          items.push(run)
        }
        continue
      }
      run = null
      items.push(describeEvent(e, nameOf))
    }
    for (const it of items) if (it.count && it.count > 1) it.title = `The same problem happened again (${it.count} times)`
  } else {
    for (const t of timeline ?? []) {
      const comment = t.kind === "comment"
      items.push({
        id: t.id, at: t.created_at, tone: comment ? (t.is_private ? "note" : "reply") : "system",
        who: t.author_type === "customer" ? "Requester" : t.author_type === "system" ? "System" : "Agent",
        title: comment ? (t.is_private ? "Internal note" : "Reply") : t.message, body: comment ? t.message : undefined, internal: comment && t.is_private,
      })
    }
    for (const e of evs) if (EXTRA_EVENT_TYPES.has(e.event_type)) items.push(describeEvent(e, nameOf))
  }
  return items.sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""))
}

/** The ticket's handling in a few plain facts for the strip above the activity. */
export function handlingFacts(t: {
  hours_to_first_response: number | null; assignment_count: number; modification_count: number; transfer_count: number
  reopen_count: number; hours_to_resolve: number | null; overdue: boolean; stale: boolean
}): { label: string; value: string; tone?: "warn" | "bad" }[] {
  const out: { label: string; value: string; tone?: "warn" | "bad" }[] = [
    { label: "First response", value: t.hours_to_first_response === null ? "Not yet" : formatHours(t.hours_to_first_response), tone: t.hours_to_first_response === null ? "warn" : undefined },
    { label: "Assigned", value: `${t.assignment_count}×` },
    { label: "Modified", value: `${t.modification_count}×` },
    { label: "Transferred", value: `${t.transfer_count}×` },
  ]
  if (t.reopen_count > 0) out.push({ label: "Reopened", value: `${t.reopen_count}×`, tone: "warn" })
  if (t.hours_to_resolve !== null) out.push({ label: "Time to resolve", value: formatHours(t.hours_to_resolve) })
  if (t.overdue) out.push({ label: "Deadline", value: "Passed", tone: "bad" })
  else if (t.stale) out.push({ label: "Activity", value: "Gone quiet", tone: "warn" })
  return out
}

/** Short label for what Jev proposes, e.g. "Queue → Technical, Priority → Urgent". */
export function proposalLabel(proposal: Record<string, unknown>, nameOf: (id: string | null | undefined) => string): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(proposal)) {
    if (k === "flagged") continue
    if (k === "status") parts.push(`Status → ${labelOf(STATUS_LABELS, String(v))}`)
    else if (k === "assignee") parts.push(`Assign to ${nameOf(String(v))}`)
    else if (k === "outcome") parts.push(`Also create: ${(OUTCOME_LABELS[String(v)] ?? String(v)).toLowerCase()}`)
    else parts.push(`${labelOf({}, k)} → ${labelOf(k === "category" ? CATEGORY_LABELS : {}, String(v))}`)
  }
  return parts.join(", ")
}
