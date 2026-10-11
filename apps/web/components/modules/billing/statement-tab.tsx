"use client"

/** Monthly card-collections statement: what customers paid, OmniDome's fee, what reached your bank, and money out. */

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { NotConnected } from "@/components/ui/not-connected"
import { fetchFeeInvoiceHtml, getGatewayStatement, listFeeInvoices, type FeeInvoice, type GatewayStatement } from "@/lib/billing-api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { NoDataYet } from "@/components/ui/not-connected"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { Field, Note, inputClass } from "./shared"

/** "2026-03" -> "March 2026". */
export const periodLabel = (p: string) => {
  const d = new Date(`${p}-01T00:00:00`)
  return Number.isNaN(d.getTime()) ? p : d.toLocaleDateString("en-GB", { month: "long", year: "numeric" })
}

/** Opens (or saves) a fee invoice. The popup is opened first so the browser treats it as a user action. Returns an error message or null. */
export async function showFeeInvoice(inv: Pick<FeeInvoice, "id" | "number">, mode: "view" | "download"): Promise<string | null> {
  const win = mode === "view" ? window.open("", "_blank") : null
  if (mode === "view" && !win) return "Allow pop-ups to view the invoice."
  const r = await fetchFeeInvoiceHtml(inv.id)
  if (!r.ok) {
    win?.close()
    return r.message
  }
  const url = URL.createObjectURL(new Blob([r.html], { type: "text/html" }))
  if (win) win.location.href = url
  else {
    const a = document.createElement("a")
    a.href = url
    a.download = `${inv.number}.html`
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
  return null
}


const currentPeriod = () => new Date().toISOString().slice(0, 7)

export function StatementTab() {
  const [period, setPeriod] = useState(currentPeriod())
  const [data, setData] = useState<Loadable<GatewayStatement>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  const validPeriod = /^\d{4}-(0[1-9]|1[0-2])$/.test(period)

  useEffect(() => {
    if (!validPeriod) return
    let off = false
    setData({ state: "loading" })
    getGatewayStatement(period).then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [period, validPeriod, tick])

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <CardTitle className="text-base">Statement</CardTitle>
          <Field label="Month" className="w-44">
            <input type="month" className={inputClass} value={period} max={currentPeriod()} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {!validPeriod ? (
          <Note tone="error">Choose a valid month.</Note>
        ) : data.state === "error" && data.status === 400 ? (
          <Note tone="error">{data.message || "That month is not valid."}</Note>
        ) : data.state !== "ready" ? (
          <NotConnected loadable={data} service="Billing" onRetry={reload} />
        ) : (
          <Body s={data.data} />
        )}
      </CardContent>
      <FeeInvoices />
    </Card>
  )
}

function FeeInvoices() {
  const [data, setData] = useState<Loadable<{ invoices: FeeInvoice[] }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let off = false
    listFeeInvoices().then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [tick])

  const act = async (inv: FeeInvoice, mode: "view" | "download") => {
    setBusy(`${mode}-${inv.id}`)
    setErr(null)
    setErr(await showFeeInvoice(inv, mode))
    setBusy(null)
  }

  return (
    <CardContent className="space-y-3 border-t border-border pt-4">
      <h4 className="text-sm font-semibold text-foreground">Tax invoices from OmniDome</h4>
      <p className="text-xs text-muted-foreground">Use these to claim the VAT on OmniDome&apos;s fees if you are VAT registered.</p>
      {err && <Note tone="error">{err}</Note>}
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={() => setTick((t) => t + 1)} />
      ) : (data.data.invoices ?? []).length === 0 ? (
        <NoDataYet message="Your first fee invoice is issued after the first full month in which OmniDome charged gateway or payout fees." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">Number</th>
                <th className="px-3 py-2">Month</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2 text-right">Subtotal (excl. VAT)</th>
                <th className="px-3 py-2 text-right">VAT</th>
                <th className="px-3 py-2 text-right">Total</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {data.data.invoices.map((i) => (
                <tr key={i.id} className="border-t border-border align-top">
                  <td className="px-3 py-2 font-mono text-xs">{i.number}</td>
                  <td className="px-3 py-2">{periodLabel(i.period)}</td>
                  <td className="px-3 py-2">
                    {i.doc_type === "Pro forma invoice" ? <Badge className="bg-secondary text-muted-foreground">{i.doc_type}</Badge> : i.doc_type}
                    {!i.complete && (
                      <span className="mt-1 block text-[11px] text-amber-400">
                        Incomplete: add your registered address in{" "}
                        <button type="button" className="underline" onClick={() => window.dispatchEvent(new CustomEvent("billing:open-tab", { detail: "tax" }))}>
                          VAT &amp; tax
                        </button>
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.subtotal_zar)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.vat_zar)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.total_zar)}</td>
                  <td className="px-3 py-2 text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="outline" disabled={!!busy} onClick={() => act(i, "view")}>
                        View
                      </Button>
                      <Button size="sm" variant="outline" disabled={!!busy} onClick={() => act(i, "download")}>
                        Download
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CardContent>
  )
}

function Body({ s }: { s: GatewayStatement }) {
  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-1">
        <Line k="Collected from your customers" v={fmtMoney(s.collections.collected_zar)} hint={`${s.collections.charges} card payment${s.collections.charges === 1 ? "" : "s"}`} />
        <Line k="OmniDome gateway fee (excl. VAT)" v={`-${fmtMoney(s.collections.commission_zar)}`} />
        {s.collections.commission_vat_zar !== undefined && <Line k="VAT on gateway fee" v={`-${fmtMoney(s.collections.commission_vat_zar)}`} />}
        <Line k="Paid to your bank (you receive)" v={fmtMoney(s.collections.you_receive_zar)} bold />
        <p className="text-xs text-muted-foreground">
          {s.settlement_checks.verified} of {s.settlement_checks.total} payments verified against Paystack.
        </p>
      </section>
      <section className="space-y-1 border-t border-border pt-3">
        <Line k="Refunds" v={`-${fmtMoney(s.refunds.total_zar)}`} hint={`${s.refunds.count} refund${s.refunds.count === 1 ? "" : "s"}`} />
        <Line k="Chargebacks" v={`-${fmtMoney(s.chargebacks.total_zar)}`} hint={`${s.chargebacks.count} lost dispute${s.chargebacks.count === 1 ? "" : "s"}`} />
      </section>
      <section className="space-y-1 border-t border-border pt-3">
        <Line k="Payouts" v={fmtMoney(s.payouts.total_zar)} hint={`${s.payouts.count} payment${s.payouts.count === 1 ? "" : "s"}`} />
        <Line k="Payout fees (excl. VAT)" v={fmtMoney(s.payouts.fees_zar)} hint={s.payouts.fees_vat_zar !== undefined ? `plus VAT ${fmtMoney(s.payouts.fees_vat_zar)}` : undefined} />
      </section>
      <section className="space-y-1 border-t border-border pt-3">
        <Line k="Payout wallet balance" v={fmtMoney(s.payout_wallet_zar)} bold />
        <Line k="Refunds and chargebacks owed to OmniDome" v={fmtMoney(s.open_liabilities_zar)} />
      </section>
      {s.fees_exclude_vat && <p className="text-xs text-muted-foreground">OmniDome&apos;s fees exclude VAT; 15% VAT is added.</p>}
    </div>
  )
}

function Line({ k, v, hint, bold }: { k: string; v: string; hint?: string; bold?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 ${bold ? "font-semibold text-foreground" : "text-foreground"}`}>
      <span>
        {k}
        {hint && <span className="ml-2 text-xs font-normal text-muted-foreground">{hint}</span>}
      </span>
      <span className="tabular-nums">{v}</span>
    </div>
  )
}
