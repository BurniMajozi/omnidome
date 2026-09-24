"use client"

/**
 * Lead action menu + lead record slide-over (SPEC-lead-actions.md).
 * Same pattern as Communication: a ⋯ menu (also on right-click) whose items
 * open a right-hand panel. Every action lands on the lead's timeline; email and
 * campaign pushes are delivered by the sales service through the event bus.
 */
import { useCallback, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import {
  AlarmClock, ArrowUpRight, CalendarPlus, CheckCircle2, Circle, ClipboardList, Flag, Loader2, Mail,
  Megaphone, MoreHorizontal, NotebookPen, Phone, PhoneOutgoing, Sparkles, UserCheck, X, Zap,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { listCampaigns, type Campaign } from "@/lib/marketing-api"
import {
  salesApi, salesErrorMessage, type LeadActivity, type LeadOwner, type SalesLead, type SalesLeadDetail,
} from "@/lib/sales-api"
import { announceSalesChange, formatDate, formatDateTime, stageLabel, stageTone } from "./sales-leads-tab"

export type LeadPanelMode =
  | "record" | "assign" | "note" | "email" | "task" | "outbound" | "campaign" | "escalate"

const MODE_TITLES: Record<LeadPanelMode, [string, string]> = {
  record: ["Lead record", "Details, tasks and timeline"],
  assign: ["Assign owner", "Who is responsible for this lead"],
  note: ["Add note / log call", "Recorded on the timeline"],
  email: ["Send email", "Sent from the OmniDome inbox; the timeline shows when it is delivered"],
  task: ["Create task", "A follow-up with a due date and an assignee"],
  outbound: ["Send to outbound agent", "Queues a call; automations can hand it to a voice agent"],
  campaign: ["Send to marketing campaign", "Adds the lead to the campaign's audience in Marketing"],
  escalate: ["Escalate", "Marks the lead urgent and alerts the team"],
}

// ── Menu ────────────────────────────────────────────────────────────────────

export function LeadActionsMenu({
  lead,
  open,
  onOpenChange,
  onAction,
}: {
  lead: SalesLead
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onAction: (mode: LeadPanelMode) => void
}) {
  const item = (mode: LeadPanelMode, icon: React.ReactNode, label: string, disabled?: string) => (
    <DropdownMenuItem className="gap-2" disabled={!!disabled} onClick={() => onAction(mode)} title={disabled}>
      {icon}
      <span className="flex-1">{label}</span>
      {disabled && <span className="text-[10px] text-muted-foreground">{disabled}</span>}
    </DropdownMenuItem>
  )
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={`Actions for ${lead.first_name}`}>
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="text-[11px] font-normal text-muted-foreground">
          {lead.reference ?? "Lead"} · {`${lead.first_name} ${lead.last_name}`.trim()}
        </DropdownMenuLabel>
        {item("record", <ArrowUpRight className="h-4 w-4" />, "Open lead record")}
        {item("assign", <UserCheck className="h-4 w-4" />, lead.owner_name ? "Change owner" : "Assign owner")}
        {item("note", <NotebookPen className="h-4 w-4" />, "Add note / log call")}
        <DropdownMenuSeparator />
        {item("email", <Mail className="h-4 w-4" />, "Send email", lead.email ? undefined : "no email")}
        {item("outbound", <PhoneOutgoing className="h-4 w-4" />, "Send to outbound agent", lead.phone ? undefined : "no phone")}
        {item("campaign", <Megaphone className="h-4 w-4" />, "Send to marketing campaign")}
        {item("task", <ClipboardList className="h-4 w-4" />, "Create task")}
        <DropdownMenuSeparator />
        {item("escalate", <Flag className="h-4 w-4 text-red-400" />, "Escalate")}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// ── Panel ───────────────────────────────────────────────────────────────────

const ACTIVITY_ICON: Record<string, React.ReactNode> = {
  created: <Circle className="h-3.5 w-3.5 text-sky-400" />,
  stage_changed: <ArrowUpRight className="h-3.5 w-3.5 text-purple-400" />,
  assigned: <UserCheck className="h-3.5 w-3.5 text-emerald-400" />,
  note: <NotebookPen className="h-3.5 w-3.5 text-muted-foreground" />,
  call_logged: <Phone className="h-3.5 w-3.5 text-muted-foreground" />,
  email_queued: <Mail className="h-3.5 w-3.5 text-amber-400" />,
  email_sent: <Mail className="h-3.5 w-3.5 text-emerald-400" />,
  email_failed: <Mail className="h-3.5 w-3.5 text-red-400" />,
  task_created: <ClipboardList className="h-3.5 w-3.5 text-sky-400" />,
  task_done: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />,
  escalated: <Flag className="h-3.5 w-3.5 text-red-400" />,
  sent_to_outbound: <PhoneOutgoing className="h-3.5 w-3.5 text-amber-400" />,
  campaign_requested: <Megaphone className="h-3.5 w-3.5 text-amber-400" />,
  campaign_added: <Megaphone className="h-3.5 w-3.5 text-emerald-400" />,
  ai_draft: <Sparkles className="h-3.5 w-3.5 text-primary" />,
  automation: <Zap className="h-3.5 w-3.5 text-amber-400" />,
}

const inputCls = "h-9 w-full rounded-md border border-border bg-background px-2.5 text-sm"
const areaCls = "w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm"

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="grid gap-1 text-xs font-medium text-foreground">
      {label}
      {children}
      {hint && <span className="font-normal text-muted-foreground">{hint}</span>}
    </label>
  )
}

export function LeadPanel({
  leadId,
  initialMode,
  onClose,
  onUpdated,
}: {
  leadId: string
  initialMode: LeadPanelMode
  onClose: () => void
  onUpdated: (lead: SalesLead) => void
}) {
  const [mode, setMode] = useState<LeadPanelMode>(initialMode)
  const [detail, setDetail] = useState<SalesLeadDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [owners, setOwners] = useState<LeadOwner[] | null>(null)
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // form state
  const [ownerId, setOwnerId] = useState("")
  const [noteBody, setNoteBody] = useState("")
  const [noteKind, setNoteKind] = useState<"note" | "call">("note")
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [taskTitle, setTaskTitle] = useState("")
  const [taskDue, setTaskDue] = useState("")
  const [taskAssignee, setTaskAssignee] = useState("")
  const [outboundNotes, setOutboundNotes] = useState("")
  const [campaignId, setCampaignId] = useState("")
  const [reason, setReason] = useState("")

  const refresh = useCallback(async () => {
    try {
      const d = await salesApi.getLead(leadId)
      setDetail(d)
      setLoadError(null)
      return d
    } catch (err) {
      setLoadError(salesErrorMessage(err, "Could not load the lead"))
      return null
    }
  }, [leadId])

  useEffect(() => {
    let cancelled = false
    salesApi.getLead(leadId)
      .then((d) => { if (!cancelled) setDetail(d) })
      .catch((err) => { if (!cancelled) setLoadError(salesErrorMessage(err, "Could not load the lead")) })
    return () => { cancelled = true }
  }, [leadId])

  // Pickers load when a form needs them.
  useEffect(() => {
    if ((mode === "assign" || mode === "task") && owners === null) {
      salesApi.listOwners().then(setOwners).catch(() => setOwners([]))
    }
    if (mode === "campaign" && campaigns === null) {
      listCampaigns({ limit: 100 }).then((c) => setCampaigns(c ?? [])).catch(() => setCampaigns([]))
    }
  }, [mode, owners, campaigns])

  // Esc closes, like the Communication panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const run = async (label: string, action: () => Promise<unknown>) => {
    setSaving(true)
    setError(null)
    try {
      await action()
      const d = await refresh()
      if (d) onUpdated(d)
      announceSalesChange()
      setNotice(label)
      setMode("record")
    } catch (err) {
      setError(salesErrorMessage(err, "The action failed"))
    } finally {
      setSaving(false)
    }
  }

  const ownerById = (id: string) => owners?.find((o) => o.id === id)
  const lead = detail
  const [modeTitle, modeHint] = MODE_TITLES[mode]

  const submit = () => {
    if (!lead) return
    switch (mode) {
      case "assign": {
        const o = ownerById(ownerId)
        return run(o ? `Assigned to ${o.name}` : "Owner cleared", () =>
          salesApi.assignLead(lead.id, { owner_id: o?.id ?? null, owner_name: o?.name ?? null }))
      }
      case "note":
        return run(noteKind === "call" ? "Call logged" : "Note added", () =>
          salesApi.addLeadNote(lead.id, { body: noteBody.trim(), kind: noteKind }))
      case "email":
        return run("Email queued — it appears on the timeline once delivered", () =>
          salesApi.emailLead(lead.id, { subject: subject.trim(), body }))
      case "task": {
        const o = ownerById(taskAssignee)
        return run("Task created", () => salesApi.createLeadTask(lead.id, {
          title: taskTitle.trim(), due_at: taskDue ? new Date(taskDue).toISOString() : undefined,
          assignee_id: o?.id, assignee_name: o?.name,
        }))
      }
      case "outbound":
        return run("Queued for an outbound call", () =>
          salesApi.sendLeadToOutbound(lead.id, { notes: outboundNotes.trim() || undefined }))
      case "campaign": {
        const c = campaigns?.find((x) => x.id === campaignId)
        if (!c) return
        return run(`Sent to ${c.name} — Marketing's audience updates in a moment`, () =>
          salesApi.sendLeadToCampaign(lead.id, { campaign_id: c.id, campaign_name: c.name }))
      }
      case "escalate":
        return run("Escalated", () => salesApi.escalateLead(lead.id, { reason: reason.trim() }))
    }
  }

  const canSubmit = !saving && !!lead && (
    mode === "assign" ? true
      : mode === "note" ? noteBody.trim().length > 0
        : mode === "email" ? subject.trim().length > 0 && body.trim().length > 0 && !!lead.email
          : mode === "task" ? taskTitle.trim().length > 0
            : mode === "outbound" ? !!lead.phone
              : mode === "campaign" ? !!campaignId
                : mode === "escalate" ? reason.trim().length >= 3
                  : false)

  const toggleTask = (taskId: string, done: boolean) =>
    run(done ? "Task completed" : "Task reopened", () => salesApi.updateLeadTask(taskId, { status: done ? "done" : "open" }))

  // Portal to <body>: an animated (transformed) module wrapper would otherwise
  // become the containing block of this fixed panel and push it off-screen.
  return createPortal(
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={modeTitle}>
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l border-border bg-background shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-sm text-muted-foreground">{modeTitle}</p>
            <h3 className="section-title truncate">
              {lead ? `${lead.first_name} ${lead.last_name}`.trim() : "Loading…"}
            </h3>
            <p className="text-xs text-muted-foreground">{modeHint}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {loadError && <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">{loadError}</p>}
          {!lead && !loadError && <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />}
          {notice && mode === "record" && (
            <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-400">{notice}</p>
          )}

          {lead && mode !== "record" && (
            <div className="space-y-3 rounded-xl border border-border bg-card p-4">
              {mode === "assign" && (
                <Field label="Owner" hint="People come from HR (active employees).">
                  <select value={ownerId || lead.owner_id || ""} onChange={(e) => setOwnerId(e.target.value)} className={inputCls}>
                    <option value="">Unassigned</option>
                    {(owners ?? []).map((o) => (
                      <option key={o.id} value={o.id}>{o.name}{o.department ? ` · ${o.department}` : ""}</option>
                    ))}
                  </select>
                </Field>
              )}
              {mode === "note" && (
                <>
                  <div className="flex gap-2 text-xs">
                    {(["note", "call"] as const).map((k) => (
                      <button key={k} type="button" onClick={() => setNoteKind(k)}
                        className={`rounded-md border px-2.5 py-1 ${noteKind === k ? "border-primary bg-primary/15 text-foreground" : "border-border text-muted-foreground"}`}>
                        {k === "note" ? "Note" : "Call log"}
                      </button>
                    ))}
                  </div>
                  <Field label={noteKind === "call" ? "Call outcome" : "Note"}>
                    <textarea rows={4} value={noteBody} onChange={(e) => setNoteBody(e.target.value)} className={areaCls} autoFocus />
                  </Field>
                </>
              )}
              {mode === "email" && (
                <>
                  <Field label="To"><input value={lead.email ?? "No email on this lead"} readOnly className={`${inputCls} text-muted-foreground`} /></Field>
                  <Field label="Subject"><input value={subject} onChange={(e) => setSubject(e.target.value)} className={inputCls} autoFocus /></Field>
                  <Field label="Message"><textarea rows={7} value={body} onChange={(e) => setBody(e.target.value)} className={areaCls} /></Field>
                </>
              )}
              {mode === "task" && (
                <>
                  <Field label="Task"><input value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} className={inputCls} autoFocus placeholder="e.g. Send coverage map" /></Field>
                  <Field label="Due"><input type="datetime-local" value={taskDue} onChange={(e) => setTaskDue(e.target.value)} className={inputCls} /></Field>
                  <Field label="Assignee">
                    <select value={taskAssignee} onChange={(e) => setTaskAssignee(e.target.value)} className={inputCls}>
                      <option value="">Unassigned</option>
                      {(owners ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </select>
                  </Field>
                </>
              )}
              {mode === "outbound" && (
                <>
                  <p className="text-xs text-muted-foreground">
                    Creates a call task for <span className="text-foreground">{lead.phone ?? "—"}</span> in the Outbound queue.
                    Workflows listening for <code className="text-[11px]">sales.lead.outbound_requested</code> in the Agentic Flow Orchestrator run too.
                  </p>
                  <Field label="Notes for the caller (optional)">
                    <textarea rows={3} value={outboundNotes} onChange={(e) => setOutboundNotes(e.target.value)} className={areaCls} />
                  </Field>
                </>
              )}
              {mode === "campaign" && (
                <Field label="Campaign" hint="The lead joins the campaign's &quot;Sales leads&quot; audience in Marketing → Audiences.">
                  <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={inputCls}>
                    <option value="">{campaigns === null ? "Loading campaigns…" : campaigns.length ? "Choose a campaign" : "No campaigns in Marketing yet"}</option>
                    {(campaigns ?? []).map((c) => <option key={c.id} value={c.id}>{c.name} · {c.channel}</option>)}
                  </select>
                </Field>
              )}
              {mode === "escalate" && (
                <Field label="Why does this need attention?">
                  <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className={areaCls} autoFocus />
                </Field>
              )}
              {error && <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => { setError(null); setMode("record") }} disabled={saving}>Cancel</Button>
                <Button size="sm" onClick={() => void submit()} disabled={!canSubmit}>
                  {saving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                  {mode === "email" ? "Queue email" : mode === "escalate" ? "Escalate" : "Save"}
                </Button>
              </div>
            </div>
          )}

          {lead && (
            <>
              <section className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{lead.reference}</span>
                  <span className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${stageTone(lead)}`}>{stageLabel(lead)}</span>
                  {lead.priority && lead.priority !== "normal" && (
                    <span className="rounded-md border border-red-500/40 bg-red-500/15 px-2 py-0.5 text-[11px] font-semibold uppercase text-red-400">{lead.priority}</span>
                  )}
                </div>
                <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1 text-xs">
                  <dt className="text-muted-foreground">Owner</dt><dd>{lead.owner_name ?? "Unassigned"}</dd>
                  <dt className="text-muted-foreground">Channel</dt><dd>{lead.source?.replace(/_/g, " ")}</dd>
                  <dt className="text-muted-foreground">Email</dt><dd className="truncate">{lead.email ?? "—"}</dd>
                  <dt className="text-muted-foreground">Phone</dt><dd>{lead.phone ?? "—"}</dd>
                  <dt className="text-muted-foreground">Created</dt><dd>{formatDateTime(lead.created_at)}</dd>
                  <dt className="text-muted-foreground">Modified</dt><dd>{formatDateTime(lead.updated_at)}</dd>
                  <dt className="text-muted-foreground">Closed</dt><dd>{lead.closed_at ? `${formatDate(lead.closed_at)}${lead.close_reason ? ` · ${lead.close_reason}` : ""}` : "—"}</dd>
                  {lead.escalated_at && (<><dt className="text-muted-foreground">Escalated</dt><dd>{formatDateTime(lead.escalated_at)}</dd></>)}
                  {lead.deal_id && (<><dt className="text-muted-foreground">Deal</dt><dd>{lead.deal_stage}{lead.deal_value_zar ? ` · R ${Number(lead.deal_value_zar).toLocaleString("en-ZA")}` : ""}</dd></>)}
                </dl>
                {mode === "record" && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {(["assign", "note", "email", "task", "outbound", "campaign", "escalate"] as LeadPanelMode[]).map((m) => (
                      <Button key={m} variant="outline" size="sm" className="h-7 text-[11px]"
                        disabled={(m === "email" && !lead.email) || (m === "outbound" && !lead.phone)}
                        onClick={() => { setNotice(null); setMode(m) }}>
                        {MODE_TITLES[m][0]}
                      </Button>
                    ))}
                  </div>
                )}
              </section>

              <section className="space-y-2">
                <h4 className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <AlarmClock className="h-3.5 w-3.5" /> Tasks ({lead.tasks.filter((t) => t.status === "open").length} open)
                </h4>
                {lead.tasks.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No tasks yet.</p>
                ) : lead.tasks.map((t) => (
                  <label key={t.id} className="flex items-start gap-2 rounded-md border border-border/60 px-2.5 py-2 text-xs">
                    <input type="checkbox" checked={t.status === "done"} disabled={saving}
                      onChange={(e) => void toggleTask(t.id, e.target.checked)} className="mt-0.5" />
                    <span className="min-w-0 flex-1">
                      <span className={t.status === "done" ? "text-muted-foreground line-through" : "text-foreground"}>
                        {t.kind === "call" && <Phone className="mr-1 inline h-3 w-3" />}{t.title}
                      </span>
                      <span className="block text-[10px] text-muted-foreground">
                        {t.assignee_name ?? "Unassigned"}{t.due_at ? ` · due ${formatDateTime(t.due_at)}` : ""}
                      </span>
                    </span>
                  </label>
                ))}
              </section>

              <section className="space-y-2">
                <h4 className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <CalendarPlus className="h-3.5 w-3.5" /> Timeline
                </h4>
                <ol className="space-y-2">
                  {lead.activities.map((a: LeadActivity) => (
                    <li key={a.id} className="flex gap-2 text-xs">
                      <span className="mt-0.5 shrink-0">{ACTIVITY_ICON[a.kind] ?? <Circle className="h-3.5 w-3.5 text-muted-foreground" />}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-foreground">{a.summary}</span>
                        <span className="block text-[10px] text-muted-foreground">
                          {formatDateTime(a.created_at)}{a.actor_name ? ` · ${a.actor_name}` : ""}
                        </span>
                        {a.kind === "ai_draft" && typeof a.details?.body === "string" && (
                          <span className="mt-1.5 block rounded-md border border-primary/30 bg-primary/5 p-2">
                            <span className="block whitespace-pre-wrap text-[11px] text-foreground">{a.details.body}</span>
                            <Button
                              size="sm"
                              variant="outline"
                              className="mt-2 h-6 text-[10px]"
                              disabled={!lead.email}
                              title={lead.email ? undefined : "This lead has no email address"}
                              onClick={() => {
                                setSubject("Following up from OmniDome")
                                setBody(String(a.details.body).replace(/\*\*/g, ""))
                                setNotice(null)
                                setMode("email")
                              }}
                            >
                              Review and send as email
                            </Button>
                          </span>
                        )}
                        {(a.kind === "note" || a.kind === "call_logged") && typeof a.details?.body === "string"
                          && a.details.body.trim() !== a.summary.replace(/^Call: /, "").trim() && (
                          <span className="mt-1 block whitespace-pre-wrap text-[11px] text-muted-foreground">{a.details.body}</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ol>
              </section>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
