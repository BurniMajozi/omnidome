"use client"

import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { supportApi, type TicketSettings } from "@/lib/support-api"
import { JEV_MODE_LABELS, NOTIFY_TRIGGERS } from "@/lib/support-derive"

const FIELD = "h-8 rounded-md border border-input bg-background px-2 text-xs"

/** Who is told what about a ticket, and how far Jev may act on its own. */
export function TicketSettingsPanel() {
  const [settings, setSettings] = useState<TicketSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    supportApi.settings().then(setSettings).catch((e) => setError(e instanceof Error ? e.message : "Could not load the settings"))
  }, [])

  const save = async (patch: Partial<TicketSettings>) => {
    setSaving(true)
    setError(null)
    try {
      setSettings(await supportApi.saveSettings(patch))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save")
    } finally {
      setSaving(false)
    }
  }

  if (!settings) {
    return <div className="surface-card flex min-h-24 items-center justify-center p-4 text-sm text-muted-foreground">{error ? <p role="alert">{error}</p> : <Loader2 className="h-4 w-4 animate-spin" aria-label="Loading settings" />}</div>
  }

  const canEdit = settings.can_edit !== false
  const disabled = saving || !canEdit
  const channels = (settings.deliverable_channels ?? ["email"]).join(", ")

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="surface-card p-5" aria-label="Telling the requester">
        <h3 className="section-title">Telling the requester</h3>
        <p className="mb-3 mt-1 text-sm text-muted-foreground">
          The requester hears back on the channel they used to reach you. Right now that works for: {channels}. For other channels the ticket
          records that they were not told, so nothing is silently missed. Wording is fixed, and internal notes are never sent.
        </p>
        <label className="mb-3 flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" checked={settings.notify_enabled} disabled={disabled} onChange={(e) => void save({ notify_enabled: e.target.checked })} />
          Keep requesters informed
        </label>
        <ul className="space-y-2">
          {NOTIFY_TRIGGERS.map((t) => (
            <li key={t.key}>
              <label className="flex items-start gap-2 text-sm">
                <input className="mt-1" type="checkbox" checked={settings[t.key]} disabled={disabled || !settings.notify_enabled} onChange={(e) => void save({ [t.key]: e.target.checked })} />
                <span>
                  <span className="font-medium">{t.label}</span>
                  <span className="block text-xs text-muted-foreground">{t.help}</span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      <section className="surface-card p-5" aria-label="Jev routing and review">
        <h3 className="section-title">Jev: routing and review</h3>
        <p className="mb-3 mt-1 text-sm text-muted-foreground">
          Jev reads each new ticket and proposes its queue, category, priority, whether it also needs a task, escalation or scheduled item, and who should take it.
          It also judges, when a ticket closes, whether it was properly resolved, and whether a late ticket needs a supervisor. It never closes or deletes anything,
          and every proposal is kept with how sure it was.
        </p>
        <label className="mb-1 block text-xs text-muted-foreground" htmlFor="jev-mode">How far Jev may go</label>
        <select id="jev-mode" className={FIELD} value={settings.jev_routing_mode} disabled={disabled}
          onChange={(e) => void save({ jev_routing_mode: e.target.value as TicketSettings["jev_routing_mode"] })}>
          {(settings.jev_modes ?? Object.keys(JEV_MODE_LABELS)).map((m) => <option key={m} value={m}>{JEV_MODE_LABELS[m] ?? m}</option>)}
        </select>
        <p className="mt-1 text-xs text-muted-foreground">
          {settings.jev_routing_mode === "off" && "Jev is never asked unless someone presses “Ask Jev” on a ticket (then it is only a suggestion)."}
          {settings.jev_routing_mode === "suggest" && "Jev proposes; a person presses Apply. Nothing changes by itself."}
          {settings.jev_routing_mode === "auto" && "Jev applies what it is at least 90% sure of and suggests the rest. Late tickets it is very sure about are escalated."}
        </p>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={settings.jev_review_on_close} disabled={disabled} onChange={(e) => void save({ jev_review_on_close: e.target.checked })} />
          Check the resolution when a ticket is closed
        </label>
        <p className="mt-2 text-xs text-muted-foreground">Ticket text is sent to Jev for this. It is skipped when your deployment keeps data inside the platform.</p>
      </section>
      {error && <p role="alert" className="text-sm text-red-400 lg:col-span-2">{error}</p>}
      {!canEdit && <p className="text-xs text-muted-foreground lg:col-span-2">Only managers can change these settings.</p>}
    </div>
  )
}
