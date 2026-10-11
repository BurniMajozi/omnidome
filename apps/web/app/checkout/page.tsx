"use client"
import { useEffect, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { QuoteSummation } from "@/components/pricing/quote-summation"
import { PricingSelector, TenantPricingCard } from "@/components/pricing/tenant-pricing"
import { adminApi, adminErrorMessage } from "@/lib/admin-api"
import { defaultSelection, type PricingSelection, type PlatformOrder } from "@/lib/platform-pricing"

export default function CheckoutPage() {
  const [selection, setSelection] = useState<PricingSelection>(defaultSelection)
  const [tenant, setTenant] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [intent, setIntent] = useState<"invoice" | "subscription">("invoice")
  const [order, setOrder] = useState<PlatformOrder | null>(null)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [busy, setBusy] = useState(false)
  const [key, setKey] = useState("")
  const [canBuy, setCanBuy] = useState(false)
  useEffect(() => {
    setKey(crypto.randomUUID())
    try { const saved = JSON.parse(localStorage.getItem("omnidome.pricing.selection") || "null"); if (saved?.modules && ["monthly", "annually"].includes(saved.period)) setSelection(saved) } catch { /* Start from the public default. */ }
    adminApi.whoami().then(async who => {
      setTenant(who.tenant_id); setCanBuy(who.roles.some(r => ["owner", "org_admin", "platform_admin"].includes(r)))
      const returned = new URLSearchParams(window.location.search).get("order")
      if (returned && /^[0-9a-f-]{36}$/i.test(returned)) { const result = await adminApi.platformVerify(who.tenant_id, returned); setMessage(`Payment status: ${result.status}${result.subscription_status ? ` · recurring billing: ${result.subscription_status}` : ""}`) }
    }).catch(e => setError(adminErrorMessage(e))).finally(() => setLoaded(true))
  }, [])
  const change = (next: PricingSelection) => { setSelection(next); setOrder(null); setKey(crypto.randomUUID()); localStorage.setItem("omnidome.pricing.selection", JSON.stringify(next)) }
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(""); try { await fn() } catch (e) { setError(adminErrorMessage(e)) } finally { setBusy(false) } }
  return <main className="max-w-3xl mx-auto p-5 sm:p-10 space-y-6">
    <Link href="/pricing" className="text-sm underline">Back to pricing</Link><h1 className="text-3xl font-semibold">Your organisation’s plan</h1>
    <p className="text-muted-foreground">Choose a bundle or individual modules, review the full invoice, then pay securely through Paystack.</p>
    <PricingSelector value={selection} onChange={change} disabled={busy || !!order} tenant={canBuy ? tenant : null} />
    {!loaded ? <p>Checking your organisation…</p> : !tenant ? <div className="rounded border p-4 space-y-3"><p>Sign in as your Organisation Admin to continue. New organisations are provisioned by the Platform Owner and receive an invitation.</p><Button asChild><Link href="/auth?next=%2Fcheckout">Sign in to continue</Link></Button></div> : !canBuy ? <p>Your Organisation Admin manages this subscription. Ask them to complete checkout.</p> : <>
      {!order ? <><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={intent === "subscription"} onChange={e => { setIntent(e.target.checked ? "subscription" : "invoice"); setKey(crypto.randomUUID()) }} disabled={busy} />Automatically renew this subscription each billing period</label><Button disabled={busy} onClick={() => run(async () => { setOrder(await adminApi.createPlatformOrder(tenant, selection, intent, key)) })}>Create invoice for review</Button></> : <div className="rounded border p-4 space-y-3"><p className="font-medium">{order.reference}</p><QuoteSummation quote={order.quote} /><p>{order.quote.period} · {order.status}</p>{order.subscription_status && <p role="status" className="text-sm">Recurring billing: {order.subscription_status}. If authorization or review is needed, automatic renewal is not yet confirmed.</p>}<p className="text-sm">{order.quote.entitlements.join(", ")} · {order.quote.seats} seats</p><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => run(() => adminApi.downloadPlatformInvoice(tenant, order))}>Download invoice</Button>{order.status !== "paid" && <Button disabled={busy} onClick={() => run(async () => { const result = await adminApi.platformCheckout(tenant, order.id); window.location.assign(result.authorization_url) })}>Continue to Paystack</Button>}<Button variant="ghost" onClick={() => change(selection)}>Edit selection</Button></div></div>}
      <TenantPricingCard tenant={tenant} editable={false} />
    </>}
    {message && <p role="status">{message}</p>}{error && <p role="alert" className="text-destructive text-sm">{error}</p>}
  </main>
}
