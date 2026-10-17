"use client"

import { useCallback, useEffect, useState } from "react"
import { Loader2, RotateCcw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { supportApi, type Assignee, type RuleOutcome, type TicketMeta, type TicketRule } from "@/lib/support-api"
import { CATEGORY_LABELS, OUTCOME_LABELS, SOURCE_LABELS, labelOf } from "@/lib/support-derive"
import { TicketCustomRules } from "./ticket-custom-rules"
import { TicketSettingsPanel } from "./ticket-settings-panel"

const FIELD = "h-8 rounded-md border border-input bg-background px-2 text-xs"

/** Which events become tickets for this tenant, and how they are routed. Defaults live in the support service. */
export function TicketRulesPanel({ meta, assignees = [] }: { meta: TicketMeta | null; assignees?: Assignee[] }) {
  const [rules, setRules] = useState<TicketRule[] | null>(null)
  const [noise, setNoise] = useState<string[]>([])
  const [outcomes, setOutcomes] = useState<Record<string, string>>(OUTCOME_LABELS)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await supportApi.rules()
      setRules(res.rules)
      setNoise(res.noise)
      if (res.outcome_labels) setOutcomes(res.outcome_labels)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the rules")
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const save = async (rule: TicketRule, patch: Parameters<typeof supportApi.saveRule>[1]) => {
    setSaving(rule.key)
    setError(null)
    try {
      const next = await supportApi.saveRule(rule.key, patch)
      setRules((cur) => (cur ?? []).map((r) => (r.key === rule.key ? { ...r, ...next } : r)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the rule")
    } finally {
      setSaving(null)
    }
  }

  if (!rules) {
    return (
      <div className="surface-card flex min-h-40 items-center justify-center p-6 text-sm text-muted-foreground">
        {error ? <p role="alert">{error}</p> : <Loader2 className="h-5 w-5 animate-spin" aria-label="Loading rules" />}
      </div>
    )
  }

  const full = (r: TicketRule, over: Parameters<typeof supportApi.saveRule>[1]) =>
    save(r, { enabled: r.enabled, priority: r.priority, category: r.category, queue: r.queue, outcome: r.outcome, ...over })

  return (
    <div className="space-y-4">
    <TicketSettingsPanel />
    <TicketCustomRules meta={meta} assignees={assignees} />
    <div className="surface-card p-5">
      <h3 className="section-title">Built-in rules</h3>
      <p className="mb-4 mt-1 text-sm text-muted-foreground">
        Every event below becomes a ticket for your team. Repeats of the same problem are added to the open ticket instead of creating a
        new one. Turn a rule off to stop it, change where its tickets land, or have it also create a task, an escalation or a scheduled
        follow-up. Health checks and debug events never create tickets.
      </p>
      {error && <p role="alert" className="mb-3 text-sm text-red-400">{error}</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2 pr-3 font-medium">On</th>
              <th className="py-2 pr-3 font-medium">Event</th>
              <th className="py-2 pr-3 font-medium">Source</th>
              <th className="py-2 pr-3 font-medium">Priority</th>
              <th className="py-2 pr-3 font-medium">Category</th>
              <th className="py-2 pr-3 font-medium">Queue</th>
              <th className="py-2 pr-3 font-medium">Also create</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.key} className="border-b border-border/60 last:border-0">
                <td className="py-2 pr-3">
                  <input type="checkbox" aria-label={`Create tickets for ${r.label}`} checked={r.enabled} disabled={saving === r.key}
                    onChange={(e) => full(r, { enabled: e.target.checked })} />
                </td>
                <td className="py-2 pr-3">
                  <div className="font-medium">{r.label}</div>
                  <div className="font-mono text-[11px] text-muted-foreground">{r.key}</div>
                </td>
                <td className="py-2 pr-3"><Badge variant="outline" className="text-[10px]">{labelOf(SOURCE_LABELS, r.source)}</Badge></td>
                {(["priority", "category", "queue"] as const).map((field) => (
                  <td key={field} className="py-2 pr-3">
                    <select className={FIELD} aria-label={`${r.label} ${field}`} value={r[field]} disabled={saving === r.key || !meta}
                      onChange={(e) => full(r, { [field]: e.target.value })}>
                      {((field === "priority" ? meta?.priorities : field === "category" ? meta?.categories : meta?.queues) ?? [r[field]]).map((v) => (
                        <option key={v} value={v}>{labelOf(field === "category" ? CATEGORY_LABELS : {}, v)}</option>
                      ))}
                    </select>
                  </td>
                ))}
                <td className="py-2 pr-3">
                  <select className={FIELD} aria-label={`${r.label} also create`} value={r.outcome ?? "ticket"} disabled={saving === r.key}
                    onChange={(e) => full(r, { outcome: e.target.value as RuleOutcome })}>
                    {Object.entries(outcomes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
                <td className="py-2 text-right">
                  {r.overridden && (
                    <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" disabled={saving === r.key} onClick={() => save(r, { reset: true })}>
                      <RotateCcw className="h-3 w-3" /> Reset
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Ignored as noise: {noise.join(", ")}, and anything logged at debug or info level.</p>
    </div>
    </div>
  )
}
