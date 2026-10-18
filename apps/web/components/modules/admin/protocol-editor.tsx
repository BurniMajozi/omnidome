"use client"

import { useCallback, useEffect, useState } from "react"
import { Loader2, RotateCcw, Save } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { getProtocolPolicy, saveProtocolPolicy, type ProtocolPolicy } from "@/lib/orchestrator-api"
import { getProtocol, resetProtocol, saveProtocol, type ProcurementProtocol } from "@/lib/sourcing-api"
import { Field } from "../products/catalogue/shared"

const num = (v: string, fallback = 0) => (v === "" || Number.isNaN(Number(v)) ? fallback : Number(v))
const errText = (e: unknown, f: string) => (e instanceof Error ? e.message : f)

function Check({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start gap-2 text-xs">
      <input type="checkbox" className="mt-0.5" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span><span className="text-foreground">{label}</span>{hint && <span className="block text-[11px] text-muted-foreground">{hint}</span>}</span>
    </label>
  )
}

/** Editable limits for the commerce protocols agents work within: UCP carts, AP2 mandates and the procurement (buying) protocol. */
export function ProtocolEditor() {
  const [commerce, setCommerce] = useState<ProtocolPolicy | null>(null)
  const [buying, setBuying] = useState<ProcurementProtocol | null>(null)
  const [defaults, setDefaults] = useState<{ commerce?: ProtocolPolicy; buying?: ProcurementProtocol }>({})
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null)
  const [busy, setBusy] = useState<"commerce" | "buying" | null>(null)
  const [loadError, setLoadError] = useState<{ commerce?: string; buying?: string }>({})

  const load = useCallback(async () => {
    const [c, b] = await Promise.allSettled([getProtocolPolicy(), getProtocol()])
    const errs: { commerce?: string; buying?: string } = {}
    if (c.status === "fulfilled") { setCommerce(c.value.policy); setDefaults((d) => ({ ...d, commerce: c.value.defaults })) } else errs.commerce = errText(c.reason, "Unavailable")
    if (b.status === "fulfilled") { setBuying(b.value.protocol); setDefaults((d) => ({ ...d, buying: b.value.defaults })) } else errs.buying = errText(b.reason, "Unavailable")
    setLoadError(errs)
  }, [])
  useEffect(() => { void load() }, [load])

  async function saveCommerce() {
    if (!commerce) return
    setBusy("commerce")
    try { setCommerce(await saveProtocolPolicy(commerce)); setNotice({ text: "Cart and mandate limits saved. They apply to new carts and mandates." }) }
    catch (e) { setNotice({ text: errText(e, "Could not save"), error: true }) } finally { setBusy(null) }
  }
  async function saveBuying() {
    if (!buying) return
    setBusy("buying")
    try { await saveProtocol(buying); setNotice({ text: "Procurement protocol saved. It applies to the next request, for people and agents alike." }) }
    catch (e) { setNotice({ text: errText(e, "Could not save"), error: true }) } finally { setBusy(null) }
  }
  async function resetBuying() {
    setBusy("buying")
    try { const r = await resetProtocol(); setBuying(r.protocol); setNotice({ text: "Procurement protocol reset to the defaults." }) }
    catch (e) { setNotice({ text: errText(e, "Could not reset"), error: true }) } finally { setBusy(null) }
  }
  const setB = (patch: Partial<ProcurementProtocol>) => setBuying((b) => (b ? { ...b, ...patch } : b))
  const weightTotal = buying ? buying.weights.price + buying.weights.lead_time + buying.weights.performance + buying.weights.completeness : 0

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">Protocol policy <Badge variant="outline" className="text-[10px]">editable</Badge></CardTitle>
        <CardDescription>The limits your agents work within when they buy or hold payment mandates. Changes apply to new activity; what is already in progress keeps the rules it started under.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {notice && <p className={`rounded-md border px-3 py-2 text-xs ${notice.error ? "border-red-500/40 text-red-400" : "border-border text-foreground"}`} role={notice.error ? "alert" : "status"}>{notice.text}</p>}

        <section className="space-y-3 rounded-lg border border-border p-4" aria-label="Cart and mandate limits">
          <h4 className="text-sm font-semibold text-foreground">Carts (UCP) and payment mandates (AP2)</h4>
          {loadError.commerce && <p className="text-xs text-amber-400">Could not load these limits: {loadError.commerce}</p>}
          {commerce && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Auto-approve carts up to (R)" hint="Agent carts above this wait for a person."><Input type="number" min={0} value={commerce.ucp_auto_approve_limit_zar} onChange={(e) => setCommerce({ ...commerce, ucp_auto_approve_limit_zar: num(e.target.value) })} className="h-9 text-xs" /></Field>
                <Field label="Largest mandate amount (R)" hint="0 means no cap."><Input type="number" min={0} value={commerce.ap2_max_mandate_amount_zar} onChange={(e) => setCommerce({ ...commerce, ap2_max_mandate_amount_zar: num(e.target.value) })} className="h-9 text-xs" /></Field>
                <Field label="Longest a mandate stays valid (minutes)" hint="Up to 1440 (one day)."><Input type="number" min={1} max={1440} value={commerce.ap2_max_expiry_minutes} onChange={(e) => setCommerce({ ...commerce, ap2_max_expiry_minutes: num(e.target.value, 1440) })} className="h-9 text-xs" /></Field>
              </div>
              <Check label="Every mandate needs a person to confirm it" checked={commerce.ap2_force_user_confirmation} onChange={(v) => setCommerce({ ...commerce, ap2_force_user_confirmation: v })} />
              <div className="flex justify-end gap-2">
                {defaults.commerce && <Button type="button" variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={() => setCommerce(defaults.commerce!)}><RotateCcw className="h-3.5 w-3.5" /> Defaults</Button>}
                <Button type="button" size="sm" className="gap-1.5 text-xs" disabled={busy !== null} onClick={() => void saveCommerce()}>{busy === "commerce" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save limits</Button>
              </div>
            </>
          )}
        </section>

        <section className="space-y-4 rounded-lg border border-border p-4" aria-label="Procurement protocol">
          <div>
            <h4 className="text-sm font-semibold text-foreground">Procurement (buying stock)</h4>
            <p className="text-[11px] text-muted-foreground">How the buying agent and your team go to market: who may be asked, how many quotes you need, what needs approval, and how replies are scored.</p>
          </div>
          {loadError.buying && <p className="text-xs text-amber-400">Could not load the procurement protocol: {loadError.buying}</p>}
          {buying && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Check label="Internal suppliers may be asked" hint="Another business unit, your own warehouse or an in-house source." checked={buying.allow_internal} onChange={(v) => setB({ allow_internal: v })} />
                <Check label="External suppliers and web prospects may be asked" checked={buying.allow_external} onChange={(v) => setB({ allow_external: v })} />
                <Check label="Requests to suppliers must be approved before they are sent" hint="Agents can prepare drafts either way; nothing reaches a supplier without this approval." checked={buying.outreach_requires_approval} onChange={(v) => setB({ outreach_requires_approval: v })} />
                <Check label="The person who prepared a request may approve it" hint="Switch off to force a second person." checked={buying.allow_self_approval} onChange={(v) => setB({ allow_self_approval: v })} />
                <Check label="Our target price may appear in the message to suppliers" hint="Off by default: costs and prices stay private." checked={buying.share_target_price} onChange={(v) => setB({ share_target_price: v })} />
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                <Field label="Most suppliers per request"><Input type="number" min={1} max={25} value={buying.max_suppliers_per_request} onChange={(e) => setB({ max_suppliers_per_request: num(e.target.value, 5) })} className="h-9 text-xs" /></Field>
                <Field label="Quotes needed before an award"><Input type="number" min={1} max={10} value={buying.min_quotes_before_award} onChange={(e) => setB({ min_quotes_before_award: num(e.target.value, 2) })} className="h-9 text-xs" /></Field>
                <Field label="Escalate orders above (R)" hint="0 means no limit."><Input type="number" min={0} value={buying.rfq_budget_limit_zar} onChange={(e) => setB({ rfq_budget_limit_zar: num(e.target.value) })} className="h-9 text-xs" /></Field>
                <Field label="Minimum delivery score (0-100)" hint="0 means off."><Input type="number" min={0} max={100} value={buying.min_supplier_score} onChange={(e) => setB({ min_supplier_score: num(e.target.value) })} className="h-9 text-xs" /></Field>
                <Field label="Ask for replies within (days)"><Input type="number" min={1} max={60} value={buying.reply_window_days} onChange={(e) => setB({ reply_window_days: num(e.target.value, 5) })} className="h-9 text-xs" /></Field>
              </div>
              <div className="space-y-2">
                <div className="text-xs font-medium text-foreground">How replies are scored (relative weights{weightTotal > 0 ? `, ${weightTotal} in total` : ""})</div>
                <div className="grid gap-3 sm:grid-cols-4">
                  {([["price", "Price"], ["lead_time", "Lead time"], ["performance", "Delivery record"], ["completeness", "Completeness"]] as const).map(([k, label]) => (
                    <Field key={k} label={label}><Input type="number" min={0} max={100} value={buying.weights[k]} onChange={(e) => setB({ weights: { ...buying.weights, [k]: num(e.target.value) } })} className="h-9 text-xs" /></Field>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <div className="text-xs font-medium text-foreground">When to reorder (from product KPIs)</div>
                <div className="grid gap-3 sm:grid-cols-4">
                  <Field label="Hold stock for (days of sales)"><Input type="number" min={1} max={365} value={buying.reorder.cover_days} onChange={(e) => setB({ reorder: { ...buying.reorder, cover_days: num(e.target.value, 30) } })} className="h-9 text-xs" /></Field>
                  <Field label="Measure sales over (days)"><Input type="number" min={7} max={365} value={buying.reorder.lookback_days} onChange={(e) => setB({ reorder: { ...buying.reorder, lookback_days: num(e.target.value, 30) } })} className="h-9 text-xs" /></Field>
                  <Field label="Flag margins below (%)"><Input type="number" min={0} max={100} value={buying.reorder.min_margin_pct} onChange={(e) => setB({ reorder: { ...buying.reorder, min_margin_pct: num(e.target.value) } })} className="h-9 text-xs" /></Field>
                  <Field label="Most drafts per automatic scan"><Input type="number" min={1} max={50} value={buying.reorder.max_requests_per_scan} onChange={(e) => setB({ reorder: { ...buying.reorder, max_requests_per_scan: num(e.target.value, 5) } })} className="h-9 text-xs" /></Field>
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" size="sm" className="gap-1.5 text-xs" disabled={busy !== null} onClick={() => void resetBuying()}><RotateCcw className="h-3.5 w-3.5" /> Reset to defaults</Button>
                <Button type="button" size="sm" className="gap-1.5 text-xs" disabled={busy !== null || weightTotal <= 0} onClick={() => void saveBuying()}>{busy === "buying" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save protocol</Button>
              </div>
            </>
          )}
        </section>
      </CardContent>
    </Card>
  )
}
