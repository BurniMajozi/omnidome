"use client"

/**
 * Suggested next actions for one invoice (from GET /invoices/{id}/timeline).
 * An action with a real endpoint becomes a working button (with a confirm step for anything that
 * changes money, service or customer comms). An action whose endpoint is null is shown DISABLED with
 * the server's reason ("integration pending ..."): nothing here pretends it works.
 */

import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { recordPayment } from "@/lib/billing-api"
import { newIdempotencyKey, runSuggestedAction, type SuggestedAction } from "@/lib/invoicing-api"
import type { BillingTier } from "@/lib/billing-derive"
import { Field, Note, inputClass, tierAtLeast, tierTip, useActionState } from "../shared"

const NEEDS_CONFIRM = new Set(["issue_invoice", "send_reminder", "send_invoice_email", "offer_arrangement", "suspend_service", "void_invoice"])
/** Actions that are served by the Delivery / share section of the drawer instead of a one-click call. */
const LOCAL_SECTION = new Set(["share_pay_link", "send_invoice_email"])

export function SuggestedActions({
  actions,
  tier,
  balance,
  onDone,
  onEdit,
  onOpenDelivery,
}: {
  actions: SuggestedAction[]
  tier: BillingTier
  balance: string
  /** Called after a state-changing action succeeded so the host reloads. */
  onDone: () => void
  onEdit: () => void
  onOpenDelivery: () => void
}) {
  const act = useActionState()
  const [confirm, setConfirm] = useState<string | null>(null)
  const [form, setForm] = useState<"record_payment" | "issue_credit" | null>(null)
  const [amount, setAmount] = useState(balance)
  const [method, setMethod] = useState("eft")
  const [ref, setRef] = useState("")
  const [reason, setReason] = useState("")
  const payKey = useRef<string | null>(null)

  if (actions.length === 0) return <p className="text-xs text-muted-foreground">No suggested actions for this invoice.</p>

  const needTier = (a: SuggestedAction) => (a.tier === "admin" ? "admin" : a.tier === "clerk" ? "clerk" : "reader")
  const allowed = (a: SuggestedAction) => tierAtLeast(tier, needTier(a) as "reader" | "clerk" | "admin")

  const run = async (a: SuggestedAction, extra?: Record<string, unknown>) => {
    const p = runSuggestedAction(a, extra)
    if (!p) return
    const r = await act.run(a.id, () => p, `${a.label}: done.`)
    setConfirm(null)
    if (r !== undefined) onDone()
  }

  const click = (a: SuggestedAction) => {
    if (a.id === "edit_draft") return onEdit()
    if (LOCAL_SECTION.has(a.id)) return onOpenDelivery()
    if (a.id === "record_payment") {
      payKey.current = newIdempotencyKey()
      setForm("record_payment")
      return
    }
    if (a.id === "issue_credit") return setForm("issue_credit")
    if (NEEDS_CONFIRM.has(a.id)) return setConfirm(a.id)
    void run(a)
  }

  const submitPayment = async (a: SuggestedAction) => {
    const key = payKey.current ?? (payKey.current = newIdempotencyKey())
    const r = await act.run("record_payment", () => recordPayment({ invoice_id: String((a.payload as { invoice_id?: string } | null)?.invoice_id ?? ""), amount_zar: amount.trim(), method, reference: ref.trim() || undefined }, key), "Payment recorded.")
    if (r !== undefined) {
      setForm(null)
      payKey.current = null
      onDone()
    }
  }

  return (
    <div className="space-y-3">
      {act.msg && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      <ul className="space-y-2">
        {actions.map((a) => {
          const pending = !a.endpoint
          const ok = allowed(a)
          const isConfirm = confirm === a.id
          return (
            <li key={a.id} className="rounded-md border border-border p-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{a.label}</p>
                  {pending ? (
                    <p className="text-[11px] text-amber-400">Integration pending{a.reason ? `: ${a.reason.replace(/^integration pending:?\s*/i, "")}` : ""}</p>
                  ) : a.reason ? (
                    <p className="text-[11px] text-muted-foreground">{a.reason}</p>
                  ) : null}
                  {!pending && !ok && <p className="text-[11px] text-muted-foreground">{tierTip(needTier(a) === "admin" ? "admin" : "clerk")}</p>}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={pending || !ok || !!act.busy}
                  title={pending ? (a.reason ?? "integration pending") : !ok ? tierTip(needTier(a) === "admin" ? "admin" : "clerk") : undefined}
                  onClick={() => click(a)}
                >
                  {act.busy === a.id ? "Working…" : pending ? "Not available" : LOCAL_SECTION.has(a.id) ? "Open" : a.label.split(" ")[0]}
                </Button>
              </div>

              {isConfirm && (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-300">
                  {a.id === "offer_arrangement" && a.payload ? (
                    <span>
                      Create arrangement: {String((a.payload as Record<string, unknown>).installments_count)} x R {String((a.payload as Record<string, unknown>).installment_zar)} from {String((a.payload as Record<string, unknown>).first_due_date)}.
                    </span>
                  ) : (
                    <span>Confirm: {a.label}?</span>
                  )}
                  <Button size="sm" disabled={!!act.busy} onClick={() => run(a)}>
                    Confirm
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirm(null)}>
                    Cancel
                  </Button>
                </div>
              )}

              {form === "record_payment" && a.id === "record_payment" && (
                <div className="mt-2 grid gap-2 sm:grid-cols-4">
                  <Field label="Amount (R)">
                    <input className={inputClass} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
                  </Field>
                  <Field label="Method">
                    <select className={inputClass} value={method} onChange={(e) => setMethod(e.target.value)}>
                      <option value="eft">EFT</option>
                      <option value="card">Card</option>
                      <option value="debit_order">Debit order</option>
                      <option value="manual">Manual / cash</option>
                    </select>
                  </Field>
                  <Field label="Reference" className="sm:col-span-2">
                    <input className={inputClass} value={ref} maxLength={200} onChange={(e) => setRef(e.target.value)} />
                  </Field>
                  <div className="flex gap-2 sm:col-span-4">
                    <Button size="sm" disabled={!!act.busy} onClick={() => submitPayment(a)}>
                      Record payment
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setForm(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {form === "issue_credit" && a.id === "issue_credit" && (
                <div className="mt-2 flex flex-wrap items-end gap-2">
                  <Field label="Reason (required)" className="min-w-[14rem] flex-1">
                    <input className={inputClass} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
                  </Field>
                  <Button
                    size="sm"
                    disabled={!!act.busy || !reason.trim()}
                    onClick={async () => {
                      await run(a, { reason: reason.trim() })
                      setForm(null)
                      setReason("")
                    }}
                  >
                    Create credit note
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setForm(null)}>
                    Cancel
                  </Button>
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
