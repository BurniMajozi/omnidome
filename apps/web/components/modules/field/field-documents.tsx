"use client"

/**
 * <FieldDocuments/> - mobile Quotes + Sales Invoices for the Field Sales and Technician apps.
 *
 * Props
 *   source        "field_sales" | "technician": stored as the quote `source` / invoice `source_type`.
 *   customer      optional { id, label, email? } (e.g. the technician's active job customer). When given the
 *                 builders lock to that customer and the lists are scoped to it.
 *   prospectSeed  optional prospect {name,email,phone,address} to open a prospect quote for (field-sales lead).
 *   initialKind   "quotes" | "invoices" (default quotes).
 *   autoCreate    opens the quote editor immediately (used by "Quote" buttons on a lead / customer row).
 *   onClose       called when an auto-opened editor is closed.
 *
 * All data is real: quotes come from billing (source + created_by), invoices are the ones this device
 * created/converted (loaded from the server by id) or, with a customer, that customer's invoices.
 * Role limits come from useBillingTier(); the server still enforces. Nothing is cached offline.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { Plus, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { NoDataYet, NotConnected } from "@/components/ui/not-connected"
import { useBillingTier } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import { getInvoiceDetail, getQuote, type InvoiceDetail, type Loadable, type QuoteDoc } from "@/lib/invoicing-api"
import { InvoiceBuilder, QuoteBuilder, type PickedCustomer } from "@/components/modules/billing/invoicing"
import { InvoiceDrawer } from "@/components/modules/billing/invoicing/invoice-drawer"
import { Note, StatusBadge, fmtDate, tierAtLeast, tierTip } from "@/components/modules/billing/shared"
import { listCustomerInvoices, listFieldQuotes, readTrackedInvoiceIds, trackInvoiceId, useWhoami } from "./use-field-docs"

type Source = "field_sales" | "technician"
export interface ProspectSeed {
  name: string
  email?: string
  phone?: string
  address?: string
}
type Editor = { t: "quote-new" } | { t: "quote"; quote: QuoteDoc } | { t: "invoice-new" } | { t: "invoice-draft"; invoice: InvoiceDetail }
type InvRow = { id: string; number: string; status: string; total_zar: string | number; due_date?: string }

export interface FieldDocumentsProps {
  source: Source
  customer?: PickedCustomer | null
  prospectSeed?: ProspectSeed | null
  initialKind?: "quotes" | "invoices"
  autoCreate?: boolean
  onClose?: () => void
}

/** Full-screen sheet on phones, centred dialog on larger screens. */
function Sheet({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; children: ReactNode }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[100dvh] max-h-[100dvh] w-screen max-w-none overflow-y-auto rounded-none p-3 sm:h-auto sm:max-h-[92vh] sm:max-w-3xl sm:rounded-lg sm:p-6">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  )
}

export function FieldDocuments({ source, customer, prospectSeed, initialKind = "quotes", autoCreate, onClose }: FieldDocumentsProps) {
  const { tier, loading: tierLoading } = useBillingTier()
  const canWrite = tierAtLeast(tier, "clerk")
  const { userId, loading: whoLoading } = useWhoami()
  const [kind, setKind] = useState<"quotes" | "invoices">(initialKind)
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  const [editor, setEditor] = useState<Editor | null>(autoCreate ? { t: "quote-new" } : null)
  const [drawerId, setDrawerId] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const [quotes, setQuotes] = useState<Loadable<{ items: QuoteDoc[]; total: number }>>({ state: "loading" })
  const [invoices, setInvoices] = useState<Loadable<InvRow[]>>({ state: "loading" })

  const closeEditor = () => {
    setEditor(null)
    if (autoCreate) onClose?.()
  }

  useEffect(() => {
    if (whoLoading || autoCreate) return
    let off = false
    setQuotes({ state: "loading" })
    listFieldQuotes({ source, createdBy: userId, customerId: customer?.id }).then((l) => !off && setQuotes(l))
    return () => {
      off = true
    }
  }, [source, userId, whoLoading, customer?.id, tick, autoCreate])

  useEffect(() => {
    if (whoLoading || autoCreate) return
    let off = false
    setInvoices({ state: "loading" })
    if (customer?.id) {
      listCustomerInvoices(customer.id).then((l) => {
        if (off) return
        if (l.state === "ready") setInvoices({ state: "ready", data: l.data.items })
        else setInvoices(l as Loadable<InvRow[]>)
      })
    } else {
      const ids = readTrackedInvoiceIds(source, userId).slice(0, 30)
      Promise.all(ids.map((id) => getInvoiceDetail(id))).then((rs) => {
        if (off) return
        const rows: InvRow[] = rs.flatMap((r) => (r.state === "ready" ? [r.data as InvRow] : []))
        // If every lookup failed (service down) say so instead of showing an empty list.
        if (ids.length > 0 && rows.length === 0) {
          const bad = rs.find((r) => r.state !== "ready")
          if (bad) return setInvoices(bad as unknown as Loadable<InvRow[]>)
        }
        setInvoices({ state: "ready", data: rows })
      })
    }
    return () => {
      off = true
    }
  }, [source, userId, whoLoading, customer?.id, tick, autoCreate])

  const openInvoice = async (id: string) => {
    setErr(null)
    const r = await getInvoiceDetail(id)
    if (r.state !== "ready") return setErr("That invoice could not be loaded.")
    if (r.data.status === "draft") setEditor({ t: "invoice-draft", invoice: r.data })
    else setDrawerId(id)
  }

  const openQuote = async (q: QuoteDoc) => {
    setErr(null)
    const r = await getQuote(q.id)
    setEditor({ t: "quote", quote: r.state === "ready" ? r.data : q })
  }

  const customerLabelFor = (q: QuoteDoc) => (q.prospect?.name ? `${q.prospect.name} (prospect)` : (customer?.label ?? "Customer"))

  const initialQuote = useMemo<Partial<QuoteDoc> | undefined>(
    () => (prospectSeed ? { prospect: { name: prospectSeed.name, email: prospectSeed.email, phone: prospectSeed.phone, address: prospectSeed.address } } : undefined),
    [prospectSeed],
  )

  const quoteOpen = !!editor && (editor.t === "quote" || editor.t === "quote-new")
  const invoiceOpen = !!editor && (editor.t === "invoice-draft" || editor.t === "invoice-new")

  return (
    <div className="space-y-3">
      {!autoCreate && (
        <>
      <div className="flex items-center gap-1">
        {(["quotes", "invoices"] as const).map((k) => (
          <button key={k} type="button" onClick={() => setKind(k)} className={`rounded-md px-3 py-1.5 text-xs transition-colors ${kind === k ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground hover:text-foreground"}`}>
            {k === "quotes" ? "Quotes" : "Sales invoices"}
          </button>
        ))}
        <Button size="icon" variant="ghost" className="ml-auto h-8 w-8" onClick={reload} aria-label="Refresh">
          <RefreshCcw className="h-3.5 w-3.5" />
        </Button>
        <Button size="sm" disabled={!canWrite} title={!canWrite && !tierLoading ? tierTip("clerk") : undefined} onClick={() => setEditor({ t: kind === "quotes" ? "quote-new" : "invoice-new" })}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          {kind === "quotes" ? "New quote" : "New invoice"}
        </Button>
      </div>
      {!canWrite && !tierLoading && <Note tone="info">Your role can view documents but not create or send them. {tierTip("clerk")}.</Note>}
      {!whoLoading && !userId && <Note tone="info">Could not confirm your user id, so the list shows every {source === "field_sales" ? "field-sales" : "technician"} quote in this tenant, not only yours.</Note>}
      {customer && <p className="text-xs text-muted-foreground">Showing documents for {customer.label}.</p>}
      {err && <Note tone="error">{err}</Note>}

      {kind === "quotes" ? (
        quotes.state !== "ready" ? (
          <NotConnected loadable={quotes} service="Billing" onRetry={reload} />
        ) : quotes.data.items.length === 0 ? (
          <NoDataYet message="No quotes yet. Tap New quote." />
        ) : (
          <ul className="space-y-2">
            {quotes.data.items.map((q) => (
              <li key={q.id}>
                <button type="button" onClick={() => void openQuote(q)} className="w-full rounded-lg border border-border bg-card p-3 text-left hover:border-primary/50">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium">{q.number}</p>
                    <StatusBadge status={q.status} />
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">{customerLabelFor(q)}</p>
                  <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                    <span>Valid until {fmtDate(q.valid_until)}</span>
                    <span className="font-semibold text-foreground tabular-nums">{fmtMoney(q.total_zar)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : invoices.state !== "ready" ? (
        <NotConnected loadable={invoices} service="Billing" onRetry={reload} />
      ) : invoices.data.length === 0 ? (
        <NoDataYet message={customer ? "No invoices for this customer." : "No invoices created on this device yet. Create one, or convert an accepted quote."} />
      ) : (
        <>
          {!customer && <p className="text-xs text-muted-foreground">Invoices you created or converted on this device (the billing list cannot filter by creator yet).</p>}
          <ul className="space-y-2">
            {invoices.data.map((i) => (
              <li key={i.id}>
                <button type="button" onClick={() => void openInvoice(i.id)} className="w-full rounded-lg border border-border bg-card p-3 text-left hover:border-primary/50">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium">{i.number}</p>
                    <StatusBadge status={i.status} />
                  </div>
                  <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                    <span>{i.due_date ? `Due ${fmtDate(i.due_date)}` : ""}</span>
                    <span className="font-semibold text-foreground tabular-nums">{fmtMoney(i.total_zar)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

        </>
      )}

      <Sheet open={quoteOpen} onOpenChange={(o) => !o && closeEditor()} title={editor?.t === "quote" ? "Quote" : "New quote"} description="Quotes never post to finance. Send by email or share a link, then convert an accepted quote to an invoice.">
        {editor && (editor.t === "quote" || editor.t === "quote-new") && (
          <QuoteBuilder
            key={editor.t === "quote" ? editor.quote.id : "new"}
            mode={editor.t === "quote" ? "edit" : "create"}
            initial={editor.t === "quote" ? editor.quote : initialQuote}
            customer={customer ?? (editor.t === "quote" && editor.quote.customer_id ? { id: editor.quote.customer_id, label: "Customer" } : null)}
            lockCustomer={!!customer}
            allowProspect={source === "field_sales" || !customer}
            source={source}
            createdBy={userId ?? undefined}
            hidePreview
            onSaved={() => reload()}
            onConverted={(inv) => {
              trackInvoiceId(source, userId, inv.id)
              reload()
              setKind("invoices")
              setEditor({ t: "invoice-draft", invoice: inv })
            }}
            onCancel={closeEditor}
          />
        )}
      </Sheet>

      <Sheet open={invoiceOpen} onOpenChange={(o) => !o && closeEditor()} title={editor?.t === "invoice-draft" ? "Sales invoice" : "New sales invoice"} description="Issuing posts revenue to finance. Save as a draft first if unsure.">
        {editor && (editor.t === "invoice-draft" || editor.t === "invoice-new") && (
          <InvoiceBuilder
            key={editor.t === "invoice-draft" ? editor.invoice.id : "new"}
            mode={editor.t === "invoice-draft" ? "edit" : "create"}
            initial={editor.t === "invoice-draft" ? editor.invoice : undefined}
            customer={customer ?? null}
            lockCustomer={!!customer}
            source={source}
            createdBy={userId ?? undefined}
            hidePreview
            onSaved={(inv) => {
              trackInvoiceId(source, userId, inv.id)
              reload()
            }}
            onCancel={closeEditor}
          />
        )}
      </Sheet>

      <InvoiceDrawer invoiceId={drawerId} customerName={customer?.label} onClose={() => setDrawerId(null)} onChanged={reload} />
    </div>
  )
}
