"use client"

/**
 * Refunds: credits that need money paid back to a customer, and the history of refunds already made.
 * A refund moves money and cannot be undone, so it always goes through a confirm step. Server errors
 * (400/422/502) carry a useful message and are shown as returned.
 */

import { useCallback, useEffect, useState } from "react"
import { RefreshCcw } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { createRefund, listRefundCredits, listRefunds, useBillingTier, type RefundCredit, type RefundRow } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { ConfirmModal } from "./confirm-modal"
import { Field, Modal, Note, fmtDateTime, humanise, inputClass, tierTip, useActionState } from "./shared"

const KIND_LABEL: Record<string, string> = {
  refund_required: "Credit note on a paid invoice",
  overpayment: "Overpayment",
  unallocated_payment: "Unallocated payment",
}

const statusTone = (s: string) => (s === "processed" ? "badge-success" : s === "failed" ? "badge-danger" : s === "pending" || s === "processing" ? "badge-warning" : "bg-secondary text-muted-foreground")

export function RefundsTab() {
  const { isAdmin } = useBillingTier()
  const [credits, setCredits] = useState<Loadable<{ credits: RefundCredit[] }>>({ state: "loading" })
  const [history, setHistory] = useState<Loadable<{ refunds: RefundRow[] }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [target, setTarget] = useState<RefundCredit | null>(null)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let off = false
    setCredits({ state: "loading" })
    setHistory({ state: "loading" })
    listRefundCredits().then((l) => !off && setCredits(l))
    listRefunds().then((l) => !off && setHistory(l))
    return () => {
      off = true
    }
  }, [tick])

  return (
    <div className="space-y-4">
      <Card className="border-border bg-card">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-base">Awaiting refund</CardTitle>
            <Button size="sm" variant="ghost" onClick={reload}>
              <RefreshCcw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {credits.state !== "ready" ? (
            <NotConnected loadable={credits} service="Billing" onRetry={reload} />
          ) : (credits.data.credits ?? []).length === 0 ? (
            <NoDataYet message="Nothing is waiting to be refunded." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Reason</th>
                    <th className="px-3 py-2 text-right">Remaining</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {credits.data.credits.map((c) => (
                    <tr key={c.id} className="border-t border-border">
                      <td className="px-3 py-2">{fmtDateTime(c.created_at)}</td>
                      <td className="px-3 py-2">{KIND_LABEL[c.kind] ?? humanise(c.kind)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{c.reason || "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {fmtMoney(c.remaining_zar)}
                        {c.remaining_zar !== c.amount_zar && <span className="block text-[11px] text-muted-foreground">of {fmtMoney(c.amount_zar)}</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button size="sm" disabled={!isAdmin} title={isAdmin ? undefined : tierTip("admin")} onClick={() => setTarget(c)}>
                          Refund
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Refund history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {history.state !== "ready" ? (
            <NotConnected loadable={history} service="Billing" onRetry={reload} />
          ) : (history.data.refunds ?? []).length === 0 ? (
            <NoDataYet message="No refunds have been made yet." />
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-secondary/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Date</th>
                    <th className="px-3 py-2">Method</th>
                    <th className="px-3 py-2">Reason</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {history.data.refunds.map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="px-3 py-2">{fmtDateTime(r.created_at)}</td>
                      <td className="px-3 py-2">{r.method === "paystack" ? "Back to card" : "Paid by EFT"}</td>
                      <td className="px-3 py-2 text-muted-foreground">{r.reason || "—"}</td>
                      <td className="px-3 py-2">
                        <Badge className={statusTone(r.status)}>{humanise(r.status)}</Badge>
                        {r.status === "failed" && r.failure_reason && <span className="mt-1 block text-[11px] text-red-400">{r.failure_reason}</span>}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(r.amount_zar)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs text-muted-foreground">Card refunds usually complete within a few business days. OmniDome keeps its gateway fee on refunded payments.</p>
        </CardContent>
      </Card>

      <RefundDialog credit={target} onClose={() => setTarget(null)} onDone={reload} />
    </div>
  )
}

function RefundDialog({ credit, onClose, onDone }: { credit: RefundCredit | null; onClose: () => void; onDone: () => void }) {
  const act = useActionState()
  const [method, setMethod] = useState<"paystack" | "manual">("manual")
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const [reference, setReference] = useState("")
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState(false)

  const cardOk = !!credit && credit.paystack_refundable_zar > 0
  const max = credit ? (method === "paystack" ? credit.paystack_refundable_zar : credit.remaining_zar) : 0

  useEffect(() => {
    if (!credit) return
    const m = credit.paystack_refundable_zar > 0 ? "paystack" : "manual"
    setMethod(m)
    setAmount((m === "paystack" ? credit.paystack_refundable_zar : credit.remaining_zar).toFixed(2))
    setReason(credit.reason ?? "")
    setReference("")
    setConfirming(false)
    setDone(false)
    act.clear()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credit])

  const pick = (m: "paystack" | "manual") => {
    if (!credit) return
    setMethod(m)
    setAmount((m === "paystack" ? credit.paystack_refundable_zar : credit.remaining_zar).toFixed(2))
  }

  const n = Number(amount)
  const amountOk = amount.trim() !== "" && Number.isFinite(n) && n > 0 && n <= max + 0.0001
  const valid = amountOk && reason.trim().length > 0 && (method === "paystack" || reference.trim().length > 0)

  const submit = async () => {
    if (!credit) return
    const r = await act.run("refund", () =>
      createRefund({ credit_id: credit.id, amount_zar: Number(n.toFixed(2)), reason: reason.trim(), method, ...(method === "manual" ? { manual_reference: reference.trim() } : {}) }),
    )
    if (r !== undefined) {
      setConfirming(false)
      setDone(true)
      onDone()
    }
  }

  return (
    <>
      <Modal open={!!credit && !confirming} onOpenChange={(o) => !o && onClose()} title="Refund customer" description={credit ? `${KIND_LABEL[credit.kind] ?? humanise(credit.kind)} · ${fmtMoney(credit.remaining_zar)} remaining` : undefined}>
        {done ? (
          <div className="space-y-3">
            <Note tone="success">{method === "paystack" ? "The refund has been submitted to the card network. It usually completes within a few business days." : "The EFT refund has been recorded."}</Note>
            <div className="flex justify-end">
              <Button size="sm" onClick={onClose}>
                Done
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <fieldset className="space-y-2 text-sm">
              <label className={`flex items-start gap-2 ${cardOk ? "" : "opacity-60"}`}>
                <input type="radio" name="refund-method" className="mt-1" checked={method === "paystack"} disabled={!cardOk} onChange={() => pick("paystack")} />
                <span>
                  Back to the customer&apos;s card (Paystack)
                  {!cardOk && <span className="block text-xs text-muted-foreground">The original payment was not by card; pay by EFT and record it below.</span>}
                  {cardOk && <span className="block text-xs text-muted-foreground">Up to {fmtMoney(credit?.paystack_refundable_zar)} can go back to the card.</span>}
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="refund-method" className="mt-1" checked={method === "manual"} onChange={() => pick("manual")} />
                <span>I paid it by EFT (record only)</span>
              </label>
            </fieldset>
            <Field label={`Amount in ZAR (maximum ${fmtMoney(max)})`}>
              <input className={inputClass} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
            <Field label="Reason">
              <input className={inputClass} value={reason} maxLength={300} onChange={(e) => setReason(e.target.value)} />
            </Field>
            {method === "manual" && (
              <Field label="Bank payment reference (required)">
                <input className={inputClass} value={reference} maxLength={100} onChange={(e) => setReference(e.target.value)} />
              </Field>
            )}
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button size="sm" disabled={!valid} onClick={() => { act.clear(); setConfirming(true) }}>
                Continue
              </Button>
            </div>
          </div>
        )}
      </Modal>
      <ConfirmModal
        open={!!credit && confirming}
        onOpenChange={(o) => !o && setConfirming(false)}
        title="Confirm refund"
        confirmLabel={`Refund ${fmtMoney(amountOk ? n : 0)}`}
        destructive
        busy={act.busy === "refund"}
        error={act.msg?.tone === "error" ? act.msg.text : null}
        onConfirm={submit}
      >
        <p>
          {method === "paystack"
            ? `${fmtMoney(n)} will be returned to the customer's card. This moves money and cannot be undone.`
            : `This records that you paid ${fmtMoney(n)} to the customer by EFT (reference ${reference.trim()}). It does not move any money. This cannot be undone.`}
        </p>
      </ConfirmModal>
    </>
  )
}
