"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Loader2, Pencil, Plus, Trash2, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  supportApi, type Assignee, type CustomRule, type CustomRuleInput, type CustomRuleList, type EventChoice, type RuleCondition, type RuleOutcome, type TicketMeta,
} from "@/lib/support-api"
import { CATEGORY_LABELS, OUTCOME_LABELS, SOURCE_LABELS, labelOf } from "@/lib/support-derive"

const FIELD = "h-8 rounded-md border border-input bg-background px-2 text-xs"
const OTHER = "__other__"

const toInput = (r: CustomRule): CustomRuleInput => ({
  name: r.name, event_pattern: r.event_pattern, conditions: r.conditions, source: r.source, category: r.category, priority: r.priority,
  queue: r.queue, outcome: r.outcome, assigned_to: r.assigned_to, title_template: r.title_template, enabled: r.enabled,
})

const blank = (meta: TicketMeta | null): CustomRuleInput => ({
  name: "", event_pattern: "", conditions: [], source: "api", category: "GENERAL", priority: "NORMAL", queue: meta?.queues[0] ?? "support",
  outcome: "ticket", assigned_to: null, title_template: null, enabled: true,
})

function Labelled({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted-foreground">{hint}</span>}
    </label>
  )
}

function RuleForm({ initial, meta, assignees, events, onSave, onCancel, busy, error }: {
  initial: CustomRuleInput
  meta: TicketMeta | null
  assignees: Assignee[]
  events: EventChoice[]
  onSave: (input: CustomRuleInput) => void
  onCancel: () => void
  busy: boolean
  error: string | null
}) {
  const [draft, setDraft] = useState<CustomRuleInput>(initial)
  const choices = useMemo(() => events.filter((e) => !e.built_in), [events])
  const known = choices.some((e) => e.event === draft.event_pattern)
  const [custom, setCustom] = useState(!!initial.event_pattern && !known)
  const set = <K extends keyof CustomRuleInput>(k: K, v: CustomRuleInput[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const setCondition = (i: number, patch: Partial<RuleCondition>) => set("conditions", draft.conditions.map((c, n) => (n === i ? { ...c, ...patch } : c)))
  const valid = draft.name.trim() && draft.event_pattern.trim().includes(".")

  return (
    <form className="space-y-4 rounded-md border border-border bg-muted/20 p-4" aria-label="Rule" onSubmit={(e) => { e.preventDefault(); if (valid) onSave({ ...draft, name: draft.name.trim(), event_pattern: draft.event_pattern.trim() }) }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Labelled label="Name">
          <input className={`${FIELD} w-full`} value={draft.name} maxLength={120} onChange={(e) => set("name", e.target.value)} placeholder="Abandoned cart follow-up" aria-label="Rule name" />
        </Labelled>
        <Labelled label="When this happens" hint={custom ? "Dotted lowercase words, like portal.cart.abandoned. End with .* for a whole group, like sales.lead.*" : undefined}>
          <select className={`${FIELD} w-full`} aria-label="Event" value={custom ? OTHER : draft.event_pattern}
            onChange={(e) => { if (e.target.value === OTHER) { setCustom(true); set("event_pattern", "") } else { setCustom(false); set("event_pattern", e.target.value) } }}>
            <option value="" disabled>Choose an event…</option>
            {choices.map((c) => <option key={c.event} value={c.event}>{c.label}{c.seen_30d ? ` (${c.seen_30d} in 30 days)` : ""}</option>)}
            <option value={OTHER}>Another event…</option>
          </select>
          {custom && <input className={`${FIELD} mt-2 w-full font-mono`} value={draft.event_pattern} onChange={(e) => set("event_pattern", e.target.value)} placeholder="portal.cart.abandoned" aria-label="Event name" />}
        </Labelled>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-xs font-medium text-muted-foreground">Only when (optional)</legend>
        {draft.conditions.map((c, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <input className={`${FIELD} w-40`} value={c.field} onChange={(e) => setCondition(i, { field: e.target.value })} placeholder="field, e.g. amount" aria-label={`Condition ${i + 1} field`} />
            <select className={FIELD} value={c.op} aria-label={`Condition ${i + 1} operator`} onChange={(e) => setCondition(i, { op: e.target.value as RuleCondition["op"] })}>
              <option value="eq">is</option><option value="neq">is not</option><option value="contains">contains</option><option value="exists">is present</option>
            </select>
            {c.op !== "exists" && <input className={`${FIELD} w-44`} value={c.value ?? ""} onChange={(e) => setCondition(i, { value: e.target.value })} placeholder="value" aria-label={`Condition ${i + 1} value`} />}
            <button type="button" aria-label={`Remove condition ${i + 1}`} className="rounded p-1 text-muted-foreground hover:bg-muted" onClick={() => set("conditions", draft.conditions.filter((_, n) => n !== i))}><X className="h-3.5 w-3.5" /></button>
          </div>
        ))}
        {draft.conditions.length < 5 && (
          <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => set("conditions", [...draft.conditions, { field: "", op: "eq", value: "" }])}>
            <Plus className="mr-1 h-3 w-3" /> Add a condition
          </Button>
        )}
      </fieldset>

      <Labelled label="Ticket title (optional)" hint="Use {field} to insert a value from the event, like Cart abandoned by {customer.name}. Without it the event's own title is used.">
        <input className={`${FIELD} w-full`} value={draft.title_template ?? ""} maxLength={200} onChange={(e) => set("title_template", e.target.value || null)} aria-label="Ticket title" />
      </Labelled>

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Labelled label="Source">
          <select className={`${FIELD} w-full`} aria-label="Source" value={draft.source} onChange={(e) => set("source", e.target.value)}>
            {(meta?.sources ?? Object.keys(SOURCE_LABELS)).map((s) => <option key={s} value={s}>{labelOf(SOURCE_LABELS, s)}</option>)}
          </select>
        </Labelled>
        <Labelled label="Priority">
          <select className={`${FIELD} w-full`} aria-label="Priority" value={draft.priority} onChange={(e) => set("priority", e.target.value)}>
            {(meta?.priorities ?? ["NORMAL"]).map((p) => <option key={p} value={p}>{labelOf({}, p)}</option>)}
          </select>
        </Labelled>
        <Labelled label="Category">
          <select className={`${FIELD} w-full`} aria-label="Category" value={draft.category} onChange={(e) => set("category", e.target.value)}>
            {(meta?.categories ?? ["GENERAL"]).map((c) => <option key={c} value={c}>{labelOf(CATEGORY_LABELS, c)}</option>)}
          </select>
        </Labelled>
        <Labelled label="Queue">
          <select className={`${FIELD} w-full`} aria-label="Queue" value={draft.queue} onChange={(e) => set("queue", e.target.value)}>
            {(meta?.queues ?? ["support"]).map((q) => <option key={q} value={q}>{labelOf({}, q)}</option>)}
          </select>
        </Labelled>
        <Labelled label="Also create">
          <select className={`${FIELD} w-full`} aria-label="Also create" value={draft.outcome} onChange={(e) => set("outcome", e.target.value as RuleOutcome)}>
            {Object.entries(OUTCOME_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Labelled>
        <Labelled label="Assign to">
          <select className={`${FIELD} w-full`} aria-label="Assign to" value={draft.assigned_to ?? ""} onChange={(e) => set("assigned_to", e.target.value || null)}>
            <option value="">Nobody (the queue)</option>
            {assignees.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </Labelled>
      </div>

      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={draft.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Switched on</label>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button type="submit" size="sm" disabled={busy || !valid}>{busy && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}Save rule</Button>
        </div>
      </div>
    </form>
  )
}

/** Rules the workspace adds itself: pick any event, say what ticket (and what else) it should create and who gets it. */
export function TicketCustomRules({ meta, assignees }: { meta: TicketMeta | null; assignees: Assignee[] }) {
  const [data, setData] = useState<CustomRuleList | null>(null)
  const [events, setEvents] = useState<EventChoice[]>([])
  const [editing, setEditing] = useState<CustomRule | "new" | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [list, ev] = await Promise.all([supportApi.customRules(), supportApi.eventChoices()])
      setData(list)
      setEvents(ev.events)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load your rules")
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const act = async (fn: () => Promise<unknown>, onFail?: (m: string) => void) => {
    setBusy(true)
    setError(null)
    setFormError(null)
    try {
      await fn()
      await load()
      return true
    } catch (e) {
      const m = e instanceof Error ? e.message : "That did not work"
      if (onFail) onFail(m)
      else setError(m)
      return false
    } finally {
      setBusy(false)
    }
  }

  const nameOf = (id: string | null) => (id ? assignees.find((a) => a.id === id)?.name ?? "A teammate" : "the queue")
  const label = (pattern: string) => events.find((e) => e.event === pattern)?.label

  return (
    <div className="surface-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="section-title">Your own rules</h3>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Pick any event your workspace produces and decide what happens: the ticket&apos;s source, priority, category and queue, who gets it, and whether a task,
            an escalation or a scheduled follow-up is created with it. Repeats of the same thing join the open ticket.
          </p>
        </div>
        {data?.can_edit !== false && editing === null && (
          <Button size="sm" onClick={() => { setFormError(null); setEditing("new") }}><Plus className="mr-1.5 h-3.5 w-3.5" /> Add a rule</Button>
        )}
      </div>

      {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}

      {editing !== null && (
        <div className="mt-4">
          <RuleForm
            key={editing === "new" ? "new" : editing.id}
            initial={editing === "new" ? blank(meta) : toInput(editing)}
            meta={meta} assignees={assignees} events={events} busy={busy} error={formError}
            onCancel={() => { setEditing(null); setFormError(null) }}
            onSave={async (input) => {
              const ok = await act(
                () => (editing === "new" ? supportApi.createCustomRule(input) : supportApi.updateCustomRule(editing.id, { ...input, clear_assignee: !input.assigned_to })),
                setFormError,
              )
              if (ok) setEditing(null)
            }}
          />
        </div>
      )}

      <div className="mt-4 overflow-x-auto">
        {!data ? (
          !error && <Loader2 className="h-4 w-4 animate-spin" aria-label="Loading your rules" />
        ) : data.rules.length === 0 ? (
          <p className="text-sm text-muted-foreground">No rules of your own yet.</p>
        ) : (
          <table className="w-full min-w-[720px] text-sm" aria-label="Your rules">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-3 font-medium">On</th>
                <th className="py-2 pr-3 font-medium">Rule</th>
                <th className="py-2 pr-3 font-medium">Becomes</th>
                <th className="py-2 pr-3 font-medium">Goes to</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {data.rules.map((r) => (
                <tr key={r.id} className="border-b border-border/60 align-top last:border-0">
                  <td className="py-2 pr-3">
                    <input type="checkbox" aria-label={`Switch ${r.name} on`} checked={r.enabled} disabled={busy || !data.can_edit}
                      onChange={(e) => void act(() => supportApi.updateCustomRule(r.id, { enabled: e.target.checked }))} />
                  </td>
                  <td className="py-2 pr-3">
                    <div className="font-medium">{r.name}</div>
                    <div className="text-xs text-muted-foreground">{label(r.event_pattern) ?? "Event"} <span className="font-mono">{r.event_pattern}</span></div>
                    {r.conditions.length > 0 && <div className="text-[11px] text-muted-foreground">only when {r.conditions.map((c) => `${c.field} ${c.op === "eq" ? "is" : c.op === "neq" ? "is not" : c.op === "contains" ? "contains" : "is present"}${c.value ? ` ${c.value}` : ""}`).join(" and ")}</div>}
                  </td>
                  <td className="py-2 pr-3">
                    <div className="flex flex-wrap gap-1">
                      <Badge variant="outline" className="text-[10px]">{labelOf({}, r.priority)}</Badge>
                      <Badge variant="outline" className="text-[10px]">{labelOf(CATEGORY_LABELS, r.category)}</Badge>
                      <Badge variant="outline" className="text-[10px]">{labelOf(SOURCE_LABELS, r.source)}</Badge>
                    </div>
                    {r.outcome !== "ticket" && <div className="mt-1 text-xs text-muted-foreground">{OUTCOME_LABELS[r.outcome]}</div>}
                  </td>
                  <td className="py-2 pr-3 text-xs">{labelOf({}, r.queue)} queue, {nameOf(r.assigned_to)}</td>
                  <td className="py-2 text-right">
                    {data.can_edit && (
                      <Button variant="ghost" size="sm" className="h-7 px-2" aria-label={`Edit ${r.name}`} disabled={busy} onClick={() => { setFormError(null); setEditing(r) }}><Pencil className="h-3.5 w-3.5" /></Button>
                    )}
                    {data.can_delete && (
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-red-400" aria-label={`Delete ${r.name}`} disabled={busy}
                        onClick={() => { if (window.confirm(`Delete the rule “${r.name}”? Tickets it already created stay.`)) void act(() => supportApi.deleteCustomRule(r.id)) }}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {data && !data.can_delete && data.rules.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Managers can switch rules off; deleting one needs an administrator.</p>}
    </div>
  )
}
