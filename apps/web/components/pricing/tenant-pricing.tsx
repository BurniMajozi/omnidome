"use client"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { TenantUsageCard } from "@/components/pricing/tenant-usage"
import { adminApi, adminErrorMessage } from "@/lib/admin-api"
import { catalog, defaultSelection, selectedPanels, bundleSelection, type PricingTier, type PricingSelection, type PlatformQuote, type PlatformPricingState } from "@/lib/platform-pricing"

export function PricingSelector({ value, onChange, disabled = false }: { value: PricingSelection; onChange: (v: PricingSelection) => void; disabled?: boolean }) {
  const [quote, setQuote] = useState<PlatformQuote | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const panels = selectedPanels(value)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setQuote(null); setError("")
    const timer = setTimeout(async () => {
      try {
        const res = await fetch("/api/pricing/quote", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value), signal: controller.signal })
        const data = await res.json()
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Choose at least one panel and a valid seat count")
        setQuote(data)
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Unable to calculate pricing") }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [value])
  const changePanel = (id: string, tier?: PricingTier) => {
    const modules = { ...panels }
    if (tier) modules[id] = tier; else delete modules[id]
    onChange({ ...value, bundle: null, modules })
  }
  return <fieldset disabled={disabled} className="space-y-4 min-w-0">
    <legend className="font-medium mb-2">Plan and panel access</legend>
    <div className="grid gap-3 sm:grid-cols-3">
      <label className="text-sm space-y-1">Pricing<select className="block w-full rounded border bg-background p-2" value={value.bundle || "modular"} onChange={e => onChange(e.target.value === "modular" ? { ...value, bundle: null, modules: panels } : bundleSelection(e.target.value, value.period))}>
        {Object.entries(catalog.bundles).map(([id, b]) => <option key={id} value={id}>{b.name} bundle</option>)}<option value="modular">Choose individual modules</option>
      </select></label>
      <label className="text-sm space-y-1">Billing period<select className="block w-full rounded border bg-background p-2" value={value.period} onChange={e => onChange({ ...value, period: e.target.value as PricingSelection["period"] })}><option value="monthly">Monthly</option><option value="annually">Annually · 20% discount</option></select></label>
      <label className="text-sm space-y-1">User seats<input type="number" min={1} max={100000} required className="block w-full rounded border bg-background p-2" value={value.seats ?? 1} onChange={e => onChange({ ...value, seats: Number(e.target.value) })} /></label>
    </div>
    <p className="text-xs text-muted-foreground">Every member inherits the organisation’s selected panels. Organisation Admin can manage all enabled panels. Changing a bundled panel switches to modular pricing.</p>
    <div className="grid gap-2 sm:grid-cols-2">
      {catalog.modules.map(m => <div key={m.id} className="flex items-center justify-between gap-2 rounded border p-2">
        <label className="flex items-center gap-2 text-sm min-w-0"><input type="checkbox" checked={!!panels[m.id]} onChange={e => changePanel(m.id, e.target.checked ? "starter" : undefined)} />{m.name}</label>
        {panels[m.id] && <select aria-label={`${m.name} tier`} className="max-w-[130px] rounded border bg-background p-1 text-xs" value={panels[m.id]} onChange={e => changePanel(m.id, e.target.value as PricingTier)}>{["starter", "professional", "enterprise"].map(t => <option key={t}>{t}</option>)}</select>}
      </div>)}
    </div>
    <div aria-live="polite" className="rounded bg-secondary p-3 text-sm">
      {loading ? "Calculating your invoice…" : error ? <p className="text-destructive">{error}</p> : quote && <><p>{quote.name} · {quote.seats} seats · {quote.entitlements.length} panels</p><p>R{Number(quote.monthly_net_zar).toLocaleString("en-ZA")} / month before VAT</p><p className="font-semibold mt-1">Due {value.period === "annually" ? "annually" : "monthly"}: R{Number(quote.total_zar).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}</p><p className="text-xs text-muted-foreground">Includes R{quote.vat_zar} VAT. {value.period === "annually" && "The invoice covers 12 months upfront."}</p></>}
    </div>
  </fieldset>
}

export function TenantPricingCard({ tenant, editable, onChanged }: { tenant: string; editable: boolean; onChanged?: () => void }) {
  const [open, setOpen] = useState(false)
  const [selection, setSelection] = useState<PricingSelection>(defaultSelection)
  const [state, setState] = useState<PlatformPricingState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const load = async () => { const s = await adminApi.getPricing(tenant); setState(s); if (s.pricing.selection) setSelection(s.pricing.selection) }
  useEffect(() => { if (open) load().catch(e => setError(adminErrorMessage(e))) }, [open, tenant]) // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setError(""); setNotice(""); try { await fn() } catch (e) { setError(adminErrorMessage(e)) } finally { setBusy(false) } }
  return <div className="space-y-3 border-t pt-3">
    <Button variant="outline" size="sm" onClick={() => setOpen(!open)}>{open ? "Close pricing" : "Plan, panels & invoices"}</Button>
    {open && <>
      <TenantUsageCard tenant={tenant} platformOwner={editable}/>
      {!state ? <p className="text-sm">Loading tenant pricing…</p> : <>
        {editable ? <><PricingSelector value={selection} onChange={setSelection} disabled={busy} /><Button disabled={busy} onClick={() => run(async () => { await adminApi.setPricing(tenant, selection, crypto.randomUUID()); await load(); onChanged?.(); setNotice("Panel access saved. A platform invoice is ready for payment.") })}>Save panel access & create invoice</Button><p className="text-xs text-muted-foreground">Platform Owner changes take effect immediately. Saving creates an invoice; payment is a separate action.</p></> : <p className="text-sm">{state.pricing.quote?.name || "Negotiated plan"} · {state.pricing.quote?.seats || "—"} seats. Contact the Platform Owner to change panel access.</p>}
        {state.subscription && <div className="flex flex-wrap gap-2 items-center text-sm"><span>Subscription: {state.subscription.status}</span>{state.subscription.status !== "cancelled" && <Button size="sm" variant="outline" disabled={busy} onClick={() => run(async () => { await adminApi.cancelPlatformSubscription(tenant, state.subscription!.order_id); await load(); setNotice("Recurring subscription cancelled; current panel access is retained.") })}>Cancel recurring billing</Button>}</div>}
        <div className="space-y-2">{state.orders.map(order => <div key={order.id} className="rounded border p-3 text-sm space-y-2"><p className="break-all">{order.reference}</p><p>R{order.quote.total_zar} · {order.quote.period} · {order.status}</p><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => run(() => adminApi.downloadPlatformInvoice(tenant, order))}>Download invoice</Button>{["issued", "checkout"].includes(order.status) && <><Button size="sm" disabled={busy} onClick={() => run(async () => { const result = await adminApi.platformCheckout(tenant, order.id); window.location.assign(result.authorization_url) })}>Pay invoice</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => run(async () => { const result = await adminApi.platformVerify(tenant, order.id); await load(); setNotice(`Payment status: ${result.status}`) })}>Check payment</Button></>}</div></div>)}</div>
      </>}
      {notice && <p role="status" className="text-sm text-emerald-500">{notice}</p>}{error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </>}
  </div>
}
