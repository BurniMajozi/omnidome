"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Plus, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { useBillingTier } from "@/lib/billing-api"
import { customerLabel } from "@/lib/billing-derive"
import { fmtMoney } from "@/lib/money"
import { getQuote, listQuotes, type Loadable, type QuoteDoc } from "@/lib/invoicing-api"
import { Modal, StatusBadge, fmtDate, humanise, inputClass, tierAtLeast, tierTip } from "../shared"
import { QuoteBuilder } from "./quote-builder"

const STATUSES = ["draft", "sent", "viewed", "accepted", "declined", "expired", "converted"]

export function QuotesTab({ names, focusQuoteId, onFocusHandled, onOpenInvoice }: { names: Record<string, string>; focusQuoteId?: string | null; onFocusHandled?: () => void; onOpenInvoice?: (invoiceId: string) => void }) {
  const { tier } = useBillingTier()
  const canWrite = tierAtLeast(tier, "clerk")
  const [status, setStatus] = useState("")
  const [q, setQ] = useState("")
  const [data, setData] = useState<Loadable<{ items: QuoteDoc[]; total: number }>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const [editor, setEditor] = useState<{ mode: "create" } | { mode: "edit"; quote: QuoteDoc } | null>(null)
  const [focusErr, setFocusErr] = useState<string | null>(null)

  useEffect(() => {
    let off = false
    setData({ state: "loading" })
    listQuotes({ status: status || undefined }).then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [status, tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])

  // Deep link from the movements board.
  useEffect(() => {
    if (!focusQuoteId) return
    let off = false
    getQuote(focusQuoteId).then((l) => {
      if (off) return
      if (l.state === "ready") setEditor({ mode: "edit", quote: l.data })
      else setFocusErr("That quote could not be loaded.")
      onFocusHandled?.()
    })
    return () => {
      off = true
    }
  }, [focusQuoteId, onFocusHandled])

  const rows = useMemo(() => {
    if (data.state !== "ready") return []
    const n = q.trim().toLowerCase()
    return data.data.items.filter((x) => !n || x.number.toLowerCase().includes(n) || (x.prospect?.name ?? "").toLowerCase().includes(n) || (x.customer_id ? customerLabel(names, x.customer_id) : "").toLowerCase().includes(n))
  }, [data, q, names])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${inputClass} max-w-xs`} placeholder="Search number, customer or prospect…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={`${inputClass} w-44`} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {humanise(s)}
            </option>
          ))}
        </select>
        <Button size="sm" variant="ghost" onClick={reload}>
          <RefreshCcw className="h-3.5 w-3.5" />
          Refresh
        </Button>
        <Button size="sm" variant="cta" className="ml-auto" disabled={!canWrite} title={!canWrite ? tierTip("clerk") : undefined} onClick={() => setEditor({ mode: "create" })}>
          <Plus className="h-3.5 w-3.5" />
          New quote
        </Button>
      </div>
      {focusErr && <p className="text-xs text-red-300">{focusErr}</p>}

      {data.state !== "ready" ? (
        <NotConnected loadable={data} service="Billing" onRetry={reload} />
      ) : data.data.items.length === 0 ? (
        <NoDataYet message="No quotes yet. Create one with New quote." />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {rows.length} shown of {data.data.total} quotes. Expired quotes are marked lazily when read.
          </p>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-secondary/40 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Quote</th>
                  <th className="px-3 py-2">For</th>
                  <th className="px-3 py-2 text-right">Total</th>
                  <th className="px-3 py-2">Valid until</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-xs text-muted-foreground">
                      No quotes match the filter.
                    </td>
                  </tr>
                )}
                {rows.map((x) => (
                  <tr key={x.id} tabIndex={0} className="cursor-pointer border-t border-border hover:bg-secondary/30 focus:bg-secondary/30 focus:outline-none" onClick={() => setEditor({ mode: "edit", quote: x })} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setEditor({ mode: "edit", quote: x })}>
                    <td className="px-3 py-2 font-medium text-foreground">{x.number}</td>
                    <td className="px-3 py-2">
                      {x.customer_id ? customerLabel(names, x.customer_id) : x.prospect?.name ? `${x.prospect.name} (prospect)` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(x.total_zar)}</td>
                    <td className="px-3 py-2">{fmtDate(x.valid_until)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{humanise(x.source)}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={x.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Modal open={!!editor} onOpenChange={(o) => !o && setEditor(null)} title={editor?.mode === "edit" ? "Quote" : "New quote"} description="Quotes never post to finance. Convert an accepted quote into a draft invoice." wide>
        {editor && (
          <QuoteBuilder
            key={editor.mode === "edit" ? editor.quote.id : "new"}
            mode={editor.mode}
            initial={editor.mode === "edit" ? editor.quote : undefined}
            customer={editor.mode === "edit" && editor.quote.customer_id ? { id: editor.quote.customer_id, label: customerLabel(names, editor.quote.customer_id) } : null}
            onSaved={() => reload()}
            onConverted={(inv) => {
              reload()
              if (onOpenInvoice) {
                setEditor(null)
                onOpenInvoice(inv.id)
              }
            }}
            onCancel={() => setEditor(null)}
          />
        )}
      </Modal>
    </div>
  )
}
