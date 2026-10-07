"use client"

/**
 * Building blocks shared by InvoiceBuilder and QuoteBuilder: editable line grid,
 * CRM customer picker, template picker and the sandboxed server-document preview.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ArrowDown, ArrowUp, Plus, RefreshCcw, Search, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { fmtCents } from "@/lib/money"
import { loadCustomers, type CustomerListItem } from "@/lib/crm-api"
import {
  asList,
  fetchDocText,
  listItems,
  listTemplates,
  type CatalogItem,
  type DocKind,
  type InvoiceTemplate,
  type Loadable,
} from "@/lib/invoicing-api"
import { Note, inputClass } from "../shared"
import {
  ASSUMED_DEFAULT_VAT,
  blankLine,
  calcLine,
  calcTotals,
  newKey,
  type EditableLine,
} from "./doc-math"

// ------------------------------------------------------------------ data hooks

export function useCatalog(): { items: CatalogItem[]; state: Loadable<unknown>["state"]; reload: () => void } {
  const [items, setItems] = useState<CatalogItem[]>([])
  const [state, setState] = useState<Loadable<unknown>["state"]>("loading")
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let off = false
    listItems({ active: true, limit: 200 }).then((l) => {
      if (off) return
      setState(l.state)
      setItems(l.state === "ready" ? asList(l.data) : [])
    })
    return () => {
      off = true
    }
  }, [tick])
  return { items, state, reload: () => setTick((t) => t + 1) }
}

export function useTemplates(): { templates: InvoiceTemplate[]; state: Loadable<unknown>["state"]; reload: () => void } {
  const [templates, setTemplates] = useState<InvoiceTemplate[]>([])
  const [state, setState] = useState<Loadable<unknown>["state"]>("loading")
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let off = false
    listTemplates().then((l) => {
      if (off) return
      setState(l.state)
      setTemplates(l.state === "ready" ? asList(l.data) : [])
    })
    return () => {
      off = true
    }
  }, [tick])
  return { templates, state, reload: () => setTick((t) => t + 1) }
}

// ------------------------------------------------------------------ lines grid

export function LinesGrid({
  lines,
  onChange,
  catalog,
  catalogState,
  disabled,
}: {
  lines: EditableLine[]
  onChange: (next: EditableLine[]) => void
  catalog: CatalogItem[]
  catalogState: string
  disabled?: boolean
}) {
  const [pick, setPick] = useState("")
  const totals = useMemo(() => calcTotals(lines), [lines])

  const patch = (key: string, p: Partial<EditableLine>) => onChange(lines.map((l) => (l.key === key ? { ...l, ...p } : l)))
  const move = (i: number, d: -1 | 1) => {
    const j = i + d
    if (j < 0 || j >= lines.length) return
    const next = [...lines]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  const addFromCatalog = (id: string) => {
    const it = catalog.find((c) => c.id === id)
    if (!it) return
    onChange([
      ...lines,
      {
        key: newKey(),
        description: it.description ? `${it.name} - ${it.description}` : it.name,
        quantity: "1",
        unit_price: String(it.unit_price_zar ?? ""),
        discount: "",
        discount_type: "amount",
        tax_rate: it.tax_rate === null || it.tax_rate === undefined ? "" : String(it.tax_rate),
        catalog_item_id: it.id,
      },
    ])
    setPick("")
  }

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onChange([...lines, blankLine()])}>
          <Plus className="h-3.5 w-3.5" />
          Free-form line
        </Button>
        <select
          aria-label="Add element from catalogue"
          className={`${inputClass} h-8 max-w-full sm:w-64`}
          value={pick}
          disabled={disabled || catalog.length === 0}
          onChange={(e) => addFromCatalog(e.target.value)}
        >
          <option value="">
            {catalogState === "loading"
              ? "Loading catalogue…"
              : catalogState !== "ready"
                ? "Catalogue unavailable"
                : catalog.length === 0
                  ? "Catalogue is empty (add items in Items & Templates)"
                  : "Add from catalogue…"}
          </option>
          {catalog.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} (R {c.unit_price_zar})
            </option>
          ))}
        </select>
      </div>

      <div className="min-w-0 overflow-x-auto rounded-md border border-border">
        <table className="block w-full text-sm md:table md:min-w-[820px]">
          <thead className="hidden bg-secondary/40 text-left text-[11px] uppercase tracking-wide text-muted-foreground md:table-header-group">
            <tr>
              <th className="px-2 py-2">Description</th>
              <th className="w-20 px-2 py-2">Qty</th>
              <th className="w-28 px-2 py-2">Unit price</th>
              <th className="w-36 px-2 py-2">Discount</th>
              <th className="w-20 px-2 py-2">VAT %</th>
              <th className="w-28 px-2 py-2 text-right">Line total*</th>
              <th className="w-24 px-2 py-2" />
            </tr>
          </thead>
          <tbody className="block md:table-row-group">
            {lines.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No lines yet. Add a free-form line or pick an element from the catalogue.
                </td>
              </tr>
            )}
            {lines.map((l, i) => {
              const c = calcLine(l)
              return (
                <tr key={l.key} className="grid grid-cols-2 border-t border-border align-top md:table-row [&>td]:block [&>td]:min-w-0 [&>td]:before:mb-1 [&>td]:before:block [&>td]:before:text-[11px] [&>td]:before:text-muted-foreground [&>td]:before:content-[attr(data-label)] md:[&>td]:table-cell md:[&>td]:before:hidden">
                  <td data-label="Description" className="col-span-2 px-2 py-1.5">
                    <input
                      aria-label="Description"
                      className={inputClass}
                      value={l.description}
                      disabled={disabled}
                      maxLength={500}
                      onChange={(e) => patch(l.key, { description: e.target.value })}
                    />
                    {l.catalog_item_id && <span className="text-[10px] text-muted-foreground">from catalogue (price snapshot)</span>}
                  </td>
                  <td data-label="Quantity" className="px-2 py-1.5">
                    <input aria-label="Quantity" className={inputClass} inputMode="decimal" value={l.quantity} disabled={disabled} onChange={(e) => patch(l.key, { quantity: e.target.value })} />
                  </td>
                  <td data-label="Unit price" className="px-2 py-1.5">
                    <input aria-label="Unit price" className={inputClass} inputMode="decimal" value={l.unit_price} disabled={disabled} onChange={(e) => patch(l.key, { unit_price: e.target.value })} />
                  </td>
                  <td data-label="Discount" className="px-2 py-1.5">
                    <div className="flex gap-1">
                      <input aria-label="Discount" className={inputClass} inputMode="decimal" value={l.discount} disabled={disabled} onChange={(e) => patch(l.key, { discount: e.target.value })} />
                      <select aria-label="Discount type" className={`${inputClass} w-14 shrink-0 px-1`} value={l.discount_type} disabled={disabled} onChange={(e) => patch(l.key, { discount_type: e.target.value as "amount" | "percent" })}>
                        <option value="amount">R</option>
                        <option value="percent">%</option>
                      </select>
                    </div>
                  </td>
                  <td data-label="VAT %" className="px-2 py-1.5">
                    <input aria-label="VAT rate" className={inputClass} inputMode="decimal" placeholder="default" value={l.tax_rate} disabled={disabled} onChange={(e) => patch(l.key, { tax_rate: e.target.value })} />
                  </td>
                  <td data-label="Line total" className="px-2 py-2 tabular-nums text-foreground md:text-right">{fmtCents(c.total)}</td>
                  <td data-label="Line actions" className="px-1 py-1.5">
                    <div className="flex justify-end gap-0.5">
                      <Button type="button" size="icon-sm" variant="ghost" aria-label="Move up" disabled={disabled || i === 0} onClick={() => move(i, -1)}>
                        <ArrowUp className="h-3.5 w-3.5" />
                      </Button>
                      <Button type="button" size="icon-sm" variant="ghost" aria-label="Move down" disabled={disabled || i === lines.length - 1} onClick={() => move(i, 1)}>
                        <ArrowDown className="h-3.5 w-3.5" />
                      </Button>
                      <Button type="button" size="icon-sm" variant="ghost-destructive" aria-label="Remove line" disabled={disabled} onClick={() => onChange(lines.filter((x) => x.key !== l.key))}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="ml-auto w-full max-w-xs space-y-1 rounded-md border border-border bg-secondary/20 p-3 text-sm">
        <Row k="Subtotal" v={fmtCents(totals.subtotal)} />
        {totals.discount > 0 && <Row k="Discounts applied" v={fmtCents(-totals.discount)} />}
        <Row k="VAT" v={fmtCents(totals.vat)} />
        <Row k="Total" v={fmtCents(totals.total)} bold />
        <p className="pt-1 text-[11px] text-muted-foreground">
          *Preview only. A blank VAT % is assumed to be {ASSUMED_DEFAULT_VAT}% here; the server applies its configured default and its totals are authoritative after saving.
        </p>
      </div>
    </div>
  )
}

function Row({ k, v, bold }: { k: string; v: string; bold?: boolean }) {
  return (
    <div className={`flex justify-between tabular-nums ${bold ? "border-t border-border pt-1 font-semibold text-foreground" : "text-muted-foreground"}`}>
      <span>{k}</span>
      <span>{v}</span>
    </div>
  )
}

// ------------------------------------------------------------------ customer picker

export interface PickedCustomer {
  id: string
  label: string
  email?: string | null
}

export const customerFullName = (c: Pick<CustomerListItem, "first_name" | "last_name" | "account_number">) =>
  [c.first_name, c.last_name].filter(Boolean).join(" ").trim() || c.account_number || "Customer"

export function CustomerPicker({
  value,
  onChange,
  disabled,
}: {
  value: PickedCustomer | null
  onChange: (c: PickedCustomer | null) => void
  disabled?: boolean
}) {
  const [q, setQ] = useState("")
  const [results, setResults] = useState<CustomerListItem[]>([])
  const [state, setState] = useState<"idle" | "loading" | "ready" | "failed">("idle")
  const [open, setOpen] = useState(false)
  const seq = useRef(0)

  const search = useCallback((term: string) => {
    const my = ++seq.current
    setState("loading")
    loadCustomers({ search: term || undefined, pageSize: 10 }).then((l) => {
      if (my !== seq.current) return
      if (l.state === "ready") {
        setResults(l.data.items ?? [])
        setState("ready")
      } else {
        setResults([])
        setState("failed")
      }
    })
  }, [])

  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => search(q.trim()), 250)
    return () => clearTimeout(t)
  }, [q, open, search])

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm">
        <div className="min-w-0">
          <p className="truncate font-medium text-foreground">{value.label}</p>
          {value.email && <p className="truncate text-xs text-muted-foreground">{value.email}</p>}
        </div>
        {!disabled && (
          <Button type="button" size="icon-sm" variant="ghost" aria-label="Change customer" onClick={() => onChange(null)}>
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
      <input
        className={`${inputClass} pl-8`}
        placeholder="Search CRM customers by name, email or account number…"
        value={q}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
      />
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg">
          {state === "loading" && <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>}
          {state === "failed" && <p className="px-3 py-2 text-xs text-red-300">CRM could not be reached. You can still enter an ID by saving from a customer record.</p>}
          {state === "ready" && results.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">No customers match.</p>}
          {results.map((c) => (
            <button
              key={c.id}
              type="button"
              className="flex w-full flex-col rounded px-3 py-1.5 text-left text-sm hover:bg-secondary"
              onClick={() => {
                onChange({ id: c.id, label: customerFullName(c), email: c.email })
                setOpen(false)
                setQ("")
              }}
            >
              <span className="text-foreground">{customerFullName(c)}</span>
              <span className="text-xs text-muted-foreground">{[c.account_number, c.email].filter(Boolean).join(" · ") || c.id}</span>
            </button>
          ))}
          <button type="button" className="w-full px-3 py-1 text-right text-[11px] text-muted-foreground hover:text-foreground" onClick={() => setOpen(false)}>
            Close
          </button>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ template picker

export function TemplatePicker({
  templates,
  state,
  value,
  onChange,
  disabled,
}: {
  templates: InvoiceTemplate[]
  state: string
  value: string
  onChange: (id: string) => void
  disabled?: boolean
}) {
  const real = templates.filter((t) => t.id)
  return (
    <select className={inputClass} value={value} disabled={disabled || state !== "ready"} onChange={(e) => onChange(e.target.value)} aria-label="Template">
      <option value="">{state === "loading" ? "Loading templates…" : state !== "ready" ? "Templates unavailable" : "Default template"}</option>
      {real.map((t) => (
        <option key={t.id} value={t.id}>
          {t.name}
          {t.is_default ? " (default)" : ""}
        </option>
      ))}
    </select>
  )
}

// ------------------------------------------------------------------ sandboxed server document preview

/**
 * Renders the server's print-ready HTML in a script-less sandbox (srcDoc, sandbox="").
 * The HTML is never injected into this page's DOM. Only available for saved documents.
 */
export function DocumentPreview({ kind, id, refreshKey, height = 520 }: { kind: DocKind; id: string | null; refreshKey?: number; height?: number }) {
  const [html, setHtml] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!id) {
      setHtml(null)
      setErr(null)
      return
    }
    let off = false
    setLoading(true)
    setErr(null)
    fetchDocText(kind, id).then((r) => {
      if (off) return
      setLoading(false)
      if (r.ok) setHtml(r.data)
      else {
        setHtml(null)
        setErr(r.message)
      }
    })
    return () => {
      off = true
    }
  }, [kind, id, refreshKey, tick])

  if (!id) {
    return <Note>Save the draft to see the server-rendered document here. The totals above are a client-side estimate until then.</Note>
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">Server-rendered document (what the customer receives)</span>
        <Button type="button" size="sm" variant="ghost" onClick={() => setTick((t) => t + 1)} disabled={loading}>
          <RefreshCcw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>
      {err && <Note tone="error">{err}</Note>}
      {html !== null && (
        <iframe title="Document preview" sandbox="" srcDoc={html} className="w-full rounded-md border border-border bg-white" style={{ height }} />
      )}
    </div>
  )
}
