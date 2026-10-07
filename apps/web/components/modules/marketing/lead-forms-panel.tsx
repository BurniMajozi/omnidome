"use client"

import { useState } from "react"
import { AlertTriangle, CheckCircle, Info, Loader2, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useMarketingLoad } from "@/lib/use-marketing-load"
import { invalidateMarketingCache } from "@/lib/marketing-api"
import {
  adLeadsPath,
  leadFormsPath,
  resultMessage,
  syncLeadForms,
  syncLeads,
  type AdLeadsResponse,
  type LeadFormsResponse,
} from "@/lib/marketing-zernio-api"
import { ConnectAccountsDialog } from "./connect-flow"

function fieldPairs(fields: unknown): Array<[string, string]> {
  if (!fields) return []
  if (Array.isArray(fields)) {
    return fields
      .map((f): [string, string] | null => {
        if (f && typeof f === "object") {
          const o = f as Record<string, unknown>
          const k = String(o.name ?? o.key ?? o.label ?? "")
          const v = Array.isArray(o.values) ? o.values.join(", ") : String(o.value ?? "")
          return k ? [k, v] : null
        }
        return null
      })
      .filter((x): x is [string, string] => x !== null)
  }
  if (typeof fields === "object") {
    return Object.entries(fields as Record<string, unknown>).map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v ?? "")])
  }
  return []
}

const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "Never")

export function LeadFormsPanel() {
  const forms = useMarketingLoad<LeadFormsResponse>(leadFormsPath)
  const [formFilter, setFormFilter] = useState("")
  const leads = useMarketingLoad<AdLeadsResponse>(adLeadsPath(formFilter || undefined))
  const [syncing, setSyncing] = useState(false)
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null)
  const [showConnect, setShowConnect] = useState(false)

  const formList = forms.value.state === "ready" ? forms.value.data.forms ?? [] : []
  const leadList = leads.value.state === "ready" ? leads.value.data.leads ?? [] : []
  const sync = forms.value.state === "ready" ? forms.value.data.sync : undefined
  const apiNote = [forms, leads].map((l) => (l.value.state === "ready" ? (l.value.data.note as string | null | undefined) : null)).find(Boolean)
  const webhookOff = [forms, leads].some((l) => l.value.state === "ready" && l.value.data.webhook_subscribed === false)

  const reloadAll = () => {
    invalidateMarketingCache()
    forms.reload()
    leads.reload()
  }

  const syncAll = async () => {
    setSyncing(true)
    setNotice(null)
    const f = await syncLeadForms({})
    if (!f.ok) {
      setSyncing(false)
      setNotice({ ok: false, text: resultMessage(f) })
      return
    }
    const l = await syncLeads({ form_id: formFilter || undefined })
    setSyncing(false)
    const errs = [...(f.data?.errors ?? []), ...(l.ok ? l.data?.errors ?? [] : [])]
    const errText = errs.length ? ` Some accounts reported problems: ${errs.map((e) => (typeof e === "string" ? e : JSON.stringify(e))).join("; ")}` : ""
    if (!l.ok) {
      setNotice({ ok: false, text: `Forms synced (${f.data?.forms_synced ?? 0}), but leads could not be synced: ${resultMessage(l)}` })
    } else {
      setNotice({ ok: errs.length === 0, text: `Synced ${f.data?.forms_synced ?? 0} form(s); ${l.data?.leads_inserted ?? 0} new lead(s) of ${l.data?.leads_seen ?? 0} seen.${errText}` })
    }
    reloadAll()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-foreground">Instant Lead Forms</h3>
          <p className="text-xs text-muted-foreground">In-feed native forms for customer inquiries. Meta and LinkedIn only: Google, TikTok, Pinterest and X do not offer lead forms through the provider.</p>
        </div>
        <Button size="sm" variant="outline" onClick={syncAll} disabled={syncing}>
          {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />} Sync forms and leads
        </Button>
      </div>

      <div className={`flex items-start gap-2 rounded-lg border p-3 text-xs ${webhookOff ? "border-amber-500/30 bg-amber-500/5 text-amber-500" : "border-border bg-card/40 text-muted-foreground"}`}>
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <p>
          {apiNote ||
            "New leads reach OmniDome in real time only after an operator subscribes the provider webhook to the lead.received event (Meta). LinkedIn has no webhook, so its leads appear after a sync and are kept for 90 days. Use Sync forms and leads to pull them now."}
        </p>
      </div>

      {notice && (
        <p role={notice.ok ? "status" : "alert"} className={`flex items-start gap-2 text-xs ${notice.ok ? "text-emerald-500" : "text-red-400"}`}>
          {notice.ok ? <CheckCircle className="mt-0.5 h-3.5 w-3.5" /> : <AlertTriangle className="mt-0.5 h-3.5 w-3.5" />} {notice.text}
        </p>
      )}

      {forms.value.state !== "ready" ? (
        <NotConnected loadable={forms.value} service="The marketing service" onRetry={forms.reload} />
      ) : formList.length === 0 ? (
        <div className="space-y-3">
          <NoDataYet message="No lead forms synced yet. Connect a Meta or LinkedIn ads account, then use Sync forms and leads." />
          <Button size="sm" variant="outline" onClick={() => setShowConnect(true)}>
            Connect an ads account
          </Button>
          {sync?.last_error && <p className="text-xs text-red-400">Last sync failed: {sync.last_error}</p>}
        </div>
      ) : (
        <Card className="border-border bg-card">
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Form</th>
                  <th className="px-4 py-3 font-medium">Platform</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Leads</th>
                  <th className="px-4 py-3 font-medium">Last lead</th>
                  <th className="px-4 py-3 font-medium">Synced</th>
                </tr>
              </thead>
              <tbody>
                {formList.map((f) => (
                  <tr key={f.form_id} className="border-b border-border/60">
                    <td className="px-4 py-3">
                      <button type="button" className="text-left font-medium text-foreground hover:underline" onClick={() => setFormFilter(formFilter === f.form_id ? "" : f.form_id)}>
                        {f.name || f.form_id}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{f.platform ?? "Not reported"}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className="text-[10px]">{f.status ?? "Not reported"}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right text-foreground">{(f.lead_count ?? 0).toLocaleString()}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{when(f.last_lead_at)}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{when(f.synced_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
      {sync?.last_synced_at && <p className="text-[11px] text-muted-foreground">Last form sync: {when(sync.last_synced_at)}{sync.last_error ? ` (error: ${sync.last_error})` : ""}</p>}

      {formList.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-foreground">
              Leads{formFilter ? ` for ${formList.find((f) => f.form_id === formFilter)?.name ?? formFilter}` : ""}
              {leads.value.state === "ready" ? ` (${leads.value.data.total ?? leadList.length})` : ""}
            </h4>
            {formFilter && (
              <Button size="sm" variant="ghost" onClick={() => setFormFilter("")}>
                Show all forms
              </Button>
            )}
          </div>
          {leads.value.state !== "ready" ? (
            <NotConnected loadable={leads.value} service="The marketing service" onRetry={leads.reload} />
          ) : leadList.length === 0 ? (
            <NoDataYet message="No leads stored yet. They appear here after a sync or once the webhook delivers them." />
          ) : (
            <div className="space-y-2">
              {leadList.map((l) => (
                <Card key={l.lead_id} className="border-border bg-card">
                  <CardContent className="space-y-1 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span>{l.form_name || l.form_id || "Form"} · {l.platform ?? "platform not reported"}{l.is_organic ? " · organic" : ""}</span>
                      <span>{when(l.created_time)} · via {l.source ?? "sync"}</span>
                    </div>
                    <dl className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2">
                      {fieldPairs(l.fields).map(([k, v]) => (
                        <div key={k} className="flex gap-2">
                          <dt className="shrink-0 text-muted-foreground">{k.replace(/_/g, " ")}:</dt>
                          <dd className="min-w-0 break-words text-foreground">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {showConnect && (
        <ConnectAccountsDialog
          category="ads"
          returnTo="/dashboard?section=marketing&marketing_tab=ads"
          onClose={() => setShowConnect(false)}
          onConnected={() => {
            setShowConnect(false)
            reloadAll()
          }}
        />
      )}
    </div>
  )
}
