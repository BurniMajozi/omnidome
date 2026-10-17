"use client"

import { useCallback, useEffect, useState } from "react"
import {
  AlertTriangle, ArrowRightLeft, ArrowUpRight, Bot, CircleDot, Loader2, Mail, MessageSquare, Pencil, RefreshCw, Repeat, Send, Sparkles,
  StickyNote, X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { supportApi, type Assignee, type JevDecision, type Ticket, type TicketMeta } from "@/lib/support-api"
import {
  CATEGORY_LABELS, PRIORITY_TONE, SLA_TONE, SOURCE_LABELS, STATUS_LABELS, buildActivity, handlingFacts, isClosed, labelOf, nextActions,
  proposalLabel, safeInternalLink, slaView, type ActivityItem, type ActivityTone,
} from "@/lib/support-derive"

const FIELD = "h-8 rounded-md border border-input bg-background px-2 text-xs"

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-ZA", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"

const TONE_STYLE: Record<ActivityTone, string> = {
  note: "bg-amber-500/15 text-amber-400",
  reply: "bg-primary/15 text-primary",
  change: "bg-sky-500/15 text-sky-400",
  move: "bg-violet-500/15 text-violet-400",
  state: "bg-muted text-muted-foreground",
  warn: "bg-red-500/15 text-red-400",
  jev: "bg-fuchsia-500/15 text-fuchsia-400",
  notify: "bg-emerald-500/15 text-emerald-400",
  system: "bg-muted text-muted-foreground",
}

function ActivityIcon({ tone }: { tone: ActivityTone }) {
  const cls = "h-3.5 w-3.5"
  switch (tone) {
    case "note": return <StickyNote className={cls} />
    case "reply": return <MessageSquare className={cls} />
    case "change": return <Pencil className={cls} />
    case "move": return <ArrowRightLeft className={cls} />
    case "warn": return <AlertTriangle className={cls} />
    case "jev": return <Sparkles className={cls} />
    case "notify": return <Mail className={cls} />
    case "system": return <Bot className={cls} />
    default: return <CircleDot className={cls} />
  }
}

const FACT_TONE = { warn: "text-amber-400", bad: "text-red-400" } as const

interface Props {
  ticketId: string
  meta: TicketMeta | null
  assignees: Assignee[]
  onChanged: (ticket: Ticket) => void
  onClose: () => void
}

/** One ticket: facts, SLA, routing, status actions, link to the originating record and the full timeline. */
export function TicketDetail({ ticketId, meta, assignees, onChanged, onClose }: Props) {
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [comment, setComment] = useState("")
  const [internal, setInternal] = useState(true)
  const [resolution, setResolution] = useState("")
  const [jevNote, setJevNote] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setTicket(await supportApi.get(ticketId))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the ticket")
    } finally {
      setLoading(false)
    }
  }, [ticketId])

  useEffect(() => {
    setTicket(null)
    setComment("")
    setResolution("")
    setJevNote(null)
    void load()
  }, [load])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      const fresh = await supportApi.get(ticketId)
      setTicket(fresh)
      setResolution("")
      onChanged(fresh)
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work")
    } finally {
      setBusy(false)
    }
  }

  if (!ticket) {
    return (
      <div className="surface-card flex min-h-64 items-center justify-center p-6 text-sm text-muted-foreground">
        {loading ? <Loader2 className="h-5 w-5 animate-spin" aria-label="Loading ticket" /> : (
          <div className="space-y-3 text-center">
            <p role="alert">{error ?? "Ticket not found"}</p>
            <Button variant="outline" size="sm" onClick={onClose}>Back to the list</Button>
          </div>
        )}
      </div>
    )
  }

  const closed = isClosed(ticket.status)
  const sla = slaView(ticket.sla_state, ticket.sla_due_at)
  const assigneeName = (id: string | null) => (id ? assignees.find((a) => a.id === id)?.name ?? "Teammate" : "Unassigned")
  const link = safeInternalLink(ticket.source_link)
  const mine = !!meta && ticket.assigned_to === meta.user_id
  const nameOf = (id: string | null | undefined) => (id ? assignees.find((a) => a.id === id)?.name ?? "a teammate" : "nobody")
  const activity = buildActivity(ticket.timeline, ticket.events, nameOf)
  const facts = handlingFacts(ticket)
  const open: JevDecision[] = (ticket.jev ?? []).filter((d) => d.disposition === "suggested")
  const review = (ticket.jev ?? []).find((d) => d.stage === "review")
  const emailed = ticket.reply_channel === "email"

  return (
    <div className="surface-card flex flex-col gap-4 p-5" aria-label={`Ticket ${ticket.ticket_ref ?? ticket.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{ticket.ticket_ref ?? ticket.id.slice(0, 8)}</span>
            <Badge variant="outline" className="text-[10px]">{labelOf(SOURCE_LABELS, ticket.source)}</Badge>
            {ticket.occurrence_count > 1 && (
              <Badge variant="outline" className="gap-1 border-amber-500/40 text-[10px] text-amber-400" title="Repeats are folded into this ticket">
                <Repeat className="h-3 w-3" /> {ticket.occurrence_count}× occurred
              </Badge>
            )}
          </div>
          <h3 className="mt-1 break-words text-lg font-semibold leading-snug">{ticket.subject}</h3>
        </div>
        <button type="button" aria-label="Close ticket panel" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden" onClick={onClose}>
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={PRIORITY_TONE[ticket.priority]}>{labelOf({}, ticket.priority)}</Badge>
        <Badge variant="outline">{labelOf(STATUS_LABELS, ticket.status)}</Badge>
        <span className={`text-xs font-medium ${SLA_TONE[sla.tone]}`}>{sla.label}</span>
        <Button variant="ghost" size="sm" className="ml-auto h-7 px-2" onClick={() => void load()} aria-label="Refresh ticket">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {error && <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      <dl className="grid grid-cols-2 gap-2 rounded-md bg-muted/30 p-3 text-xs sm:grid-cols-4" aria-label="How this ticket has been handled">
        {facts.map((f) => (
          <div key={f.label}>
            <dt className="text-muted-foreground">{f.label}</dt>
            <dd className={`mt-0.5 font-medium ${f.tone ? FACT_TONE[f.tone] : ""}`}>{f.value}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-2">
        {nextActions(ticket.status).map((a) => (
          <Button
            key={a.status}
            size="sm"
            variant={a.tone === "primary" ? "default" : "outline"}
            disabled={busy}
            onClick={() => run(() => supportApi.update(ticket.id, { status: a.status, note: a.status === "CLOSED" || a.status === "RESOLVED" ? resolution : undefined }))}
          >
            {a.label}
          </Button>
        ))}
      </div>
      {!closed && (
        <input
          className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
          placeholder="Resolution note (optional, saved when you resolve or close)"
          value={resolution}
          maxLength={500}
          onChange={(e) => setResolution(e.target.value)}
          aria-label="Resolution note"
        />
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
        <div>
          <dt className="mb-1 text-muted-foreground">Assignee</dt>
          <dd className="flex items-center gap-2">
            <select
              className={FIELD}
              aria-label="Assignee"
              value={ticket.assigned_to ?? ""}
              disabled={busy}
              onChange={(e) => run(() => supportApi.assign(ticket.id, e.target.value || null))}
            >
              <option value="">Unassigned</option>
              {assignees.map((a) => <option key={a.id} value={a.id}>{a.name}{a.id === meta?.user_id ? " (me)" : ""}</option>)}
              {ticket.assigned_to && !assignees.some((a) => a.id === ticket.assigned_to) && <option value={ticket.assigned_to}>Teammate</option>}
            </select>
            {!mine && meta && (
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" disabled={busy} onClick={() => run(() => supportApi.assign(ticket.id, meta.user_id))}>
                Take it
              </Button>
            )}
          </dd>
        </div>
        <div>
          <dt className="mb-1 text-muted-foreground">Queue</dt>
          <dd>
            <select className={FIELD} aria-label="Queue" value={ticket.queue ?? ""} disabled={busy || !meta}
              onChange={(e) => e.target.value && run(() => supportApi.update(ticket.id, { queue: e.target.value }))}>
              {!ticket.queue && <option value="">No queue</option>}
              {(meta?.queues ?? []).map((q) => <option key={q} value={q}>{labelOf({}, q)}</option>)}
            </select>
          </dd>
        </div>
        <div>
          <dt className="mb-1 text-muted-foreground">Priority</dt>
          <dd>
            <select className={FIELD} aria-label="Priority" value={ticket.priority} disabled={busy}
              onChange={(e) => run(() => supportApi.update(ticket.id, { priority: e.target.value }))}>
              {(meta?.priorities ?? [ticket.priority]).map((p) => <option key={p} value={p}>{labelOf({}, p)}</option>)}
            </select>
          </dd>
        </div>
        <div>
          <dt className="mb-1 text-muted-foreground">Category</dt>
          <dd>
            <select className={FIELD} aria-label="Category" value={ticket.category ?? ""} disabled={busy}
              onChange={(e) => e.target.value && run(() => supportApi.update(ticket.id, { category: e.target.value }))}>
              {!ticket.category && <option value="">None</option>}
              {(meta?.categories ?? []).map((c) => <option key={c} value={c}>{labelOf(CATEGORY_LABELS, c)}</option>)}
            </select>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Customer</dt>
          <dd className="mt-0.5">{ticket.customer_name || (ticket.customer_id ? `#${ticket.customer_id.slice(0, 8)}` : "Not linked")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Opened</dt>
          <dd className="mt-0.5">{when(ticket.created_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Assigned</dt>
          <dd className="mt-0.5">{assigneeName(ticket.assigned_to)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">First response</dt>
          <dd className="mt-0.5">{ticket.first_response_at ? when(ticket.first_response_at) : "Not yet"}</dd>
        </div>
      </dl>

      {link && (
        <a href={link} className="inline-flex w-fit items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted">
          Open the originating record{ticket.source_ref_type ? ` (${ticket.source_ref_type.replace(/_/g, " ")})` : ""}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </a>
      )}

      {ticket.description && (
        <section>
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Description</h4>
          <p className="whitespace-pre-wrap break-words rounded-md bg-muted/30 p-3 text-sm">{ticket.description}</p>
        </section>
      )}
      {ticket.resolution_notes && closed && (
        <section>
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Resolution</h4>
          <p className="whitespace-pre-wrap break-words text-sm">{ticket.resolution_notes}</p>
        </section>
      )}

      <section aria-label="Jev">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" /> Jev
          </h4>
          {!closed && (
            <Button variant="outline" size="sm" className="h-7 px-2 text-xs" disabled={busy}
              onClick={() => run(async () => {
                const r = await supportApi.askJev(ticket.id)
                setJevNote(r.status === "unavailable" ? (r.reason ?? "Jev is not available right now") : r.status === "routed"
                  ? (Object.keys(r.applied ?? {}).length || Object.keys(r.suggested ?? {}).length ? null : "Jev agrees with the current routing")
                  : "Nothing to do for this ticket")
              })}>
              Ask Jev to route it
            </Button>
          )}
        </div>
        {jevNote && <p className="mb-2 text-xs text-muted-foreground">{jevNote}</p>}
        {open.map((d) => (
          <div key={d.id} className="mb-2 rounded-md border border-fuchsia-500/30 bg-fuchsia-500/5 p-3 text-sm">
            <p className="text-xs text-muted-foreground">
              {d.stage === "stage" ? "Jev thinks this has sat too long" : "Jev suggests"} · {Math.round(Math.max(0, ...Object.values(d.confidence)) * 100)}% sure
            </p>
            <p className="mt-0.5 font-medium">{proposalLabel(d.proposal, nameOf)}</p>
            {d.reason && <p className="mt-0.5 text-xs text-muted-foreground">{d.reason}</p>}
            <div className="mt-2 flex gap-2">
              <Button size="sm" className="h-7 px-2 text-xs" disabled={busy} onClick={() => run(() => supportApi.applyJev(ticket.id, d.id))}>Apply</Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" disabled={busy} onClick={() => run(() => supportApi.dismissJev(ticket.id, d.id))}>Dismiss</Button>
            </div>
          </div>
        ))}
        {review && (
          <p className={`text-xs ${review.disposition === "flagged" ? "text-amber-400" : "text-muted-foreground"}`}>
            {review.disposition === "flagged" ? "Jev flagged the resolution: " : "Jev checked the resolution: "}{review.reason}
          </p>
        )}
        {!open.length && !review && !jevNote && <p className="text-xs text-muted-foreground">No suggestions. Jev routes new tickets and reviews them when they close, if your workspace has it on.</p>}
      </section>

      <section>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Activity</h4>
        {activity.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing has happened yet.</p>
        ) : (
          <ol className="space-y-3" aria-label="Ticket activity">
            {activity.map((e: ActivityItem) => (
              <li key={e.id} className="flex gap-2.5 text-sm">
                <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${TONE_STYLE[e.tone]}`}>
                  <ActivityIcon tone={e.tone} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] text-muted-foreground">{e.who} · {when(e.at)}{e.internal ? " · only staff can see this" : ""}</p>
                  <p className={e.tone === "note" || e.tone === "reply" ? "font-medium" : "text-muted-foreground"}>{e.title}</p>
                  {e.body && <p className="mt-0.5 whitespace-pre-wrap break-words rounded-md bg-muted/30 px-2.5 py-1.5">{e.body}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <form
        className="space-y-2 border-t border-border pt-4"
        onSubmit={(ev) => {
          ev.preventDefault()
          const text = comment.trim()
          if (!text) return
          void run(async () => {
            await supportApi.comment(ticket.id, text, internal)
            setComment("")
          })
        }}
      >
        <div role="tablist" aria-label="Add to this ticket" className="flex gap-1">
          <Button type="button" role="tab" aria-selected={internal} size="sm" variant={internal ? "secondary" : "ghost"} className="h-8 gap-1.5" onClick={() => setInternal(true)}>
            <StickyNote className="h-3.5 w-3.5" /> Add a note
          </Button>
          <Button type="button" role="tab" aria-selected={!internal} size="sm" variant={!internal ? "secondary" : "ghost"} className="h-8 gap-1.5" onClick={() => setInternal(false)}>
            <Send className="h-3.5 w-3.5" /> Reply to the requester
          </Button>
        </div>
        <Textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={5000} aria-label={internal ? "Add a note" : "Reply to the requester"}
          placeholder={internal ? "What happened, what you tried, what is next. Only staff see notes." : "Visible to the requester"} />
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            {internal
              ? "Notes are kept with the ticket's history and never sent to the requester."
              : emailed ? "Saved on the ticket and emailed to the requester." : "Saved on the ticket. This request did not come in by email, so nothing is sent."}
          </p>
          <Button type="submit" size="sm" disabled={busy || !comment.trim()}>
            {busy && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
            {internal ? "Add note" : "Send reply"}
          </Button>
        </div>
      </form>
    </div>
  )
}
