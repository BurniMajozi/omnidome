"use client"

/**
 * Cards a customer has saved for future payments, plus (when an invoice is given) a "Charge saved card"
 * action. Only the brand, last 4 digits and expiry are ever shown; a full card number is never held here.
 */

import { useCallback, useEffect, useState } from "react"
import { CreditCard } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import {
  chargeSavedCard,
  listPaymentMethods,
  makePaymentMethodDefault,
  removePaymentMethod,
  useBillingTier,
  type PaymentMethod,
} from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { ConfirmModal } from "./confirm-modal"
import { Note, humanise, tierTip, useActionState } from "./shared"

const isActive = (m: PaymentMethod) => m.status !== "expired" && m.status !== "removed" && m.status !== "inactive"

const cardName = (m: PaymentMethod) => {
  const brand = m.brand ? humanise(m.brand) : "Card"
  return `${brand} ending ${m.last4}`
}
const expiry = (m: PaymentMethod) => {
  if (!m.exp_month || !m.exp_year) return null
  return `${String(m.exp_month).padStart(2, "0")}/${m.exp_year}`
}

export function SavedCards({ customerId, invoiceId, balance, onCharged }: { customerId: string; invoiceId?: string; /** Invoice balance, shown in the charge confirmation. */ balance?: string | number; onCharged?: () => void }) {
  const { canWrite, isAdmin } = useBillingTier()
  const [data, setData] = useState<Loadable<{ methods: PaymentMethod[] }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [removing, setRemoving] = useState<PaymentMethod | null>(null)
  const [charging, setCharging] = useState(false)
  const act = useActionState()
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listPaymentMethods(customerId).then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [customerId, tick])

  const methods = data.state === "ready" ? (data.data.methods ?? []) : []
  const chargeCard = methods.find((m) => m.is_default && isActive(m)) ?? methods.find(isActive)

  const makeDefault = async (m: PaymentMethod) => {
    const r = await act.run(`default-${m.id}`, () => makePaymentMethodDefault(m.id), `${cardName(m)} is now the default card.`)
    if (r !== undefined) reload()
  }

  const remove = async () => {
    if (!removing) return
    const m = removing
    const r = await act.run(`remove-${m.id}`, () => removePaymentMethod(m.id), `${cardName(m)} was removed.`)
    if (r !== undefined) {
      setRemoving(null)
      reload()
    }
  }

  const charge = async () => {
    if (!invoiceId || !chargeCard) return
    const r = await act.run("charge", () => chargeSavedCard({ invoice_id: invoiceId, payment_method_id: chargeCard.id }))
    if (r === undefined) return
    setCharging(false)
    if (r?.status === "succeeded") {
      act.setMsg({ tone: "success", text: "Payment succeeded." })
      onCharged?.()
    } else if (r?.status === "pending") {
      act.setMsg({ tone: "info", text: "The payment is pending. It will update once the bank confirms." })
      onCharged?.()
    } else {
      act.setMsg({ tone: "error", text: `The payment failed${r?.reason ? `: ${r.reason}` : "."}` })
    }
  }

  return (
    <section className="space-y-2">
      <h4 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <CreditCard className="h-4 w-4" />
        Cards on file
      </h4>
      {act.msg && !charging && !removing && <Note tone={act.msg.tone}>{act.msg.text}</Note>}
      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} className="p-4" />
      ) : methods.length === 0 ? (
        <NoDataYet message="No saved cards. A customer can save one when paying online." className="p-4" />
      ) : (
        <ul className="divide-y divide-border rounded-md border border-border text-sm">
          {methods.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
              <div className="min-w-0">
                <p className="font-medium text-foreground">
                  {cardName(m)}
                  {m.is_default && <Badge className="badge-info ml-2">Default</Badge>}
                  {!isActive(m) && <Badge className="badge-danger ml-2">Expired</Badge>}
                </p>
                <p className="text-xs text-muted-foreground">
                  {[expiry(m) ? `Expires ${expiry(m)}` : null, m.card_type ? humanise(m.card_type) : null, m.bank].filter(Boolean).join(" · ")}
                </p>
              </div>
              {canWrite && (
                <div className="flex gap-1.5">
                  {!m.is_default && isActive(m) && (
                    <Button size="sm" variant="outline" disabled={!!act.busy} onClick={() => makeDefault(m)}>
                      Make default
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" disabled={!!act.busy} onClick={() => { act.clear(); setRemoving(m) }}>
                    Remove
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {invoiceId && chargeCard && (
        <Button size="sm" disabled={!isAdmin || !!act.busy} title={isAdmin ? undefined : tierTip("admin")} onClick={() => { act.clear(); setCharging(true) }}>
          Charge saved card
        </Button>
      )}

      <ConfirmModal
        open={charging}
        onOpenChange={setCharging}
        title="Charge saved card"
        confirmLabel={balance !== undefined ? `Charge ${fmtMoney(balance)}` : "Charge card"}
        busy={act.busy === "charge"}
        error={act.msg?.tone === "error" ? act.msg.text : null}
        onConfirm={charge}
      >
        <p>
          {chargeCard ? `This charges ${cardName(chargeCard)}` : "This charges the saved card"}
          {balance !== undefined ? ` for the outstanding balance of ${fmtMoney(balance)}` : " for the outstanding balance"}. The customer's bank may decline it.
        </p>
      </ConfirmModal>

      <ConfirmModal
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="Remove saved card"
        confirmLabel="Remove card"
        destructive
        busy={!!act.busy}
        error={act.msg?.tone === "error" ? act.msg.text : null}
        onConfirm={remove}
      >
        <p>{removing ? `${cardName(removing)} will no longer be used for this customer's payments.` : ""}</p>
      </ConfirmModal>
    </section>
  )
}
