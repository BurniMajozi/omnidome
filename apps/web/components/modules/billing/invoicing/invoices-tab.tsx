"use client"

import { useEffect, useMemo, useState } from "react"
import { Plus, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useBillingTier, type InvoiceRow, type PagedResult } from "@/lib/billing-api"
import type { Loadable } from "@/lib/service-state"
import { customerLabel, showingLabel } from "@/lib/billing-derive"
import { fmtMoney } from "@/lib/money"
import { Modal, StatusBadge, fmtDate, inputClass, tierAtLeast, tierTip } from "../shared"
import { InvoiceBuilder } from "./invoice-builder"
import { InvoiceDrawer } from "./invoice-drawer"

const STATUSES = ["draft", "sent", "partially_paid", "overdue", "paid", "voided"]

export function InvoicesTab({
  invoices,
  reload,
  names,
  namesPartial,
  newOpen,
  onNewOpenChange,
  openRequest,
  onOpenRequestHandled,
}: {
  invoices: Loadable<PagedResult<InvoiceRow>>
  reload: () => void
  names: Record<string, string>
  namesPartial: boolean
  newOpen: boolean
  onNewOpenChange: (o: boolean) => void
  /** Deep link: open this invoice's drawer (from the movements board, quote conversion or fee calculations). */
  openRequest?: string | null
  onOpenRequestHandled?: () => void
}) {
  const { tier } = useBillingTier()
  const [q, setQ] = useState("")
  const [status, setStatus] = useState("")
  const [openId, setOpenId] = useState<string | null>(openRequest ?? null)
  useEffect(() => {
    if (openRequest) {
      setOpenId(openRequest)
      onOpenRequestHandled?.()
    }
  }, [openRequest, onOpenRequestHandled])

  const rows = useMemo(() => {
    if (invoices.state !== "ready") return []
    const needle = q.trim().toLowerCase()
    return invoices.data.items
      .filter((i) => (!status || i.status === status) && (!needle || i.number.toLowerCase().includes(needle) || customerLabel(names, i.customer_id).toLowerCase().includes(needle)))
      .sort((a, b) => ((a.created_at ?? a.due_date) < (b.created_at ?? b.due_date) ? 1 : -1))
  }, [invoices, q, status, names])

  const canWrite = tierAtLeast(tier, "clerk")

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${inputClass} max-w-xs`} placeholder="Search number or customer…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={`${inputClass} w-44`} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </select>
        <Button size="sm" variant="ghost" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
        <Button size="sm" variant="cta" className="ml-auto" disabled={!canWrite} title={!canWrite ? tierTip("clerk") : undefined} onClick={() => onNewOpenChange(true)}>
          <Plus className="h-3.5 w-3.5" />
          New invoice
        </Button>
      </div>

      {invoices.state !== "ready" ? (
        <NotConnected loadable={invoices} service="Billing" onRetry={reload} />
      ) : invoices.data.items.length === 0 ? (
        <NoDataYet message="No invoices yet. Create one with New invoice." />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {showingLabel(rows.length, invoices.data.total)} invoices{invoices.data.truncated ? " (partial dataset: only the first pages were loaded)" : ""}.
            {namesPartial ? " Customer directory is incomplete; unknown names use a short customer ID." : ""}
          </p>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Invoice</th>
                  <th className="px-3 py-2">Customer</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2 text-right">Paid</th>
                  <th className="px-3 py-2">Due</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-xs text-muted-foreground">
                      No invoices match the filter.
                    </td>
                  </tr>
                )}
                {rows.map((i) => (
                  <tr key={i.id} tabIndex={0} className="cursor-pointer border-t border-border hover:bg-secondary/30 focus:bg-secondary/30 focus:outline-none" onClick={() => setOpenId(i.id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setOpenId(i.id)}>
                    <td className="px-3 py-2 font-medium text-foreground">{i.number}</td>
                    <td className="px-3 py-2">{customerLabel(names, i.customer_id)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.total_zar)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(i.amount_paid_zar)}</td>
                    <td className="px-3 py-2">{fmtDate(i.due_date)}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={i.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Modal open={newOpen} onOpenChange={onNewOpenChange} title="New invoice" description="Creates a draft. Nothing posts to finance until you issue it." wide>
        {newOpen && (
          <InvoiceBuilder
            mode="create"
            onSaved={(inv, action) => {
              reload()
              if (action === "issued" || action === "saved") {
                /* stay open so the user can keep working with the saved invoice */
              }
              void inv
            }}
            onCancel={() => onNewOpenChange(false)}
          />
        )}
      </Modal>

      <InvoiceDrawer invoiceId={openId} customerName={openId ? customerLabel(names, invoices.state === "ready" ? (invoices.data.items.find((x) => x.id === openId)?.customer_id ?? "") : "") : undefined} onClose={() => setOpenId(null)} onChanged={reload} />
    </div>
  )
}
