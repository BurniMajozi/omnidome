"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { customerLabel } from "@/lib/billing-derive"
import { fmtCents, fmtMoney, sumCents, toCents } from "@/lib/money"
import { listMovements, type Loadable, type Movement, type MovementsResponse } from "@/lib/invoicing-api"
import { Field, StatusBadge, fmtDateTime, humanise, inputClass } from "../shared"
import { CustomerPicker, type PickedCustomer } from "./doc-editor"
import { InvoiceDrawer } from "./invoice-drawer"

const TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: "", label: "All movements" },
  { value: "invoice_issued", label: "Issued" },
  { value: "invoice_emailed,invoice_reminder_sent", label: "Sent / emailed" },
  { value: "invoice_delivered,invoice_viewed,invoice_opened", label: "Delivered / viewed" },
  { value: "payment,partial_payment", label: "Payments" },
  { value: "payment_failed", label: "Failed payments" },
  { value: "dunning_*", label: "Dunning" },
  { value: "payment_arrangement", label: "Arrangements" },
  { value: "credit_note,credit,refund,refund_due", label: "Credits and refunds" },
  { value: "invoice_voided", label: "Voids" },
  { value: "quote_*", label: "Quote events" },
  { value: "termination_fee", label: "Termination fees" },
  { value: "invoice_bounced,invoice_complained,invoice_failed,invoice_suppressed", label: "Email problems" },
]

/** Actions the billing service reports as having no endpoint yet (see docs/billing-invoicing-api.md section 8). */
const PENDING_ACTIONS = new Set(["queue_call", "mailer_builder", "review_upgrade_request", "issue_refund"])

type Group = "issued" | "comms" | "payments" | "failed" | "dunning" | "credits" | "voids" | "quotes" | "fees" | "arrangements" | "other"
function groupOf(type: string): Group {
  if (type === "invoice_issued") return "issued"
  if (type === "payment" || type === "partial_payment") return "payments"
  if (type === "payment_failed" || /^invoice_(bounced|complained|failed|suppressed|email_unconfirmed)$/.test(type)) return "failed"
  if (type.startsWith("dunning_")) return "dunning"
  if (type === "payment_arrangement") return "arrangements"
  if (["credit_note", "credit", "refund", "refund_due"].includes(type)) return "credits"
  if (type === "invoice_voided") return "voids"
  if (type.startsWith("quote_")) return "quotes"
  if (type === "termination_fee") return "fees"
  if (type.startsWith("invoice_")) return "comms"
  return "other"
}
const GROUP_LABEL: Record<Group, string> = {
  issued: "Issued",
  comms: "Sent / delivered / viewed",
  payments: "Payments",
  failed: "Failures and bounces",
  dunning: "Dunning actions",
  credits: "Credits and refunds",
  voids: "Voids",
  quotes: "Quote events",
  fees: "Termination fees",
  arrangements: "Arrangements",
  other: "Other",
}
const GROUP_TONE: Partial<Record<Group, string>> = {
  payments: "badge-success",
  failed: "badge-danger",
  dunning: "badge-warning",
  credits: "badge-warning",
  voids: "bg-secondary text-muted-foreground",
  issued: "badge-info",
  quotes: "badge-info",
  fees: "badge-warning",
}

const isoDay = (d: Date) => d.toISOString().slice(0, 10)

export function MovementsTab({
  names,
  onOpenQuote,
}: {
  names: Record<string, string>
  onOpenQuote: (quoteId: string) => void
}) {
  const [type, setType] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [cust, setCust] = useState<PickedCustomer | null>(null)
  const [data, setData] = useState<Loadable<MovementsResponse>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [openInvoice, setOpenInvoice] = useState<string | null>(null)

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listMovements({ type: type || undefined, from: from || undefined, to: to || undefined, customer_id: cust?.id, limit: 300 }).then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [type, from, to, cust, tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])

  const stats = useMemo(() => {
    if (data.state !== "ready") return null
    const items = data.data.items
    const byGroup = new Map<Group, number>()
    for (const m of items) byGroup.set(groupOf(m.type), (byGroup.get(groupOf(m.type)) ?? 0) + 1)
    const paid = sumCents(items.filter((m) => groupOf(m.type) === "payments").map((m) => m.amount))
    const failedAmt = sumCents(items.filter((m) => m.type === "payment_failed").map((m) => m.amount))
    return { byGroup, paid, failedAmt, n: items.length }
  }, [data])

  const setRange = (days: number) => {
    const t = new Date()
    const f = new Date()
    f.setDate(f.getDate() - days)
    setFrom(isoDay(f))
    setTo(isoDay(t))
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-[1fr_9rem_9rem_minmax(0,1.2fr)]">
        <Field label="Type">
          <select className={inputClass} value={type} onChange={(e) => setType(e.target.value)}>
            {TYPE_FILTERS.map((t) => (
              <option key={t.label} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="From">
          <input type="date" className={inputClass} value={from} onChange={(e) => setFrom(e.target.value)} />
        </Field>
        <Field label="To">
          <input type="date" className={inputClass} value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
        <Field label="Customer">
          <CustomerPicker value={cust} onChange={setCust} />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">Quick range:</span>
        <Button size="sm" variant="outline" onClick={() => setRange(7)}>
          7 days
        </Button>
        <Button size="sm" variant="outline" onClick={() => setRange(30)}>
          30 days
        </Button>
        <Button size="sm" variant="ghost" onClick={() => { setFrom(""); setTo("") }}>
          Clear dates
        </Button>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : data.data.items.length === 0 ? (
        <NoDataYet message="No movements match these filters." />
      ) : (
        <>
          {stats && (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-6">
                {[...stats.byGroup.entries()]
                  .sort((a, b) => b[1] - a[1])
                  .map(([g, n]) => (
                    <div key={g} className="rounded-md border border-border bg-secondary/20 p-2.5">
                      <p className="text-[11px] text-muted-foreground">{GROUP_LABEL[g]}</p>
                      <p className="text-lg font-semibold text-foreground">{n}</p>
                    </div>
                  ))}
                <div className="rounded-md border border-border bg-secondary/20 p-2.5">
                  <p className="text-[11px] text-muted-foreground">Payments received (in view)</p>
                  <p className="text-lg font-semibold text-foreground">{fmtCents(stats.paid)}</p>
                </div>
                {stats.failedAmt > 0 && (
                  <div className="rounded-md border border-border bg-secondary/20 p-2.5">
                    <p className="text-[11px] text-muted-foreground">Failed payment value</p>
                    <p className="text-lg font-semibold text-foreground">{fmtCents(stats.failedAmt)}</p>
                  </div>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">
                Counters are computed from the {data.data.count} movements returned
                {data.data.total_matching > data.data.count ? ` (${data.data.total_matching} match in total; narrow the filters to see the rest)` : ""}. Newest first.
              </p>
            </div>
          )}

          <ul className="divide-y divide-border rounded-md border border-border">
            {data.data.items.map((m) => (
              <MovementRow key={m.id} m={m} names={names} onOpenInvoice={setOpenInvoice} onOpenQuote={onOpenQuote} />
            ))}
          </ul>
        </>
      )}

      <InvoiceDrawer invoiceId={openInvoice} customerName={undefined} onClose={() => setOpenInvoice(null)} onChanged={reload} />
    </div>
  )
}

function MovementRow({ m, names, onOpenInvoice, onOpenQuote }: { m: Movement; names: Record<string, string>; onOpenInvoice: (id: string) => void; onOpenQuote: (id: string) => void }) {
  const g = groupOf(m.type)
  const who = m.customer_id ? customerLabel(names, m.customer_id) : null
  const detailText = m.detail && typeof (m.detail as { recipient?: unknown }).recipient === "string" ? String((m.detail as { recipient: string }).recipient) : null
  const amount = m.amount !== null && toCents(m.amount) !== null ? fmtMoney(m.amount) : null
  return (
    <li className="flex flex-col gap-2 px-3 py-2.5 text-sm md:flex-row md:items-center md:justify-between">
      <div className="min-w-0 space-y-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={GROUP_TONE[g] ?? "bg-secondary text-muted-foreground"}>{humanise(m.type)}</Badge>
          {m.status && <StatusBadge status={m.status} />}
          {amount && <span className="font-medium tabular-nums text-foreground">{amount}</span>}
        </div>
        <p className="text-xs text-muted-foreground">
          {fmtDateTime(m.at)}
          {who ? ` · ${who}` : ""}
          {detailText ? ` · ${detailText}` : ""}
          {m.actor ? ` · by ${m.actor}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {m.invoice_id && (
          <Button size="sm" variant="outline" onClick={() => onOpenInvoice(m.invoice_id as string)}>
            Open invoice
          </Button>
        )}
        {m.quote_id && (
          <Button size="sm" variant="outline" onClick={() => onOpenQuote(m.quote_id as string)}>
            Open quote
          </Button>
        )}
        {(m.next_actions ?? []).map((a) =>
          PENDING_ACTIONS.has(a) ? (
            <span key={a} title="Integration pending: billing has no endpoint for this yet" className="rounded border border-dashed border-border px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-70">
              {humanise(a)} (pending)
            </span>
          ) : m.invoice_id ? (
            <button key={a} type="button" onClick={() => onOpenInvoice(m.invoice_id as string)} className="rounded border border-border px-1.5 py-0.5 text-[11px] text-foreground hover:bg-secondary">
              {humanise(a)}
            </button>
          ) : (
            <span key={a} className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {humanise(a)}
            </span>
          ),
        )}
      </div>
    </li>
  )
}
