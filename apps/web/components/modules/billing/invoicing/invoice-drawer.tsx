"use client"

/**
 * Invoice detail drawer: lines, payments, timeline, suggested actions, and the shared
 * DocumentActions (export / print / email / share / delivery history). Everything is read
 * from the billing service; nothing is derived or invented client-side.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useBillingTier } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import {
  getInvoiceDetail,
  getInvoiceTimeline,
  listInvoicePayments,
  type InvoiceDetail,
  type InvoiceTimeline,
  type Loadable,
} from "@/lib/invoicing-api"
import { Modal, SidePanel, StatusBadge, fmtDate, fmtDateTime, humanise, tierAtLeast } from "../shared"
import { DocumentActions } from "./document-actions"
import { InvoiceBuilder } from "./invoice-builder"
import { SuggestedActions } from "./suggested-actions"

type Payments = Awaited<ReturnType<typeof listInvoicePayments>>

export function InvoiceDrawer({
  invoiceId,
  customerName,
  onClose,
  onChanged,
}: {
  invoiceId: string | null
  customerName?: string
  onClose: () => void
  /** Called whenever something changed on the server so the host list reloads. */
  onChanged: () => void
}) {
  const { tier } = useBillingTier()
  const [detail, setDetail] = useState<Loadable<InvoiceDetail>>({ state: "loading" })
  const [timeline, setTimeline] = useState<Loadable<InvoiceTimeline>>({ state: "loading" })
  const [payments, setPayments] = useState<Payments>({ state: "loading" })
  const [editing, setEditing] = useState(false)
  const deliveryRef = useRef<HTMLDivElement | null>(null)
  const [deliveryOpen, setDeliveryOpen] = useState(false)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((t) => t + 1), [])
  useEffect(() => {
    if (!invoiceId) return
    let off = false
    getInvoiceDetail(invoiceId).then((l) => !off && setDetail(l))
    getInvoiceTimeline(invoiceId).then((l) => !off && setTimeline(l))
    listInvoicePayments(invoiceId).then((l) => !off && setPayments(l))
    return () => {
      off = true
    }
  }, [invoiceId, tick])
  useEffect(() => {
    setDetail({ state: "loading" })
    setTimeline({ state: "loading" })
    setPayments({ state: "loading" })
    setEditing(false)
    setDeliveryOpen(false)
  }, [invoiceId])

  const changed = () => {
    reload()
    onChanged()
  }

  const d = detail.state === "ready" ? detail.data : null

  return (
    <>
      <SidePanel
        open={!!invoiceId && !editing}
        onOpenChange={(o) => !o && onClose()}
        title={d ? `Invoice ${d.number}` : "Invoice"}
        description={customerName ? `Customer: ${customerName}` : undefined}
      >
        {detail.state !== "ready" ? (
          <NotConnected loadable={detail} service="Billing" onRetry={reload} />
        ) : (
          <div className="space-y-6 pb-8">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={detail.data.status} />
              {detail.data.credit_note_of && <span className="text-xs text-muted-foreground">Credit note</span>}
              {detail.data.source_type && <span className="rounded bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">{humanise(detail.data.source_type)}</span>}
              {detail.data.status === "draft" && detail.data.subscription_id == null && !detail.data.credit_note_of && tierAtLeast(tier, "clerk") && (
                <Button size="sm" variant="outline" className="ml-auto" onClick={() => setEditing(true)}>
                  <Pencil className="h-3.5 w-3.5" />
                  Edit draft
                </Button>
              )}
            </div>

            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Stat k="Total" v={fmtMoney(detail.data.total_zar)} />
              <Stat k="Paid" v={fmtMoney(detail.data.amount_paid_zar)} />
              <Stat k="Balance" v={fmtMoney(detail.data.balance_zar)} />
              <Stat k="Due" v={fmtDate(detail.data.due_date)} />
              <Stat k="Issued" v={fmtDate(detail.data.issue_date)} />
              <Stat k="Subtotal" v={fmtMoney(detail.data.subtotal_zar)} />
              <Stat k="VAT" v={fmtMoney(detail.data.vat_zar)} />
              <Stat k="PO" v={detail.data.po_number || "—"} />
            </dl>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold text-foreground">Lines</h4>
              {detail.data.lines.length === 0 ? (
                <NoDataYet message="This invoice has no stored line items." className="p-4" />
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-xs">
                    <thead className="bg-secondary/40 text-left text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1.5">Description</th>
                        <th className="px-2 py-1.5 text-right">Qty</th>
                        <th className="px-2 py-1.5 text-right">Unit</th>
                        <th className="px-2 py-1.5 text-right">Discount</th>
                        <th className="px-2 py-1.5 text-right">VAT</th>
                        <th className="px-2 py-1.5 text-right">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.lines.map((l, i) => (
                        <tr key={l.line_id ?? i} className="border-t border-border">
                          <td className="px-2 py-1.5">{l.description}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{String(l.quantity)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtMoney(l.unit_price_zar)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{l.discount_zar && Number(l.discount_zar) ? fmtMoney(l.discount_zar) : "—"}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtMoney(l.vat_zar)}</td>
                          <td className="px-2 py-1.5 text-right tabular-nums">{fmtMoney(l.line_total_incl_zar ?? l.total_zar)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold text-foreground">Payments</h4>
              {payments.state !== "ready" ? (
                <NotConnected loadable={payments} service="Billing" onRetry={reload} className="p-4" />
              ) : (payments.data.items ?? []).length === 0 ? (
                <NoDataYet message="No payments recorded against this invoice." className="p-4" />
              ) : (
                <ul className="divide-y divide-border rounded-md border border-border text-xs">
                  {payments.data.items.map((p) => (
                    <li key={p.id} className="flex items-center justify-between gap-2 px-3 py-2">
                      <span>
                        {humanise(p.method)} {p.reference ? `· ${p.reference}` : ""}
                        <span className="ml-2 text-muted-foreground">{fmtDateTime(p.created_at)}</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <StatusBadge status={p.status} />
                        <span className="tabular-nums">{fmtMoney(p.amount_zar)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold text-foreground">Suggested actions</h4>
              {timeline.state !== "ready" ? (
                <NotConnected loadable={timeline} service="Billing" onRetry={reload} className="p-4" />
              ) : (
                <SuggestedActions
                  actions={timeline.data.suggested_actions ?? []}
                  tier={tier}
                  balance={String(detail.data.balance_zar)}
                  onDone={changed}
                  onEdit={() => setEditing(true)}
                  onOpenDelivery={() => {
                    setDeliveryOpen(true)
                    setTimeout(() => deliveryRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50)
                  }}
                />
              )}
            </section>

            <section className="space-y-2">
              <h4 className="text-sm font-semibold text-foreground">Timeline</h4>
              {timeline.state !== "ready" ? (
                <NotConnected loadable={timeline} service="Billing" onRetry={reload} className="p-4" />
              ) : (timeline.data.events ?? []).length === 0 ? (
                <NoDataYet message="No events recorded yet." className="p-4" />
              ) : (
                <ol className="space-y-2 border-l border-border pl-4">
                  {timeline.data.events.map((e) => (
                    <li key={e.id} className="relative text-xs">
                      <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-primary" />
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground">{humanise(e.type)}</span>
                        {e.status && <StatusBadge status={e.status} />}
                        {e.amount !== null && e.amount !== undefined && <span className="tabular-nums">{fmtMoney(e.amount)}</span>}
                      </div>
                      <p className="text-muted-foreground">
                        {fmtDateTime(e.at)}
                        {e.actor ? ` · ${e.actor}` : ""}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <div ref={deliveryRef} className="space-y-2 border-t border-border pt-4">
              <details open={deliveryOpen} onToggle={(ev) => setDeliveryOpen((ev.currentTarget as HTMLDetailsElement).open)}>
                <summary className="cursor-pointer text-sm font-semibold text-foreground">Document, email and share link</summary>
                <div className="pt-3">
                  <DocumentActions kind="invoice" id={detail.data.id} number={detail.data.number} status={detail.data.status} defaultEmail={detail.data.bill_to?.email} onChanged={changed} />
                </div>
              </details>
            </div>
          </div>
        )}
      </SidePanel>

      <Modal open={editing && !!invoiceId} onOpenChange={(o) => !o && setEditing(false)} title="Edit draft invoice" wide>
        {d && (
          <InvoiceBuilder
            mode="edit"
            initial={d}
            customer={d.customer_id ? { id: d.customer_id, label: customerName || d.bill_to?.name || "Customer", email: d.bill_to?.email } : null}
            lockCustomer
            onSaved={() => changed()}
            onCancel={() => setEditing(false)}
          />
        )}
      </Modal>
    </>
  )
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</dt>
      <dd className="font-medium text-foreground">{v}</dd>
    </div>
  )
}
