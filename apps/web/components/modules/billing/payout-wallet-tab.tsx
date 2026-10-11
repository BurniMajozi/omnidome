"use client"

/**
 * Payout wallet: the pre-funded balance that payroll payouts are paid from. Shows the balance and
 * ledger, tops up by card (Paystack checkout), quotes the fee for a payment, lists recent payout
 * batches, and (platform admins only) records an EFT received.
 */

import { useCallback, useEffect, useState } from "react"
import { ChevronDown, ChevronRight, RefreshCcw, Wallet } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import {
  getPayoutWallet,
  initializeWalletFunding,
  listPendingGatewayChanges,
  listPayoutBatches,
  quotePayout,
  reconcilePayoutBatch,
  recordManualFunding,
  useBillingTier,
  type PayoutBatch,
  type PayoutQuote,
  type PayoutWallet,
} from "@/lib/billing-api"
import { getSessionSafe } from "@/lib/supabase/client"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { ConfirmModal } from "./confirm-modal"
import { Field, Note, fmtDateTime, humanise, inputClass, tierTip, useActionState } from "./shared"

const KIND_LABEL: Record<string, string> = {
  funding: "Card funding",
  manual_funding: "EFT received",
  payout: "Payout",
  payout_fee: "Payout fee (incl. VAT)",
  reversal: "Returned (transfer failed)",
  fee_reversal: "Fee + VAT returned",
  liability_recovery: "Refund/chargeback recovery",
}
const CREDITS = new Set(["funding", "manual_funding", "reversal", "fee_reversal"])

const batchTone = (s: string) => (s === "completed" ? "badge-success" : s === "failed" ? "badge-danger" : s === "processing" || s === "partial" || s === "pending" ? "badge-warning" : "bg-secondary text-muted-foreground")
const isFinal = (s: string) => s === "completed" || s === "failed"

export function PayoutWalletTab() {
  const { isAdmin } = useBillingTier()
  const [wallet, setWallet] = useState<Loadable<PayoutWallet>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    let off = false
    setWallet({ state: "loading" })
    getPayoutWallet().then((l) => !off && setWallet(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <div className="space-y-4">
      <Card className="border-border bg-card">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Wallet className="h-4 w-4" />
              Payout wallet
            </CardTitle>
            <Button size="sm" variant="ghost" onClick={reload}>
              <RefreshCcw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {wallet.state !== "ready" ? (
            <NotConnected loadable={wallet} service="Billing" onRetry={reload} />
          ) : (
            <>
              <p className="text-3xl font-bold tabular-nums text-foreground">{fmtMoney(wallet.data.balance_zar)}</p>
              <p className="text-xs text-muted-foreground">Available for payroll payouts. Payroll can only be paid from this balance.</p>
              {wallet.data.open_liabilities_zar > 0 && (
                <Note tone="info">{fmtMoney(wallet.data.open_liabilities_zar)} of refunds/chargebacks will be deducted from your next funding.</Note>
              )}
              {(wallet.data.entries ?? []).length === 0 ? (
                <NoDataYet message="No wallet activity yet." />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-sm">
                    <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2">Date</th>
                        <th className="px-3 py-2">Type</th>
                        <th className="px-3 py-2">Note</th>
                        <th className="px-3 py-2 text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wallet.data.entries.map((e, i) => {
                        const credit = CREDITS.has(e.kind)
                        return (
                          <tr key={`${e.created_at}-${i}`} className="border-t border-border">
                            <td className="px-3 py-2">{fmtDateTime(e.created_at)}</td>
                            <td className="px-3 py-2">{KIND_LABEL[e.kind] ?? humanise(e.kind)}</td>
                            <td className="px-3 py-2 text-muted-foreground">{e.note || "—"}</td>
                            <td className={`px-3 py-2 text-right tabular-nums ${credit ? "text-emerald-400" : ""}`}>
                              {credit ? "+" : "-"}
                              {fmtMoney(Math.abs(e.amount_zar))}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <AddFunds isAdmin={isAdmin} />
        <QuoteCard />
      </div>

      <RecentPayouts isAdmin={isAdmin} />
      <ManualFunding onDone={reload} />
    </div>
  )
}

// ------------------------------------------------------------------ add funds

function AddFunds({ isAdmin }: { isAdmin: boolean }) {
  const [amount, setAmount] = useState("")
  const [email, setEmail] = useState("")
  const act = useActionState()
  useEffect(() => {
    let off = false
    getSessionSafe()
      .then(({ data }) => {
        const e = data?.session?.user?.email
        if (!off && e) setEmail((cur) => cur || e)
      })
      .catch(() => {})
    return () => {
      off = true
    }
  }, [])

  const n = Number(amount)
  const valid = amount.trim() !== "" && Number.isFinite(n) && n > 0 && /^\S+@\S+\.\S+$/.test(email.trim())

  const submit = async () => {
    const r = await act.run("fund", () => initializeWalletFunding({ amount_zar: Number(n.toFixed(2)), email: email.trim() }))
    const url = r?.authorization_url
    if (!r) return
    let ok = false
    try {
      const u = new URL(String(url))
      ok = u.protocol === "https:" && u.hostname === "checkout.paystack.com"
    } catch {
      ok = false
    }
    if (ok) window.location.assign(String(url))
    else act.setMsg({ tone: "error", text: "The payment page address was not recognised, so you were not redirected. Please contact support." })
  }

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Add funds</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Amount in ZAR">
            <input className={inputClass} inputMode="decimal" value={amount} disabled={!isAdmin} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Email for the payment receipt">
            <input type="email" className={inputClass} value={email} disabled={!isAdmin} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        </div>
        {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
        <Button size="sm" disabled={!isAdmin || !valid || !!act.busy} title={isAdmin ? undefined : tierTip("admin")} onClick={submit}>
          {act.busy ? "Starting…" : "Pay by card"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Paying a large payroll? Card payments cost more to process. Pay by EFT instead and we will credit the wallet once it reflects: contact support with your proof of payment.
        </p>
      </CardContent>
    </Card>
  )
}

// ------------------------------------------------------------------ quote

function QuoteCard() {
  const [amount, setAmount] = useState("")
  const [quote, setQuote] = useState<PayoutQuote | null>(null)
  const act = useActionState()
  const n = Number(amount)
  const valid = amount.trim() !== "" && Number.isFinite(n) && n > 0

  const check = async () => {
    setQuote(null)
    const r = await act.run("quote", () => quotePayout(Number(n.toFixed(2))))
    if (r) setQuote(r)
  }

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Check a payment</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Amount to pay out (ZAR)" className="w-48">
            <input className={inputClass} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} onKeyDown={(e) => e.key === "Enter" && valid && void check()} />
          </Field>
          <Button size="sm" variant="outline" disabled={!valid || !!act.busy} onClick={check}>
            {act.busy ? "Checking…" : "Check"}
          </Button>
        </div>
        {act.msg?.tone === "error" && <Note tone="error">{act.msg.text}</Note>}
        {quote && (
          <Note tone={quote.shortfall_zar > 0 ? "error" : "success"}>
            {quote.shortfall_zar > 0
              ? `Needed in the wallet: ${fmtMoney(quote.required_zar)} (fee excl. VAT ${fmtMoney(quote.fee_zar)}, VAT ${fmtMoney(quote.vat_zar ?? 0)}); shortfall ${fmtMoney(quote.shortfall_zar)}.`
              : `Covered. Needed in the wallet: ${fmtMoney(quote.required_zar)} (fee excl. VAT ${fmtMoney(quote.fee_zar)}, VAT ${fmtMoney(quote.vat_zar ?? 0)}) and you have ${fmtMoney(quote.balance_zar)}.`}
          </Note>
        )}
      </CardContent>
    </Card>
  )
}

// ------------------------------------------------------------------ batches

function RecentPayouts({ isAdmin }: { isAdmin: boolean }) {
  const [data, setData] = useState<Loadable<{ batches: PayoutBatch[] }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [open, setOpen] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listPayoutBatches().then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [tick])

  const refresh = async (id: string) => {
    setBusyId(id)
    setError(null)
    const r = await reconcilePayoutBatch(id)
    setBusyId(null)
    if (r.ok && r.data) {
      const updated = r.data
      setData((d) => (d.state === "ready" ? { state: "ready", data: { batches: d.data.batches.map((b) => (b.id === id ? { ...b, ...updated } : b)) } } : d))
    } else setError(r.message ?? "Could not refresh this payout.")
  }

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Recent payouts</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <Note tone="error">{error}</Note>}
        {data.state !== "ready" ? (
          <NotConnected loadable={data} service="Billing" onRetry={reload} />
        ) : (data.data.batches ?? []).length === 0 ? (
          <NoDataYet message="No payouts yet." />
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-8 px-2 py-2" />
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Paid / failed</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-right">Fee</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {data.data.batches.map((b) => {
                  const expanded = open === b.id
                  return (
                    <BatchRows key={b.id} b={b} expanded={expanded} onToggle={() => setOpen(expanded ? null : b.id)} isAdmin={isAdmin} busy={busyId === b.id} onRefresh={() => refresh(b.id)} />
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function BatchRows({ b, expanded, onToggle, isAdmin, busy, onRefresh }: { b: PayoutBatch; expanded: boolean; onToggle: () => void; isAdmin: boolean; busy: boolean; onRefresh: () => void }) {
  const counts = b.counts ?? { pending: 0, processing: 0, success: 0, failed: 0 }
  return (
    <>
      <tr className="border-t border-border">
        <td className="px-2 py-2">
          <button type="button" aria-label={expanded ? "Hide payments" : "Show payments"} onClick={onToggle}>
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </td>
        <td className="px-3 py-2">{fmtDateTime(b.created_at)}</td>
        <td className="px-3 py-2">{humanise(b.kind)}</td>
        <td className="px-3 py-2">
          <Badge className={batchTone(b.status)}>{humanise(b.status)}</Badge>
        </td>
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {counts.success} paid{counts.processing + counts.pending > 0 ? `, ${counts.processing + counts.pending} in progress` : ""}
          {counts.failed > 0 ? `, ${counts.failed} failed` : ""}
        </td>
        <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(b.total_zar)}</td>
        <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(b.fee_zar)}</td>
        <td className="px-3 py-2 text-right">
          {!isFinal(b.status) && (
            <Button size="sm" variant="outline" disabled={!isAdmin || busy} title={isAdmin ? undefined : tierTip("admin")} onClick={onRefresh}>
              {busy ? "Refreshing…" : "Refresh status"}
            </Button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-t border-border bg-secondary/10">
          <td />
          <td colSpan={7} className="px-3 py-2">
            {(b.items ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">No individual payments recorded.</p>
            ) : (
              <ul className="divide-y divide-border text-xs">
                {b.items.map((it) => (
                  <li key={it.item_ref} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                    <span>
                      {it.reference || it.item_ref}
                      {it.message && <span className="ml-2 text-muted-foreground">{it.message}</span>}
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge className={it.status === "success" ? "badge-success" : it.status === "failed" ? "badge-danger" : "badge-warning"}>{humanise(it.status)}</Badge>
                      <span className="tabular-nums">{fmtMoney(it.amount_zar)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ------------------------------------------------------------------ platform admin

/** Platform admins only. The gateway approvals list answers 403 for everyone else, which is used as the probe to hide this section. */
function ManualFunding({ onDone }: { onDone: () => void }) {
  const [tenant, setTenant] = useState("")
  const [amount, setAmount] = useState("")
  const [ref, setRef] = useState("")
  const [confirming, setConfirming] = useState(false)
  const [hidden, setHidden] = useState(true)
  const act = useActionState()
  useEffect(() => {
    let off = false
    listPendingGatewayChanges().then((l) => !off && setHidden(l.state !== "ready"))
    return () => {
      off = true
    }
  }, [])

  const n = Number(amount)
  const valid = /^[0-9a-fA-F-]{32,36}$/.test(tenant.trim()) && Number.isFinite(n) && n > 0 && ref.trim().length > 0

  // A 403 means the caller is not a platform admin: hide the section completely.
  if (hidden) return null

  const submit = async () => {
    const r = await act.run("manual", async () => {
      const res = await recordManualFunding({ tenant_id: tenant.trim(), amount_zar: Number(n.toFixed(2)), bank_reference: ref.trim() })
      if (res.status === 403 || res.status === 404) setHidden(true)
      return res
    })
    if (r === undefined) return
    setConfirming(false)
    if (r?.credited === false) act.setMsg({ tone: "info", text: "Already recorded. This bank reference was credited before, so nothing was added." })
    else {
      act.setMsg({ tone: "success", text: "EFT recorded and the wallet credited." })
      onDone()
    }
  }

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Record an EFT (platform admin)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Tenant ID">
            <input className={inputClass} value={tenant} onChange={(e) => setTenant(e.target.value)} />
          </Field>
          <Field label="Amount in ZAR">
            <input className={inputClass} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="Bank reference">
            <input className={inputClass} value={ref} onChange={(e) => setRef(e.target.value)} />
          </Field>
        </div>
        {act.msg && !confirming && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
        <Button size="sm" disabled={!valid} onClick={() => { act.clear(); setConfirming(true) }}>
          Record EFT
        </Button>
      </CardContent>
      <ConfirmModal
        open={confirming}
        onOpenChange={setConfirming}
        title="Record EFT"
        confirmLabel={`Credit ${fmtMoney(valid ? n : 0)}`}
        busy={act.busy === "manual"}
        error={act.msg?.tone === "error" ? act.msg.text : null}
        onConfirm={submit}
      >
        <p>
          This credits {fmtMoney(n)} to the payout wallet of tenant {tenant.trim()} for bank reference {ref.trim()}. Only record an EFT that has reflected in the bank account.
        </p>
      </ConfirmModal>
    </Card>
  )
}
